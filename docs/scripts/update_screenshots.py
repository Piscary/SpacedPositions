"""Screenshots of the app in every theme: for the README (docs/images/) and for publishing (publishing/screenshots/).

    .venv/bin/python docs/scripts/update_screenshots.py                     every scene in every theme
    .venv/bin/python docs/scripts/update_screenshots.py train stats         some scenes
    .venv/bin/python docs/scripts/update_screenshots.py --themes paper,ink  some themes
    .venv/bin/python docs/scripts/update_screenshots.py --list              the scenes and what they show

Every picture is saved as `<scene>_<theme>.png` in publishing/screenshots/ (git ignores that folder: about a hundred
pictures would make the repository heavier with every update). The README's pictures are copies of some Paper ones,
under the names the README uses (docs/images/train.png …), and docs/images/themes.png puts the Analyse picture of
every theme into one grid.

The app runs as testers run it (`python -m spaced_positions`, the launcher), on a fresh data folder in the system's
temporary folder that is deleted afterwards: never on `.data/`, the maintainer's own training. The Welcome screen and
the starter pack's preview come first (they only show while the library is empty); then the starter pack is imported
and two months of made-up training are added (same scheduler as real training, dates in the past), so Home, Stats
and the training screens look like the app in use. Needs the dev extras (`pip install -e ".[dev]"`: Playwright,
Pillow) and Playwright's Chromium.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README_DIR = ROOT / "docs" / "images"
OUT_DIR = ROOT / "publishing" / "screenshots"
SIZE = {"width": 1440, "height": 860}  # the README's pictures
STILL = "*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }"
THEMES = [("paper", "Paper (default, light)"), ("ink", "Ink (dark)"), ("nord", "Nord"),
          ("forest", "Forest"), ("sepia", "Sepia"), ("contrast", "High contrast")]
QUERY = "motif:fork diff:2..3 sort:difficulty"  # the Library pictures: a search with filters
README = {"welcome": "welcome", "train": "train", "library": "library", "analyse": "analyse"}  # scene → docs/images name
HISTORY_DAYS = 60  # long enough for mature cards (three weeks between reviews)


def fail(message: str, log: Path | None = None):
    if log and log.exists():
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
        message += "\n\nThe app's last lines:\n" + "\n".join(tail)
    sys.exit(f"update_screenshots: {message}")


# ── Made-up training history (runs in a process of its own, with the app's settings) ──────────────────────────


def seed_history(days: int = HISTORY_DAYS):
    """Two months of training on the imported puzzles: most days a Review, some days a Storm, accuracy that
    grows; recorded with the app's own scheduler at times in the past, so cards are due, learning, young and mature."""
    import django

    django.setup()
    from datetime import timedelta

    from django.utils import timezone

    from spaced_positions.training import srs
    from spaced_positions.training.models import Attempt, Card, Position, Session

    rng = random.Random(7)
    now = timezone.now()
    # Stats replays each card from the day it was made: the imported puzzles were there before the training started
    before = now - timedelta(days=days + 3)
    Card.objects.update(created_at=before)
    Position.objects.update(created_at=before)
    cards = list(Card.objects.filter(in_solution=True).order_by("id"))
    rng.shuffle(cards)
    pool, used = cards[:420], []
    for back in range(days, 0, -1):
        if back > 7 and rng.random() < 0.15:
            continue  # a day off (none in the last week: a streak)
        day = (now - timedelta(days=back)).replace(hour=rng.choice([7, 12, 19, 21]), minute=rng.randrange(60))
        skill = 0.62 + 0.25 * (days - back) / days
        for mode in ["review"] + (["storm"] if rng.random() < 0.35 else []):
            at = day + timedelta(minutes=rng.randrange(5, 40)) if mode == "storm" else day
            options = {"look": "normal", "minutes": 3} if mode == "storm" else {"look": "normal"}
            session = Session.objects.create(mode=mode, started_at=at, options=options)
            due = [c for c in used if c.due <= at]
            todo = due[:rng.randint(8, 18)] + [pool.pop() for _ in range(min(len(pool), rng.randint(4, 10)))]
            solved = failed = combo = best = 0
            for card in todo:
                success = rng.random() < skill + (0.1 if card.attempts else 0)
                ms = int(rng.uniform(4, 9 if mode == "storm" else 35) * 1000)
                outcome = srs.record(card, success, ms, at)
                card.save()
                Attempt.objects.create(card=card, session=session, at=at, success=success, ms=ms, mode=mode, look="normal",
                                       counted=outcome.counted, state_before=outcome.state_before,
                                       interval_before=outcome.interval_before, interval_after=outcome.interval,
                                       due_before=outcome.due_before)
                if card not in used:
                    used.append(card)
                solved, failed = solved + success, failed + (not success)
                combo = combo + 1 if success else 0
                best = max(best, combo)
                at += timedelta(milliseconds=ms + 2500)
            Session.objects.filter(pk=session.pk).update(ended_at=at, solved=solved, failed=failed, best_combo=best,
                                                         duration_s=int((at - session.started_at).total_seconds()))
    print(f"  history: {Attempt.objects.count()} attempts in {Session.objects.count()} sessions over {days} days")


# ── The app ──────────────────────────────────────────────────────────────────────────────────────────────────


def clean_env() -> dict:
    return {k: v for k, v in os.environ.items() if not k.startswith(("SPOS_", "DJANGO_"))}  # not the dev settings


def start_app(data: Path, log: Path):
    """The launcher on a free port; returns (process, info from runtime.json) once it answers."""
    out = open(log, "ab")
    app = subprocess.Popen([sys.executable, "-m", "spaced_positions", "--no-browser", "--data-dir", str(data)],
                           cwd=ROOT, env=clean_env(), stdout=out, stderr=subprocess.STDOUT)
    runtime = data / "runtime.json"
    deadline = time.time() + 120  # the first start creates the database
    while time.time() < deadline:
        if app.poll() is not None:
            fail(f"the app stopped with exit code {app.returncode} while starting", log)
        try:
            info = json.loads(runtime.read_text(encoding="utf-8"))
            with urllib.request.urlopen(f"http://127.0.0.1:{info['port']}/healthz", timeout=2) as r:
                if r.status == 200:
                    return app, info
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.3)
    app.terminate()
    fail("the app didn't answer within two minutes", log)


def stop_app(app, data: Path):
    subprocess.run([sys.executable, "-m", "spaced_positions", "stop", "--data-dir", str(data)], cwd=ROOT,
                   env=clean_env(), capture_output=True, timeout=60)
    try:
        app.wait(timeout=20)
    except subprocess.TimeoutExpired:
        app.kill()


# ── Helpers in the page ──────────────────────────────────────────────────────────────────────────────────────


def open_mode(page, base: str, mode: str):
    page.goto(f"{base}/{mode}/")
    page.wait_for_function("window.SPOS && window.SPOS.ctx && window.SPOS.ctx.pane", timeout=30000)
    page.add_style_tag(content=STILL)


def settle(page, ms: int = 400):
    """Let fetches finish and the board draw (chessground, the move tree, numbers counting up), then a moment more."""
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(ms)


def focus(page, mode: str, view: str):
    page.click(f"#ws-{mode} [data-view={view}] .pane__title")
    page.wait_for_function("document.getElementById('shell').dataset.layer === 'normal'")  # keys are commands


def command(page, text: str):
    """A command typed on the command line, as `:text ↵`."""
    page.keyboard.press(":")
    page.wait_for_function("window.SPOS.ctx.overlay === 'cmdline'")
    page.keyboard.type(text)
    page.keyboard.press("Enter")
    page.wait_for_function("window.SPOS.ctx.overlay !== 'cmdline'")


def post(page, url: str, body: dict) -> dict:
    return page.evaluate("""async ([url, body]) => {
        const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json',
          'X-CSRFToken': document.querySelector('meta[name=csrf-token]').content}, body: JSON.stringify(body)})
        return r.json() }""", [url, body])


def set_theme(page, base: str, theme: str):
    open_mode(page, base, "home")
    if not post(page, "/cmd/theme.set/", {"args": [theme]}).get("ok"):
        fail(f"couldn't switch to the theme {theme}")


def solve(page):
    """Type the solution of the puzzle on the board (its solver moves), waiting for each answer."""
    line = page.evaluate("window.SPOS.train.puzzle().line")
    page.keyboard.press("i")
    for i in range(0, len(line), 2):
        page.keyboard.type(line[i])
        page.keyboard.press("Enter")
        if i + 1 < len(line):
            page.wait_for_function(f"!window.SPOS.train.puzzle() || window.SPOS.train.puzzle().at >= {i + 2}")
            page.wait_for_timeout(400)  # the answer is played after a short pause
    page.wait_for_function("window.SPOS.train.state().state === 'feedback'")
    page.keyboard.press("Escape")  # out of the move entry


def start_session(page, base: str, key: str):
    open_mode(page, base, "train")
    page.wait_for_selector("[data-train-launcher]:not([hidden])")
    focus(page, "train", "queue")
    page.keyboard.press(key)
    page.wait_for_function("window.SPOS.train && window.SPOS.train.state().state === 'solving'", timeout=15000)


# ── Scenes: each leaves the screen ready for its picture ─────────────────────────────────────────────────────


def welcome(page, base):
    """Home on the first run: the Welcome section, the key intro."""
    open_mode(page, base, "home")
    page.wait_for_selector(".home__welcome", timeout=15000)
    settle(page)


def starter(page, base):
    """The starter pack's preview: what's in it, its licence, Import."""
    welcome(page, base)
    focus(page, "home", "today")
    page.keyboard.press("s")
    page.wait_for_selector(".packview", timeout=15000)
    settle(page)


def home(page, base):
    """Home in use: due cards, one-key sessions, today's numbers."""
    open_mode(page, base, "home")
    page.wait_for_selector("#ws-home [data-view=today] [data-ticker]", state="attached")
    settle(page, 1000)


def train(page, base):
    """A Storm against the clock."""
    start_session(page, base, "1")  # Storm, 3 minutes
    settle(page, 1500)  # the opponent's first move is played after a moment


def train_feedback(page, base):
    """A puzzle solved: the verdict, the next date, the solution, its tags."""
    start_session(page, base, "r")  # Review
    solve(page)
    settle(page, 600)


def train_result(page, base):
    """The end of a session: its numbers and its puzzles."""
    train_feedback(page, base)
    page.keyboard.press("Enter")  # the next puzzle
    page.wait_for_function("window.SPOS.train.state().state === 'solving'")
    solve(page)
    page.click("[data-train-feedback] [data-cmd='train.quit']")  # Stop: the result
    page.wait_for_function("window.SPOS.train.state().state === 'result'")
    page.wait_for_selector("[data-train-result] .list__row")
    settle(page, 800)


def train_silhouette(page, base):
    """Training with the silhouette look: where the pieces stand and whose they are, not which."""
    open_mode(page, base, "train")
    page.wait_for_selector("[data-train-launcher]:not([hidden])")
    focus(page, "train", "queue")
    page.keyboard.press("w")  # custom session: look silhouette
    page.keyboard.press("Enter")
    page.wait_for_function("window.SPOS.train && window.SPOS.train.state().state === 'solving'", timeout=15000)
    settle(page, 1500)


def library(page, base):
    """The Library: a search with filters, the facets, the board beside the list."""
    open_mode(page, base, "library")
    page.wait_for_selector("#ws-library [data-library-results] [data-row]", timeout=15000)
    page.evaluate("(q) => window.SPOS.library.setQuery(q, 'positions')", QUERY)  # as typed into the query bar
    page.wait_for_function("(q) => document.querySelector('#ws-library [data-querybar]').value === q"
                           " && document.querySelectorAll('#ws-library [data-library-results] [data-row]').length > 0", arg=QUERY)
    focus(page, "library", "library")
    command(page, "display list")
    page.wait_for_selector("#ws-library [data-library-results][data-display=list] [data-row]")
    page.keyboard.press("j")
    page.keyboard.press("j")  # the cursor on a row, the board beside it shows it
    settle(page, 800)


def library_grid(page, base):
    """The same search as diagrams."""
    library(page, base)
    command(page, "display grid")
    page.wait_for_selector("#ws-library [data-library-results][data-display=grid] [data-row]")
    settle(page, 800)


def analyse(page, base):
    """A puzzle of the Library in Analyse: the move tree, the Puzzle pane, the inspector."""
    library(page, base)
    page.keyboard.press("a")  # analyse the row under the cursor
    page.wait_for_function("window.SPOS.ctx.mode === 'analyse'")
    page.wait_for_selector("#ws-analyse [data-movetree] .mt-move", timeout=15000)
    page.add_style_tag(content=STILL)
    focus(page, "analyse", "moves")
    page.keyboard.press("g")
    page.keyboard.press("g")  # the start position (the app remembers where the cursor was the last time)
    page.keyboard.press("l")  # the puzzle's first move: the Puzzle pane shows its start, solution and training
    page.wait_for_selector("#ws-analyse .pzpane__where--start", timeout=15000)
    if page.evaluate("window.SPOS.engine.state().enabled"):  # on since the engine scene (remembered): off here
        page.keyboard.press("e")
    settle(page, 800)


def analyse_engine(page, base):
    """Stockfish on: its lines, the evaluation bar, the best moves as arrows."""
    analyse(page, base)
    if not page.evaluate("window.SPOS.engine.state().enabled"):  # the engine's on / off is remembered
        page.keyboard.press("e")
    page.wait_for_selector("#ws-analyse .engine__line .engine__move", timeout=60000)
    page.wait_for_timeout(2500)  # a few more plies of depth


def analyse_file_eval(page, base):
    """The eval bar with two sources: a lichess game with file evals, engine on — both halves of the bar show."""
    # Import the analysed lichess study fixture (has [%eval] on moves)
    pgn = (Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "pgn"
            / "lichess-study-analysed.pgn").read_text(encoding="utf-8")
    result = post(page, "/lib/import/run/", {"text": pgn, "ready": True})
    if not result.get("ok"):
        fail(f"couldn't import the analysed game: {result}")
    uuid = result["first"]
    # Open it in Analyse
    page.goto(f"{base}/analysis/{uuid}/")
    page.wait_for_function("window.SPOS.ctx.mode === 'analyse'")
    page.wait_for_selector("#ws-analyse [data-movetree] .mt-move", timeout=15000)
    page.add_style_tag(content=STILL)
    # Navigate to a move that has a file eval (move 27 c3 has [%eval -0.8])
    focus(page, "analyse", "moves")
    # Click a later move in the tree that carries an eval
    page.wait_for_selector("#ws-analyse .mt-move", timeout=10000)
    # Move forward in the tree to reach a move with evals
    for _ in range(20):
        page.keyboard.press("l")
    page.wait_for_timeout(300)
    # Turn the engine on
    if not page.evaluate("window.SPOS.engine.state().enabled"):
        page.keyboard.press("e")
    # Wait for the engine to produce at least one line
    page.wait_for_selector("#ws-analyse .engine__line .engine__move", timeout=60000)
    page.wait_for_timeout(2000)  # let depth grow a bit
    # Wait for both halves of the eval bar to show (engine solid + file hatched)
    page.wait_for_function("""() => {
        const bar = document.querySelector('#ws-analyse .evalbar');
        if (!bar || bar.hidden) return false;
        const engine = bar.querySelector('[data-eval=engine]');
        const file = bar.querySelector('[data-eval=file]');
        return !engine.hidden && !file.hidden;
    }""", timeout=30000)
    settle(page, 800)


def collect(page, base):
    """Collect: the board editor and the entry session for diagrams from a book."""
    open_mode(page, base, "collect")
    page.wait_for_function("document.querySelector('#ws-collect [data-island=board]')?.board?.layer === 'setup'")
    settle(page, 600)


def stats(page, base):
    """Stats: the pattern library, card stages, retention, mastery; every number drills down."""
    open_mode(page, base, "stats")
    page.wait_for_selector("#ws-stats figure[data-chart]", timeout=15000)
    settle(page, 1200)


def settings(page, base):
    """Settings and the keymap: themes, languages, every key."""
    open_mode(page, base, "settings")
    page.wait_for_selector("#ws-settings [data-settings-list] [data-row]", timeout=15000)
    page.wait_for_selector("#ws-settings [data-keymap-list] [data-row]", timeout=15000)
    settle(page)


def help_guide(page, base):
    """`?`: the guide of the pane you are in, with its keys."""
    analyse(page, base)
    page.keyboard.press("?")
    page.wait_for_selector(".help", timeout=15000)
    settle(page)


def keys(page, base):
    """Space: the keys that follow, shown while you hesitate (which-key)."""
    analyse(page, base)
    page.keyboard.press("Space")
    page.wait_for_selector(".whichkey__grid", timeout=10000)
    settle(page, 300)


def command_line(page, base):
    """`:`: every command by its name, with suggestions."""
    analyse(page, base)
    page.keyboard.press(":")
    page.keyboard.type("theme ")
    page.wait_for_selector(".cmdline__row")
    settle(page, 300)


def library_menu(page, base):
    """With the mouse: a right click on a row lists what can be done with it, each with its key."""
    library(page, base)
    row = page.locator("#ws-library [data-library-results] [data-row].is-cursor")
    box = row.bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.4, box["y"] + box["height"] / 2, button="right")
    page.wait_for_selector(".menu", timeout=10000)
    settle(page, 300)


def details(page, base):
    """The Details pane beside the Library: every field of the row, ✎ to change, the diagram and flag switches."""
    library(page, base)
    page.keyboard.press("I")
    page.wait_for_selector("#ws-library [data-details-list] [data-row=is-diagram]", timeout=10000)
    settle(page, 500)


def lesson_pick(page, base):
    """`L` on a selection: the lessons as you type, or a new one."""
    library(page, base)
    for title in ("Back-rank mates", "Forks for beginners"):
        post(page, "/cmd/lesson.new/", {"args": [title]})
    page.keyboard.press("x")
    page.keyboard.press("j")
    page.keyboard.press("x")
    page.keyboard.press("L")
    page.wait_for_selector(".cmdline__input")
    page.keyboard.type("f")
    page.wait_for_selector(".cmdline__row >> text=a new lesson", timeout=10000)
    settle(page, 300)


EMPTY = {"welcome": welcome, "starter": starter}  # only while the library is empty
FULL = {
    "home": home, "train": train, "train-feedback": train_feedback, "train-result": train_result,
    "train-silhouette": train_silhouette, "library": library, "library-grid": library_grid, "analyse": analyse,
    "analyse-engine": analyse_engine, "analyse-file-eval": analyse_file_eval, "collect": collect, "stats": stats,
    "settings": settings, "help": help_guide, "keys": keys, "command-line": command_line, "library-menu": library_menu,
    "details": details, "lesson-pick": lesson_pick,
}
SCENES = {**EMPTY, **FULL}


# ── The README's pictures ────────────────────────────────────────────────────────────────────────────────────


def font(size: int):
    from PIL import ImageFont

    for path in ("/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def stitch(tiles, path: Path):
    """3 columns × 2 rows of 636 × 380 tiles with a caption under each: 2016 × 912, as in the README."""
    from PIL import Image, ImageDraw

    tile_w, tile_h, top, caption, columns = 636, 380, 24, 52, 3
    width = 2016
    gap = (width - columns * tile_w) // (columns + 1)
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (width, rows * (top + tile_h + caption)), (244, 242, 238))
    draw = ImageDraw.Draw(sheet)
    text = font(22)
    for i, (image, label) in enumerate(tiles):
        x = gap + (i % columns) * (tile_w + gap)
        y = top + (i // columns) * (top + tile_h + caption)
        sheet.paste(image.resize((tile_w, tile_h), Image.LANCZOS), (x, y))
        draw.rectangle([x - 1, y - 1, x + tile_w, y + tile_h], outline=(205, 200, 192))
        draw.text((x, y + tile_h + 12), label, fill=(30, 30, 30), font=text)
    sheet.save(path, optimize=True)


def readme_pictures(taken: list[Path]) -> list[Path]:
    """Copies of the Paper pictures taken now under the README's names, and the grid of the six themes."""
    from PIL import Image

    done = []
    for scene, name in README.items():
        source = OUT_DIR / f"{scene}_paper.png"
        if source in taken:
            shutil.copyfile(source, README_DIR / f"{name}.png")
            done.append(README_DIR / f"{name}.png")
    if all(OUT_DIR / f"analyse_{t}.png" in taken for t, _ in THEMES):
        stitch([(Image.open(OUT_DIR / f"analyse_{t}.png").convert("RGB"), label) for t, label in THEMES], README_DIR / "themes.png")
        done.append(README_DIR / "themes.png")
    return done


# ── Run ──────────────────────────────────────────────────────────────────────────────────────────────────────


def run(wanted: list[str], themes: list[str]):
    from PIL import Image
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    README_DIR.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix="spos-screenshots-"))
    log = data / "app.log"
    taken: list[Path] = []
    failed: list[str] = []
    app, info = start_app(data, log)
    base = f"http://127.0.0.1:{info['port']}"
    print(f"app on {base}, data in {data}")

    def shoot(page, scene, theme):
        try:
            SCENES[scene](page, base)
            path = OUT_DIR / f"{scene}_{theme}.png"
            page.screenshot(path=str(path))
            taken.append(path)
            print(f"  {path.name}")
        except Exception as error:  # one scene that doesn't come must not stop the others
            failed.append(f"{scene}_{theme}: {type(error).__name__}: {str(error).splitlines()[0]}")
            print(f"  {scene}_{theme}: FAILED ({type(error).__name__})")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport=SIZE, device_scale_factor=1, color_scheme="light")
            page.set_default_timeout(30000)
            page.goto(info["url"])  # the one-time link: the token becomes a cookie
            empty, full = [s for s in wanted if s in EMPTY], [s for s in wanted if s in FULL]
            for theme in themes if empty else []:  # the empty library first
                set_theme(page, base, theme)
                for scene in empty:
                    shoot(page, scene, theme)
            open_mode(page, base, "home")
            preview = post(page, "/packs/starter/", {})  # what the first-run screen shows: a preview and its token
            result = post(page, "/packs/run/", {"token": preview.get("token", ""), "ready": True}) if preview.get("ok") else preview
            if not result.get("ok"):
                fail(f"the starter pack didn't import: {result}", log)
            print(f"  {result['message']}")
            seeding = subprocess.run([sys.executable, __file__, "--seed-history"], cwd=ROOT, capture_output=True, text=True,
                                     env={**clean_env(), "SPOS_DATA_DIR": str(data), "DJANGO_SETTINGS_MODULE": "spaced_positions.settings"})
            if seeding.returncode:
                fail(f"the training history couldn't be added:\n{seeding.stdout}{seeding.stderr}", log)
            print(seeding.stdout.rstrip())
            for theme in themes if full else []:
                set_theme(page, base, theme)
                for scene in full:
                    shoot(page, scene, theme)
            browser.close()
    finally:
        stop_app(app, data)
        shutil.rmtree(data, ignore_errors=True)

    readme = readme_pictures(taken)
    print(f"\n{len(taken)} pictures in {OUT_DIR.relative_to(ROOT)}/")
    if readme:
        print("README:")
        for path in readme:
            with Image.open(path) as image:
                print(f"  {path.relative_to(ROOT)}  {image.width}×{image.height}")
    if failed:
        print("\nNot taken:")
        for line in failed:
            print(f"  {line}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenes", nargs="*", help=f"some of: {' '.join(SCENES)} (default: all)")
    parser.add_argument("--themes", default=",".join(t for t, _ in THEMES), help="comma-separated (default: all six)")
    parser.add_argument("--list", action="store_true", help="the scenes and what they show")
    parser.add_argument("--seed-history", action="store_true", help=argparse.SUPPRESS)  # run by the script itself
    args = parser.parse_args()
    if args.seed_history:
        return seed_history()
    if args.list:
        for name, scene in SCENES.items():
            print(f"{name:18} {scene.__doc__}")
        return
    wanted = args.scenes or list(SCENES)
    themes = [t.strip() for t in args.themes.split(",") if t.strip()]
    unknown = [s for s in wanted if s not in SCENES] + [t for t in themes if t not in dict(THEMES)]
    if unknown:
        sys.exit(f"update_screenshots: unknown {unknown}; scenes: {list(SCENES)}; themes: {[t for t, _ in THEMES]}")
    run(wanted, themes)


if __name__ == "__main__":
    main()
