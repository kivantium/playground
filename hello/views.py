from django.shortcuts import render, redirect
from social_django.models import UserSocialAuth
from django.conf import settings
from django.utils import translation
from django.http import HttpResponse, JsonResponse
from django.db.models import Count
from django.utils.timezone import make_aware
from django.http import QueryDict

import datetime
import tweepy
import pytz
import i2v
import os
import re
import numpy as np
import onnxruntime
import threading
import time
import fcntl

from urllib.parse import urlparse, quote
import urllib.request
from PIL import Image
import traceback

from .models import Tag, ImageEntry, Favorite

def crop_and_resize(img, size):
    width, height = img.size
    crop_size = min(width, height)
    img_crop = img.crop(((width - crop_size) // 2, (height - crop_size) // 2,
                         (width + crop_size) // 2, (height + crop_size) // 2))
    return img_crop.resize((size, size))

def softmax(x):
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum()

img_mean = np.asarray([0.485, 0.456, 0.406])
img_std = np.asarray([0.229, 0.224, 0.225])

ort_session = onnxruntime.InferenceSession(
    os.path.join(os.path.dirname(__file__), "model.onnx"))

def index(request):
    i2vtag_list = Tag.objects.all().filter(tag_type='IV').annotate(tag_count=Count('imageentry')).order_by('-tag_count')[:18]
    i2vtag_list = [{"name": t.name, "name_escape": quote(t.name)} for t in i2vtag_list]
    hashtag_list = Tag.objects.all().filter(tag_type='HS').annotate(tag_count=Count('imageentry')).order_by('-tag_count')[:50]
    hashtag_list = [{"name": t.name, "name_escape": quote(t.name)} for t in hashtag_list if len(t.name)<10][:12]
    safe_tag = Tag.objects.get(name='safe')
    image_entry_list = ImageEntry.objects.filter(is_illust=True, tags=safe_tag, image_number=0).order_by('-id')[:12]
    new_image_entry_list = ImageEntry.objects.filter(is_illust=True, tags=safe_tag, image_number=0).order_by('-created_at')[:12]
    now = datetime.datetime.now(pytz.timezone('UTC'))
    td = datetime.timedelta(hours=33)
    start = now - td
    popular_image_entry_list = ImageEntry.objects.filter(is_illust=True, tags=safe_tag, created_at__range=(start, now), image_number=0).order_by('-like_count')[:12]
    return render(request, 'hello/index.html', {
        'hashtag_list': hashtag_list,
        'i2vtag_list': i2vtag_list,
        'image_entry_list': image_entry_list,
        'new_image_entry_list': new_image_entry_list,
        'popular_image_entry_list': popular_image_entry_list,})

def about(request):
    return render(request, 'hello/about.html')

def get_twitter_api():
    consumer_key = settings.SOCIAL_AUTH_TWITTER_KEY
    consumer_secret = settings.SOCIAL_AUTH_TWITTER_SECRET
    access_token = settings.SOCIAL_AUTH_ACCESS_TOKEN
    access_secret = settings.SOCIAL_AUTH_ACCESS_SECRET

    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_secret)
    return tweepy.API(auth)

def author_search(request):
    author_list = ImageEntry.objects.filter(is_illust=True).values("author_screen_name").annotate(cnt=Count('author_screen_name')).order_by('-cnt')[:30]
    return render(request, 'hello/author_search.html', {
        'author_list': author_list})

def author(request, screen_name):
    page = request.GET.get('page', default='1')
    page = int(page)
    order = request.GET.get('order', default='like')
    safe = request.GET.get('safe', default='t')
    safe = True if safe == 't' else False

    api = get_twitter_api()
    try:
        user = api.get_user(screen_name=screen_name)
        if user.protected:
            return render(request, 'hello/author.html', {
                'isPrivate': True,
                'screen_name': screen_name})
    except:
        return render(request, 'hello/author.html', {
            'notFound': True,
            'screen_name': screen_name})

    filename = os.path.join(os.path.dirname(__file__), 'user_done.txt')
    with open(filename, 'r') as f:
        user_done = f.read().splitlines()
    if screen_name in user_done:
        isScraped = True
    else:
        isScraped = False
        image_entry_list = ImageEntry.objects.filter(is_illust=True, author_screen_name=screen_name)
        if image_entry_list:
            t = threading.Thread(target=scrape_author, args=(screen_name, ))
            t.start();
        else:
            filename = os.path.join(os.path.dirname(__file__), 'new_user.txt')
            with open(filename, 'r') as f:
                new_user = f.read().splitlines()
            if screen_name not in new_user:
                with open(filename, 'a') as f:
                    print(screen_name, file=f)

    image_entry_list = ImageEntry.objects.filter(is_illust=True, author_screen_name=screen_name)
    count = image_entry_list.count()

    n = 50
    if page > 1:
        previous_page = request.path + '?page={}&order={}'.format(page-1, order)
    else:
        previous_page = None

    if len(image_entry_list) > n * page:
        next_page = request.path + '?page={}&order={}'.format(page+1, order)
        if not safe:
            next_page += '&safe=f'
    else:
        next_page = None

    image_entry_list = image_entry_list[n*(page-1):n*page]

    checked_page = request.path + '?page={}&order={}'.format(page, order)
    like_order_page = request.path + '?order=like'.format(page, order)
    created_at_order_page = request.path + '?&order=created_at'.format(page, order)
    id_order_page = request.path + '?&order=id'.format(page, order)
    if safe:
        checked_page += '&safe=f'

    if safe:
        safe_tag = Tag.objects.get(name='safe')
        image_entry_list = [entry for entry in image_entry_list if safe_tag in entry.tags.all()]

    return render(request, 'hello/author.html', {
        'notFound': False,
        'screen_name': screen_name,
        'name': user.name,
        'profile_photo': user.profile_image_url_https.replace('_normal', ''),
        'isScraped': isScraped,
        'count': count,
        'order': order,
        'image_entry_list': image_entry_list,
        'safe': safe,
        'checked_page': checked_page,
        'like_order_page': like_order_page,
        'created_at_order_page': created_at_order_page,
        'id_order_page': id_order_page,
        'previous_page': previous_page,
        'next_page': next_page})

def scrape_author(screen_name):
    filename = os.path.join(os.path.dirname(__file__), 'user_queue.txt')
    with open(filename, 'r') as f:
        user_queue = f.read().splitlines()
    if screen_name in user_queue:
        return
    with open(filename, 'a') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            print(screen_name, file=f)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def ajax_tweets(request, screen_name):
    page = request.GET.get('page', default='1')
    page = int(page)
    try:
        user = UserSocialAuth.objects.get(user_id=request.user.id)
    except:
        d = { 'status': 'Authentication Error', }
        return JsonResponse(d)
    consumer_key = settings.SOCIAL_AUTH_TWITTER_KEY
    consumer_secret = settings.SOCIAL_AUTH_TWITTER_SECRET
    access_token = user.extra_data['access_token']['oauth_token']
    access_secret = user.extra_data['access_token']['oauth_token_secret']
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_secret)
    api = tweepy.API(auth)
    tweet_list = []
    try:
        for status in api.user_timeline(screen_name, count=200, page=page):
            if hasattr(status, "retweeted_status"):
                continue
            if 'media' not in status.entities:
                continue
            entries = ImageEntry.objects.filter(status_id=status.id)
            if entries:
                registered = True
            else:
                registered = False
            tweet_list.append({"id_str": status.id_str, "registered": registered})

        d = {
            'status': 'OK',
            'tweet_list': tweet_list,
        }
        return JsonResponse(d)
    except:
        d = { 'status': 'Reached API Limit?', }
        return JsonResponse(d)


def tweets(request, screen_name):

    api = get_twitter_api()
    try:
        user = api.get_user(screen_name=screen_name)
        if user.protected:
            return render(request, 'hello/author.html', {
                'isPrivate': True,
                'screen_name': screen_name})
    except:
        return render(request, 'hello/author.html', {
            'notFound': True,
            'screen_name': screen_name})

    return render(request, 'hello/tweets.html', {
        'notFound': False,
        'screen_name': user.screen_name,
        'name': user.name,
        'profile_photo': user.profile_image_url_https.replace('_normal', '')})

def report(request, status_id):
    if request.method == 'POST':
        forwarded_addresses = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded_addresses:
            client_addr = forwarded_addresses.split(',')[0]
        else:
            client_addr = request.META.get('REMOTE_ADDR')

        report_log = os.path.join(os.path.dirname(__file__), "report_log.csv")
        with open(report_log, 'a+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                now = datetime.datetime.now(pytz.timezone('Asia/Tokyo'))
                print('{},{},{}'.format(now.strftime('%Y-%m-%d %H:%M:%S'), 
                    status_id, client_addr), file=f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        image_entry_list = ImageEntry.objects.filter(status_id=status_id)

        dic = QueryDict(request.body, encoding='utf-8')
        report_type = dic.get('report_type')

        if report_type == "is_illust":
            if not image_entry_list:
                return HttpResponse("Status {} is not registered.".format(status_id))

            for entry in image_entry_list:
                entry.is_illust = True
                entry.save()

            return HttpResponse("Added status {}.".format(status_id))
        elif report_type == "not_illust":
            if not image_entry_list:
                return HttpResponse("Status {} is not registered.".format(status_id))

            for entry in image_entry_list:
                entry.is_illust = False
                entry.save()

            return HttpResponse("Deleted status {}.".format(status_id))
        elif report_type == "not_safe":
            for entry in image_entry_list:
                try:
                    safe = Tag.objects.get(name='safe', tag_type='IV')
                    entry.tags.remove(safe)
                except:
                    pass
                questionable = Tag.objects.get(name='questionable', tag_type='IV')
                entry.tags.add(questionable)
            return HttpResponse("Changed safe tag for status {}.".format(status_id))
        else:
            return HttpResponse("Unknown report for status {}.".format(status_id))
    else:
        return HttpResponse("You must use POST to report status {}.".format(status_id))

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

    return render(request, 'hello/fix.html', {
        'image_entry_list': image_entry_list, 
        'next_page': next_page})

def ranking(request):
    page = request.GET.get('page', default='1')
    page = int(page)
    safe = request.GET.get('safe', default='t')
    safe = True if safe == 't' else False
    now = datetime.datetime.now(pytz.timezone('UTC'))
    td = datetime.timedelta(hours=33)
    start = now - td
    image_entry_list = ImageEntry.objects.filter(created_at__range=(start, now)).filter(is_illust=True).filter(image_number=0).order_by('-like_count')

    n = 50
    if len(image_entry_list) > n * page:
        next_page = request.path + '?page={}'.format(page+1)
        if not safe:
            next_page += '&safe=f'
    else:
        next_page = None

    if page > 1:
        previous_page = request.path + '?page={}'.format(page-1)
    else:
        previous_page = None

    image_entry_list = image_entry_list[n*(page-1):n*page]

    checked_page = request.path + '?page={}'.format(page)
    if safe:
        checked_page += '&safe=f'

    if safe:
        safe_tag = Tag.objects.get(name='safe')
        image_entry_list = [entry for entry in image_entry_list if safe_tag in entry.tags.all()]

    return render(request, 'hello/ranking.html', {
            'image_entry_list': image_entry_list,
            'previous_page': previous_page,
            'next_page': next_page,
            'safe': safe,
            'checked_page': checked_page})

def search(request):
    tag_name = request.GET.get('tag')
    page = request.GET.get('page', default='1')
    page = int(page)
    order = request.GET.get('order', default='like')
    safe = request.GET.get('safe', default='t')
    safe = True if safe == 't' else False
    text = request.GET.get('text')

    n = 50
    tag_type = None
    if tag_name is None and text is None:
        image_entry_list = ImageEntry.objects.filter(is_illust=True)
        count = ImageEntry.objects.filter(is_illust=True).count()
    elif tag_name is not None:
        try:
            t = Tag.objects.get(name=tag_name, tag_type='UR')
        except:
            try: 
                t = Tag.objects.get(name=tag_name, tag_type='HS')
            except:
                try:
                    t = Tag.objects.get(name=tag_name)
                except:
                    return render(request, 'hello/search.html', {
                        'tag_name': tag_name, 'notFound': True, 'count': 0})
        image_entry_list = ImageEntry.objects.filter(is_illust=True, tags=t)
        count = image_entry_list.count()
        tag_type = t.tag_type
        if count == 0:
            return render(request, 'hello/search.html', {
                'text': text, 'notFound': True, 'count': 0})
    else:
        image_entry_list = ImageEntry.objects.filter(is_illust=True, text__contains=text, image_number=0)
        image_entry_list = ImageEntry.objects.filter(is_illust=True, text__contains=text)
        count = image_entry_list.count()
        if count == 0:
            return render(request, 'hello/search.html', {
                'text': text, 'notFound': True, 'count': 0})

    if order == 'id':
        image_entry_list = image_entry_list.order_by('-id')
    elif order == 'created_at':
        image_entry_list = image_entry_list.order_by('-created_at')
    else:
        image_entry_list = image_entry_list.order_by('-like_count')

    query = ""
    if tag_name is not None:
        query += '&tag={}'.format(tag_name)
    if text is not None:
        query += '&text={}'.format(text)

    if page > 1:
        previous_page = request.path + '?{}&page={}&order={}'.format(query, page-1, order)
        if not safe:
            previous_page += '&safe=f'
    else:
        previous_page = None

    if len(image_entry_list) > n * page:
        next_page = request.path + '?{}&page={}&order={}'.format(query, page+1, order)
        if not safe:
            next_page += '&safe=f'
    else:
        next_page = None

    image_entry_list = image_entry_list[n*(page-1):n*page]

    checked_page = request.path + '?{}&page={}&order={}'.format(query, page, order)
    like_order_page = request.path + '?{}&order=like'.format(query)
    created_at_order_page = request.path + '?{}&order=created_at'.format(query)
    id_order_page = request.path + '?{}&order=id'.format(query)
    if safe:
        checked_page += '&safe=f'

    if safe:
        safe_tag = Tag.objects.get(name='safe')
        image_entry_list = [entry for entry in image_entry_list if safe_tag in entry.tags.all()]

    return render(request, 'hello/search.html', {
        'tag_name': tag_name,
        'tag_type': tag_type,
        'text': text,
        'count': count,
        'order': order,
        'image_entry_list': image_entry_list,
        'safe': safe,
        'checked_page': checked_page,
        'like_order_page': like_order_page,
        'created_at_order_page': created_at_order_page,
        'id_order_page': id_order_page,
        'previous_page': previous_page,
        'next_page': next_page})

def ajax_search_tweets(request):
    tag_name = request.GET.get('tag')
    text = request.GET.get('text', default='')
    try:
        user = UserSocialAuth.objects.get(user_id=request.user.id)
    except:
        d = { 'status': 'Authentication Error', }
        return JsonResponse(d)
    consumer_key = settings.SOCIAL_AUTH_TWITTER_KEY
    consumer_secret = settings.SOCIAL_AUTH_TWITTER_SECRET
    access_token = user.extra_data['access_token']['oauth_token']
    access_secret = user.extra_data['access_token']['oauth_token_secret']
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_secret)
    api = tweepy.API(auth)
    tweet_list = []
    if tag_name:
        q = "#{} filter:images exclude:retweets min_faves:100".format(tag_name)
    else:
        q = "{} filter:images exclude:retweets min_faves:10".format(text)
    try:
        for status in api.search(q, count=200):
            if hasattr(status, "retweeted_status"):
                status = status.retweeted_status
            if 'media' not in status.entities:
                continue
            entries = ImageEntry.objects.filter(status_id=status.id)
            if entries:
                registered = True
            else:
                registered = False
            tweet_list.append({"id_str": str(status.id), "registered": registered})

        d = {
            'status': 'OK',
            'tweet_list': tweet_list,
        }
        return JsonResponse(d)
    except:
        print(traceback.format_exc())
        d = { 'status': 'Reached API Limit?', }
        return JsonResponse(d)

def search_tweets(request):
    tag_name = request.GET.get('tag')
    text = request.GET.get('text', default='')

    if tag_name:
        return render(request, 'hello/search_tweets.html', {
            'tag_name': tag_name})
    else:
        return render(request, 'hello/search_tweets.html', {
            'text': text})

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


def register(request, status_id):
    only_girl = True if request.GET.get('girl', default='f') == 't' else False

    api = get_twitter_api()

    try:
        status = api.get_status(status_id)
    except:
        return HttpResponse("Could not retrieve status id {}.".format(status_id))

    if hasattr(status, "retweeted_status"):
        status = status.retweeted_status

    if status.author.protected:
        return HttpResponse("The author {} is protected.".format(status.author.screen_name))
    if status.author.verified:
        return HttpResponse('The author @{} is a verified user.'.format(status.author.screen_name))
    if 'media' not in status.entities:
        log_file_name = os.path.join(os.path.dirname(__file__), "failed_status.txt")
        now = datetime.datetime.now(pytz.timezone('Asia/Tokyo'))
        with open(log_file_name, 'a+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                print('{} @{} {}'.format(now.strftime('%Y-%m-%d %H:%M:%S'), 
                    status.author.screen_name, status.id), file=f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
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
        probs = softmax(ort_outs[0])

        is_illust = True if probs[1] > 0.3 else False
        if not is_illust:
            rejected = True

        img_entry = ImageEntry(status_id=status.id,
                    author_id=status.author.id,
                    author_screen_name=status.author.screen_name,
                    text=full_text,
                    image_number=num,
                    retweet_count=status.retweet_count,
                    like_count=status.favorite_count,
                    media_url=media_url,
                    created_at=make_aware(status.created_at),
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
                rejected = True
        # Reject monochrome image
        try:
            t = Tag.objects.get(name='monochrome', tag_type='IV')
        except:
            t = Tag.objects.create(name='monochrome', tag_type='IV')
        if t in img_entry.tags.all():
            img_entry.is_illust = False
            img_entry.save()
            rejected = True
    if rejected:
        image_entry_list = ImageEntry.objects.filter(status_id=status_id)
        for entry in image_entry_list:
            entry.is_illust = False
            entry.save()
        return HttpResponse("Done but rejected.")
    return HttpResponse("Done!")

def register_status(url):
    urllib.request.urlopen(url).read()

def update_like_count(image_entry_list, status_id):
    api = get_twitter_api()
    try:
        status = api.get_status(status_id)
    except:
        return

    for entry in image_entry_list:
        entry.retweet_count=status.retweet_count
        entry.like_count=status.favorite_count
        entry.save()

def status(request, status_id):
    image_entry_list = ImageEntry.objects.filter(status_id=status_id) \
                                         .order_by('image_number')
    if not image_entry_list:
        url = '{}://{}/register/{}'.format(request.scheme, request.get_host(), status_id)
        t = threading.Thread(target=register_status, args=(url, ))
        t.start()
        return render(request, 'hello/status.html', {
            'title': 'ツイート詳細 - にじさーち',
            'status_id': status_id,
            'screen_name': 'unknown'})
    else:
        t = threading.Thread(target=update_like_count, args=(image_entry_list, status_id))
        t.start()
        hashtags = []
        usertags = []
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
                elif tag.tag_type == 'UR':
                    usertags.append(tag)
                elif tag.tag_type == 'IV':
                    if tag.name in ['safe', 'questionable', 'explicit']:
                        rating = tag
                    else:
                        i2vtags.append(tag)
            if rating is not None:
                i2vtags.insert(0, rating)
            i2vtags = [{"name": t.name, "name_escape": quote(t.name)} for t in i2vtags]
            i2vtags_list.append(i2vtags)
        hashtags = list(set(hashtags))
        hashtags = [{"name": t.name, "name_escape": quote(t.name)} for t in hashtags]
        usertags = [{"name": t.name, "name_escape": quote(t.name)} for t in usertags]

        all_usertags = Tag.objects.filter(tag_type='UR')

        return render(request, 'hello/status.html', {
            'title': 'ツイート詳細 - にじさーち',
            'status_id': status_id,
            'screen_name': image_entry_list[0].author_screen_name,
            'hashtags': hashtags, 
            'usertags': usertags, 
            'all_usertags': all_usertags, 
            'i2vtags_list': i2vtags_list, 
            'is_illust': is_illust})

def register_favs(api, is_first_time):
    user_id = api.me().id
    for status in tweepy.Cursor(api.favorites).items():
        if status.author.protected:
            continue
        if not is_first_time and Favorite.objects.filter(status_id=status.id):
            break
        fav = Favorite.objects.create(
                status_id=status.id,
                user_id=user_id,
                created_at=make_aware(status.created_at))
        fav.save()

def mypage(request):
    page = request.GET.get('page', default='1')
    page = int(page)

    if not request.user.is_authenticated:
        return render(request, 'hello/mypage.html')
    try:
        user = UserSocialAuth.objects.get(user_id=request.user.id)
    except:
        return render(request, 'hello/mypage.html', {'Error': True})

    consumer_key = settings.SOCIAL_AUTH_TWITTER_KEY
    consumer_secret = settings.SOCIAL_AUTH_TWITTER_SECRET
    access_token = user.extra_data['access_token']['oauth_token']
    access_secret = user.extra_data['access_token']['oauth_token_secret']
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_secret)
    api = tweepy.API(auth, wait_on_rate_limit=True)


    favorites = Favorite.objects.filter(user_id=api.me().id)
    if not favorites:
        t = threading.Thread(target=register_favs, args=(api, True))
        t.start()
        return render(request, 'hello/mypage.html', {
            'is_first_time': True})
    else:
        t = threading.Thread(target=register_favs, args=(api, False))
        t.start()

    fav_ids = [fav.status_id for fav in favorites]
    image_entry_list = ImageEntry.objects.filter(is_illust=True, status_id__in=fav_ids, image_number=0).order_by('-created_at')

    n = 50
    if page > 1:
        previous_page = request.path + '?page={}'.format(page-1)
    else:
        previous_page = None

    if len(image_entry_list) > n * page:
        next_page = request.path + '?page={}'.format(page+1)
    else:
        next_page = None

    return render(request, 'hello/mypage.html', {
        'image_entry_list': image_entry_list[n*(page-1):n*page],
        'previous_page': previous_page,
        'next_page': next_page})

def mypage_tweets(request):
    return render(request, 'hello/mypage_tweets.html')

def ajax_mypage_tweets(request):
    page = request.GET.get('page', default='1')
    page = int(page)

    try:
        user = UserSocialAuth.objects.get(user_id=request.user.id)
    except:
        d = {'status': 'Failed'}
        return JsonResponse(d)

    consumer_key = settings.SOCIAL_AUTH_TWITTER_KEY
    consumer_secret = settings.SOCIAL_AUTH_TWITTER_SECRET
    access_token = user.extra_data['access_token']['oauth_token']
    access_secret = user.extra_data['access_token']['oauth_token_secret']
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_secret)
    api = tweepy.API(auth)
    tweet_list = []
    try:
        for status in api.favorites(page=page):
            if status.author.protected:
                continue
            if 'media' not in status.entities:
                continue
            entries = ImageEntry.objects.filter(status_id=status.id)
            if entries:
                registered = True
            else:
                registered = False
            tweet_list.append({"id_str": status.id_str, "registered": registered})

        d = {
            'status': 'OK',
            'tweet_list': tweet_list,
        }
        return JsonResponse(d)
    except:
        d = { 'status': 'Reached API Limit?', }
        return JsonResponse(d)

def add_tag(request, status_id):
    if request.method == 'POST':
        forwarded_addresses = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded_addresses:
            client_addr = forwarded_addresses.split(',')[0]
        else:
            client_addr = request.META.get('REMOTE_ADDR')

        report_log = os.path.join(os.path.dirname(__file__), "add_tag_log.csv")
        with open(report_log, 'a+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                now = datetime.datetime.now(pytz.timezone('Asia/Tokyo'))
                print('{},{},{}'.format(now.strftime('%Y-%m-%d %H:%M:%S'), 
                    status_id, client_addr), file=f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        image_entry_list = ImageEntry.objects.filter(status_id=status_id)

        if not image_entry_list:
            return HttpResponse("Status {} is not registered.".format(status_id))

        tag_name = request.POST['tag_name']
        print(tag_name)

        try:
            t = Tag.objects.get(name=tag_name, tag_type='UR')
        except:
            t = Tag.objects.create(name=tag_name, tag_type='UR')

        for entry in image_entry_list:
            entry.tags.add(t)

        return redirect('status', status_id=status_id)
    else:
        return HttpResponse("You must use POST to add tag status {}.".format(status_id))
