"""Chess endpoints for the board island and paste detection (spec 06), and MiniBoard SVGs (spec 05 · F)."""

import hashlib
import json

from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from spaced_positions import chesslogic

from . import registry
from .models import Preferences

MAX_PASTE = 2_000_000  # characters: a large PGN file, not a database


def board_look() -> tuple[str, str, str]:
    """Square colours and piece set of the active theme + the user's overrides."""
    prefs = Preferences.current()
    from .themes import all_themes

    themes = all_themes()
    name = prefs.theme or "paper"
    values = themes.get(name, themes["paper"])["values"] | prefs.tokens
    return values["sq-light"], values["sq-dark"], values.get("piece-set", "cburnett")


def colors_hash() -> str:
    """Part of every MiniBoard URL: changes when the square colours or the piece set change."""
    return hashlib.sha1("".join(board_look()).encode()).hexdigest()[:8]


@require_GET
def fen_check(request):
    from spaced_positions.library.collect import describe, duplicate_of

    fen = request.GET.get("fen", "")
    result = chesslogic.check_fen(fen, diagram=request.GET.get("diagram") == "1")
    found = duplicate_of(result.get("canonical") or "")
    result["duplicate"] = describe(found) if found else None  # the live duplicate check of the board editor (spec 11 §2)
    return JsonResponse(result)


@require_POST
def paste(request):
    try:
        text = json.loads(request.body).get("text", "")
    except ValueError:
        return HttpResponseBadRequest("not JSON")
    if len(text) > MAX_PASTE:
        return JsonResponse({"kind": "unknown", "message": "too large to paste: import it as a file (:import)"})
    return JsonResponse(chesslogic.parse_paste(text))


@require_GET
def board_svg(request):
    fen = request.GET.get("fen", chesslogic.START_FEN)
    if not chesslogic.valid_placement(fen):
        return HttpResponseBadRequest("not a FEN")
    try:
        size = max(16, min(800, int(request.GET.get("size", 160))))
    except ValueError:
        size = 160
    light, dark, pieces = board_look()
    svg = chesslogic.board_svg(fen, size, request.GET.get("flip") == "1", light, dark, pieces)
    response = HttpResponse(svg, content_type="image/svg+xml")
    # The URL carries the colours' hash (t=…), so a cached copy is never wrong for its URL.
    response["Cache-Control"] = "public, max-age=31536000, immutable" if request.GET.get("t") else "no-cache"
    return response
