"""The interface language (spec 09 §14): English, German, French or Italian.

`ui.language` (Settings → Language) picks one, or `auto` follows the browser. The middleware switches Django's
translations for each request, so templates, server messages and the boot data come in that language, and the page's
`<html lang>` tells `static/js/core/i18n.js` which catalogue to load. Catalogues are built by `manage.py i18n`
(core/i18n_catalog.py) from `locale/<lang>/LC_MESSAGES/django.po`."""

from __future__ import annotations

import contextvars

from django.conf import settings
from django.utils import translation

LANGUAGES = [("en", "English"), ("de", "Deutsch"), ("fr", "Français"), ("it", "Italiano")]
CODES = [code for code, _ in LANGUAGES]
# The sides in objective lines of tags ({side}, and {side_short} where a language needs a second form)
SIDES = {"en": (("White", "White"), ("Black", "Black")), "de": (("Weiss", "Weiss"), ("Schwarz", "Schwarz")),
         "fr": (("Les Blancs", "Blancs"), ("Les Noirs", "Noirs")), "it": (("Il Bianco", "il Bianco"), ("Il Nero", "il Nero"))}

_tag_language = contextvars.ContextVar("tag_language", default=None)


def _settings() -> dict:
    from . import settings as user_settings
    from .models import Preferences

    return user_settings.values(Preferences.current().settings)


def for_request(request) -> tuple[str, str]:
    """(the interface language, the language of tag names) for a request."""
    values = _settings()
    choice = values.get("ui.language") or "auto"
    language = choice if choice in CODES else (translation.get_language_from_request(request) or "en")
    tags = values.get("tags.language") or "ui"
    return language, tags if tags in CODES else language


def tag_language() -> str:
    """The language tag names are shown in: set per request by the middleware, else the active language."""
    language = _tag_language.get() or translation.get_language() or "en"
    return language if language in CODES else "en"


class LanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith((settings.STATIC_URL, "/healthz", "/beat/")):
            return self.get_response(request)
        language, tags = for_request(request)
        translation.activate(language)
        token = _tag_language.set(tags)
        request.LANGUAGE_CODE = language
        try:
            response = self.get_response(request)
        finally:
            translation.deactivate()
            _tag_language.reset(token)
        response.headers.setdefault("Content-Language", language)
        return response


_catalogs: dict[str, tuple[float, dict]] = {}


def js_catalog(language: str) -> dict | None:
    """The page's catalogue for JavaScript (static/i18n/<lang>.json), read once per change of the file."""
    if language == "en":
        return None
    path = settings.PACKAGE_DIR / "static" / "i18n" / f"{language}.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cached = _catalogs.get(language)
    if cached is None or cached[0] != mtime:
        import json

        cached = _catalogs[language] = (mtime, json.loads(path.read_text(encoding="utf-8")))
    return cached[1]
