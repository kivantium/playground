from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('', include('hello.urls')),
    path('', include('social_django.urls', namespace='social')),
    path('admin/', admin.site.urls),
]
