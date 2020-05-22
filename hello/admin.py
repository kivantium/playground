from django.contrib import admin
from .models import Tag, ImageEntry

# Register your models here.
class ImageEntryAdmin(admin.ModelAdmin):
    search_fields = ('status_id', )
    filter_horizontal = ('tags', )

admin.site.register(Tag)
admin.site.register(ImageEntry, ImageEntryAdmin)
