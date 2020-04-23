import os
import re
import urllib.request
from urllib.parse import urlparse
from PIL import Image
from joblib import dump, load
import tweepy

from django.shortcuts import render
from social_django.models import UserSocialAuth
from django.conf import settings
import more_itertools

import sys
sys.path.append(os.path.dirname(__file__))
import i2v

illust2vec = i2v.make_i2v_with_onnx(os.path.join(os.path.dirname(__file__), "illust2vec_ver200.onnx"))

clf = load(os.path.join(os.path.dirname(__file__), "clf.joblib"))

def index(request):
    if request.user.is_authenticated:
        user = UserSocialAuth.objects.get(user_id=request.user.id)
        consumer_key = settings.SOCIAL_AUTH_TWITTER_KEY
        consumer_secret = settings.SOCIAL_AUTH_TWITTER_SECRET
        access_token = user.extra_data['access_token']['oauth_token']
        access_secret = user.extra_data['access_token']['oauth_token_secret']
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_secret)
        api = tweepy.API(auth)
        timeline = api.home_timeline(count=200, tweet_mode = 'extended')

        tweet_illust = []
        for tweet in timeline:
            if 'media' in tweet.entities:
                media  = tweet.extended_entities['media'][0]
                media_url = media['media_url']
                filename = os.path.basename(urlparse(media_url).path)
                filename = os.path.join(os.path.dirname(__file__), 'images', filename)
                urllib.request.urlretrieve(media_url, filename)
                img = Image.open(filename)
                feature = illust2vec.extract_feature([img])
                prob = clf.predict_proba(feature)[0]
                if prob[1] > 0.4:
                    if hasattr(tweet, "retweeted_status"): 
                        profile_image_url = tweet.retweeted_status.author.profile_image_url_https
                        author = {'name': tweet.retweeted_status.author.name,
                                  'screen_name': tweet.retweeted_status.author.screen_name}
                        id_str = tweet.retweeted_status.id_str
                    else:
                        profile_image_url = tweet.author.profile_image_url_https
                        author = {'name': tweet.author.name,
                                  'screen_name': tweet.author.screen_name}
                        id_str = tweet.id_str
                    try:
                        text = tweet.retweeted_status.full_text
                    except AttributeError:
                        text = tweet.full_text
                    text = re.sub(r"https?://[\w/:%#\$&\?\(\)~\.=\+\-]+$", '', text).rstrip()
                    tweet_illust.append({'id_str': id_str, 
                                         'profile_image_url': profile_image_url,
                                         'author': author,
                                         'text': text,
                                         'image_url': media_url})
        tweet_illust_chunked = list(more_itertools.chunked(tweet_illust, 4))
        return render(request,'hello/index.html', {'user': user, 'timeline_chunked': tweet_illust_chunked})
    else:
        return render(request,'hello/index.html')
