import json

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.views.decorators.http import require_GET, require_POST

from . import i18n, keymap, layouts, registry, server_commands, themes, user_pieces
from . import settings as user_settings
from .models import LOCAL_USER, NamedLayout, Preferences, UIState


def home(request):
    return redirect("core:mode", mode="home")


@require_POST
def beat(request):
    """An open tab says it's there (each minute): the app stops by itself when none has for a while (app.autostop)."""
    from spaced_positions import launcher

    launcher.beat()
    return JsonResponse({"ok": True})


def healthz(request):
    return JsonResponse({"ok": True})


def _mode(mode: str) -> layouts.Mode:
    try:
        return layouts.MODES_BY_KEY[mode]
    except KeyError:
        raise Http404(f"no mode '{mode}'") from None


def _state(mode: str) -> UIState:
    state = UIState.objects.filter(user=LOCAL_USER, mode=mode).first()
    if state is None or not layouts.valid_layout(state.layout) or layouts.is_old_default(mode, state.layout):
        state = state or UIState(user=LOCAL_USER, mode=mode)
        state.layout = layouts.default_layout(mode)
    layouts.number_panes(state.layout)
    return state


def _workspace_context(mode: str) -> dict:
    _mode(mode)
    state = _state(mode)
    panes = layouts.number_panes(state.layout)
    focus = state.focus if any(p["id"] == state.focus for p in panes) else panes[0]["id"]
    return {
        "mode": _mode(mode),
        "layout": state.layout,
        "layout_id": f"layout-{mode}",
        "tree": layouts.for_template(state.layout),
        "focus": focus,
        "subject": state.subject or {},
        "subject_id": f"subject-{mode}",
        "views": layouts.VIEWS,
        "placeholder_hints": layouts.PLACEHOLDER_HINTS,
    }


def safe_css(css: str) -> str:
    """CSS for a <style> element: it can't end the element early."""
    return str(css).replace("</", "<\\/")


@require_GET
def mode_page(request, mode):
    prefs = Preferences.current()
    context = _workspace_context(mode)
    context |= {
        "theme_css": themes.theme_css(prefs.theme, prefs.tokens),
        # your own CSS, applied last (Settings → Advanced); ?safe opens the app without it
        "custom_css": "" if "safe" in request.GET else safe_css(prefs.settings.get("custom.css", "")),
        "piece_set": prefs.tokens.get("piece-set", "cburnett"),
        "figurines": prefs.tokens.get("figurines") is True,
        "coords": prefs.tokens.get("board-coords", "inside"),
        "letters": user_settings.get("board.letters"),
        "modes": layouts.MODES,
        "i18n_catalog": i18n.js_catalog(getattr(request, "LANGUAGE_CODE", "en")),
        "boot": {
            "mode": mode,
            "theme": prefs.theme,
            "tokens": prefs.tokens,
            "settings": user_settings.values(prefs.settings),
            "settingsSchema": [{"name": s.name, "label": s.label, "help": s.help, "type": s.type, "values": list(s.values),
                                "labels": {v: user_settings.value_label(v) for v in s.values},
                                "words": {v: user_settings.value_words(v) for v in s.values}, "low": s.low, "high": s.high}
                               for s in user_settings.SETTINGS],
            "launched": settings.SPOS_LAUNCHED,
            "registry": keymap.for_page(),  # the default keymap with the user's overrides, in the page's language
            "themes": registry.themes() | {"themes": themes.all_themes(), "pieces": user_pieces.all_sets()},  # with the user's themes (and their CSS: live preview)
            "views": {
                k: {"label": v.label, "picker": v.picker, "list": v.list_view}
                for k, v in layouts.VIEWS.items()
            },
            "modes": {m.key: {"label": m.label, "leader": m.leader} for m in layouts.MODES},
        },
    }
    return render(request, "shell.html", context)


@require_GET
def workspace(request, mode):
    return render(request, "components/workspace.html", _workspace_context(mode))


@require_GET
def default_layout(request, mode):
    _mode(mode)
    return JsonResponse({"layout": layouts.default_layout(mode)})


@require_GET
def view_fragment(request, view):
    """One pane (header + body) for `layout.js` when a pane is created or its view changes."""
    if not view.replace("-", "").isalnum():
        raise Http404(f"no view '{view}'")  # an unknown view gets a pane that says so (a saved layout may name one)
    node = layouts.pane(
        view,
        request.GET.get("group") or None,
        id=request.GET.get("pane", "p0"),
        n=int(request.GET.get("n", 0) or 0),
        pinned=request.GET.get("pinned") == "1",
    )
    mode = request.GET.get("mode", "home")
    context = {"node": node, "views": layouts.VIEWS, "mode": _mode(mode), "placeholder_hints": layouts.PLACEHOLDER_HINTS}
    return render(request, "components/pane.html", context)


@require_GET
def help_page(request, topic):
    """A guide for the help overlay (`?`): one per view (templates/help/<view>.html), the query language (search)
    and panes in general (pane). In the language of the app, with the keys of the keymap."""
    known = set(layouts.VIEWS) | {"search", "pane"}
    name = topic if topic in known else "pane"
    try:
        get_template(f"help/{name}.html")
    except TemplateDoesNotExist:
        name = "pane"
    view = layouts.VIEWS.get(name)
    return render(request, f"help/{name}.html", {"view": view, "views": layouts.VIEWS})


@require_POST
def save_state(request, mode):
    _mode(mode)
    try:
        body = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest("not JSON")
    if "layout" in body and not layouts.valid_layout(body["layout"]):
        return HttpResponseBadRequest("invalid layout")
    if "subject" in body:
        subject = body["subject"]
        if not isinstance(subject, dict) or len(json.dumps(subject)) > 200_000:
            return HttpResponseBadRequest("invalid subject")
    # Saves arrive together (layout, lines, the library query): the first one creates the row, the others update it.
    for _attempt in range(3):
        try:
            with transaction.atomic():
                state, _ = UIState.objects.get_or_create(user=LOCAL_USER, mode=mode, defaults={"layout": layouts.default_layout(mode)})
                if "layout" in body:
                    state.layout = body["layout"]
                    state.focus = str(body.get("focus", ""))[:24]
                if "subject" in body:
                    state.subject = {**(state.subject or {}), **body["subject"]}  # parts (lines, analysis) are saved separately
                if not state.layout:
                    state.layout = layouts.default_layout(mode)
                state.save()
            break
        except IntegrityError:
            continue
    return JsonResponse({"ok": True})


@require_GET
def named_layouts(request):
    rows = NamedLayout.objects.filter(user=LOCAL_USER).order_by("name")
    return JsonResponse({"layouts": [{"name": r.name, "mode": r.mode, "layout": r.layout} for r in rows]})


@require_POST
def run_command(request, cid):
    handler = server_commands.handlers().get(cid)
    if handler is None:
        raise Http404(f"no server command '{cid}'")
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponseBadRequest("not JSON")
    args = [str(a) for a in body.get("args", [])]
    try:
        result = handler(args, body.get("context", {}), body)
    except server_commands.CommandError as e:
        return JsonResponse({"ok": False, "message": str(e)}, status=422)
    return JsonResponse({"ok": True} | result)

