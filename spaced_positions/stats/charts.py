"""Charts as server-rendered SVG (spec 05 · G): no chart library, colours from the chart tokens (by class), minimal
axes as HTML around the SVG. Every chart is a <figure data-chart> with its points as JSON: the chart island
(static/js/core/charts.js) moves a cursor over them with h/l, shows the value in the read-out row, drills down with
↵ and shows the table with t. Shapes carry data-i, the index of their point."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy

W, H = 600, 150  # the SVG's own coordinates; it scales to the figure's width


@dataclass
class Point:
    label: str  # x label: a day, a week, a tag
    values: list[float]  # one per series
    text: str  # the read-out: "Mon 3.10. · 12 mature"
    drill: str = ""  # a Library query, or a command "cmd:train.streak 0 normal|filter"


@dataclass
class Series:
    name: str
    color: str  # chart-1 … chart-6, good, bad


@dataclass
class Chart:
    id: str
    title: str
    points: list[Point]
    series: list[Series] = field(default_factory=list)
    unit: str = ""
    empty: str = gettext_lazy("No data yet.")


def _figure(chart: Chart, svg: str, kind: str, legend: bool = True, foot: str = "") -> str:
    data = [{"label": p.label, "text": p.text, "drill": p.drill} for p in chart.points]
    head = "".join(f"<th>{escape(s.name)}</th>" for s in chart.series)
    rows = "".join(
        "<tr><td>{}</td>{}</tr>".format(escape(p.label), "".join(f"<td>{_num(v)}</td>" for v in p.values)) for p in chart.points
    )
    keys = "".join(
        f'<span class="chart__key"><span class="chart__swatch c-{s.color}"></span>{escape(s.name)}</span>' for s in chart.series
    ) if legend and len(chart.series) > 1 else ""
    body = svg if chart.points else f'<p class="muted chart__empty">{escape(str(chart.empty))}</p>'
    return mark_safe(
        f'<figure class="chart chart--{kind}" data-chart="{escape(chart.id)}" tabindex="0" aria-label="{escape(chart.title)}" '
        f"data-points='{escape(json.dumps(data))}'>"
        f'<figcaption class="chart__title">{escape(chart.title)}</figcaption>'
        f'<div class="chart__readout mono" data-readout aria-live="polite">{escape(chart.points[-1].text) if chart.points else ""}</div>'
        f'<div class="chart__plot">{body}</div>{foot}'
        f'<div class="chart__legend">{keys}</div>'
        f'<table class="chart__table" hidden><thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table>'
        "</figure>"
    )


def _num(v) -> str:
    if v is None:
        return "–"
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.2f}"


def _axis(left: str, right: str, top: str = "") -> str:
    return format_html('<div class="chart__axis"><span>{}</span><span>{}</span><span>{}</span></div>', left, top, right)


def line(chart: Chart, max_value: float | None = None) -> str:
    """Lines over the points (one per series), a dot per point for the cursor."""
    pts = chart.points
    if not pts:
        return _figure(chart, "", "line")
    top = max_value or max((max(v for v in p.values if v is not None) for p in pts if any(v is not None for v in p.values)), default=1) or 1
    n = len(pts)
    x = (lambda i: W / 2) if n == 1 else (lambda i: i * W / (n - 1))
    shapes = []
    for si, s in enumerate(chart.series):
        coords = [(x(i), H - (p.values[si] or 0) / top * (H - 8) - 4) for i, p in enumerate(pts) if p.values[si] is not None]
        if len(coords) > 1:
            path = " ".join(f"{cx:.1f},{cy:.1f}" for cx, cy in coords)
            shapes.append(f'<polyline class="chart__line s-{s.color}" points="{path}" />')
    for i, p in enumerate(pts):
        v = p.values[0]
        if v is not None:
            shapes.append(f'<circle class="chart__dot s-{chart.series[0].color}" data-i="{i}" cx="{x(i):.1f}" cy="{H - v / top * (H - 8) - 4:.1f}" r="3" />')
    shapes.append(f'<line class="chart__base" x1="0" y1="{H - 0.5}" x2="{W}" y2="{H - 0.5}" />')
    svg = f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-hidden="true">{"".join(shapes)}</svg>'
    return _figure(chart, svg, "line", foot=_axis(pts[0].label, pts[-1].label, gettext("max {value}").format(value=f"{_num(top)}{chart.unit}")))


def bars(chart: Chart) -> str:
    """Stacked bars: one bar per point, its series stacked from the bottom."""
    pts = chart.points
    if not pts:
        return _figure(chart, "", "bars")
    top = max((sum(v or 0 for v in p.values) for p in pts), default=1) or 1
    n = max(len(pts), 12)  # a few bars stay narrow instead of filling the width
    slot = W / n
    width = max(1.0, slot * 0.8)
    shapes = []
    for i, p in enumerate(pts):
        y = H
        group = []
        for si, s in enumerate(chart.series):
            h = (p.values[si] or 0) / top * (H - 4)
            if h <= 0:
                continue
            y -= h
            group.append(f'<rect class="f-{s.color}" x="{i * slot + (slot - width) / 2:.1f}" y="{y:.1f}" width="{width:.1f}" height="{h:.1f}" />')
        shapes.append(f'<g class="chart__bar" data-i="{i}"><rect class="chart__hit" x="{i * slot:.1f}" y="0" width="{slot:.1f}" height="{H}" />{"".join(group)}</g>')
    shapes.append(f'<line class="chart__base" x1="0" y1="{H - 0.5}" x2="{W}" y2="{H - 0.5}" />')
    svg = f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-hidden="true">{"".join(shapes)}</svg>'
    return _figure(chart, svg, "bars", foot=_axis(pts[0].label, pts[-1].label, gettext("max {value}").format(value=f"{_num(top)}{chart.unit}")))


def hbars(chart: Chart) -> str:
    """Horizontal bars with their labels (collection by tag, by source, the funnel): HTML, not SVG."""
    pts = chart.points
    top = max((p.values[0] or 0 for p in pts), default=1) or 1
    color = chart.series[0].color if chart.series else "chart-1"
    rows = "".join(
        f'<div class="hbar" data-i="{i}"><span class="hbar__label">{escape(p.label)}</span>'
        f'<span class="hbar__track"><span class="hbar__fill f-{color}" style="--w: {100 * (p.values[0] or 0) / top:.1f}%"></span></span>'
        f'<span class="hbar__value mono">{_num(p.values[0])}</span></div>'
        for i, p in enumerate(pts)
    )
    return _figure(chart, f'<div class="hbars">{rows}</div>', "hbars", legend=False)


def heatmap(chart: Chart, weeks: list[list[dict]]) -> str:
    """The activity calendar: weeks as columns, Monday on top, 5 levels."""
    cells, points, i = [], [], 0
    size = W / max(1, len(weeks))
    for w, week in enumerate(weeks):
        for d, day in enumerate(week):
            if day["future"]:
                continue
            points.append(Point(day["day"].isoformat(), [day["n"]], f"{day['day']:%a %d %b} · " +
                                (f"{day['n']} puzzle{'s' if day['n'] != 1 else ''}, {round(100 * day['ok'] / day['n'])}% solved" if day["n"] else "no training")))
            cells.append(f'<rect class="chart__cell lv-{day["level"]}" data-i="{i}" x="{w * size + 1:.1f}" y="{d * size + 1:.1f}" '
                         f'width="{size - 2:.1f}" height="{size - 2:.1f}" rx="1.5" />')
            i += 1
    chart.points = points
    svg = f'<svg viewBox="0 0 {W} {size * 7:.1f}" role="img" aria-hidden="true">{"".join(cells)}</svg>'
    return _figure(chart, svg, "heatmap", foot=_axis(points[0].label if points else "", points[-1].label if points else ""))


def sparkline(values: list[float], color: str = "chart-1") -> str:
    """A small trend inside a stat tile (not interactive)."""
    if len(values) < 2:
        return ""
    top = max(values) or 1
    path = " ".join(f"{i * 100 / (len(values) - 1):.1f},{30 - v / top * 28 - 1:.1f}" for i, v in enumerate(values))
    return mark_safe(f'<svg class="sparkline" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">'
                     f'<polyline class="chart__line s-{color}" points="{path}" /></svg>')
