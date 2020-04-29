from django.shortcuts import render
from social_django.models import UserSocialAuth
from django.conf import settings

import tweepy


def index(request):
    lists = []
    if request.user.is_authenticated:
        user = UserSocialAuth.objects.get(user_id=request.user.id)
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
