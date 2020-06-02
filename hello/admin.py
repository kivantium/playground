from django.contrib import admin
from .models import Tag, ImageEntry

# Register your models here.
class ImageEntryAdmin(admin.ModelAdmin):
    search_fields = ('status_id', 'author_screen_name')
    filter_horizontal = ('tags', )

class TagAdmin(admin.ModelAdmin):
    search_fields = ('name', )

admin.site.register(Tag, TagAdmin)
admin.site.register(ImageEntry, ImageEntryAdmin)
