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
        "coach_on": _coach_on,  # a callable: only asked by the page that shows the mode tabs
    }


def _coach_on() -> bool:
    from . import settings as user_settings

    return user_settings.get("coach.on") is True
