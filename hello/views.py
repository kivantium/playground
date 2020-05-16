from django.shortcuts import render, redirect
from social_django.models import UserSocialAuth
from django.conf import settings
from django.http import HttpResponse

import datetime
import tweepy
import pytz
import i2v
import os

from urllib.parse import urlparse
import urllib.request
from PIL import Image

from .models import Tag, ImageEntry


def index(request):
    lists = []
    if request.user.is_authenticated:
        try:
            user = UserSocialAuth.objects.get(user_id=request.user.id)
        except:
            return redirect('/logout')
        consumer_key = settings.SOCIAL_AUTH_TWITTER_KEY
        consumer_secret = settings.SOCIAL_AUTH_TWITTER_SECRET
        access_token = user.extra_data['access_token']['oauth_token']
        access_secret = user.extra_data['access_token']['oauth_token_secret']
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_secret)
        api = tweepy.API(auth)
        lists = api.lists_all(
            screen_name=user.extra_data['access_token']['screen_name'])
    return render(request, 'hello/index.html', {'lists': lists})

def ranking(request):
    now = datetime.datetime.now(pytz.timezone('UTC'))
    td = datetime.timedelta(hours=24)
    start = now - td
    image_entry_list = ImageEntry.objects.filter(created_at__range=(start, now)).filter(is_illust=True).filter(image_number=0).order_by('-like_count')[:50]
    return render(request, 'hello/ranking.html', {'image_entry_list': image_entry_list})

def status(request, status_id):
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
        image_entry_list = ImageEntry.objects.filter(tags=t).filter(image_number=0) \
                                     .order_by('-like_count')[:50]
    else:
        image_entry_list = ImageEntry.objects.filter(tags=t) \
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
