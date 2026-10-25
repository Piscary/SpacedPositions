from django.conf import settings
from django.utils import translation

from spaced_positions import __version__


def shell(request):
    return {
        "is_mac": "Macintosh" in request.META.get("HTTP_USER_AGENT", ""),
        "app_version": __version__,
        "app_launched": settings.SPOS_LAUNCHED,
        "lang": translation.get_language() or "en",
        "debug": settings.DEBUG,
    }
