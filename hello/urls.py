from django.urls import path, include
import django.contrib.auth.views

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('about/', views.about, name='about'),
    path('author/', views.author_search, name='author_search'),
    path('author/<str:screen_name>/', views.author, name='author'),
    path('fix/', views.fix, name='fix'),
    path('ranking/', views.ranking, name='ranking'),
    path('status/<int:status_id>/', views.status, name='status'),
    path('register/<int:status_id>/', views.register, name='register'),
    path('add/<int:status_id>/', views.add, name='add'),
    path('delete/<int:status_id>/', views.delete, name='delete'),
    path('set_i2v_tag/<int:status_id>/', views.set_i2v_tag, name='set_i2v_tag'),
    path('search/', views.search, name='search'),
    path('logout/',
        django.contrib.auth.views.LogoutView.as_view(template_name = 'hello/logout.html'),
        name='logout'),
]
