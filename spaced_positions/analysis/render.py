"""The move tree as a book (spec 05 · MoveTree): the main line as flowing text, each variation an indented block
under the move it replaces, comments in place, annotation symbols, marks as a coloured edge, and the puzzles' roles
(start framed, solver moves underlined, answers dotted, ends with a small square)."""

from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from spaced_positions.library.models import NodeTag

from . import puzzles as analysis_puzzles
from . import tree

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
FIGURINES = {"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘"}
GERMAN = {"K": "K", "Q": "D", "R": "T", "B": "L", "N": "S"}
FRENCH = {"K": "R", "Q": "D", "R": "T", "B": "F", "N": "C"}
ITALIAN = {"K": "R", "Q": "D", "R": "T", "B": "A", "N": "C"}


def san_html(san: str) -> str:
    """A SAN whose piece letters carry their German, French and Italian letter and figurine; `html[data-letters]` and
    `html[data-figurines]` draw those instead (07 · figurines, Settings → Board · piece letters). The text stays
    the SAN, so searching and copying find `Nf3` in every look."""

    def piece(letter: str) -> str:
        return (f'<span class="san-p" data-de="{GERMAN[letter]}" data-fr="{FRENCH[letter]}" data-it="{ITALIAN[letter]}" '
                f'data-fig="{FIGURINES[letter]}"><span class="san-l">{letter}</span></span>')

    out = escape(san)
    if out[:1] in FIGURINES:
        out = piece(out[0]) + out[1:]
    if "=" in out and out.split("=")[1][:1] in FIGURINES:
        head, tail = out.split("=", 1)
        out = f"{head}={piece(tail[0])}{tail[1:]}"
    return mark_safe(out)


def _size(node_id, kids) -> int:
    """Moves in the subtree from a node on (itself included)."""
    count, stack = 0, [node_id]
    while stack:
        n = stack.pop()
        count += 1
        stack.extend(k.id for k in kids.get(n, []))
    return count


def _number(before_fen: str, force: bool) -> str:
    """'12.' before a white move; '12…' before a black move that starts a line or follows a comment."""
    fields = before_fen.split()
    side = fields[1] if len(fields) > 1 else "w"
    full = fields[5] if len(fields) > 5 else "1"
    if side == "w":
        return f"{full}."
    return f"{full}…" if force else ""


def render(position) -> str:
    all_nodes = tree.nodes(position)
    kids = tree.kids_map(all_nodes)
    root = next(n for n in all_nodes if n.parent_id is None)
    fens = {n.id: n.fen for n in all_nodes}
    roles = analysis_puzzles.roles(position, kids)
    move_tags = {}
    for node_id, name in NodeTag.objects.filter(node__in=[n.id for n in all_nodes]).order_by("tag__field__order").values_list("node_id", "tag__name"):
        move_tags.setdefault(node_id, []).append(name)
    parts = []
    start_role = roles.get(root.id)
    if start_role:
        parts.append(format_html('<div class="mt-puzzle{}">▶ Puzzle from the start{}</div>', " is-draft" if start_role["draft"] else "", " (draft)" if start_role["draft"] else ""))
    if root.comment:
        parts.append(format_html('<p class="mt-comment mt-comment--root" data-comment="{}">{}</p>', root.id, root.comment))
    if kids.get(root.id):
        parts.append(_line(kids[root.id][0], kids, roles, fens, force_number=True, siblings=kids[root.id][1:], depth=0, tags=move_tags))
    else:
        parts.append(format_html('<p class="muted mt-empty">{}</p>', _("No moves yet: play one on the board, paste a PGN, or let the engine suggest one.")))
    return format_html('<div class="movetree" data-movetree data-root="{}">{}</div>', root.id, mark_safe("".join(str(p) for p in parts)))


def _token(node, roles, fens, force_number, tags):
    role = roles.get(node.id, {})
    classes = ["mt-move"]
    if node.mark:
        classes.append(f"is-{node.mark}")
    if role:
        classes.append(f"pz-{role['role']}")
        if role.get("draft"):
            classes.append("pz-draft")
        if role.get("end"):
            classes.append("pz-end")
    nags = "".join(tree.NAGS.get(n, "") for n in node.nags)
    chips = mark_safe("".join(str(format_html('<span class="mt-tag">{}</span>', t)) for t in tags.get(node.id, [])))
    return format_html(
        '<span class="{}" data-node="{}" role="button" tabindex="-1"><span class="mt-num">{}</span><span class="mt-san">{}</span><span class="mt-nag">{}</span></span>{}',
        " ".join(classes), node.id, _number(fens[node.parent_id], force_number), san_html(node.san), nags, chips,
    )


def _line(start, kids, roles, fens, force_number, siblings, depth, tags):
    """One line from `start` on; the siblings of `start` (alternatives to it) follow it as variation blocks."""
    out = []
    node, alternatives, force = start, siblings, force_number
    while node is not None:
        out.append(str(_token(node, roles, fens, force, tags)))
        force = False
        if node.comment:
            out.append(str(format_html('<span class="mt-comment" data-comment="{}">{}</span>', node.id, node.comment)))
            force = True
        if alternatives:
            blocks = []
            for i, alt in enumerate(alternatives):
                edge = alt.color or ""
                blocks.append(
                    format_html(
                        '<div class="mt-variation{}" style="{}" data-variation="{}" data-more="{}">'
                        '<button type="button" class="mt-caret" data-fold tabindex="-1" aria-expanded="true" aria-label="Fold this variation (z)"></button>'
                        '<span class="mt-label">{}</span>{}</div>',
                        f" is-{alt.mark}" if alt.mark else "",
                        f"--edge: {escape(edge)}" if edge else "",
                        alt.id,
                        _size(alt.id, kids) - 1,  # the moves a fold hides
                        _label(depth, i),
                        mark_safe(_line(alt, kids, roles, fens, True, [], depth + 1, tags)),
                    )
                )
            out.append(str(format_html('<div class="mt-variations">{}</div>', mark_safe("".join(str(b) for b in blocks)))))
            force = True
        children = kids.get(node.id, [])
        node, alternatives = (children[0], children[1:]) if children else (None, [])
    return mark_safe(" ".join(out))


def _label(depth, index):
    return LETTERS[index % 26] if depth == 0 else f"{LETTERS[index % 26].lower()}"

