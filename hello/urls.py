from django.urls import path, include
import django.contrib.auth.views

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('ranking/', views.ranking, name='ranking'),
    path('status/<int:status_id>/', views.status, name='status'),
    path('search/', views.search, name='search'),
    path('logout/',
        django.contrib.auth.views.LogoutView.as_view(template_name = 'hello/logout.html'),
        name='logout'),
]
