from django.contrib import admin
from django.urls import include, path
from django.conf.urls.i18n import i18n_patterns

urlpatterns = [
    path('', include('social_django.urls', namespace='social')),
    # path('admin/', admin.site.urls),
]
urlpatterns += i18n_patterns(
    path('', include('hello.urls')),
    prefix_default_language=False,
)
