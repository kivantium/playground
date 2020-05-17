from django.shortcuts import render, redirect
from social_django.models import UserSocialAuth
from django.conf import settings
from django.http import HttpResponse
from django.db.models import Count

import datetime
import tweepy
import pytz
import i2v
import os
import re
import numpy as np
import onnxruntime

from urllib.parse import urlparse
import urllib.request
from PIL import Image

from .models import Tag, ImageEntry

def index(request):
    t = Tag.objects.get(name='safe')
    tag_list = Tag.objects.all().annotate(tag_count=Count('imageentry')).order_by('-tag_count')[:16]
    image_entry_list = ImageEntry.objects.filter(tags=t, is_illust=True, image_number=0, like_count__gte=20).order_by('-id')[:50]
    return render(request, 'hello/index.html', {'tag_list': tag_list, 'image_entry_list': image_entry_list})

def about(request):
    return render(request, 'hello/about.html')

def ranking(request):
    now = datetime.datetime.now(pytz.timezone('UTC'))
    td = datetime.timedelta(hours=24)
    start = now - td
    image_entry_list = ImageEntry.objects.filter(created_at__range=(start, now)).filter(is_illust=True).filter(image_number=0).order_by('-like_count')[:50]
    return render(request, 'hello/ranking.html', {'image_entry_list': image_entry_list})

def add(request, status_id):
    image_entry_list = ImageEntry.objects.filter(status_id=status_id)

    if not image_entry_list:
        return HttpResponse("Status {} is not registered.".format(status_id))

    for entry in image_entry_list:
        entry.is_illust = True
        entry.save()

    return HttpResponse("Added status {}.".format(status_id))

def delete(request, status_id):
    image_entry_list = ImageEntry.objects.filter(status_id=status_id)

    if not image_entry_list:
        return HttpResponse("Status {} is not registered.".format(status_id))

    for entry in image_entry_list:
        entry.is_illust = False
        entry.save()

    return HttpResponse("Deleted status {}.".format(status_id))

def status(request, status_id):
    image_entry_list = ImageEntry.objects.filter(status_id=status_id) \
                                         .order_by('image_number')
    if not image_entry_list:
        url = '{}://{}/register/{}'.format(request.scheme, request.get_host(), status_id)
        urllib.request.urlopen(url).read()
        image_entry_list = ImageEntry.objects.filter(status_id=status_id) \
                                             .order_by('image_number')
    hashtags = []
    i2vtags_list = []
    for image_entry in image_entry_list:
        tags = image_entry.tags.all()
        i2vtags = []
        rating = None
        for tag in tags:
            if tag.tag_type == 'HS':
                hashtags.append(tag)
            elif tag.tag_type == 'IV':
                if tag.name in ['safe', 'questionable', 'explicit']:
                    rating = tag
                else:
                    i2vtags.append(tag)
        if rating is not None:
            i2vtags.insert(0, rating)
        i2vtags_list.append(i2vtags)
    hashtags = list(set(hashtags))
    return render(request, 'hello/status.html', {'status_id': status_id,
        'hashtags': hashtags, 'i2vtags_list': i2vtags_list})

def search(request):
    tag_name = request.GET.get('tag')
    try:
        t = Tag.objects.get(name=tag_name)
    except:
        return render(request, 'hello/search.html', {'tag_name': tag_name, 'notFound': True})
    if t.tag_type == 'HS':
        image_entry_list = ImageEntry.objects.filter(tags=t).filter(is_illust=True, image_number=0) \
                                     .order_by('-like_count')[:50]
    else:
        image_entry_list = ImageEntry.objects.filter(is_illust=True, tags=t) \
                                     .order_by('-like_count')[:50]
    return render(request, 'hello/search.html', {
        'tag_name': tag_name,
        'notFound': False,
        'image_entry_list': image_entry_list})

illust2vec = i2v.make_i2v_with_onnx(
        os.path.join(os.path.dirname(__file__), "illust2vec_tag_ver200.onnx"),
        os.path.join(os.path.dirname(__file__), "tag_list.json"))


def set_i2v_tag(request, status_id):
    image_entry_list = ImageEntry.objects.filter(status_id=status_id) \
                                         .order_by('image_number')
    for img_entry in image_entry_list:
        media_url = img_entry.media_url
        filename = os.path.basename(urlparse(media_url).path)
        filename = os.path.join('/tmp', filename)
        urllib.request.urlretrieve(media_url, filename)
        img = Image.open(filename).convert('RGB')

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
    return HttpResponse("Done!")

# https://gist.github.com/mahmoud/237eb20108b5805aed5f
hashtag_re = re.compile("(?:^|\s)[＃#]{1}(\w+)", re.UNICODE)

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

def register(request, status_id):
    consumer_key = settings.SOCIAL_AUTH_TWITTER_KEY
    consumer_secret = settings.SOCIAL_AUTH_TWITTER_SECRET
    access_token = settings.SOCIAL_AUTH_ACCESS_TOKEN
    access_secret = settings.SOCIAL_AUTH_ACCESS_SECRET

    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_secret)
    api = tweepy.API(auth)


    try:
        status = api.get_status(status_id)
    except:
        return HttpResponse("Could not retrieve status id {}.".format(status_id))

    if hasattr(status, "retweeted_status"):
        status = status.retweeted_status

    if status.author.protected:
        return HttpResponse("The author {} is protected.".format(status.author.screen_name))
    if 'media' not in status.entities:
        return HttpResponse("Status id {} does not include any media.".format(status_id))

    entries = ImageEntry.objects.filter(status_id=status_id)

    if entries:
        for entry in entries:
            entry.retweet_count=status.retweet_count
            entry.like_count=status.favorite_count
            entry.save()
        return HttpResponse("Known status. Updated like/retweet count.")

    try:
        full_text = status.extended_tweet["full_text"]
    except:
        full_text = status.text
    hashtags = hashtag_re.findall(full_text)

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

        img_entry = ImageEntry(status_id=status.id,
                    author_id=status.author.id,
                    author_screen_name=status.author.screen_name,
                    text=full_text,
                    image_number=num,
                    retweet_count=status.retweet_count,
                    like_count=status.favorite_count,
                    media_url=media_url,
                    created_at=status.created_at,
                    is_illust=is_illust)
        img_entry.save()

        # Add hashtags as image tags
        for tag_name in hashtags:
            try:
                t = Tag.objects.get(name=tag_name, tag_type='HS')
            except:
                t = Tag.objects.create(name=tag_name, tag_type='HS')
            img_entry.tags.add(t)

        # Run Illustration2Vec
        i2vtags = illust2vec.estimate_plausible_tags([img_pil], threshold=0.6)
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
    return HttpResponse("Done!")
