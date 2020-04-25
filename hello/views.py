import os
import re
import urllib.request
from urllib.parse import urlparse
from PIL import Image
import tweepy

from django.shortcuts import render
from social_django.models import UserSocialAuth
from django.conf import settings
import more_itertools

import numpy as np
import onnxruntime
import torchvision.transforms as transforms


def to_numpy(tensor):
    return tensor.detach().cpu().numpy() if tensor.requires_grad else tensor.cpu().numpy()


ort_session = onnxruntime.InferenceSession(
    os.path.join(os.path.dirname(__file__), "model.onnx"))

data_transforms = transforms.Compose([
    transforms.RandomResizedCrop(224),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])


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
        timeline = api.home_timeline(count=200, tweet_mode='extended')

        tweet_media = []
        for tweet in timeline:
            if 'media' in tweet.entities:
                tweet_media.append(tweet)

        batch_size = 4
        tweet_illust = []
        for batch_tweet in more_itertools.chunked(tweet_media, batch_size):
            batch_img = []
            for tweet in batch_tweet:
                media_url = tweet.extended_entities['media'][0]['media_url']
                filename = os.path.basename(urlparse(media_url).path)
                filename = os.path.join('/tmp', filename)
                urllib.request.urlretrieve(media_url, filename)
                img = Image.open(filename).convert('RGB')
                img = data_transforms(img)
                batch_img.append(to_numpy(img))

            ort_inputs = {ort_session.get_inputs()[0].name: batch_img}
            ort_outs = ort_session.run(None, ort_inputs)[0]
            batch_result = np.argmax(ort_outs, axis=1)
            for tweet, result in zip(batch_tweet, batch_result):
                if result == 1:
                    media_url = tweet.extended_entities['media'][0]['media_url']
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
                    text = re.sub(
                        r"https?://[\w/:%#\$&\?\(\)~\.=\+\-]+$", '', text).rstrip()
                    tweet_illust.append({'id_str': id_str,
                                         'profile_image_url': profile_image_url,
                                         'author': author,
                                         'text': text,
                                         'image_url': media_url})
        tweet_illust_chunked = list(more_itertools.chunked(tweet_illust, 4))
        return render(request, 'hello/index.html', {'user': user, 'timeline_chunked': tweet_illust_chunked})
    else:
        return render(request, 'hello/index.html')
