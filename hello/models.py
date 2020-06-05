from django.db import models

class Tag(models.Model):
    name = models.CharField(max_length=140)

    TAG_TYPE_CHOICES = [
        ('HS', 'Hashtag'),
        ('IV', 'I2V'),
        ('ES', 'Estimated'),
        ('UR', 'User'),
    ]
    tag_type = models.CharField(max_length=2, choices=TAG_TYPE_CHOICES)

    def __str__(self):
        return self.name

class ImageEntry(models.Model):
    status_id = models.BigIntegerField()
    author_id = models.BigIntegerField()
    author_screen_name = models.CharField(max_length=32)
    text = models.CharField(max_length=300)
    image_number = models.IntegerField()
    retweet_count = models.IntegerField()
    like_count = models.IntegerField()
    media_url = models.URLField()
    created_at = models.DateTimeField()
    is_illust = models.BooleanField()
    tags = models.ManyToManyField(Tag)

    def __str__(self):
        return "{} (by @{})".format(self.media_url, self.author_screen_name)

class Favorite(models.Model):
    status_id = models.BigIntegerField()
    user_id   = models.BigIntegerField()
    created_at = models.DateTimeField()

    def __str__(self):
        return "{} by {}".format(self.status_id, self.user_id)
