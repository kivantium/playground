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
from datetime import datetime
from pytz import timezone
from twitter_scraper import get_tweets, Profile
import fcntl
import time

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
image_neg_dir = os.path.join(os.path.dirname(__file__), 'images_neg/')
image_unk_dir = os.path.join(os.path.dirname(__file__), 'images_unk/')

def softmax(x):
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum()

def handle_tweet(tweet):
    now = datetime.now(timezone('Asia/Tokyo'))
    print('{} Check @{} {} ({})'.format(now.strftime('%Y-%m-%d %H:%M:%S'), 
        tweet['username'], tweet['tweetId'], tweet['time']))

    include2d = False
    for num, media_url in enumerate(tweet['entries']['photos']):
        filename_base = os.path.basename(urlparse(media_url).path)
        filename = os.path.join(image_dir, '{}-{}'.format(tweet['tweetId'], filename_base))
        if os.path.exists(filename):
            now = datetime.now(timezone('Asia/Tokyo'))
            print('{} Already checked. Abort.'.format(now.strftime('%Y-%m-%d %H:%M:%S')))
            return
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
        probs = softmax(ort_outs[0])
        time.sleep(3)

        if probs[1] > 0.1:
            include2d = True
            break
        try:
            if probs[1] > 0.1:
                shutil.copy(filename, os.path.join(image_pos_dir, filename_base))
            elif probs[1] > 0.05:
                shutil.copy(filename, os.path.join(image_unk_dir, filename_base))
            else:
                shutil.copy(filename, os.path.join(image_neg_dir, filename_base))
        except:
            print(traceback.format_exc())
            return

    if include2d:
        url = 'https://nijisearch.kivantium.net/register/{}'.format(tweet['tweetId'])
        print('Open:', url)
        try:
            res = urllib.request.urlopen(url).read()
            print('Response: {}'.format(res))
        except:
            print(traceback.format_exc())
        time.sleep(10)


file_done = os.path.join(os.path.dirname(__file__), 'hello/user_done.txt')
with open(file_done, 'r') as f:
    user_done = f.read().splitlines()

filename = os.path.join(os.path.dirname(__file__), 'hello/user_queue.txt')
with open(filename, 'r') as f:
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        user_queue = f.read().splitlines()
    except IOError:
        print(traceback.format_exc())
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

for screen_name in user_queue:
    if screen_name in user_done:
        continue
    now = datetime.now(timezone('Asia/Tokyo'))
    print('\n\n{} Start scraping  @{})'.format(
        now.strftime('%Y-%m-%d %H:%M:%S'), screen_name))

    for tweet in get_tweets(screen_name):
        if not tweet['entries']['photos']:
            continue
        if tweet['likes'] < 50:
            continue
        handle_tweet(tweet)

    now = datetime.now(timezone('Asia/Tokyo'))
    print('\n\n{} Finish scraping  @{})'.format(
        now.strftime('%Y-%m-%d %H:%M:%S'), screen_name))

    with open(file_done, 'a') as f_done:
        print(screen_name, file=f_done)
    break
