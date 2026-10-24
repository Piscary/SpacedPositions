# Spaced Positions

Collect, solve and train chess puzzles: keyboard first, with spaced repetition. Free software (GPL-3.0-or-later).

**Status: phase 7 (migration).** Phase 0 built the shell, panes and splits, the command and key system, the
design tokens and themes, the style guide and the launcher. Phase 1 added the board (moves, drawings, typed moves, the
board editor), MiniBoards, paste detection and piece sets. Phase 2 added puzzles, cards with spaced repetition, and
the Train mode: Review, Storm and Streak. Phase 3 adds the Analyse mode: a book-style move tree with variations,
comments, annotation symbols and marks, the Inspector, Stockfish in the browser with lines, arrows and an eval bar,
puzzles set up from the analysis, and undo of every change (also after a reload). Phase 4 adds the Library (a query
language with completion, results as table, list or grid, a filter pane, bulk tagging and training with undo), tags
in Analyse and Train, Collect for entering book diagrams fast, and PGN import and export with games in Analyse.
Phase 5 adds Stats (pattern library, retention, mastery, weak spots, records, activity, collection, all as keyboard
charts), Home, achievements, tag detection with python-chess, and the eval and variation graphs. Phase 6 adds the
Settings mode with the keymap editor, your own themes, key bindings and piece sets, settings as one TOML file (export
and import), editing tags, sources and players, a local Stockfish through the app, key moments of games (`:moments`),
figurines and folding in the move tree, and optional sounds. Phase 7 brings everything over from
chess-study-manager (`spos import-csm <its db.sqlite3>`, or Settings → Data; it can run again and adds only what's
new), plus opening a row beside the Library's list, sorting and folding groups, the puzzle's analysis beside the
board in Train, structure suggestions, and big PGN imports in the background. The specification is in [spec/](spec/README.md).

## Start it

```bash
pipx install .        # or: pip install -e . in a virtual environment
spos                  # starts the app and opens the browser
```

`spos` works like `jupyter notebook`: it picks a free port (8765 or the next one), opens the browser with a one-time
token, and keeps running until `Ctrl+C`, `:quit` in the app, or `spos stop`. Running `spos` again just opens the
browser at the running instance. `spos list` shows where it runs, `spos import-csm <db.sqlite3> [--dry-run]` brings
over a chess-study-manager library; `--no-browser`, `--port`, `--data-dir` and `--lan`
are the options. Data lives in the platform's user-data folder (`~/Library/Application Support/Spaced Positions/`
on macOS), with a backup before every migration. Your own piece sets go in its `pieces/` folder (`pieces/<name>/` with
`wK.svg` … `bP.svg`); a local engine is chosen in Settings → Engine (`stockfish` on the PATH by default).

## Try it

| Keys | |
|---|---|
| `␣` | Leader: the which-key panel lists what can follow |
| `␣ h` `␣ t` `␣ a` `␣ c` `␣ l` `␣ s` `␣ ,` · `␣ ␣` | Modes · back to the previous mode |
| `⇥` · `␣ 1`–`␣ 9` · `␣ w h/j/k/l` | Focus the next pane · pane N · by direction |
| In the focused pane | `j`/`k` scroll (lists: cursor) · `J`/`K` half a page · `g g`/`G` top/bottom · `]`/`[` next/previous section · `i` edit its text field · `Esc` back |
| `␣ u p` | Piece set, with live preview (12 free sets) · or `:pieces merida` |
| `␣ w v` / `␣ w s` | Split (then pick a view) · `␣ w q` close · `␣ w m` maximise · `␣ w c` collapse |
| `␣ w <` `>` `+` `-` | Resize (sticky: keep pressing, `Esc` ends) · or drag a gutter |
| `:` | Command line: `:vsplit notes`, `:theme ink`, `:set main=#e2b714`, `:set density=compact`, `:layout-save study` |
| `F` | Hint labels: click anything by keyboard |
| `u` / `U` | Undo / redo (layout, settings, every change of an analysis) |
| `?` | Every key that works here |
| `:ui` | The style guide: every component, plus a demo list linked to a board |
| On a board | Click/drag to move · right-drag arrows (⇧ red, ⌥ blue) · `i` type a move (`Nf3`, `Sf3`, `g1f3`) · `S` board editor · `h`/`l` step · `f` flip · `q` square tool · `y`/`Y` copy FEN/PGN |
| `⌘V` | Paste a FEN, PGN or lichess link anywhere (not in a text field): the status line offers `b` show on a board, `a` analyse |
| `␣ t` Train | `r` Review · `1` `2` `3` Storm 3′/5′/10′ · `4` Streak · `5` Streak ♥3 · `6` blind · while solving `h` hint, `s` solution, `Esc` pause |
| `:puzzle` | On any board: the line played so far becomes a puzzle |
| `␣ a` Analyse | `:analyse <title>` opens a position · `h`/`l` step · `j`/`k` other variation · `1`–`7` `! ? !! ?? !? ?! □` · `m g/d/b` mark · `c` comment · `P` main line · `d` delete · `e` engine, `↵` its best move · `p s` puzzle from here, `p x` ends here, `p r` ready |
| From Train | Feedback: `a` analyse, `e` edit the puzzle, `t` tag · Result: `↵` opens the puzzle under the cursor, `a` the missed ones (`n`/`N` the others) |
| `␣ l` Library | `/` query (`motif:gabel diff:>=3 -is:diagram sort:-difficulty`, `⇥` completes) · `1`–`6` collections · `x` select · `t` tag · `T` train · `a` analyse · `d` trash · `e` PGN · `␣ u v` table/list/grid · `u` undoes any of it |
| `␣ c` Collect | Paste a FEN and `c`, or set up with `S` · `⌘↵` save & next · in the entry pane: `s` source, `↑↓` diagram, `t` tags, `1`–`9` presets |
| `:import` | A PGN file: games, and short set-up lines as puzzles (`r` into training) |
| `␣ s` Stats | `j`/`k` charts · `h`/`l` points · `↵` drill down · `t` table · `1`–`5` period · `g <key>` a section |
| `␣ h` Home | `r` review · `1`–`6` sessions (`5` weakest motifs) · `a` continue the analysis · `c` continue collecting |
| `:detect` · `:evaluate` | Tags from python-chess (Library selection or Analyse) · the engine over the main line (`␣ w v`, `g` the eval graph) |

## Puzzles to train with

Make puzzles from any board with `:puzzle`, or import the training puzzles of a chess-study-manager database (it reads
a copy; the original is never opened):

```bash
.venv/bin/python manage.py import_csm ../chess-study-manager/db.sqlite3
```

## Develop

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python manage.py runserver 8020        # development: data in .data/, DEBUG on
.venv/bin/python manage.py design build          # after changing anything in design/
.venv/bin/python manage.py design check          # the design lint (also runs in CI)
.venv/bin/python -m pytest -m "not browser"      # Python tests
node --experimental-default-type=module --test tests/js/
.venv/bin/python -m playwright install chromium && .venv/bin/python -m pytest -m browser
```

### Where things are

```
design/                  source of truth for the design system
  tokens.toml            tier 1 tokens (types, defaults, ranges)
  derived.css            tier 2 tokens (derived in CSS)
  themes/*.toml          paper, ink
  commands/*.toml        every command: title, args, when, handler
  keymap/default.toml    bindings by context
  licences.toml          licences of vendored files
spaced_positions/
  launcher.py            the `spos` command
  design/                build + lint (`manage.py design build|check`)
  chesslogic.py          all chess rules on the server (python-chess): FEN checks and fixes, paste parsing, SVG boards
  core/                  shell views, layouts, server commands, chess endpoints, token middleware, template tags
  training/              positions, puzzles (solution trees), cards, scheduler (srs.py), Storm pace, selection, API
  analysis/              move trees of positions and games, the journal (undo), puzzles from the analysis, PGN, API
  library/               sources, players, tags (data/tags.json: the starter vocabulary), games, saved queries,
                         the query language (query.py), Collect, the PGN importer, bulk commands, tag detection
  stats/                 metrics, achievements, the Stats sections, Home, SVG charts (charts.py)
  static/design/         generated: tokens.css, themes.json, commands.json (committed)
  static/css/            components (cascade layers; no literal colours or sizes)
  static/js/core/        keys, commands, layout, command line, hints, help, lists, menu, lines, paste, san,
                         analysis (tree, Moves and Inspector panes), engine (Stockfish worker, lines, eval bar),
                         library (QueryBar, results, bulk), collect (entry session), importer, confirm
  static/js/islands/     the board (chessground + chess.js), the PGN/FEN view, the trainer
  static/vendor/         htmx, chessground, chess.js, Stockfish 17.1 lite (licences in licences/ and design/licences.toml)
  templates/             shell, components, views
docs/keymap.md           generated keymap reference
tests/                   pytest (design, shell, chess, launcher, training, analysis, browser journeys, axe) and tests/js (node)
```

Rules the lint enforces: every command has a client or server handler; every `{% cmd %}` and `data-cmd` names a
real command; no key is both a command and a prefix in one context; global keys are reserved; browser-owned keys are
never bound; built-in themes pass the contrast checks; component CSS uses tokens only; dependencies and vendored files
have GPL-compatible licences; the generated files are up to date.
