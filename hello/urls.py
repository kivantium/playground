from django.urls import path, include
import django.contrib.auth.views
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('about/', views.about, name='about'),
    path('author/', views.author_search, name='author_search'),
    path('author/<str:screen_name>/', views.author, name='author'),
    path('ajax_tweets/<str:screen_name>/', views.ajax_tweets, name='ajax_tweets'),
    path('tweets/<str:screen_name>/', views.tweets, name='tweets'),
    path('fix/', views.fix, name='fix'),
    path('ranking/', views.ranking, name='ranking'),
    path('status/<int:status_id>/', views.status, name='status'),
    path('add_tag/<int:status_id>/', views.add_tag, name='add_tag'),
    path('register/<int:status_id>/', views.register, name='register'),
    path('report/<int:status_id>/', views.report, name='report'),
    path('set_i2v_tag/<int:status_id>/', views.set_i2v_tag, name='set_i2v_tag'),
    path('search/', views.search, name='search'),
    path('ajax_search_tweets/', views.ajax_search_tweets, name='ajax_search_tweets'),
    path('search_tweets/', views.search_tweets, name='search_tweets'),
    path('mypage/', views.mypage, name='mypage'),
    path('mypage_tweets/', views.mypage_tweets, name='mypage_tweets'),
    path('ajax_mypage_tweets/', views.ajax_mypage_tweets, name='ajax_mypage_tweets'),
    path('logout/',
        django.contrib.auth.views.LogoutView.as_view(template_name = 'hello/logout.html'),
        name='logout'),
    path('i18n/', include('django.conf.urls.i18n')),
   path('sw.js', (TemplateView.as_view(template_name="hello/sw.js",
    content_type='application/javascript', )), name='sw.js'),
]
