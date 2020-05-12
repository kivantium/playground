from django.shortcuts import render
from social_django.models import UserSocialAuth
from django.conf import settings

import tweepy

from .models import ImageEntry


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
    image_entry_list = ImageEntry.objects.filter(is_illust=True).filter(image_number=0).order_by('-like_count')[:120]
    for item in image_entry_list:
        print(item.like_count, item.status_id)
    return render(request, 'hello/ranking.html', {'image_entry_list': image_entry_list})
