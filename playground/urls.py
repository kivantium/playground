from django.urls import include, path

urlpatterns = [
    path('', include('hello.urls')),
    path('', include('social_django.urls', namespace='social')),
]
