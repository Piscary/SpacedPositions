"""The usage report for the test group (spec 14 §5): counts only, written into a file on request (`:test-report`).

What is counted: how often each command ran and how it was started (a key, a click, a hint label, the command line),
per day; the errors the app caught (in the browser, on the server). What the report adds from the training data:
the days used, puzzles per day, solved and missed, minutes per session, the time from the install to the first solved
puzzle. Never positions, names, comments, tags or any other text. Nothing is sent: the tester reads the file and
decides whether to send it."""

from __future__ import annotations

import json
import platform
import statistics
from collections import Counter, defaultdict

from django.db.migrations.recorder import MigrationRecorder
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from spaced_positions import __version__

from . import registry
from .models import LOCAL_USER, UsageCount

SOURCES = ("key", "mouse", "hint", "cmdline")
ERRORS = ("error.js", "error.server")
MOST_USED = 40


def count(name: str, source: str, n: int = 1) -> None:
    day = timezone.localdate()
    row, _created = UsageCount.objects.get_or_create(user=LOCAL_USER, day=day, name=name, source=source)
    UsageCount.objects.filter(pk=row.pk).update(count=F("count") + n)


@require_POST
def record(request):
    """The browser's counts since its last call: [[name, source, n], …]. Anything that isn't a known command with a
    known source, or a caught error, is ignored: no free text gets in."""
    try:
        counts = json.loads(request.body or b"{}").get("counts", [])
    except (ValueError, AttributeError):
        return JsonResponse({"ok": False}, status=400)
    known = registry.commands()["commands"]
    for item in counts if isinstance(counts, list) else []:
        if not (isinstance(item, list) and len(item) == 3 and isinstance(item[2], int) and 0 < item[2] <= 10_000):
            continue
        name, source, n = item
        if (name in known and source in SOURCES) or (name == "error.js" and source == "error"):
            count(name, source, n)
    return JsonResponse({"ok": True})


def server_error(sender, **kwargs) -> None:
    """A request failed with an exception (django's got_request_exception): one more server error."""
    try:
        count("error.server", "error")
    except Exception:  # the database itself may be what failed
        pass


# ── The report ───────────────────────────────────────────────────────────────────────────────────────────────


def _installed():
    first = MigrationRecorder.Migration.objects.order_by("applied").values_list("applied", flat=True).first()
    return timezone.localtime(first) if first else None


def _system() -> str:
    if platform.system() == "Darwin":
        return f"macOS {platform.mac_ver()[0]} {platform.machine()}"
    if platform.system() == "Windows":
        release, build, *_rest = platform.win32_ver()
        return f"Windows {release} ({build}) {platform.machine()}"
    return f"{platform.system()} {platform.release()} {platform.machine()}"


def _table(headers: list[str], rows: list[list]) -> list[str]:
    widths = [max(len(str(x)) for x in [h, *[r[i] for r in rows]]) for i, h in enumerate(headers)]
    line = lambda cells: "  ".join(str(c).ljust(w) if i == 0 else str(c).rjust(w) for i, (c, w) in enumerate(zip(cells, widths)))
    return [line(headers), *[line(r) for r in rows]]


def report() -> str:
    from spaced_positions.core import settings as user_settings
    from spaced_positions.training.models import Attempt, Session

    attempts = list(Attempt.objects.filter(origin="").values_list("at", "success", "ms"))
    sessions = list(Session.objects.filter(origin="").exclude(ended_at=None).values_list("mode", "duration_s"))
    usage = list(UsageCount.objects.filter(user=LOCAL_USER).values_list("day", "name", "source", "count"))
    installed = _installed()

    per_day = defaultdict(lambda: [0, 0, 0, 0])  # puzzles, solved, missed, ms
    for at, success, ms in attempts:
        d = per_day[timezone.localtime(at).date()]
        d[0] += 1
        d[1 if success else 2] += 1
        d[3] += ms
    days_used = set(per_day) | {day for day, *_rest in usage}
    first_solved = min((at for at, success, _ms in attempts if success), default=None)

    out = [
        _("Spaced Positions: usage report"),
        _("Written {date}. Counts only: no positions, names, comments or other texts. Nothing has been sent: you decide "
          "whether to send this file.").format(date=timezone.localdate().isoformat()),
        "",
        f"{_('Version')} {__version__} · {_system()} · {_('language')} {user_settings.get('ui.language') or 'auto'}"
        f" ({translation.get_language()})",
        _("Installed {date} · days used: {n}").format(date=installed.date().isoformat() if installed else "?", n=len(days_used)),
    ]
    if first_solved and installed:
        minutes = max(0, round((first_solved - installed).total_seconds() / 60))
        out.append(_("First solved puzzle: {n} minutes after the install").format(n=minutes))
    else:
        out.append(_("No puzzle solved yet"))

    out += ["", _("Training per day")]
    if per_day:
        rows = [[d.isoformat(), p, s, m, round(ms / 60000)] for d, (p, s, m, ms) in sorted(per_day.items())]
        out += _table([_("day"), _("puzzles"), _("solved"), _("missed"), _("minutes")], rows)
    else:
        out.append(_("none yet"))

    out += ["", _("Sessions: {n}").format(n=len(sessions))]
    if sessions:
        modes = Counter(mode for mode, _d in sessions)
        out.append(_("by mode: {modes}").format(modes=", ".join(f"{m} {n}" for m, n in modes.most_common())))
        minutes = [d / 60 for _m, d in sessions if d]
        if minutes:
            out.append(_("minutes per session: median {median}, longest {longest}").format(
                median=round(statistics.median(minutes)), longest=round(max(minutes))))

    heads = [_("keys"), _("clicks"), _("hint labels"), _("command line")]
    weeks = defaultdict(Counter)
    commands = defaultdict(Counter)
    errors = Counter()
    for day, name, source, n in usage:
        if source == "error":
            errors[name] += n
            continue
        year, week, _weekday = day.isocalendar()
        weeks[f"{year}-W{week:02d}"][source] += n
        commands[name][source] += n
    out += ["", _("How commands were started, per week")]
    if weeks:
        out += _table([_("week"), *heads], [[w, *(c[s] for s in SOURCES)] for w, c in sorted(weeks.items())])
    else:
        out.append(_("none yet"))
    if commands:
        ranked = sorted(commands.items(), key=lambda kv: -sum(kv[1].values()))[:MOST_USED]
        out += ["", _("Commands used most ({shown} of {n} used)").format(shown=len(ranked), n=len(commands))]
        out += _table([_("command"), *heads], [[name, *(c[s] for s in SOURCES)] for name, c in ranked])
    out += ["", _("Errors the app caught: in the browser {js}, in the app {server}").format(
        js=errors["error.js"], server=errors["error.server"])]
    return "\n".join(out) + "\n"


@require_GET
def report_file(request):
    response = HttpResponse(report(), content_type="text/plain; charset=utf-8")
    name = f"spaced-positions-usage-{timezone.localdate().isoformat()}.txt"
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response
