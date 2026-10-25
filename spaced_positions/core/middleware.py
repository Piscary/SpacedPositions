"""Jupyter-style access control (spec 09 §11).

The launcher opens the browser at `/?token=<random>`. That request sets a cookie and redirects to the same URL
without the token. Later requests without the cookie are refused, so other local programs and web pages can't read
or change the data. Without a token (development with `manage.py runserver`, tests) the check is off.
"""

import hmac

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.template.loader import render_to_string

COOKIE = "spos_auth"


def _expected() -> str:
    return hmac.new(settings.SECRET_KEY.encode(), settings.SPOS_TOKEN.encode(), "sha256").hexdigest()


class TokenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self.request = request
        open_paths = (settings.STATIC_URL, "/healthz")  # static files and the liveness check reveal nothing
        if not settings.SPOS_TOKEN or request.path.startswith(open_paths):
            return self.get_response(request)

        token = request.GET.get("token")
        if token is not None:
            if not hmac.compare_digest(token, settings.SPOS_TOKEN):
                return self._refuse()
            query = request.GET.copy()
            del query["token"]
            url = request.path + (f"?{query.urlencode()}" if query else "")
            response = HttpResponseRedirect(url)
            response.set_cookie(COOKIE, _expected(), httponly=True, samesite="Strict")
            return response

        if not hmac.compare_digest(request.COOKIES.get(COOKIE, ""), _expected()):
            return self._refuse()
        return self.get_response(request)

    def _refuse(self):
        from django.utils import translation

        language = translation.get_language_from_request(self.request) or "en"
        with translation.override(language):
            return HttpResponse(render_to_string("refused.html", {"lang": language}), status=403)
