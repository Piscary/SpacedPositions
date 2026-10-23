import json

from django.conf import settings
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from . import layouts, registry, server_commands
from .models import LOCAL_USER, NamedLayout, Preferences, UIState


def home(request):
    return redirect("core:mode", mode="home")


def healthz(request):
    return JsonResponse({"ok": True})


def _mode(mode: str) -> layouts.Mode:
    try:
        return layouts.MODES_BY_KEY[mode]
    except KeyError:
        raise Http404(f"no mode '{mode}'") from None


def _state(mode: str) -> UIState:
    state = UIState.objects.filter(user=LOCAL_USER, mode=mode).first()
    if state is None or not layouts.valid_layout(state.layout):
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


@require_GET
def mode_page(request, mode):
    prefs = Preferences.current()
    context = _workspace_context(mode)
    context |= {
        "theme_css": registry.theme_css(prefs.theme, prefs.tokens),
        "piece_set": prefs.tokens.get("piece-set", "cburnett"),
        "modes": layouts.MODES,
        "boot": {
            "mode": mode,
            "theme": prefs.theme,
            "tokens": prefs.tokens,
            "launched": settings.SPOS_LAUNCHED,
            "registry": registry.commands(),
            "themes": registry.themes(),
            "views": {
                k: {"label": v.label, "picker": v.picker, "phase": v.phase, "list": v.list_view}
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
    if view not in layouts.VIEWS:
        raise Http404(f"no view '{view}'")
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


@require_POST
def save_state(request, mode):
    _mode(mode)
    try:
        body = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest("not JSON")
    state = UIState.objects.filter(user=LOCAL_USER, mode=mode).first() or UIState(user=LOCAL_USER, mode=mode)
    if "layout" in body:
        if not layouts.valid_layout(body["layout"]):
            return HttpResponseBadRequest("invalid layout")
        state.layout = body["layout"]
        state.focus = str(body.get("focus", ""))[:24]
    if "subject" in body:
        subject = body["subject"]
        if not isinstance(subject, dict) or len(json.dumps(subject)) > 200_000:
            return HttpResponseBadRequest("invalid subject")
        state.subject = subject
    if not state.layout:
        state.layout = layouts.default_layout(mode)
    state.save()
    return JsonResponse({"ok": True})


@require_GET
def named_layouts(request):
    rows = NamedLayout.objects.filter(user=LOCAL_USER).order_by("name")
    return JsonResponse({"layouts": [{"name": r.name, "mode": r.mode, "layout": r.layout} for r in rows]})


@require_POST
def run_command(request, cid):
    handler = server_commands.HANDLERS.get(cid)
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

