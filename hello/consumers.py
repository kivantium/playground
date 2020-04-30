import os
import re
import html
import json
import threading

import tweepy
import more_itertools

import numpy as np
import onnxruntime
from PIL import Image
import urllib.request
from urllib.parse import urlparse
import torchvision.transforms as transforms

from channels.generic.websocket import WebsocketConsumer
from django.conf import settings
from social_django.models import UserSocialAuth


def to_numpy(tensor):
    return tensor.detach().cpu().numpy() if tensor.requires_grad else tensor.cpu().numpy()


ort_session = onnxruntime.InferenceSession(
    os.path.join(os.path.dirname(__file__), "model.onnx"))

data_transforms = transforms.Compose([
    transforms.RandomResizedCrop(224),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])


class ChatConsumer(WebsocketConsumer):
    def connect(self):
        user = self.scope["user"]
        self.sender = None
        self.sending = False
        if user.is_authenticated:
            self.accept()
            user = UserSocialAuth.objects.get(user_id=user.id)
            consumer_key = settings.SOCIAL_AUTH_TWITTER_KEY
            consumer_secret = settings.SOCIAL_AUTH_TWITTER_SECRET
            access_token = user.extra_data['access_token']['oauth_token']
            access_secret = user.extra_data['access_token']['oauth_token_secret']
            auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
            auth.set_access_token(access_token, access_secret)
            self.api = tweepy.API(auth)
            self.send(text_data=json.dumps({
                'limit_reached': False,
                'html': 'connected',
            }))
        else:
            self.close()

    def disconnect(self, close_code):
        self.sending = False
        if self.sender is not None:
            self.sender.join()

    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        selected = text_data_json['selected']
        # Kill existing thread
        if self.sender is not None:
            self.sending = False
            self.sender.join()
        # Start new thread
        self.sending = True
        self.sender = threading.Thread(
            target=self.send_message, args=(selected, ))
        self.sender.start()

    def send_message(self, selected):
        def limit_handled(cursor):
            while True:
                try:
                    yield cursor.next()
                except:
                    self.send(text_data=json.dumps({'limit_reached': True}))
                    break

        # Done is better than perfect!
        if selected == "home":
            for status in limit_handled(tweepy.Cursor(self.api.home_timeline, tweet_mode='extended').items()):
                if self.sending == False:
                    break
                self.handle_status(status)
        else:
            for status in limit_handled(tweepy.Cursor(self.api.list_timeline, list_id=int(selected), tweet_mode='extended').items()):
                if self.sending == False:
                    break
                self.handle_status(status)

    def handle_status(self, status):
        if status.author.protected:
            return
        if 'media' not in status.entities:
            return
        media_url = status.extended_entities['media'][0]['media_url']
        filename = os.path.basename(urlparse(media_url).path)
        filename = os.path.join('/tmp', filename)
        urllib.request.urlretrieve(media_url, filename)
        img = Image.open(filename).convert('RGB')
        img = data_transforms(img)
        img = img.unsqueeze_(0)

        ort_inputs = {ort_session.get_inputs()[0].name: to_numpy(img)}
        ort_outs = ort_session.run(None, ort_inputs)[0]
        result = np.argmax(ort_outs)

        if result == 0:
            return

        if hasattr(status, "retweeted_status"):
            status_id = status.retweeted_status.id
            screen_name = status.retweeted_status.author.screen_name
        else:
            status_id = status.id
            screen_name = status.author.screen_name

        html = '<blockquote class="twitter-tweet" data-conversation="none"><a href="https://twitter.com/{}/status/{}"></a></blockquote>'.format(
            screen_name, status_id)

        self.send(text_data=json.dumps({
            'limit_reached': False,
            'html': html,
        }))
