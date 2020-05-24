from django.conf import settings

# https://djangobrothers.com/blogs/django_google_analytics/
def google_analytics(request):
    ga_tracking_id = getattr(settings, 'GOOGLE_ANALYTICS_TRACKING_ID', False)

    if not settings.DEBUG and ga_tracking_id:
        return {
            'GOOGLE_ANALYTICS_TRACKING_ID': ga_tracking_id,
        }
    return {}

def google_adsense(request):
    ga_tracking_id = getattr(settings, 'GOOGLE_ADSENSE_ID', False)

    if not settings.DEBUG and ga_tracking_id:
        return {
            'GOOGLE_ADSENSE_ID': ga_tracking_id,
        }
    return {}

def ninja_admax(request):
    admax_url_sm = getattr(settings, 'NINJA_ADMAX_URL_SM', False)
    admax_url_lg = getattr(settings, 'NINJA_ADMAX_URL_LG', False)

    if not settings.DEBUG and admax_url_sm and admax_url_lg:
        return {
            'NINJA_ADMAX_URL_SM': admax_url_sm,
            'NINJA_ADMAX_URL_LG': admax_url_lg,
        }
    return {}
