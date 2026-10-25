"""Template tags of the component system (spec 05, 09 §9).

{% keycap "space w v" %}                    keys as keycaps
{% cmd "board.flip" %}                      a KeyButton rendered from the command registry
{% cmd "pane.split.vertical" display="compact" variant="ghost" label="Split" args="pgn" %}
{% section "Tags" key="t" summary="5 tags" %} … {% endsection %}
Texts are translated by the caller (`label=_("Split")`); a command's own title is translated here.
"""

from django import template
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

from spaced_positions.core import registry
from spaced_positions.design import lib

register = template.Library()


def _is_mac(context) -> bool:
    return bool(context.get("is_mac", True))


def keycaps_html(keys: list[str], mac: bool, extra_class: str = "") -> str:
    caps = format_html_join(
        "", '<kbd class="keycap{}">{}</kbd>', ((extra_class, lib.display_key(k, mac)) for k in keys)
    )
    return format_html('<span class="keys">{}</span>', caps)


@register.simple_tag(takes_context=True)
def keycap(context, seq: str, on_accent=False):
    keys = lib.parse_seq(seq)
    return keycaps_html(keys, _is_mac(context), " keycap--on-accent" if on_accent else "")


@register.simple_tag(takes_context=True)
def key(context, cid: str, args: str = "", keys_in: str = ""):
    """The keys of a command, for a guide (help/*.html): the default keys, replaced in the page by the user's own
    (help.js fills `data-keys-for`), so a guide never names a key that was rebound. keys_in: as for {% cmd %}."""
    arg_list = args.split() if args else None
    keys = registry.primary_keys(cid, arg_list, keys_in or None) or []
    return format_html('<span class="guide__keys" data-keys-for="{}" data-keys-args="{}" data-keys-in="{}">{}</span>', cid, args,
                       keys_in, keycaps_html(keys, _is_mac(context)) if keys else ":" + cid)


@register.simple_tag(takes_context=True)
def cmd(context, cid: str, display="full", variant="secondary", label="", args="", size="md", icon="", extra="", keys_in=""):
    """A KeyButton. Label, keys and disabled reason come from the registry, so a button and its key can't differ.
    keys_in: show the key of that context (e.g. "state.result") when the command has several."""
    spec = registry.command(cid)
    arg_list = args.split() if args else []
    keys = registry.primary_keys(cid, arg_list or None, keys_in or None) or registry.primary_keys(cid)
    title = label or gettext(spec["title"])
    classes = [f"keybutton keybutton--{variant} keybutton--{size} keybutton--{display}"]
    if spec.get("danger"):
        classes.append("keybutton--danger")
    if extra:
        classes.append(extra)
    parts = []
    if icon:
        parts.append(format_html('<span class="keybutton__icon" aria-hidden="true">{}</span>', icon))
    if display == "full":
        parts.append(format_html('<span class="keybutton__label">{}</span>', title))
    if keys:
        parts.append(keycaps_html(keys, _is_mac(context)))
    elif display != "full":
        parts.append(format_html('<span class="keybutton__label">{}</span>', title))
    return format_html(
        '<button type="button" class="{}" data-cmd="{}" data-args="{}" title="{}"{}>{}</button>',
        " ".join(classes),
        cid,
        " ".join(arg_list),
        gettext(spec["title"]),
        format_html(' aria-label="{}"', gettext(spec["title"])) if display != "full" else "",
        mark_safe("".join(str(p) for p in parts)),
    )


class SectionNode(template.Node):
    def __init__(self, nodelist, title, kwargs):
        self.nodelist, self.title, self.kwargs = nodelist, title, kwargs

    def render(self, context):
        title = self.title.resolve(context)
        kw = {k: v.resolve(context) for k, v in self.kwargs.items()}
        key = kw.get("key", "")
        collapsed = bool(kw.get("collapsed"))
        pinned = bool(kw.get("pinned"))
        body = self.nodelist.render(context)
        key_html = keycaps_html(["g", key], _is_mac(context)) if key else ""
        return format_html(
            '<section class="section{}" data-section{}{}>'
            '<header class="section__header" data-section-toggle role="button" aria-expanded="{}">'
            '<span class="section__caret" aria-hidden="true"></span>'
            '<span class="section__title">{}</span>'
            '<span class="section__summary">{}</span>'
            '<span class="section__keys">{}</span>'
            "</header>"
            '<div class="section__body">{}</div>'
            "</section>",
            " is-collapsed" if collapsed else "",
            mark_safe(f' data-section-key="{key}"') if key else "",
            mark_safe(" data-pinned") if pinned else "",
            "false" if collapsed else "true",
            title,
            kw.get("summary", ""),
            key_html,
            mark_safe(body),
        )


@register.tag("section")
def do_section(parser, token):
    bits = token.split_contents()
    if len(bits) < 2:
        raise template.TemplateSyntaxError("{% section \"Title\" key=… summary=… collapsed=… pinned=… %}")
    title = parser.compile_filter(bits[1])
    kwargs = {}
    for bit in bits[2:]:
        name, _, value = bit.partition("=")
        kwargs[name] = parser.compile_filter(value)
    nodelist = parser.parse(("endsection",))
    parser.delete_first_token()
    return SectionNode(nodelist, title, kwargs)


@register.simple_tag(takes_context=True)
def keyhint(context, binding: str, label: str):
    """One "keys → action" pair of a key strip; clicking it runs the command (spec 05 · KeyHint)."""
    cid, *args = binding.split(" ")
    keys = registry.primary_keys(cid, args or None) or registry.primary_keys(cid)
    if not keys:
        return ""
    return format_html(
        '<span class="keyhint" data-cmd="{}" data-args="{}">{}<span>{}</span></span>',
        cid,
        " ".join(args),
        keycaps_html(keys, _is_mac(context)),
        label,
    )


@register.simple_tag
def miniboard(fen: str, size: int = 120, flip: bool = False, extra: str = ""):
    """A static board (spec 05 · MiniBoard): a cached SVG image, theme colours in its URL."""
    from urllib.parse import urlencode

    from spaced_positions.core.chess_views import colors_hash

    query = urlencode({"fen": fen, "size": size, "flip": "1" if flip else "", "t": colors_hash()})
    return format_html(
        '<img class="miniboard {}" src="/svg/board/?{}" width="{}" height="{}" alt="{}" loading="lazy" data-fen="{}">',
        extra, query, size, size, gettext("Position {fen}").format(fen=fen), fen,
    )


@register.inclusion_tag("training/launcher.html", takes_context=True)
def train_launcher(context):
    from spaced_positions.training.views import launcher_context

    return launcher_context() | {"is_mac": context.get("is_mac", True)}


@register.simple_tag
def piece_codes():
    return ["wK", "wQ", "wR", "wB", "wN", "wP", "bK", "bQ", "bR", "bB", "bN", "bP"]


@register.simple_tag
def piece_sets():
    """The piece sets with their credits (style guide, settings): the bundled ones and the user's."""
    from spaced_positions.core import user_pieces

    return [{"key": k} | v for k, v in user_pieces.all_sets().items()]


@register.simple_tag
def home_today():
    from spaced_positions.stats.home import today

    return today()


@register.simple_tag
def home_continue():
    from spaced_positions.stats.home import continue_

    return continue_()


@register.simple_tag
def tag_presets():
    from spaced_positions.library.collect import presets

    return presets()


@register.simple_tag
def demo_rows():
    from spaced_positions.core.demo import DEMO_ROWS

    return DEMO_ROWS


@register.simple_tag
def color_tokens():
    """Names of the colour tokens, for the style guide's swatches."""
    return [name for name, spec in registry.themes()["schema"].items() if spec["type"] == "color"]


@register.filter
def safe_json(value):
    """JSON for a <script type="application/json"> block (escapes <, > and &)."""
    import json

    return mark_safe(json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


@register.filter
def get(mapping, key):
    return mapping.get(key) if hasattr(mapping, "get") else None


@register.filter
def stars(n) -> str:
    """Difficulty 1–5 as ★★★☆☆."""
    try:
        n = max(0, min(5, int(n)))
    except (TypeError, ValueError):
        return ""
    return "★" * n + "☆" * (5 - n)
