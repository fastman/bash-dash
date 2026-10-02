from django.conf import settings


def tracking(request):
    return {'tracking_website_id': settings.TRACKING_WEBSITE_ID}
