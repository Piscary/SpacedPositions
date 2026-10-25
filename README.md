# Spaced Positions

**Collect, solve and train chess puzzles, keyboard first, with spaced repetition.** Each puzzle comes back just
before you would forget it, so the patterns stay. Spaced Positions runs on your own computer, in your browser,
without an account and without sending anything anywhere. It is free software (GPL-3.0-or-later), in English,
German, French and Italian.

- **Train**: Review (spaced repetition from solved or missed, no self-rating), Storm (against the clock, with combos),
  Streak (until the first miss, also with lives or blind), your weakest motifs, and custom sessions filtered by any
  search.
- **Collect**: enter the diagrams of a book fast (source, page and diagram number count up), paste a FEN, a PGN or a
  lichess link anywhere, import PGN files of any size.
- **Analyse**: a book-style move tree with variations, comments, annotation symbols and drawings, Stockfish in the
  browser (or a local engine), the evaluation graph, key moments of a game, and puzzles set up straight from the
  analysis.
- **Library**: positions, games, puzzles, players, sources and tags with a search language
  (`motif:fork diff:>=3 -is:diagram src:"Endgame Manual" sort:source`), filters, bulk tagging and automatic tag
  detection for 205 tactical, mating, positional and endgame motifs. A search is also a work list: analyse what it
  found, and each position drops out once its puzzle is in training.
- **Stats**: the pattern library, retention, mastery per motif, weak spots, records and activity; every number
  leads to the puzzles behind it.
- **Puzzle packs**: share positions, puzzles and games as one file, for example as a coach with your students, or
  move your own material to another computer.

## Install

**The app** (no Python needed): download it from the
[releases](https://github.com/Piscary/SpacedPositions/releases).

- macOS: open the `.dmg` and drag *Spaced Positions* to Applications.
- Windows: unzip the `.zip` and double-click `Spaced Positions.exe` in the folder.

The apps aren't signed yet (that needs paid certificates), so the system asks once: on macOS right click the app →
*Open*, on Windows *More info → Run anyway*. A double click starts Spaced Positions in the background and opens it
in your browser; another double click opens it again. It stops by itself 10 minutes after you closed the last tab.

**With Python** (3.12 or newer), from a copy of this repository:

```bash
pipx install .
spos
```

`spos` starts the app and opens the browser, like `jupyter notebook`; `Ctrl+C`, `spos stop` or `:quit` in the app
stops it. `spos list` shows where it runs, `spos restore <backup>` puts a backup back; the options are
`--no-browser`, `--port`, `--data-dir` (for example a synced folder) and `--lan` (open it from another computer at
home, with the same one-time link).

## First steps

1. **Fill the library.** Home shows how while it is empty: import a puzzle pack (drop the `.sppack` file on the
   window), collect diagrams from a book (`␣ c`), or paste positions and games anywhere (`⌘V` / `Ctrl+V`).
2. **Make puzzles.** In Analyse (`␣ a`), go to the move after which the puzzle starts, `p s` sets it up, `p r` puts
   it into training. On any board, `:puzzle` makes a puzzle from the moves played. Imported PGN files with set-up
   positions become puzzles by themselves.
3. **Train.** `␣ t`, then `r` for today's review, `1`–`3` for a Storm, `4` for a Streak.

Every action has a key, and every button shows it. `?` opens the help of the pane you are in: a short guide to it
(what it is for, how to do the usual things, what it works with), the keys that work there, and the search language.
`␣` (space) shows what can follow, `:` opens the command line (with completion, also for the values of settings), `F`
puts a letter on everything clickable.

| Keys | |
|---|---|
| `␣ h` `␣ t` `␣ a` `␣ c` `␣ l` `␣ s` `␣ ,` | Home · Train · Analyse · Collect · Library · Stats · Settings |
| `⇥` · `␣ 1`–`␣ 9` | Focus the next pane · pane N |
| `j` `k` · `g g` `G` · `]` `[` | Down, up · top, bottom · next, previous section |
| `u` `U` | Undo, redo (also every change of an analysis, after a reload too) |
| On a board | Click or drag to move · right-drag for arrows (⇧ red, ⌥ blue) · `i` type a move (`Nf3`, also German, French or Italian letters) · `S` board editor · `f` flip |
| While solving | `h` hint (counts as missed) · `s` solution · `Esc` pause |
| `␣ l` Library | `/` search (`⇥` completes, `g ?` explains it) · `C` clear it · `x` select · `t` tag · `T` train · `a` analyse · `e` export (PGN or pack) |
| `␣ w v` · `␣ w s` | Split side by side · above and below; `␣ w q` closes, `␣ w m` maximises |

## Languages

Settings → Language: English, Deutsch, Français or Italiano, or automatically the browser's language. Tag names
follow the language of the app, or keep one of their own (for example German tag names in an English app). Piece
letters in moves (Settings → Board) can be English (KQRBN), German (KDTLS), French (RDTFC) or Italian (RDTAC).

## Puzzle packs

A pack (`.sppack`) holds positions with their analysis, tags and puzzles, and games. Training history and private
notes never travel. In the Library, search or select what goes in, then `e` → *Pack* or
`:pack-export "Back ranks" for=Ben`. `for=` makes a personal copy: the name shows with every puzzle of it ("from
Coach for Ben"), and Settings → Packs logs which version went to whom. Exporting under the same title again is the
next version of the same pack: when the receiver imports it, new positions and moves are added and their training
history stays. To import, drop the file on the app or use `:pack-import`; a preview shows what is new and the
pack's licence.

**Packs and copyright.** Spaced Positions doesn't check what goes into a pack, so you decide what you may share.
As a guide (not legal advice):

- Moves of games and positions are facts, and old games are public domain anyway; your own analysis and comments
  are yours to share.
- A published puzzle book is protected as a collection (its selection, order and solution texts). Copying a whole
  book, or most of it, into a pack for others needs the publisher's permission. For your own study, a pack of your
  own book is fine.
- Teaching exceptions (in Switzerland Art. 19 of the Copyright Act, similar elsewhere) allow excerpts for your
  pupils, not complete books.
- The licence you give a pack (`licence="…"`) is shown to whoever imports it. The default asks the receiver not to
  pass a personal copy on.

## Your data

Everything stays on your computer, in the user-data folder (`~/Library/Application Support/Spaced Positions/` on
macOS, `%APPDATA%\Spaced Positions\` on Windows, `~/.local/share/spaced-positions/` on Linux; Settings → App shows
it). A compressed backup is made every day and before every update, in its `backups/` folder; *back up now* is in
Settings → App. The app asks no server anything unless you turn on the update check (Settings → App), which asks
GitHub once a day for the newest version. Your own piece sets go in the data folder's `pieces/` folder
(`pieces/<name>/wK.svg` … `bP.svg`); a local engine is chosen in Settings → Engine.

## Licence

Spaced Positions is free software under the GNU General Public License, version 3 or later ([LICENSE](LICENSE)):
use it, read and change its source, and pass it on under the same licence. It bundles chessground and python-chess
(GPL-3.0), Stockfish 17.1 (GPL-3.0), chess.js (BSD-2-Clause), htmx (0BSD), Django, waitress, WhiteNoise and
platformdirs (BSD, ZPL, MIT) and 12 piece sets under free licences; Settings → Licences in the app lists every
component with its licence and shows all licence texts.

## Develop

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python manage.py runserver 8020        # data in .data/, DEBUG on
.venv/bin/python manage.py design build          # after changing anything in design/
.venv/bin/python manage.py design check          # the design lint and the translation check (also in CI)
.venv/bin/python manage.py i18n extract          # after changing texts: new texts into locale/*/django.po
.venv/bin/python manage.py i18n build            # the compiled catalogues (django.mo, static/i18n/*.json)
.venv/bin/python -m pytest -m "not browser"      # Python tests
node --experimental-default-type=module --test tests/js/
.venv/bin/python -m playwright install chromium && .venv/bin/python -m pytest -m browser
sh packaging/build-macos.sh                      # the double-click app and its .dmg in dist/ (with the venv active)
```

Every view has its guide for the help overlay in `templates/help/<view>.html` (the same parts in each: what it is for,
*How to*, *Works with*, *Good to know*; keys written as `{% key "command" %}`, so they follow the keymap): a new view
or a new workflow gets its guide in the same change. Texts are marked for translation with `_()` (Python),
`{% translate %}` (templates) and `tr()` / `trn()`
(JavaScript); `manage.py i18n missing` lists what still needs a translation. A version tag (`git tag v0.2.0 && git
push --tags`) builds and tests the macOS and Windows apps in GitHub Actions and attaches them to a draft release;
bump `version` in `pyproject.toml` and `__version__` in `spaced_positions/__init__.py` first. The design and the
architecture are described in [spec/](spec/README.md).

### Where things are

```
design/                  the design system's source: tokens, themes, commands, keymap, licences of vendored files
spaced_positions/
  launcher.py            the `spos` command
  core/                  shell, layouts, server commands, settings, languages (i18n.py, i18n_catalog.py), updates
  training/              positions, puzzles, cards, the scheduler (srs.py), Storm pace, sessions
  analysis/              move trees, the journal (undo), puzzles from the analysis, PGN
  library/               sources, players, tags (data/tags.json: the vocabulary in four languages), games, the query
                         language, Collect, the PGN importer, tag detection, puzzle packs
  stats/                 metrics, achievements, the Stats sections, Home, SVG charts
  locale/                translations (German, French, Italian)
  static/                CSS, JavaScript (core/, islands/), generated design files and catalogues, vendored libraries
  templates/             shell, components, views
packaging/               the double-click app: entry, PyInstaller spec, icons, macOS build, smoke test
tests/                   pytest (incl. Playwright journeys and the axe accessibility check) and tests/js (node)
```
