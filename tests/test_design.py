"""The design pipeline: generated files are current, the lint passes, and the lint catches what it should."""

import copy

import pytest
from django.conf import settings

from spaced_positions.design import check, lib


@pytest.fixture(scope="module")
def sources():
    return lib.load(settings.DESIGN_DIR)


def test_generated_files_are_current():
    stale = lib.generated_is_current(settings.DESIGN_DIR, settings.DESIGN_OUT, settings.REPO_DIR / "docs")
    assert stale == [], "run `python manage.py design build`"


def test_design_check_has_no_errors():
    from spaced_positions.core import server_commands

    package = settings.PACKAGE_DIR
    problems = check.run_all(
        design_dir=settings.DESIGN_DIR,
        out_dir=settings.DESIGN_OUT,
        docs_dir=settings.REPO_DIR / "docs",
        templates_dir=package / "templates",
        js_dir=package / "static" / "js",
        css_dir=package / "static" / "css",
        pyproject=settings.REPO_DIR / "pyproject.toml",
        vendor_dir=package / "static" / "vendor",
        server_handlers=set(server_commands.handlers()),
        pieces_dir=package / "static" / "pieces",
    )
    assert [str(p) for p in problems if p.level == "error"] == []


@pytest.mark.parametrize(
    ("seq", "tokens"),
    [
        ("space w v", ["space", "w", "v"]),
        ("mod+shift+z", ["mod+shift+z"]),
        ("shift+mod+Z", ["mod+shift+z"]),
        ("G", ["G"]),
        ("space w +", ["space", "w", "+"]),
        ("alt+k", ["alt+k"]),
        ("shift+tab", ["shift+tab"]),
    ],
)
def test_parse_seq(seq, tokens):
    assert lib.parse_seq(seq) == tokens


@pytest.mark.parametrize("bad", ["shift+u", "hyper+k", "spacebar"])
def test_parse_seq_rejects(bad):
    with pytest.raises(ValueError):
        lib.parse_seq(bad)


def test_display_key():
    assert lib.display_key("mod+enter") == "⌘↵"
    assert lib.display_key("mod+enter", mac=False) == "Ctrl+↵"
    assert lib.display_key("space") == "␣"


@pytest.mark.parametrize(
    ("expr", "ok"),
    [("panes > 1", True), ("view.list && !pane.pinned", True), ("(a || b) && c == 'x'", True), ("a &&", False), ("a b", False)],
)
def test_when_grammar(expr, ok):
    assert (lib.check_when(expr) is None) is ok


def test_validate_token(sources):
    assert lib.validate_token(sources.schema, "main", "E2B714") == ("#e2b714", None)
    assert lib.validate_token(sources.schema, "main", "#abc") == ("#aabbcc", None)
    assert lib.validate_token(sources.schema, "font-size", "14")[1] is None
    assert "outside" in lib.validate_token(sources.schema, "font-size", "40")[1]
    assert lib.validate_token(sources.schema, "density", "tiny")[1]
    assert lib.validate_token(sources.schema, "nope", "1")[1] == "unknown token 'nope'"


def test_contrast_maths():
    assert check.contrast("#000000", "#ffffff") == pytest.approx(21, rel=0.01)
    assert check.contrast("#777777", "#777777") == pytest.approx(1)


def test_lint_catches_a_weak_theme(sources):
    weak = copy.deepcopy(sources)
    weak.themes["paper"]["color"]["text-sub"] = "#e0e0e0"
    weak.themes["paper"]["color"]["good"] = "#c23b32"  # same as bad
    messages = [p.message for p in check.check_themes(weak)]
    assert any("text-sub on bg" in m for m in messages)
    assert any("good vs bad" in m for m in messages)


def test_lint_catches_keymap_conflicts(sources):
    broken = copy.deepcopy(sources)
    broken.keymap["view.list"]["g"] = "list.first"  # 'g' is a command here and a prefix of 'g g'
    broken.keymap["pane"]["u"] = "list.down"  # 'u' is reserved by global
    broken.keymap["global"]["mod+w"] = "pane.close"  # the browser owns it
    messages = [p.message for p in check.check_keymap(broken)]
    assert any("is a command and a prefix" in m for m in messages)
    assert any("reserved by global" in m for m in messages)
    assert any("browser owns" in m for m in messages)


def test_css_literal_lint(tmp_path):
    (tmp_path / "x.css").write_text(".a { color: #fff; width: 12px; transition: color 200ms; margin: 0; }\n")
    (tmp_path / "y.css").write_text(".b { width: 3px; } /* lint-allow */\n.c { padding: var(--s-2); }\n")
    found = [p.message for p in check.check_css_literals(tmp_path)]
    assert len(found) == 3 and all(m.startswith("x.css") for m in found)


def test_piece_set_lint(sources, tmp_path):
    pieces = tmp_path / "pieces"
    (pieces / "cburnett").mkdir(parents=True)
    for code in lib.PIECE_CODES:
        (pieces / "cburnett" / f"{code}.svg").write_text('<svg viewBox="0 0 45 45"><path d="M0 0"/></svg>')
    (pieces / "cburnett" / "LICENSE").write_text("GPL")
    (pieces / "cburnett" / "wK.svg").write_text('<svg><script>alert(1)</script></svg>')
    (pieces / "stray").mkdir()
    one = copy.deepcopy(sources)
    one.schema["piece-set"]["values"] = ["cburnett", "merida"]
    messages = [p.message for p in check.check_piece_sets(one, pieces)]
    assert any("cburnett/wK.svg: scripts" in m for m in messages)
    assert any(m.startswith("merida: missing") for m in messages)
    assert any(m.startswith("stray:") for m in messages)


def test_pieces_css_switches_by_attribute(sources):
    css = lib.pieces_css(sources)
    assert '.cg-wrap piece.king.white { background-image: url("../pieces/cburnett/wK.svg"); }' in css
    assert ':root[data-pieces="merida"] .cg-wrap piece.pawn.black { background-image: url("../pieces/merida/bP.svg"); }' in css
