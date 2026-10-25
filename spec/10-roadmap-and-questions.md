# 10 · Roadmap and open questions

## Build order

Each phase ends with something usable and with its components in the `/_ui/` style guide.

| Phase | Builds | Done when |
|---|---|---|
| **0 · Foundation** | Token pipeline (`design build/check`), 2 themes (`paper`, `ink`), shell (AppBar, StatusLine), command registry, `keys.js` (layers, sequences, which-key, flash), CommandLine, Pane/Split/Gutter/Section, focus model, `/_ui/` gallery, **the `spos` launcher** (09 §11: one command starts the server and opens the browser), CI with lint + screenshots | You can split, focus, resize, collapse and close panes with keys and mouse in the style guide; every key shows up in which-key and the command line; `spos` opens it in the browser |
| **1 · Board** | Board island (play, drawing, setup, move entry), MiniBoard renderer, FEN/PGN copy-paste detection | Board parity with lichess for moving and drawing; paste anything anywhere works |
| **2 · Train** | Puzzle/card model, scheduler, Launcher, Solving, Feedback, Result, Storm/Streak/Review, training hot path | A full Storm and a Review run without a single blocking request; keyboard journey test passes |
| **3 · Analyse** | MoveTree, Inspector, EngineLines/EvalBar, link groups, puzzle setup from the analysis, undo journal | The old app's analysis workflow is possible keys-only |
| **4 · Library + Collect** | The data model of 11 (games, tags, sources, players, saved queries, trash), QueryBar and search language, List/Table/CardGrid, selection + bulk, filters, rapid entry, PGN import, and the items moved here from phases 1–3 | Find → select → tag → train in under 10 keystrokes |
| **5 · Stats + rewards** | Charts island, Stats sections, milestones, records, AchievementChips, mastery | Every number drills down |
| **6 · Customisation** | Settings mode, theme editor, keymap editor, settings export/import, more themes and piece sets | A user theme and a remapped key survive export → import on a fresh install |
| **7 · Migration** | Import from `chess-study-manager/db.sqlite3` (read-only) | Positions, games, trees, tags, cards with history arrive intact |
| **8 · Packs + distribution** | Puzzle packs (export/import, personalised exports, export log, 09 §12), double-click installers for macOS and Windows, first-run screen, licences page with a link to the source, update check | A student installs the app with a double click, imports a coach's pack and trains it, without a console |

Phase 2 comes before Analyse on purpose: training is the main focus, and it stresses the board, the keys and the
speed budgets hardest.

### Phase 0 status (2026-10-23)

Built in `spaced_positions/`: token pipeline with `design build/check` (incl. contrast, keymap, reference, CSS-literal
and licence lint), themes `paper` and `ink`, shell, command registry, `keys.js` (layers, sequences, which-key, sticky
window submode, flash, teach-keys tips), command line with completion, hint labels, help overlay, menus and the view
picker, panes/splits/gutters/sections, focus, link groups, maximise/collapse/swap/rotate/resize, hidden buffers,
named layouts, layout undo, mode switching with three live workspaces, `/ui/` style guide, the `spos` launcher with
token access, and CI (lint, Python and JS unit tests, Playwright keyboard journeys, latency budget, screenshots).

Not yet done from the phase-0 list, moved on:
- Accessibility check with axe-core in CI → phase 1 (needs the vendored axe script).
- Icon sprite → with the first icons (phase 1).
- Auto-stop after the last tab closes (heartbeat) → phase 8, with the double-click installers.
- Undo of server data through a persistent command journal → phase 3; phase 0 undo covers layout and settings, in
  memory.

### Phase 1 status (2026-10-23)

Built: the board island on chessground 9.2.1 + chess.js 1.4.0 (vendored, licences recorded): click and drag moves
with legal-move dots, promotion menu, last-move and check highlights, lichess drawing (right-drag arrows, right-click
circles, Shift/Alt colours), the square tool, typed moves (SAN, German letters, UCI, with arrow previews), the board
editor (palette, side, castling, en passant, mirror, diagram, live validation with python-chess and one-key fixes),
flip, stepping, copy FEN/PGN, undo of moves and setups. Boards in a link group share a *line* that survives reloads;
browsing a list moves its linked board. The PGN/FEN view. MiniBoards (cached server SVG). Paste anything anywhere
(FEN, placement, lichess links, PGN, FEN lists) with offers in the status line. Tests: chess module and endpoints,
the move matcher (node), 13 board journeys, and the axe-core accessibility check (moved here from phase 0).

After trying it (same day): thin token-coloured scrollbars in every browser; keyboard movement inside any pane
(`j k J K PgDn PgUp g g G ] [`) and `i` to edit a pane's field; 12 free piece sets with a live-preview picker
(`␣ u p`, `:pieces`), MiniBoards drawn in the chosen set.

Moved on:
- Live duplicate check in the editor → phase 4 (needs the library).
- German letters for the setup palette and `board-coords = outside` → phase 6 (settings).
- Icon sprite → when the first icon is needed (none so far: the UI uses text glyphs).
- Variations instead of replacing the rest of a line → phase 3 (move tree).

### Phase 2 status (2026-10-23)

Built: Position, Puzzle (a self-contained solution tree: main move, also-correct moves, answer lines), Card (one
answer line, with the spaced-repetition state), Session and Attempt (`training/`). The scheduler and the Storm pace
keep the old app's rules (solved/missed only; hints count as missed; early solves don't push a card out). Selection:
Review (due learning, due reviews, then up to 20 new a day), Storm and Streak (one card per puzzle, easy → hard).
The Train mode: launcher with one-key sessions and a custom builder (mode, look, side, lives, first move), solving with
a judged board (any mating move counts when the main move mates; the opponent answers along the card's line), a
heads-up display (clock with bonus/penalty, combo meter, lives, prompt, blind piece list), feedback with the solution
replayed, retry, flag, pause, and a server-rendered result (stats, records, a time-per-puzzle chart, the puzzle list
linked to the board). Looks: normal, silhouette, blind; solving as either colour (mirroring). `:puzzle` makes a puzzle
from any board line; `manage.py import_csm <db>` imports the old app's puzzles and schedules as test data (from a
copy; history and the rest follow in phase 7). Tests: scheduler, trees, selection, API, import, 7 Train journeys,
accessibility of the launcher.

Moved on:
- Weakest motifs, milestones, achievements beyond records, mastery → phase 5 (needs tags and statistics).
- Filters in the custom builder and objectives from tags → phase 4 (library, tags).
- Analyse/edit a puzzle from feedback or the result → phase 3.
- Choosing the Storm pace in the launcher (medium for now) → phase 6 (settings).

### Phase 3 status (2026-10-24)

Built: the analysis of a position as a tree of nodes (`analysis/`), with comments, annotation symbols (move and
evaluation NAGs), marks, line colours and drawings per move; the operations play (an existing move is reused, a new
one becomes a variation), add a line, delete, promote, reorder and correcting the start position (the analysis is
kept when its moves stay legal). Every change is a journal entry with snapshots before and after: `u`/`U` undo and
redo it, also after a reload. The Analyse mode: board, Engine, Moves and Inspector linked in group A; the move tree
as a book (main line as text, lettered variation blocks, comments in place, marks as coloured edges); stepping
without requests; the Inspector (move, annotation, mark, comment with figurine keys, puzzle, position); Stockfish
17.1 lite in a worker (MultiPV lines, arrows, eval bar, best move on `↵`, clicking a line adds it); puzzles set up
from the analysis with the old app's walker (start, ends, also correct, all answers, ready, discard), rebuilt into
cards after every change and shown in the move tree. Ways in: `:analyse` with live search, paste → `a`, Train
feedback `a`/`e`, the result list `↵` (with `n`/`N` through the session). Safeguards: attempts are never deleted
through a cascade (`Attempt.card` is `PROTECT`); undo takes a trained puzzle out of training instead of deleting it.
Tests: tree operations, journal, puzzles, rendering and endpoints (17), 10 Analyse journeys incl. axe.

Moved on:
- Move tags and position tags (`t`, `T`, the Tags section of the Inspector) → phase 4 (the tag vocabulary).
- Eval graph and variation graph → phase 5 (the eval graph needs games, which arrive with the library).
- Analysing a puzzle in a split inside Train (instead of switching to Analyse), and `a` on the result (Analyse the
  missed ones as a subject list) → phase 4, with subject lists from the library.
- Puzzles made with `:puzzle` from a board line keep their own solution and have no analysis: Analyse opens their
  position at the start. Making them through the analysis → phase 4, with Collect.
- A local Stockfish binary (more threads, deeper) streamed by the server → phase 6 (settings); engine depth and
  line count settings → phase 6.
- Fold carets for variations and figurines in the move tree (`figurines` token) → phase 6.

### Phase 4 status (2026-10-24)

Built: the data model of 11 in a `library` app: sources, players, tag fields with the old app's 205 tags (decision
18, a data file loaded by a migration), position, move and game tags with their origin, tag presets, saved queries,
games with their own move tree (Node and the journal have a position or a game as owner), and the trash. Positions
gained description, notes, source with page and reference, difficulty override, diagram flag, game link, derived
side and material. Your positions were migrated additively: citations became sources with page and diagram number
(the text is kept), tag names became tags (665 of 665). The query language (`library/query.py`: parser with
problems and spans, compiler for six collections, saved queries inside queries). The Library mode: QueryBar with
completion, results as table, list or grid, collections 1–6, the filter pane with live facets (`↵` toggles, `-`
excludes), selection and bulk commands (tag, untag, trash, restore, train, analyse, copy FENs, export PGN) with
exact undo, `:save-query`, `:trash-empty` (keeps positions with training history). Tags in Analyse (`T` position,
`t` move, the Inspector's Tags section, chips in the move tree) and Train (`t` in feedback); objectives from goal
tags; custom sessions filtered by a query (`/`, saved-query chips, a live match count); `a` on the Train result
analyses the missed ones. Collect: the entry session, save & next, live duplicates with merge, pasting FENs.
PGN import (games with variations, comments, NAGs and drawings; short set-up lines as puzzles; player matching;
duplicates) with undo, PGN export, games in Analyse with `:new-position`. `:puzzle` now goes through the analysis.
Untouched default layouts move to the new defaults. SQLite transactions are IMMEDIATE (saves that arrive together
queue). Tests: the query language (8), the library on the server (13), 12 Library/Collect/import journeys incl. axe.

Moved on:
- Imports bigger than 5,000 games or 20 MB (in the background, with progress) → phase 7, with the migration of the
  old database.
- Editing the vocabulary (new tags, renaming, the hierarchy), sources and players, `:player link` for names that
  match nobody → phase 6 (Settings); the old app's players → phase 7.
- Tag detectors and suggested tags (`:detect`) → phase 5.
- `o` open in a split, sorting by a column key, folding groups in the table, analysing a puzzle in a split inside
  Train → phase 6 (layouts).

### Phase 5 status (2026-10-24)

Built: the `stats` app with chess-study-manager's metrics ported (stages, pattern library with history and
forecast, retention, mastery ladder per tag and family, weak spots, robustness, Storm and Streak records,
consistency, the activity calendar, points per week, the collection and its funnel) and achievements (milestones,
records, level-ups; logged once, the first run logs the history as seen except the latest). Charts as
server-rendered SVG (line, stacked bars, horizontal bars, calendar heatmap, ladder, sparkline) with a keyboard
island: the Stats mode with ten sections, periods, table views and drill-downs into the Library or a Streak. Home
built: Today (due, quick sessions, today, the pattern library, the achievement banner) and Continue (analysis,
collect, paste box, recent). Achievement chips on the result screen and once in the status line; the weakest motifs
in the launcher and as a session. Tag detection ported from the old app (all 1,161 old auto tags reproduced) with
suggestions, dismissals and automatic difficulty from the old tag weights; `:detect`, and detection on Collect saves
and imported puzzles. `:evaluate`, the eval graph and the variation graph. Tests: 11 on the server, 5 journeys.

Moved on:
- Sound (optional clicks and tones) and the Ticker (numbers counting up) → phase 6 (settings and polish).
- Detection by the engine (errors by win-chance drop, turning points: the old app's `engine` and `moments`
  detectors), structural suggestions (pawn structure, batteries as position themes) and annotation-symbol moments
  → phase 6, with the local engine.
- An EvalGraph thumbnail in the Library's game rows → phase 6.

### Phase 6 status (2026-10-24)

Built: the Settings mode (themes with a live preview, tokens and settings in eight sections, `h l` steps a value,
`↵` edits it on the command line, `⌫` resets it, contrast shown next to the colours) beside the keymap editor (every
command with its keys, `↵` records new ones and checks them like the lint, `⌫` removes one; `:map`, `:unmap`,
`:map-reset`, also for one context with `@view.library`). Settings next to the tokens (`:set training.new-per-day=30`):
new cards a day, Storm pace (also in the launcher), keycaps, teach keys, which-key, piece letters, the engine (browser
or a local program, lines, depth, threads, hash, arrows), sounds and counting numbers. User themes (`:theme-save`,
`:theme-delete`, `:theme-export`), four more themes (Nord, Sepia, Forest, High contrast), and the whole setup as one
TOML file (Settings → Data: export, paste to import; a pasted theme becomes a theme of its own). Piece sets of the
user's own in the data folder (07 §6). Editing the vocabulary, sources and players in the Library (`:edit` on the
selection, `c`; `:new-tag`, `:new-player`, `:new-source`; `d` deletes the unused ones; `:player-link` with
`is:unlinked`), each with undo. The moved-on items: figurines, German letters and fold carets in the move tree (`z`,
`Z`), German letters in the board editor, coordinates outside the board, `:lichess`, sound (WebAudio, off by
default) and the Ticker, EvalGraph thumbnails in the game rows, the local engine through the app, and `:moments`
(the old app's engine, moments and annotation detectors: errors by win-chance drop, missed wins, turning points,
only moves and critical moments with the local engine, missed and allowed mates, tactical explosions, the
annotator's symbols). Tests: 23 on the server, 13 journeys incl. axe.

Moved on:
- `o` open in a split, sorting by a column key, folding groups in the table, analysing a puzzle in a split inside
  Train → phase 7 (with the migration, which brings the old app's large libraries that need them).
- Structural suggestions (pawn structures, batteries as position themes) → phase 7.

### Phase 7 status (2026-10-24)

Built: the migration from chess-study-manager (11 §6): sources, players, games and positions with their trees,
tags with their evidence, suggestions and dismissals, puzzles, cards, every session and
attempt, the old analysis activity; achievements found again from the joined history. It reads a copy of the old
database, backs this one up first, and can run again (it adds only what is new), so both apps can be used side by
side for a while; what was done here is never undone. `spos import-csm`, `manage.py import_csm`, Settings → Data,
each with a dry run. Checked on a copy of the development database: 2,002 positions and 4,059 moves as in the old
app, 5,378 old attempts joined to the 319 made here, a second run adds nothing. The items moved here: `o` opens a
row beside the list (a board and its move tree), `s` sorts by a column, groups fold with `z`/`Z`, `a` on the Train
feedback shows the puzzle's analysis beside the board (`A`: in Analyse), the old app's structure detector
(pawn structures, rooks and files, batteries, imbalances, king safety, endgame set-ups) as suggestions, and big
PGN imports in the background with progress. Tests: 8 on the server, 3 journeys.

Not migrated: publishing (out of scope). The old app's players arrive, and `:player-link` (phase 6) links names
that match nobody.

### Cleanup before phase 8 (2026-10-25)

- Search: `src:` picks one source exactly (its whole name, or `s5`) or every source with all the given words (title,
  short name, authors); the filter pane and the completion use the exact form, so choosing one source marks only that
  one. Words search title, task, description, notes, citation, source, tags and the analysis' comments, without
  case or accents.
- The old app's pipeline boards are gone (their tags removed by a migration): the filters say what is analysed and
  solved. Sorting a book in its order: `sort:source` (title, page, diagram number, as numbers), `sort:diagram`,
  `sort:page`, and for puzzles `due`, `last`; `T` and `a` follow the query's sort.
- Removed: the placeholder Tags view, the demo views (Demo list, Notes, Linked preview, About this mode), the phase
  labels of modes, views and commands, unused CSS and JS. The style guide shows a Library with its board.
- Every view works in every mode or says why not (03 §4): analyses, their keys and the engine anywhere but the
  engine in Train; Session and Entry session point to their mode; removed views keep the layout and say so.
- Finished what the spec promised: your own CSS (07 §5), prefetching workspaces (09 §10), daily compressed backups
  with `spos restore`, Settings → App, stopping by itself (09 §11).
- Speed and size at 50,000 positions (09 §10): every page under 200 ms (Stats was 68 s), 19 % less on disk, backups
  a fifth of the database; the pack format of phase 8 is defined (09 §12: about 60 bytes a position, zipped).

### Phase 8 status (2026-10-25)

Built:
- **Puzzle packs** (09 §12): `:pack-export` from the Library's selection or query (`e` → *Pack*), personalised copies
  (`for=Ben`: the student's name and a copy id travel in the manifest), the licence (default: personal use by the
  named student), versions under the same pack id, the export log and the received packs in Settings → Packs. Import
  by dropping the file on the app or `:pack-import`: a preview with the licence and what is new, updated, a duplicate
  or the user's own; a newer version updates the positions and keeps the student's cards and history. Received
  packs are the source of their positions, cited as *from Coach for Ben* under each puzzle; a student's pack export
  leaves personal copies out.
- **The double-click app** (09 §11): PyInstaller (`packaging/`), a `.dmg` for macOS built and smoke-tested here (68 MB
  app, 43 MB image; first start about a second), a `.zip` for Windows built by the release workflow on a version
  tag. A double click starts the server in the background and opens the browser; later double clicks only open
  the browser; it stops by itself 10 minutes after the last tab. The app icon (`packaging/icons.py`).
- **First run**: Home's *Welcome* while the library is empty (import a pack, collect from a book, paste, the old
  app's database if one is found).
- **Licences** in Settings, with the link to the source; **update check** (opt-in, once a day, GitHub releases).
- No backup of an empty database on the very first start.

Not done, moved on:
- **Starter pack** (decision 16): needs the lichess puzzle database (CC0, a large download) and a choice of motifs
  and size; the first-run screen offers importing a pack instead.
- Password on pack files: left out (09 §12).
- Signing the apps (Apple Developer ID, Windows certificate): paid; until then the first open needs right click →
  *Open* (macOS) or *Run anyway* (Windows).
- The Windows build is untested until the first tag runs the workflow.

## Out of scope for now

- **Publishing** (documents, print, PDF): the old app's document editor. The Diagram renderer is shared, so it can
  come back later as its own mode.
- **Pipeline boards** (Trello-style stages): replaced by *status* facets and saved queries in the Library. Could
  come back as a Library display (`␣ u v` → board).
- Playing games against the engine or online.
- **Phone and tablet layouts** (decision 9).
- **Hosted / synced multi-user** (accounts, a coach seeing students' progress online). Students run their own local
  copy and share material through puzzle packs (decision 2). Progress reports from student to coach could come
  later as an exported file, before any server exists.
- Payments, licence keys, a shop: the app is free (decision 13).

## Decided

Decisions 1–17 were taken on 2026-10-23, 18–20 on 2026-10-24.

| # | Question | Decision | Consequence in the spec |
|---|---|---|---|
| 1 | **Keyboard layout** | **QWERTY** (US/intl) | Defaults are designed and tested on QWERTY. Matching stays layout-aware (02 §4); the AltGr check in the lint is a warning, not a failure (07 §8). |
| 2 | **Local or hosted** | **Local first.** Each person (you, each student) runs their own copy with their own database. No login. Material moves as **puzzle packs**. | 09 §8 (models keep a `user` field, so hosting later needs no redesign), 09 §11 launch, 09 §12 packs. |
| 3 | **Board library** | **chessground** | 06 §9. |
| 4 | **Engine location** | **Both**: Stockfish WASM in the browser by default, the local binary through the server when configured | 06 §7, 09 §1. |
| 5 | **CSS approach** | **Plain CSS with cascade layers**, no Tailwind | 09 §1. |
| 6 | **Interface language** | **English UI, German tag names** (as in the old app) | All UI strings go through Django i18n from day one, so a German UI for students can follow without rework. |
| 7 | **Leader key** | **`Space`** | 02, 08 as written. |
| 8 | **Vim keys** | **On**: `h j k l` by default, arrows always bound too | 08 as written. |
| 9 | **Mobile** | **Ignored for now**: desktop and laptop only | 03 §7: no phone or tablet layouts. The training screen still uses the large size variant (`lg`). |
| 10 | **Project name** | **Spaced Positions**; console command **`spos`**; Python package `spaced_positions` | Folder `spaced-positions/`, data folder *Spaced Positions*, pack files `.sppack`. |
| 11 | **Hints and SRS** | **A hinted puzzle counts as missed** | 04 · Train, 08 as written. |
| 12 | **Pipeline boards** | **Dropped for now** | Status facets and saved queries in the Library cover it (see *Out of scope*). |
| 13 | **Distribution** | **The app is free**, published under GPL-3.0. Own training first, then students. **Puzzle packs are only given to the user's students** and are not part of the app. | GPL dependencies are fine (09 §13); the licence check in CI keeps everything GPL-compatible. Packs get a licence, personalised exports and an export log (09 §12). |
| 14 | **Ease of use** | **Jupyter-style start**: one console command, or a double click, starts the app and opens the browser | 09 §11. Students never see a terminal, a migration or a settings file. |
| 15 | **GPL dependencies** | **Accepted**: python-chess and Stockfish are used freely, since the app itself is GPL-3.0 | No swap needed, but chess code still goes through one module for structure. |
| 16 | **Student onboarding** | **Starter pack + import**: a small public-domain starter pack on first run, *import a pack* as the second choice on the first-run screen | Phase 8 (first-run screen, starter pack from CC0 sources). |
| 17 | **Where the source lives** | **A public repository** (GitHub or Codeberg) | Meets the GPL for everyone who gets the app; also the update channel and issue tracker (09 §11 *Updates*, 09 §13 Licences page). |
| 18 | **Starter tag vocabulary** (2026-10-24) | **The old app's vocabulary**: 10 fields, 205 German tags with English names and the motif hierarchy, built in from phase 4 | 11 §1 Tags. Read once from the old database (read-only) into a data file in the repository; phase 7 needs no tag mapping. |
| 19 | **Trash** (2026-10-24) | **Emptied by hand only** (`:trash empty`, with a confirmation); nothing disappears on its own | 11 (rules for every model). |
| 20 | **Puzzles in PGN files** (2026-10-24) | A `FEN` header with a short line and no players is imported **as a draft puzzle**; `r` in the import list puts them into training at once | 11 §4. |

## Open questions

None at the moment. Questions that come up while building go here, numbered from 21.
