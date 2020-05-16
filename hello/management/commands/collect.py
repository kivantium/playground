# -*- coding: utf_8 -*-
import os
import re
import sys
import urllib.request
from urllib.parse import urlparse
import tweepy

import numpy as np
import onnxruntime
from PIL import Image

import i2v
from hello.models import ImageEntry, Tag
from django.core.management.base import BaseCommand, CommandError
import pytz


def crop_and_resize(img, size):
    width, height = img.size
    crop_size = min(width, height)
    img_crop = img.crop(((width - crop_size) // 2, (height - crop_size) // 2,
                         (width + crop_size) // 2, (height + crop_size) // 2))
    return img_crop.resize((size, size))

img_mean = np.asarray([0.485, 0.456, 0.406])
img_std = np.asarray([0.229, 0.224, 0.225])

ort_session = onnxruntime.InferenceSession(
    os.path.join(os.path.dirname(__file__), "../../model.onnx"))

# https://gist.github.com/mahmoud/237eb20108b5805aed5f
hashtag_re = re.compile("(?:^|\s)[＃#]{1}(\w+)", re.UNICODE)

def handle_status(status):
    if hasattr(status, "retweeted_status"):
        status = status.retweeted_status

    if status.author.protected:
        return
    if 'media' not in status.entities:
        return

    print('Processing:', status.author.screen_name)
    entries = ImageEntry.objects.filter(status_id=status.id)
    if entries:  # if the status is cached
        print('Known')
        for entry in entries:
            entry.retweet_count = status.retweet_count
            entry.like_count = status.favorite_count
            entry.save()
    else:
        print('Unknown')
        include2D = False
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

            try:
                full_text = status.extended_tweet["full_text"]
            except:
                full_text = status.text

            img_entry = ImageEntry(status_id=status.id,
                        author_id=status.author.id,
                        author_screen_name=status.author.screen_name,
                        text=full_text,
                        image_number=num,
                        retweet_count=status.retweet_count,
                        like_count=status.favorite_count,
                        media_url=media_url,
                        created_at=status.created_at.astimezone(pytz.timezone('UTC')),
                        is_illust=is_illust)
            img_entry.save()

            if is_illust:
                print('is 2D')
                include2D = True
                hashtags = hashtag_re.findall(full_text)
                for tag_name in hashtags:
                    try:
                        t = Tag.objects.get(name=tag_name, tag_type='HS')
                    except:
                        t = Tag.objects.create(name=tag_name, tag_type='HS')
                    img_entry.tags.add(t)

        if include2D:
            print('Setting tag...')
            url = 'http://127.0.0.1:8000/set_i2v_tag/{}'.format(status.id)
            urllib.request.urlopen(url).read()

class MyStreamListener(tweepy.StreamListener):
    def on_status(self, status):
        handle_status(status)

class Command(BaseCommand):
    help = 'Collect 2D images'

    def handle(self, *args, **options):
        f = open(os.path.join(os.path.dirname(__file__), 'config.txt'))
        data = f.read()
        f.close()
        lines = data.split('\n')

        KEY = lines[0]
        SECRET = lines[1]
        ATOKEN = lines[2]
        ASECRET = lines[3]

        auth = tweepy.OAuthHandler(KEY, SECRET)
        auth.set_access_token(ATOKEN, ASECRET)
        api = tweepy.API(auth)

        followee_ids = api.followers_ids(screen_name=api.me().screen_name)
        watch_list = [str(user_id) for user_id in followee_ids]
        watch_list.append(str(api.me().id))

        # followには5000人までしか指定できない
        # https://developer.twitter.com/en/docs/tweets/filter-realtime/api-reference/post-statuses-filter
        assert(len(watch_list) <= 5000)

        myStreamListener = MyStreamListener()
        myStream = tweepy.Stream(auth=api.auth, listener=myStreamListener)
        myStream.filter(follow=watch_list)
