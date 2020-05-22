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
from requests_html import HTMLSession
from PIL import Image
import traceback

from .models import Tag, ImageEntry

def index(request):
    tag_list = Tag.objects.all().annotate(tag_count=Count('imageentry')).order_by('-tag_count')[:16]
    count = ImageEntry.objects.filter(is_illust=True).count()
    safe_tag = Tag.objects.get(name='safe')
    image_entry_list = ImageEntry.objects.filter(is_illust=True, tags=safe_tag, image_number=0).order_by('-id')[:50]
    safe_tag = Tag.objects.get(name='safe')
    return render(request, 'hello/index.html', {'tag_list': tag_list, 'image_entry_list': image_entry_list,
        'count': count})

def about(request):
    return render(request, 'hello/about.html')

def add(request, status_id):
    if request.user.is_authenticated and request.user.username == 'kivantium':
        image_entry_list = ImageEntry.objects.filter(status_id=status_id)

        if not image_entry_list:
            url = '{}://{}/register/{}'.format(request.scheme, request.get_host(), status_id)
            try:
                urllib.request.urlopen(url).read()
                image_entry_list = ImageEntry.objects.filter(status_id=status_id)
            except:
                return

        for entry in image_entry_list:
            entry.is_illust = True
            entry.save()

        return HttpResponse("Added status {}.".format(status_id))
    else:
        return HttpResponse("You are not allowed to run this operation.")

def delete(request, status_id):
    if request.user.is_authenticated and request.user.username == 'kivantium':
        image_entry_list = ImageEntry.objects.filter(status_id=status_id)

        if not image_entry_list:
            url = '{}://{}/register/{}'.format(request.scheme, request.get_host(), status_id)
            try:
                urllib.request.urlopen(url).read()
                image_entry_list = ImageEntry.objects.filter(status_id=status_id)
            except:
                return

        for entry in image_entry_list:
            entry.is_illust = False
            entry.save()

        return HttpResponse("Deleted status {}.".format(status_id))
    else:
        return HttpResponse("You are not allowed to run this operation.")

def fix(request):
    if not request.user.is_authenticated or request.user.username != 'kivantium':
        return HttpResponse("You are not allowed to run this operation.")
    page = request.GET.get('page', default='1')
    page = int(page)
    image_entry_list = ImageEntry.objects.filter(is_illust=False).order_by('-id')

    n = 50
    if len(image_entry_list) > n * page:
        next_page = request.path + '?page={}'.format(page+1)
    else:
        next_page = None
    image_entry_list = image_entry_list[n*(page-1):n*page]

    return render(request, 'hello/fix.html', {'image_entry_list': image_entry_list, 'next_page': next_page})

def ranking(request):
    page = request.GET.get('page', default='1')
    page = int(page)
    safe = request.GET.get('safe', default='t')
    safe = True if safe == 't' else False
    now = datetime.datetime.now(pytz.timezone('UTC'))
    td = datetime.timedelta(hours=24)
    start = now - td
    image_entry_list = ImageEntry.objects.filter(created_at__range=(start, now)).filter(is_illust=True).filter(image_number=0).order_by('-like_count')

    n = 50
    if len(image_entry_list) > n * page:
        next_page = request.path + '?page={}'.format(page+1)
        if not safe:
            next_page += '&safe=f'
    else:
        next_page = None

    image_entry_list = image_entry_list[n*(page-1):n*page]

    checked_page = request.path + '?page={}'.format(page)
    if safe:
        checked_page += '&safe=f'

    if safe:
        safe_tag = Tag.objects.get(name='safe')
        image_entry_list = [entry for entry in image_entry_list if safe_tag in entry.tags.all()]

    return render(request, 'hello/ranking.html', 
            {'image_entry_list': image_entry_list, 'next_page': next_page, 'safe': safe, 'checked_page': checked_page})


def search(request):
    tag_name = request.GET.get('tag')
    page = request.GET.get('page', default='1')
    page = int(page)
    order = request.GET.get('order', default='like')
    safe = request.GET.get('safe', default='t')
    safe = True if safe == 't' else False

    n = 50
    if tag_name is None:
        image_entry_list = ImageEntry.objects.filter(is_illust=True)
    else:
        try:
            t = Tag.objects.get(name=tag_name)
        except:
            return render(request, 'hello/search.html', {'tag_name': tag_name, 'notFound': True})
        if t.tag_type == 'HS':
            image_entry_list = ImageEntry.objects.filter(tags=t).filter(is_illust=True, image_number=0)
        else:
            image_entry_list = ImageEntry.objects.filter(is_illust=True, tags=t)

    if order == 'id':
        image_entry_list = image_entry_list.order_by('-id')
    else:
        image_entry_list = image_entry_list.order_by('-like_count')

    if len(image_entry_list) > n * page:
        next_page = request.path + '?page={}&order={}'.format(page+1, order)
        if tag_name is not None:
            next_page += '&tag={}'.format(tag_name)
        if not safe:
            next_page += '&safe=f'
    else:
        next_page = None
    image_entry_list = image_entry_list[n*(page-1):n*page]


    checked_page = request.path + '?page={}&order={}'.format(page, order)
    if tag_name is not None:
        checked_page += '&tag={}'.format(tag_name)
    if safe:
        checked_page += '&safe=f'

    if safe:
        safe_tag = Tag.objects.get(name='safe')
        image_entry_list = [entry for entry in image_entry_list if safe_tag in entry.tags.all()]

    return render(request, 'hello/search.html', {
        'tag_name': tag_name,
        'notFound': False,
        'image_entry_list': image_entry_list,
        'safe': safe,
        'checked_page': checked_page,
        'next_page': next_page})

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
    only_girl = True if request.GET.get('girl', default='f') == 't' else False

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

    rejected = False
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

        if only_girl:
            has_girl = False
            names = ['1girl', 'multiple girls', '2girls', '3girls', '4girls']
            for tag_name in names:
                try:
                    t = Tag.objects.get(name=tag_name, tag_type='IV')
                except:
                    t = Tag.objects.create(name=tag_name, tag_type='IV')
                if t in img_entry.tags.all():
                    has_girl = True
                    break
            if not has_girl:
                img_entry.is_illust = False
                img_entry.save()
                rejected = True
    if rejected:
        return HttpResponse("Done but rejected.")

    return HttpResponse("Done!")

def status(request, status_id):
    image_entry_list = ImageEntry.objects.filter(status_id=status_id) \
                                         .order_by('image_number')
    if not image_entry_list:
        url = '{}://{}/register/{}'.format(request.scheme, request.get_host(), status_id)
        urllib.request.urlopen(url).read()
        image_entry_list = ImageEntry.objects.filter(status_id=status_id) \
                                             .order_by('image_number')
    else: # Update like count
        session = HTMLSession()
        headers = { "X-Requested-With": "XMLHttpRequest", }
        status_id = image_entry_list[0].status_id
        url = 'https://twitter.com/i/web/status/{}'.format(status_id)
        try:
            r = session.get(url, headers=headers)

            a = r.html.find('#profile-tweet-action-favorite-count-aria-{}'.format(status_id), first=True)
            b = a.element.getparent()
            like_count = int(b.get('data-tweet-stat-count'))

            if like_count > image_entry_list[0].like_count:
                for entry in image_entry_list:
                    entry.like_count = like_count
                    entry.save()
        except:
            print('Failed to update like_count of {}'.format(status_id))
            print(traceback.format_exc())
    hashtags = []
    i2vtags_list = []
    is_illust = []
    for image_entry in image_entry_list:
        is_illust.append(image_entry.is_illust)
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
        'hashtags': hashtags, 'i2vtags_list': i2vtags_list, 'is_illust': is_illust})
