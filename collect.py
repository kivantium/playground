# -*- coding: utf_8 -*-
import os
import urllib.request
from urllib.parse import urlparse
import tweepy
import traceback
import shutil

import numpy as np
import onnxruntime
from PIL import Image


def crop_and_resize(img, size):
    width, height = img.size
    crop_size = min(width, height)
    img_crop = img.crop(((width - crop_size) // 2, (height - crop_size) // 2,
                         (width + crop_size) // 2, (height + crop_size) // 2))
    return img_crop.resize((size, size))

img_mean = np.asarray([0.485, 0.456, 0.406])
img_std = np.asarray([0.229, 0.224, 0.225])

ort_session = onnxruntime.InferenceSession(
    os.path.join(os.path.dirname(__file__), "hello/model.onnx"))
image_dir = os.path.join(os.path.dirname(__file__), 'images')
image_pos_dir = os.path.join(os.path.dirname(__file__), 'images_pos')
image_neg_dir = os.path.join(os.path.dirname(__file__), 'images_neg')
image_unk_dir = os.path.join(os.path.dirname(__file__), 'images_unk')

def softmax(x):
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum()

def handle_status(status):
    if status.author.protected:
        return
    if 'media' not in status.entities:
        return

    include2D = False
    for num, media in enumerate(status.extended_entities['media']):
        media_url = media['media_url_https']
        filename_base = os.path.basename(urlparse(media_url).path)
        filename = os.path.join(image_dir, filename_base)
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

        if result == 1:
            include2D = True
        probs = softmax(ort_outs[0])
        if probs[1] > 0.7:
            shutil.move(filename, os.path.join(image_pos_dir, filename_base))
        elif probs[1] > 0.3:
            shutil.move(filename, os.path.join(image_unk_dir, filename_base))
        else:
            shutil.move(filename, os.path.join(image_neg_dir, filename_base))

    if include2D:
        url = 'https://nijisearch.kivantium.net/register/{}'.format(status.id)
        print('Register: @{} {}'.format(status.author.screen_name, status.id))
        print('Open:', url)
        res = urllib.request.urlopen(url).read()
        print('Response:', res)

class MyStreamListener(tweepy.StreamListener):
    def __init__(self):
        super(MyStreamListener, self).__init__()
        self.known_statuses = {}

    def on_status(self, status):
        if hasattr(status, "retweeted_status"):
            status = status.retweeted_status
        if 'media' not in status.entities:
            return

        if status.id in self.known_statuses:
            if self.known_statuses[status.id] < 20 and status.favorite_count > 20:
                self.known_statuses[status.id] = status.favorite_count
                handle_status(status)
        else:
            self.known_statuses[status.id] = status.favorite_count
            handle_status(status)

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
my_id = api.me().id

followee_ids = api.followers_ids(screen_name=api.me().screen_name)
watch_list = [str(user_id) for user_id in followee_ids]
watch_list.append(str(my_id))
lists = api.lists_all()

members = api.list_members(list_id=1026379470305808385)
watch_list.extend([str(member.id) for member in members])

# followには5000人までしか指定できない
# https://developer.twitter.com/en/docs/tweets/filter-realtime/api-reference/post-statuses-filter
assert(len(watch_list) <= 5000)

myStreamListener = MyStreamListener()
myStream = tweepy.Stream(auth=api.auth, listener=myStreamListener)
myStream.filter(follow=watch_list, is_async=True)
