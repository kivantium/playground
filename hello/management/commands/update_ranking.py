from django.conf import settings
from django.core.management.base import BaseCommand

from ...models import Tag, ImageEntry, Favorite

import datetime
import tweepy
import time
import pytz

def get_twitter_api():
    consumer_key = settings.SOCIAL_AUTH_TWITTER_KEY
    consumer_secret = settings.SOCIAL_AUTH_TWITTER_SECRET
    access_token = settings.SOCIAL_AUTH_ACCESS_TOKEN
    access_secret = settings.SOCIAL_AUTH_ACCESS_SECRET

    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_secret)
    return tweepy.API(auth)

api = get_twitter_api()

def update_like_count(status_id):
    entries = ImageEntry.objects.filter(status_id=status_id)
    try:
        status = api.get_status(status_id)
    except:
        return

    for entry in entries:
        entry.retweet_count=status.retweet_count
        entry.like_count=status.favorite_count
        entry.save()

class Command(BaseCommand):
    def handle(self, *args, **options):
        now = datetime.datetime.now(pytz.timezone('UTC'))
        td = datetime.timedelta(hours=33)
        start = now - td
        recent_images = ImageEntry.objects.filter(is_illust=True, created_at__range=(start, now), image_number=0)
        for entry in recent_images:
            update_like_count(entry.status_id)
            time.sleep(1)
