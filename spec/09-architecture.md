# 09 · Architecture of the UI system

How 01–08 map onto Django + HTMX + a few small JavaScript islands. This covers only what the UI system needs. The
chess data model and the query language are in 11.

## 1 · Stack

| Layer | Choice | Why |
|---|---|---|
| Server | Django ≥ 6.0, SQLite (WAL, `transaction_mode = IMMEDIATE`), python-chess | Template partials are built into 6.0 (`{% partialdef %}`), a natural fit for HTMX. python-chess is the authority on legality and the source of PGN/FEN handling. IMMEDIATE transactions take the write lock when they start, so saves that arrive together queue (20 s timeout) instead of one overwriting what the other just read. |
| Server ↔ client | HTMX 2 | Panes, sections and command results are server-rendered HTML partials. |
| Styling | Plain CSS with cascade layers (`@layer tokens, base, components, views, utilities`) | Components map 1:1 onto classes; tokens are custom properties; no build step. (Tailwind is the alternative, see 10.) |
| Board | chessground + chess.js | Exactly the lichess feel; GPL-3.0 like the app (§13); client-side legality for instant moves. |
| Our JS | Vanilla ES modules, no framework, no bundler (import maps) | Target ≤ ~3,000 lines in total, split into the islands below. |
| Engine | Stockfish WASM in a Web Worker by default; the local binary through the server when configured in Settings → Engine | No setup needed by default; the native binary is stronger and deeper when installed. |
| Deployment | Local, one copy per person (you, each student), no login; started like Jupyter (§11) | UI-state models keep a `user` field anyway, so hosting later needs no redesign. |
| App server | waitress (pure Python, macOS/Windows/Linux) + WhiteNoise for static files | `runserver` is for development only; the launcher needs a real server with no compiler or extra system packages. |
| Tests | pytest + Django test client, Playwright (journeys, screenshots), a small JS unit-test runner | 07 §8. |

## 2 · Page structure

There is **one document**: the shell. Modes and panes are fragments.

```
GET /analyse/p123           → full shell: app bar, status line, the Analyse workspace with its panes rendered
                              server-side in one response (no request waterfall on first paint)
␣ t (first time)            → hx-get /m/train/workspace       → swaps into #ws-train, other workspaces hidden
␣ a (back)                  → no request: #ws-analyse is shown again (kept alive, 03 §6)
:vsplit engine              → layout.js inserts a pane, hx-get /v/engine?group=A&subject=p123&node=4517
step to the next move       → no request for the board and the moves cursor; inspector re-fetches its partial
                              (debounced 100 ms); engine island restarts on the new FEN
```

- **URL routes**: `/<mode>/<subject?>` for full pages (deep links, reloads), `/m/<mode>/workspace` for a mode's
  workspace fragment, `/v/<view>` for a pane's view fragment, `/cmd/<command-id>` for server commands.
- `hx-push-url` only on mode and subject changes (03 §6 *URLs*).
- Every view fragment is a **template partial** of its view template, so the same template renders the full page and
  the fragment.

## 3 · Client runtime (our JS)

| Module | Responsibility | Approx. size |
|---|---|---|
| `core/context.js` | The context object (02 §5), a tiny event bus (`subject:change`, `cursor:change`, `layer:change`) | 150 |
| `core/keys.js` | Key events → bindings: layout-aware matching, sequences, resolution order, which-key, key flash, teach-keys tips | 500 |
| `core/commands.js` | Loads `commands.json`, evaluates `when`, runs client handlers, sends server commands, optimistic updates, undo/repeat | 350 |
| `core/layout.js` | Split tree, gutters, focus, maximise/collapse, link groups, pane drag, persistence | 500 |
| `core/cmdline.js` | Command line + finder (`␣ f`): fuzzy matching, argument completion, history | 300 |
| `core/hints.js` | Hint layer labels | 100 |
| `islands/board.js` | Wraps chessground + chess.js; layers (play, setup, entry; solving in phase 2); drawings, square tool; the PGN/FEN view | 500 |
| `core/lines.js` | The line a board or link group shows (start, moves, ply, drawings); undo; saved with the mode's UI state. In Analyse the analysis tree owns the line (a *delegate*: moves, stepping, drawings and loading go to it) | 230 |
| `core/analysis.js` | Analyse: the tree of each link group in the browser, the cursor, the Moves and Inspector panes, every `analysis.*` command, the journal on the undo stack, the subject saved per tab and on the server | 600 |
| `core/san.js`, `core/keyname.js` | Pure helpers (typed-move matching, key normalisation), unit-tested with node | 120 |
| `core/paste.js` | Paste detection and the offers in the status line | 150 |
| `core/islands.js` | Mounts `[data-island]` elements when a workspace renders or a pane arrives | 30 |
| `islands/train.js` | Session runner: states, queue in batches, judging moves against the solution tree, clock, combo, lives, attempts in the background, pause, result | 600 |
| `core/library.js` | The Library: QueryBar (completion, problems, live count), results in three displays, collections, bulk commands with undo (the server's inverse is replayed, never the client side), the filter pane; `:tag` targets in Analyse and Train | 450 |
| `core/collect.js` | Collect's entry session (source, page, number, title pattern, tags, presets, ready), save & next, duplicates, pasting into Collect | 250 |
| `core/importer.js` | The PGN import list (from a paste or a file) | 160 |
| `core/charts.js` | Stats: loads the sections, the chart cursor and read-out, table view, period, drill-down; Home's commands; announcing achievements once | 170 |
| `islands/graphs.js` | The eval graph and the variation graph, drawn from the analysis tree | 150 |
| `core/confirm.js` | A one-key question in the status line (`y / n`, `m / s`) | 20 |
| `core/engine.js` | Stockfish 17.1 lite in a worker (UCI, MultiPV), the Engine pane, arrows and eval bar on the boards of the line it follows; runs only while Analyse is visible. A local binary streamed by the server follows in phase 6 | 280 |

Server side, the apps are `core` (shell, layouts, UI state, server commands), `training` (positions, puzzles,
cards, sessions, scheduler), `analysis` (move trees of positions and games, journal, puzzles from the analysis, PGN
in and out) and `library` (sources, players, tags, saved queries, games; the query language `library/query.py`;
Collect's saving; the PGN importer; bulk commands in `library/commands.py`, registered through
`core.server_commands.MODULES`) and `stats` (metrics from the training tables, achievements, the Stats sections,
Home; charts as server-rendered SVG in `stats/charts.py`). Tag detection is `library/detect.py` and
`library/sequences.py` (chess-study-manager's autotagger, ported: it reproduces all 1,161 auto tags of the old
database's positions).

**Islands** attach to server-rendered markup by attribute (`<div data-island="board" data-fen="…" data-group="A">`)
on `htmx:load`, and clean up on `htmx:beforeCleanupElement`. They never render HTML that the server could render.

## 4 · Commands end to end

```
key / click / :cmd ──▶ commands.js ──▶ handler = client  → JS function, done
                                    ├─ handler = server  → POST /cmd/<id>  {args, context}
                                    └─ handler = both    → client function (optimistic) + POST
POST /cmd/<id> ──▶ Django: registry lookup → permission/when re-check → handler(request, args, ctx)
               ◀── HTML: hx-swap-oob fragments for every affected pane/section
                   + HX-Trigger: {"status": {"text": "Tagged 12 positions", "undo": "u7f3"}, "subject:change": …}
```

- The **registry** (`design/commands/*.toml` → `commands.json`) is the single source for ids,
  titles, keys and `when`. Server handlers register with a decorator: `@command("library.tag")`.
- Template tag `{% cmd "board.flip" %}` renders a KeyButton from the registry (label, icon, keycap, disabled reason,
  `data-cmd`). Clicking any `[data-cmd]` element runs the command through `commands.js`, so clicks and keys share
  one code path.
- A failed server command rolls back its optimistic change and shows the error with a retry key in the status line.
  Writes that fail because the server is unreachable go into a retry queue (status line: `⚠ 1 not saved · r retry`).

## 5 · Undo: the command journal

- Analysis changes (phase 3) are journaled as **snapshots**: `JournalEntry(user, label, position, before, after,
  undone)` holds the position's tree (every node with its id, comment, symbols, mark, drawings) and its puzzles'
  setup before and after the change. Undo restores `before`, redo `after`, by comparing node ids, so nodes keep
  their ids and puzzles stay linked; puzzles made after the snapshot are deleted on undo unless they were trained
  (then they only leave training: attempts are never deleted, `Attempt.card` is `PROTECT`). A new change drops the
  undone entries (the redo chain ends). The client puts each entry on its undo stack, and on load the last 50
  entries come back from `GET /journal/`, so `u` works after a reload.
- Library commands (phase 4) store an **inverse** instead (a command id + args that reverts it, e.g.
  `library.untag {ids, tag}`): bulk changes are too big for snapshots. `u` runs the inverse of the latest not-undone
  entry, `U` re-runs the original. Bulk commands are one entry.
- Client-only state (layout, folds) has its own small undo stack in memory.

## 6 · Link groups

- A link group is a client-side record `{id, subject, cursor}`. Panes subscribe by `data-group`.
- On `cursor:change` panes update **locally when they can** (board from the node's FEN, the moves cursor by
  `data-node`), otherwise re-fetch their fragment with `hx-get … hx-sync="this:replace"` (only the latest request
  wins, so fast stepping never queues requests).
- For Analyse, the subject's move tree is sent once as JSON (`GET /analysis/<id>/`: every node with parent, order,
  SAN, FEN, symbols, mark, drawings) so stepping through moves needs no requests at all. Every change
  (`POST /analysis/<id>/play|line|edit|delete|promote|reorder|position|replace|puzzle/`) answers with the whole tree,
  the move tree as HTML for the Moves pane and the journal entry; the Inspector is a fragment fetched for the move
  under the cursor (debounced, never replacing a comment being written).

## 7 · Training hot path

Nothing in the solve → next loop waits for the network.

1. Starting a session returns the session id and the first **10 puzzles** as JSON (FEN, side, prompt, solution tree
   with all accepted moves and answer lines, card ids).
2. `train.js` validates moves against the solution tree locally, plays answers, runs the clock and the combo.
3. Each attempt is posted in the background (`fetch` with `keepalive`); the server updates the schedule and the stats.
4. When fewer than 5 puzzles are left, the next batch is fetched in the background. Storm order (easy → hard) is
   decided by the server per batch.
5. The result screen is rendered by the server from the stored attempts (the source of truth), and the client shows
   its own numbers until it arrives.

## 8 · UI state persistence

| Model | Contents |
|---|---|
| `UIState(user, mode)` | layout tree JSON, subject (the lines of the boards; in Analyse the position, cursor and subject list of each link group), collapsed sections, last launcher choices |
| `NamedLayout(user, name, mode, tree)` | `:layout save` |
| `Preferences(user)` | settings (07 §5) as validated JSON; export/import as TOML |
| `Theme(user, name, extends, tokens)` | user themes |
| `KeymapOverride(user, keys, command, args, context)` | user bindings |
| `Draft(user, target, text)` | text left with `Esc` |

Writes are debounced (500–600 ms) POSTs, flushed with `keepalive` when the page goes away. On load the shell renders
from `UIState`, so the first paint is already the right layout. The Analyse cursor is also kept in the tab's
`sessionStorage` (written at once), so a reload right after a step returns to the same move.

## 9 · Template building blocks

- `templates/components/<name>.html`: one file per component from 05, with partials for its parts. Rendered through
  inclusion tags: `{% pane view="moves" n=3 group="A" %}`, `{% section "Tags" key="t" summary=… %}`,
  `{% keycap "␣ w v" %}`, `{% cmd "board.flip" display="compact" %}`.
- `templates/views/<view>.html`: one per view, using only components.
- `templates/modes/<mode>.html`: the default layout of the mode (as data) + mode-level partials (launcher, result).
- `/_ui/` renders every component from fixtures (07 §8).
- (Optional) `django-cotton` gives HTML-like component syntax (`<c-pane view="moves">`) if inclusion tags get
  awkward. Decide after building the first ten components.

## 10 · Performance practices

- Server fragments target < 80 ms: select only the columns needed, prefetch tags, cache rendered MiniBoards (SVG by
  canonical FEN + theme hash).
- `hx-sync` on every pane so fast keys never pile up requests; `hx-trigger="… delay:100ms"` for previews.
- Lists over 200 rows are virtualised (rows rendered by the server in pages of 100, swapped in on scroll).
- No layout shift: skeletons have the content's size; fonts are self-hosted with `font-display: swap` and fixed
  metrics.
- Prefetch the likely next view: hovering a ModeTab or holding `␣` prefetches mode workspaces not yet loaded.

## 11 · Starting the app (Jupyter-style)

The goal: a student double-clicks an icon, or types one command, and the app opens in the browser. Nobody sees
migrations, settings files or a Python environment.

**Install**
- Console users: `pipx install spaced-positions` or `uv tool install spaced-positions` (one isolated environment, one
  command on the PATH).
- Everyone else (phase 8): a **double-click installer** per platform (macOS `.dmg` with an `.app`, Windows `.exe`)
  that bundles Python, built with PyInstaller or Briefcase in CI. No Python install needed.

**`spos`** (the command, and what the double-click runs):
1. Finds the **data folder** (below) and takes a lock. If an instance is already running, it only opens the browser
   at that instance and exits, like a second `jupyter notebook`.
2. Backs up the database if migrations are pending, applies them, seeds what is missing (tag vocabulary, starter
   pack on first run).
3. Starts waitress on `127.0.0.1` on a free port (default 8765, else the next free one).
4. Opens the default browser at `http://127.0.0.1:<port>/?token=<random>`. The token is exchanged for a cookie and
   removed from the URL. Requests without the cookie get a "start the app from its icon" page. This stops other local
   programs and web pages from reading or changing the data. The `Host` header is checked against `localhost` and
   `127.0.0.1` to block DNS rebinding.
5. Prints the URL (with token) to the console and keeps running. `Ctrl+C` stops it.

| Option | Does |
|---|---|
| `--no-browser` | Don't open a browser |
| `--port N` | Use this port |
| `--data-dir PATH` | Use another data folder (e.g. a synced folder, a USB stick) |
| `--lan` | Listen on the home network too (e.g. a second computer). Token required. |
| `spos stop` / `spos list` | Stop the running instance / show where it runs |
| `spos import-csm <db.sqlite3> [--dry-run]` | Bring over a chess-study-manager library (phase 7, 11 §6): reads a copy, backs up first, adds only what is new |

**Stopping without a console** (double-click start): `:quit` (also in Settings → App) stops the server. The server
also stops by itself 10 minutes after the last open tab stopped sending its heartbeat (setting, default on for
double-click starts, off for console starts).

**Data folder**: the platform's user-data folder (`~/Library/Application Support/Spaced Positions/` on macOS,
`%APPDATA%\Spaced Positions\` on Windows, `~/.local/share/spaced-positions/` on Linux). It holds `db.sqlite3`, `backups/`
(before every migration + a daily rotating backup, keeping 14), `exports/`, `packs/` and `engine/`. It is never
inside the install folder, so updates and reinstalls never touch user data. Settings → App shows it, with *open
folder* and *back up now*.

**Updates**: an opt-in check at start shows `update 1.4 available` in the app bar's pulse area with a link. Updating
is reinstalling. Data stays, and migrations run with a backup on the next start.

**Offline**: everything (fonts, pieces, Stockfish WASM, icons) is bundled. The app needs no network after install.

## 12 · Puzzle packs (sharing between coach and students)

Each person has their own database, so material moves between them as files. The app is free for everyone. **The
packs are the coach's own material**, made for their students and not for publication.

- A **pack** (`.sppack`) is a zip: `manifest.json` (format version, title, author, description, licence, created,
  pack id) + positions, puzzles (solution trees, answer lines), tags and sources as JSON, plus a PGN copy for other
  tools.
- **Every object has a UUID** next to its database id, from day one. Packs, re-imports and the later migration
  depend on it.
- **Export**: from a Library selection or a saved query (`e` → *Pack*), or `:pack export`. Training history is
  never included.
- **Import**: drag the file onto the app, paste it, or `:pack import`. A preview lists what is new, what is a
  duplicate (canonical FEN) and which tags are unknown (mapped by key, or created as free tags). `↵` imports.
  The pack becomes the **source** of its positions, so `source:` filters and training filters work on it.
- **Re-importing** a newer version of the same pack updates its content and keeps the student's cards and history.
- Later: a **progress report** file (`.spreport`, export from Stats) a student can send to their coach, with
  retention, mastery and weak motifs. No server needed.
- Starter content: the lichess puzzle database is published under CC0, so public-domain starter packs by motif are
  possible (check its terms again before bundling).

**Keeping packs with the students they're for.** The app is open source and runs on the student's computer, so no
technical measure can *stop* a student from passing a pack on: whoever can open a pack can read its contents.
Encryption or DRM would only add hassle for real students. The spec therefore relies on clear terms, plus
traceability:

| Measure | What it does |
|---|---|
| **Pack licence** in the manifest (default for new packs: *personal use by the named student, do not share*) | Shown in the import preview, which the student confirms, and on the pack's source page |
| **Personalised export**: `:pack export for <student>` | Writes the student's name into the manifest and a per-copy id. The app shows *"from <coach> for <student>"* on the pack's source page and in the Feedback line under each puzzle. A shared copy shows who it came from. |
| **Coach's export log** | Settings → Packs lists which pack version went to which student and when, so updates go to the right people |
| *(optional)* password on the pack file | Protects the file in transit (email, cloud folder). The student enters it once on import. Not a protection against the student. |

Puzzles from a personalised pack can be trained, tagged and analysed like any other, but a pack export by the
student leaves them out by default (`--include-received` to override), so packs don't spread by accident.

## 13 · Licences

The app is **given away for free** and published under **GPL-3.0** (10 · decision 13). That fits the dependencies the
app needs most, which are GPL themselves (chessground, python-chess, Stockfish). Anyone who receives the app may
also get its source, change it and pass it on. The **puzzle packs are separate**: they are content, not part of the
program, and their licence is set by their author (§12).

| Dependency | Licence | Status |
|---|---|---|
| Django, HTMX, waitress, WhiteNoise, platformdirs | BSD / 0BSD / ZPL / MIT | fine (GPL-compatible) |
| chessground, python-chess | GPL-3.0 | fine under the app's GPL-3.0 |
| Stockfish (native and WASM) | GPL-3.0 | fine; shipped with its licence and source as usual |
| chess.js, Bootstrap Icons | BSD-2 / MIT | fine |
| Fonts (Inter, JetBrains Mono, IBM Plex, Noto) | SIL OFL | fine |
| Piece sets | vary per set | Prefer sets under free licences (GPL, CC BY, CC BY-SA, CC0). Non-commercial sets (CC BY-NC-SA) only as an optional download, so that anyone may redistribute the app itself. Each set's licence lives next to it (07 §6). |
| Lichess puzzle database | CC0 | fine for starter packs |

`design check` gets a **licence check**: Python and JS dependencies are compared to an allowlist of GPL-3.0-compatible
licences (MIT, BSD, Apache-2.0, ISC, 0BSD, ZPL, LGPL, GPL-2.0+/3.0, OFL for fonts, CC0/CC BY/CC BY-SA for assets).
Anything else fails CI unless it is a documented exception in this table. A **Licences** page in Settings → App lists
every bundled component and its licence, and links the app's source. (This is an engineering summary, not legal
advice.)
