import os
import re
import html
import json
import threading

import tweepy

import numpy as np
import onnxruntime
from PIL import Image
import urllib.request
from urllib.parse import urlparse
from datetime import datetime

from channels.generic.websocket import WebsocketConsumer
from django.conf import settings
from social_django.models import UserSocialAuth
from .models import Tag, ImageEntry
import i2v

def crop_and_resize(img, size):
    width, height = img.size
    crop_size = min(width, height)
    img_crop = img.crop(((width - crop_size) // 2, (height - crop_size) // 2,
                         (width + crop_size) // 2, (height + crop_size) // 2))
    return img_crop.resize((size, size))

img_mean = np.asarray([0.485, 0.456, 0.406])
img_std = np.asarray([0.229, 0.224, 0.225])

ort_session = onnxruntime.InferenceSession(
    os.path.join(os.path.dirname(__file__), "model.onnx"))

# https://gist.github.com/mahmoud/237eb20108b5805aed5f
hashtag_re = re.compile("(?:^|\s)[＃#]{1}(\w+)", re.UNICODE)

illust2vec = i2v.make_i2v_with_onnx(
        os.path.join(os.path.dirname(__file__), "illust2vec_tag_ver200.onnx"),
        os.path.join(os.path.dirname(__file__), "tag_list.json"))

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
                    breakset_i2v_tags
                self.handle_status(status)
        else:
            for status in limit_handled(tweepy.Cursor(self.api.list_timeline, list_id=int(selected), tweet_mode='extended').items()):
                if self.sending == False:
                    break
                self.handle_status(status)

    def set_i2v_tags(self, img, img_entry):
        i2vtags = illust2vec.estimate_plausible_tags([img], threshold=0.6)
        for category in ['character', 'copyright', 'general']:
            for tag in i2vtags[0][category]:
                tag_name, tag_prob = tag
                try:
                    t = Tag.objects.get(name=tag_name, tag_type='IV')
                except:
                    t = Tag.objects.create(name=tag_name, tag_type='IV')
                img_entry.tags.add(t)

        rating = i2vtags[0]['rating'][0][0]
        try:
            t = Tag.objects.get(name=rating, tag_type='IV')
        except:
            t = Tag.objects.create(name=rating, tag_type='IV')
        img_entry.tags.add(t)

    def handle_status(self, status):
        if hasattr(status, "retweeted_status"):
            status = status.retweeted_status

        if status.author.protected:
            return
        if 'media' not in status.entities:
            return

        entries = ImageEntry.objects.filter(status_id=status.id)
        include2d = False
        if entries:  # if the status is cached
            for entry in entries:
                entry.retweet_count = status.retweet_count
                entry.like_count = status.favorite_count
                entry.save()
                if entry.is_illust:
                    include2d = True
        else:
            for num, media in enumerate(status.extended_entities['media']):
                media_url = media['media_url_https']
                filename = os.path.basename(urlparse(media_url).path)
                filename = os.path.join('/tmp', filename)
                urllib.request.urlretrieve(media_url, filename)
                img_pil = Image.open(filename).convert('RGB')
                img = crop_and_resize(img_pil, 224)

                img_np = np.asarray(img).astype(np.float32)/255.0
                img_np_normalized = (img_np - img_mean) / img_std

                # (H, W, C) -> (C, H, W)
                img_np_transposed = img_np_normalized.transpose(2, 0, 1)

                batch_img = [img_np_transposed]

                ort_inputs = {ort_session.get_inputs()[0].name: batch_img}
                ort_outs = ort_session.run(None, ort_inputs)[0]
                result = np.argmax(ort_outs)

                is_illust = True if result == 1 else False

                if is_illust:
                    include2d = True 

                img_entry = ImageEntry(status_id=status.id,
                            author_id=status.author.id,
                            author_screen_name=status.author.screen_name,
                            text=status.full_text,
                            image_number=num,
                            retweet_count=status.retweet_count,
                            like_count=status.favorite_count,
                            media_url=media_url,
                            created_at=status.created_at,
                            is_illust=is_illust)
                img_entry.save()

                if is_illust:
                    # Add hashtags as image tags
                    hashtags = hashtag_re.findall(status.full_text)
                    for tag_name in hashtags:
                        try:
                            t = Tag.objects.get(name=tag_name, tag_type='HS')
                        except:
                            t = Tag.objects.create(name=tag_name, tag_type='HS')
                        img_entry.tags.add(t)

                    self.set_i2v_tags(img_pil, img_entry)

        if include2d:
            html = '<blockquote class="twitter-tweet" data-conversation="none"><a href="https://twitter.com/user/status/{}"></a></blockquote>'.format(status.id)

            self.send(text_data=json.dumps({
                'limit_reached': False,
                'html': html,
            }))
