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
        if user.is_authenticated:
            self.accept()
            user = UserSocialAuth.objects.get(user_id=user.id)
            self.connecting = True
            self.sender = threading.Thread(target=self.send_message, args=(user,))
            self.sender.start()
        else:
            self.close()

    def disconnect(self, close_code):
        self.connecting = False
        self.sender.join()

    def receive(self, text_data):
        pass

    def send_message(self, user):
        consumer_key = settings.SOCIAL_AUTH_TWITTER_KEY
        consumer_secret = settings.SOCIAL_AUTH_TWITTER_SECRET
        access_token = user.extra_data['access_token']['oauth_token']
        access_secret = user.extra_data['access_token']['oauth_token_secret']
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_secret)
        api = tweepy.API(auth)

        def limit_handled(cursor):
            while True:
                try:
                    yield cursor.next()
                except:
                    self.send(text_data=json.dumps({'limit_reached': True}))
                    break

        for status in limit_handled(tweepy.Cursor(api.home_timeline, tweet_mode='extended').items()):
            if self.connecting == False:
                break
            if 'media' not in status.entities:
                continue
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
                continue

            if hasattr(status, "retweeted_status"):
                profile_image_url = status.retweeted_status.author.profile_image_url_https
                author = {'name': status.retweeted_status.author.name,
                          'screen_name': status.retweeted_status.author.screen_name}
                id_str = status.retweeted_status.id_str
            else:
                profile_image_url = status.author.profile_image_url_https
                author = {'name': status.author.name,
                          'screen_name': status.author.screen_name}
                id_str = status.id_str
            try:
                text = status.retweeted_status.full_text
            except AttributeError:
                text = status.full_text

            text = re.sub(
                r"https?://[\w/:%#\$&\?\(\)~\.=\+\-]+$", '', text).rstrip()
            text = html.unescape(text)

            self.send(text_data=json.dumps({
                'limit_reached': False,
                'content': {
                    'id_str': id_str,
                    'profile_image_url': profile_image_url,
                    'author': author,
                    'text': text,
                    'image_url': media_url
                    }
                }))
