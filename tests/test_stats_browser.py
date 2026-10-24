"""Phase 5 journeys in a real browser: the Stats charts by keyboard (focus, cursor, table, period, drill-down), Home
(due, sessions, the achievement banner, continue), the eval and variation graphs, and detecting tags from Analyse."""

from pathlib import Path

import pytest
from django.utils import timezone

from spaced_positions.analysis import puzzles as analysis_puzzles
from spaced_positions.analysis import tree
from spaced_positions.library.models import PositionTag, Tag
from spaced_positions.stats.models import Achievement
from spaced_positions.training.models import Session
from tests.browser import keys, open_mode
from tests.factories import back_rank

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AXE = Path(__file__).parent / "vendor" / "axe.min.js"


@pytest.fixture
def material():
    made = []
    for i, diff in enumerate((2, 3, 3)):
        p = tree.create_position(back_rank(i), ["d1d8"], title=f"Mate {i}")
        p.difficulty_override = diff
        p.save()
        PositionTag.objects.create(position=p, tag=Tag.objects.get(key="back-rank-mate"))
        root = tree.root(p)
        analysis_puzzles.act(root, "start")
        analysis_puzzles.act(root, "ready")
        analysis_puzzles.rebuild_all(p)
        made.append(p)
    Session.objects.create(mode="storm", options={"minutes": 3}, solved=21, failed=2, ended_at=timezone.now())
    return made


def stats(page):
    open_mode(page, "stats")
    page.wait_for_selector("#ws-stats figure[data-chart='library']")
    page.click("#ws-stats [data-view=chart] .pane__title")
    return page


def test_charts_by_keyboard_table_period_and_drill(page, material):
    stats(page)
    keys(page, "j")
    page.wait_for_selector("#ws-stats figure[data-chart='stages'].is-focused")
    keys(page, "k")
    page.wait_for_selector("#ws-stats figure[data-chart='library'].is-focused")
    before = page.inner_text("#ws-stats figure[data-chart='library'] [data-readout]")
    keys(page, "h", "h")
    assert page.inner_text("#ws-stats figure[data-chart='library'] [data-readout]") != before
    keys(page, "t")
    page.wait_for_selector("#ws-stats figure[data-chart='library'].is-table .chart__table:not([hidden])")
    keys(page, "2")  # 30 days
    page.wait_for_selector("#ws-stats [data-cmd='stats.period'][data-args='30d'][aria-checked='true']")
    # the difficulty chart drills into the Library
    figures = page.eval_on_selector_all("#ws-stats figure[data-chart]", "els => els.map(e => e.dataset.chart)")
    keys(page, *(["j"] * figures.index("difficulty")))
    page.wait_for_selector("#ws-stats figure[data-chart='difficulty'].is-focused")
    keys(page, "L", "h", "h")  # ★★★
    assert page.inner_text("#ws-stats figure[data-chart='difficulty'] [data-readout]").startswith("★★★: 2")
    keys(page, "Enter")
    page.wait_for_function("window.SPOS.ctx.mode === 'library' && window.SPOS.library.state().q === 'diff:3'")


def test_home_due_banner_and_sessions(page, material):
    Achievement.objects.create(kind="library", value=25, label="25 patterns in your library")
    open_mode(page, "home")
    page.wait_for_selector("#ws-home [data-banner] >> text=25 patterns in your library")
    page.wait_for_function("document.querySelector('#ws-home [data-view=today]').innerText.includes('3 new')")  # numbers count up
    page.click("#ws-home [data-view=today] .pane__title")
    with page.expect_response("**/stats/seen/"):
        keys(page, "x")
    page.wait_for_selector("#ws-home [data-banner]", state="detached")
    assert not Achievement.objects.filter(seen=False).exists()
    keys(page, "r")
    page.wait_for_function("window.SPOS.ctx.mode === 'train' && window.SPOS.train.state().state === 'solving'")


def test_eval_graph_and_variation_graph(page):
    p = tree.create_position(START, ["e2e4", "e7e5", "g1f3"], title="Open game")
    tree.play(p.nodes.get(san="e4"), "c7c5")
    open_mode(page, "analyse")
    page.evaluate("(pid) => window.SPOS.analysis.open(pid)", str(p.uuid))
    page.wait_for_selector("#ws-analyse [data-movetree]")
    page.click("#ws-analyse [data-view=moves] .pane__title")
    keys(page, ":")
    page.keyboard.type("vsplit vargraph")
    keys(page, "Enter")
    page.wait_for_selector("#ws-analyse [data-island=vargraph] circle[data-node]")
    assert page.locator("#ws-analyse [data-island=vargraph] circle[data-node]").count() == 5
    page.click(f"#ws-analyse [data-island=vargraph] circle[data-node='{p.nodes.get(san='c5').id}']")
    page.wait_for_function("document.querySelector('#ws-analyse .mt-move.is-cursor')?.textContent.includes('c5')")
    keys(page, ":")
    page.keyboard.type("vsplit evalgraph")
    keys(page, "Enter")
    page.wait_for_selector("#ws-analyse [data-island=evalgraph] [data-readout] >> text=:evaluate")
    keys(page, ":")
    page.keyboard.type("evaluate 6")
    keys(page, "Enter")
    page.wait_for_selector("#ws-analyse [data-island=evalgraph] polyline", timeout=30000)
    page.wait_for_function("document.getElementById('status-message').textContent.startsWith('Evaluated 4 moves')")
    assert p.nodes.filter(eval_depth__isnull=False).count() >= 3


def test_detect_from_the_inspector(page):
    p = tree.create_position(back_rank(0), ["d1d8"], title="Back rank")
    open_mode(page, "analyse")
    page.evaluate("(pid) => window.SPOS.analysis.open(pid)", str(p.uuid))
    page.wait_for_selector("#ws-analyse [data-inspector] [data-cmd='library.detect']")
    page.click("#ws-analyse [data-inspector] [data-cmd='library.detect']")
    page.wait_for_function("document.getElementById('status-message').textContent.startsWith('Detected on 1 position')")
    page.wait_for_selector("#ws-analyse [data-inspector] .inspector__tags >> text=Grundreihenmatt")
    assert p.tag_links.get(tag__key="back-rank-mate").origin == "auto"


def test_stats_accessibility(page, material):
    stats(page)
    page.add_script_tag(path=str(AXE))
    result = page.evaluate(
        """async () => {
          const r = await axe.run(document, {resultTypes: ['violations'], preload: false})
          return r.violations.filter(v => ['serious', 'critical'].includes(v.impact))
            .map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.slice(0, 3).map(n => n.target.join(' '))}))
        }"""
    )
    assert result == [], result
