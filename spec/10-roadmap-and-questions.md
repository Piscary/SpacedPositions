# 10 · Status, roadmap and decisions

## Status (version 0.1)

Built, with tests (pytest, Playwright journeys with the axe accessibility check, node tests for the JavaScript):

| Area | What is there |
|---|---|
| Shell | Modes, panes and splits, link groups, named layouts, the command registry, layered keys with which-key, the command line with completion, hint labels, help, undo of layout and settings, the style guide (`:ui`, development only) |
| Board | chessground with legal moves, drawings, the square tool, typed moves (English, German, French or Italian letters), the board editor with live checks and one-key fixes, paste detection (FEN, PGN, lichess links), MiniBoards, 12 free piece sets and the user's own |
| Train | Review (spaced repetition from solved / missed), Storm with an adaptive clock and combos, Streak with lives and blind, weakest motifs, custom sessions filtered by a Library query, result screens, stopping a session at any time |
| Analyse | Book-style move tree, variations, comments, annotation symbols, marks and colours, the Inspector, Stockfish in the browser or a local engine, eval and variation graphs, key moments, puzzles set up from the analysis, an undo journal that survives reloads |
| Library + Collect | Positions, games, puzzles, players, sources, tags; the query language with completion; table, list and grid; filters; bulk tagging, training, trash; editing tags, sources and players; tag detection for 205 motifs; rapid entry from a book; PGN import of any size; PGN export |
| Stats | Pattern library, card stages, retention, mastery, weak spots, robustness, records, activity, collection, achievements; every number drills down |
| Settings | Themes and the user's own, tokens, the keymap editor, settings as one TOML file, custom CSS, languages, licences |
| Packs | Export (selection or query, positions, puzzles and games, personal copies, versions, the export log), import with a preview, updates that keep the receiver's training (09 §12); the starter pack: 748 lichess puzzles (CC0) by motif in four rating bands, shipped with the app and offered on the first-run screen (`manage.py starter` builds it again) |
| Languages | English, German (Swiss spelling), French, Italian; tag names in the four languages (09 §14) |
| Distribution | `spos` (pipx), the double-click apps for macOS and Windows built by the release workflow, daily backups, auto-stop, the opt-in update check (09 §11) |

Performance (09 §10): every page answers in under 200 ms with 50,000 positions; a pack holds about 60 bytes a
position.

## Next

The way ahead is in milestones with goals that have to be met before the next step (13 §6): **M0** the test group
(14), **M1** a public beta, **M2** course packs with licences, **M3** a marketplace pilot, **M4** open to coaches.

**Before the test group (M0):**

- `:test-report` (a usage report with counts only, written on request) and `:feedback` (opens the feedback form with
  the version and the mode), 14 §5.
- Release builds tested on clean macOS and Windows accounts: install, first puzzle, an update with the data kept.
- A tester note, the surveys and the feedback log (`docs/testing/feedback-log.csv`).

**For the public beta (M1):** packs and books as collections (12 §2–4: where a puzzle comes from, training one
collection, stats per collection), what the test group asks for, and:

- **Signing** the apps (Apple Developer ID, a Windows certificate), so the first open needs no extra step.
- **Third-party sources with each release**: the release workflow attaches the apps; the sources of the bundled GPL
  components (chessground, stockfish.js, python-chess) are linked from the notices. Attaching them to each release
  as an archive would make the release self-contained (GPL-3.0 §6).
- **Progress reports**: a file a student can send to a coach (retention, mastery, weak motifs), no server needed.
- **Password on pack files** (09 §12): protection in transit only; left out until someone needs it.
- Review of the French and Italian translations by native speakers (`manage.py i18n missing` lists new texts).
- **Publishing on PyPI**, so the Python install is `pipx install spaced-positions` (today it installs from GitHub).

**Later (M2–M4):** the composition of a pack and the good-citizen checks (12 §5–6), pack format 2 with licences and
signatures (13 §2), the review process (13 §4), the marketplace (13 §5).

## Out of scope for now

- **Publishing** (documents, print, PDF). The diagram renderer is shared, so it can come later as its own mode.
- **Pipeline boards** (Trello-style stages): status facets and saved queries in the Library do that job. Could come
  back as a Library display (`␣ u v` → board).
- Playing games against the engine or online.
- **Phone and tablet layouts** (decision 9).
- **Hosted / synced multi-user** (accounts, a coach seeing students' progress online). Everyone runs a local copy
  and shares material through puzzle packs (decision 2).
- Payments, licence keys, a shop: the app is free (decision 13).

## Decided

| # | Question | Decision | Consequence in the spec |
|---|---|---|---|
| 1 | **Keyboard layout** | **QWERTY** (US/intl) | Defaults are designed and tested on QWERTY. Matching stays layout-aware (02 §4); the AltGr check in the lint is a warning, not a failure (07 §8). |
| 2 | **Local or hosted** | **Local first.** Each person runs their own copy with their own database. No login. Material moves as **puzzle packs**. | 09 §8 (models keep a `user` field, so hosting later needs no redesign), 09 §11 launch, 09 §12 packs. |
| 3 | **Board library** | **chessground** | 06 §9. |
| 4 | **Engine location** | **Both**: Stockfish WASM in the browser by default, the local binary through the server when configured | 06 §7, 09 §1. |
| 5 | **CSS approach** | **Plain CSS with cascade layers**, no Tailwind | 09 §1. |
| 6 | **Interface texts** | Every text through Django's i18n (templates, Python) and the page's catalogue (JavaScript) | See decision 21. |
| 7 | **Leader key** | **`Space`** | 02, 08 as written. |
| 8 | **Vim keys** | **On**: `h j k l` by default, arrows always bound too | 08 as written. |
| 9 | **Mobile** | **Desktop and laptop only for now** | 03 §7: no phone or tablet layouts. The training screen still uses the large size variant (`lg`). |
| 10 | **Project name** | **Spaced Positions**; console command **`spos`**; Python package `spaced_positions` | Data folder *Spaced Positions*, pack files `.sppack`. |
| 11 | **Hints and SRS** | **A hinted puzzle counts as missed** | 04 · Train, 08 as written. |
| 12 | **Pipeline boards** | **Dropped for now** | Status facets and saved queries in the Library cover it (see *Out of scope*). |
| 13 | **Distribution** | **The app is free**, published under GPL-3.0. **Puzzle packs are content**, made and shared by their authors, not part of the app. | GPL dependencies are fine (09 §13); the licence check in CI keeps everything GPL-compatible. Packs get a licence, personalised exports and an export log (09 §12). |
| 14 | **Ease of use** | **Jupyter-style start**: one console command, or a double click, starts the app and opens the browser | 09 §11. Nobody needs a terminal, a migration or a settings file. |
| 15 | **GPL dependencies** | **Accepted**: python-chess and Stockfish are used freely, since the app itself is GPL-3.0 | Chess code still goes through one module for structure. |
| 16 | **Onboarding** | **The starter pack** (public domain, by motif), **import a pack** or collect from a book, from the first-run screen | 04 · Home (first run); 09 §12 *Starter pack*. |
| 17 | **Where the source lives** | **A public repository** | Meets the GPL for everyone who gets the app; also the update channel and issue tracker (09 §11 *Updates*, 09 §13). |
| 18 | **Tag vocabulary** | **Built in**: 10 fields, 205 tags with German, English, French and Italian names and the motif hierarchy | 11 §1 Tags; `library/data/tags.json`. |
| 19 | **Trash** | **Emptied by hand only** (`:trash empty`, with a confirmation); nothing disappears on its own | 11 (rules for every model). |
| 20 | **Puzzles in PGN files** | A `FEN` header with a short line and no players is imported **as a draft puzzle**; `r` in the import list puts them into training at once | 11 §4. |
| 21 | **Languages** | **English, German, French and Italian** (the main audience is in Switzerland: Swiss German spelling with *ss*, Swiss number formats). Automatic follows the browser. Tag names follow the app or a language of their own. | 09 §14. |

## Open questions

None at the moment.
