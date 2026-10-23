# 10 · Roadmap and open questions

## Build order

Each phase ends with something usable and with its components in the `/_ui/` style guide.

| Phase | Builds | Done when |
|---|---|---|
| **0 · Foundation** | Token pipeline (`design build/check`), 2 themes (`paper`, `ink`), shell (AppBar, StatusLine), command registry, `keys.js` (layers, sequences, which-key, flash), CommandLine, Pane/Split/Gutter/Section, focus model, `/_ui/` gallery, **the `spos` launcher** (09 §11: one command starts the server and opens the browser), CI with lint + screenshots | You can split, focus, resize, collapse and close panes with keys and mouse in the style guide; every key shows up in which-key and the command line; `spos` opens it in the browser |
| **1 · Board** | Board island (play, drawing, setup, move entry), MiniBoard renderer, FEN/PGN copy-paste detection | Board parity with lichess for moving and drawing; paste anything anywhere works |
| **2 · Train** | Puzzle/card model, scheduler, Launcher, Solving, Feedback, Result, Storm/Streak/Review, training hot path | A full Storm and a Review run without a single blocking request; keyboard journey test passes |
| **3 · Analyse** | MoveTree, Inspector, EngineLines/EvalBar, link groups, puzzle setup from the analysis, undo journal | The old app's analysis workflow is possible keys-only |
| **4 · Library + Collect** | QueryBar and search language, List/Table/CardGrid, selection + bulk, filters, rapid entry, PGN import | Find → select → tag → train in under 10 keystrokes |
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

All decisions were taken on 2026-10-23.

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

## Open questions

None at the moment. Questions that come up while building go here, numbered from 18.
