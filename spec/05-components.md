# 05 · Component catalogue

Every screen is built from these components and nothing else. A new need means a new variant or a new component in
this list, plus its gallery entry (07 · Living style guide). Component names are used 1:1 in templates
(`components/pane.html`) and CSS (`.pane`, `.pane--focused`).

**Conventions for every component**
- Colours, sizes, radii and timings come from tokens only (07). No literal values in component CSS.
- Interactive components call **commands** (02 §3) and display their key. They never bind keys themselves.
- States are classes or `aria-*`/`data-*` attributes: `--focused`, `--selected`, `--disabled`, `--loading`,
  `aria-expanded`, `aria-pressed`, `data-cursor`. Tokens style them consistently.
- Size variants: `sm` (20px rows), `md` (24px, default), `lg` (32px, the training screen).

---

## A · Shell

| Component | Purpose | Anatomy | Notes |
|---|---|---|---|
| **AppBar** | Mode switcher + pulse | logo · ModeTab × n · Pulse items · settings · help | 28px. Hidden in fullscreen training. |
| **ModeTab** | One mode in the app bar | label · Keycap (`␣t`) · optional count badge | `--active`. Click = command `mode.train`. |
| **StatusLine** | Always-visible state (03 §1) | ModeBlock · LayerBlock · PendingKeys · PaneRef · SubjectRef · MessageSlot · ActivitySlot · help hint | 22px. MessageSlot holds results, undo hints, inline confirmations. |
| **LayerBlock** | Current layer | text in the layer's colour | Colour tokens `layer-normal`, `layer-insert`, ... |
| **CommandLine** | `:` palette | prompt · input · ResultList (fuzzy, with Keycaps and *when* reasons) · argument hint | Overlays the bottom of the workspace. |
| **WhichKey** | Next keys after a prefix | grid of `key → title` in columns, grouped | Opens with no delay. Width = workspace. |
| **HintOverlay** | Labels on clickables (`F`) | small label chips positioned over targets | Labels are home-row first (`a s d f j k l ;` …), 2 letters when needed. |
| **HelpOverlay** | `?` | grouped key tables, search | Over the focused pane only, not the whole screen. |
| **Toast** | Rare, for events outside the current focus (import finished, milestone) | icon · text · 1–2 KeyButtons · auto-dismiss | Top-right of the workspace, max 3. Most results go to the StatusLine instead. |
| **Confirm** (inline) | Rare yes/no | question in MessageSlot · `y` / `n` | No modal dialogs exist in the system, except Dialog below. |
| **Dialog** | Last resort for a form that cannot live in a pane (first-run setup) | header · body · ActionBar | Centred, max 560px, traps focus. Avoid. |

## B · Layout

| Component | Purpose | Anatomy | States / variants |
|---|---|---|---|
| **Workspace** | The layout area of one mode | Split tree | One per mode, hidden when the mode is not active (03 §6). |
| **Split** | Two or more children with ratios | children · Gutter(s) | `--row` / `--column`. |
| **Gutter** | Resize handle | 1px rule + 4px hit area | hover/drag: accent rule. Snaps (03 §3). |
| **Pane** | The only container | PaneHeader · body (a View) · PaneFooter? | normal · focused · collapsed (rail) · maximised · loading · empty · error. |
| **PaneHeader** | Identity + local actions | number · view name · SubjectRef · LinkBadge · KeyButton (compact) × ≤4 · window buttons | 24px. Inverted when the pane is focused. Drag handle. |
| **PaneFooter** | Key strip or view status | KeyHint × n, or text | Optional, `␣ u k`. |
| **Rail** | A collapsed pane in a row split | vertical title · number | 24px wide. Click or focusing it (`␣` + its number) restores it. |
| **LinkBadge** | Link group / pinned | `⛓ A` in the group colour, or `⊙` | Click cycles group. |
| **Section** | Collapsible group inside a pane | SectionHeader · body | expanded · collapsed (shows summary) · pinned-open. |
| **SectionHeader** | — | caret · title · summary/count · `g`-key · right-aligned KeyButtons | 22px. |
| **PaneTabs** | Several sub-views inside one pane (Library collections) | Tab × n with digit Keycaps | Digits `1`–`9` within the pane. |
| **Stack** | Vertical rhythm inside a pane | children with token gap | `gap-1` … `gap-4`. |
| **Columns** | Fixed sub-columns inside a pane (e.g. a form with label/value) | — | Collapses to one column under 360px pane width. |

## C · Actions

| Component | Purpose | Anatomy | Variants / states |
|---|---|---|---|
| **Keycap** | Shows a key | the key text in mono, 1px border, `radius-sm` | `--inline` (in text), `--on-accent`. Platform symbols (`⌘` vs `Ctrl`). Sequences render as several caps: `␣` `w` `v`. |
| **KeyButton** | The button of the system | icon? · label · Keycap | Variants: `primary` (one per pane at most), `secondary` (default), `ghost` (in headers/toolbars), `danger`. Sizes sm/md/lg. Display: `full` (icon label key), `compact` (icon key), `key` (key only, for dense toolbars). States: hover, pressed, **flash** (key pressed), disabled (with reason on hover *and* in the CommandLine). Always rendered from a command. |
| **ActionBar** | A row of KeyButtons | KeyButton × n, overflow `⋯` menu | Overflow items stay reachable by key. |
| **SegmentedControl** | One choice from 2–7 | label · segments with Keycaps | Keys either digits, or a keyboard row (`q w e r`, `a s d f`) when several controls are stacked: each control row uses one keyboard row. `h/l` move when focused. |
| **Toggle** | On/off setting | label · switch · Keycap | `aria-pressed`. |
| **Menu** | A list of commands (context menu, overflow, which-key in menu form) | MenuItem × n (icon · title · Keycap) · separators | Opens at cursor or under its button. `j/k`, `Enter`, item keys. |
| **KeyHint** | One "key → action" pair in a footer or strip | Keycap · short text | Not clickable by itself, but each one is also a command (click = run). |
| **Stepper** | Number ± | `−` · value · `+` with keys | `+`/`-` when focused (page number in Collect). |

## D · Input

All inputs put the app into the **Insert** layer while focused (02 §2). `Esc` leaves and keeps the value as a draft;
`Enter`/`Mod+Enter` submits.

| Component | Purpose | Notes |
|---|---|---|
| **TextField** | Single line | Label left or above, inline error below. |
| **TextArea** | Multi-line | Auto-grows to max 12 lines. |
| **CommentEditor** | Move/position comments | Markdown, piece symbols (`Alt+K Q R B N P`, Shift = black), drawing chips (`[[arrow:e2e4]]` shown as a coloured chip that flashes the drawing on hover/focus), object references (`p123`, `#gabel`). Preview toggle `Alt+V`. |
| **QueryBar** | Library and filter queries | Tokenises `key:value` terms into chips while typing; completion for keys and values (tags, sources, players); invalid terms underlined with the reason; result count live. The query string is the single source of truth (filters write into it). |
| **Combobox** | Choose or create one item (source, player, tag) | Type to filter, `↑↓`, `Enter` choose, `Mod+Enter` create new from the text. |
| **TagInput** | Many tags | Chips + combobox; field-limited (only motif tags) or all fields; hierarchy shown as `Gabel › Springergabel`; `Backspace` on empty removes the last chip. |
| **FenField** | A FEN | Mono, validates live (06), shows the problem inline (`castling KQ impossible: rook not on h1 · fix f`). Paste-detects lichess links. |
| **PgnArea** | PGN text | Mono, validates, shows the number of games/moves found. |
| **ColorField** | Hex colour | Swatch + hex input (`1f3a5f`, `#abc` normalised), system picker on swatch click, copy button. Contrast warning when used for text tokens. |
| **Select** | Long fixed lists (fonts) | Combobox look, no creation. |
| **Slider** | Ranges (difficulty 1–5, engine depth) | Two thumbs for ranges; `h/l` step, `H/L` big step. |
| **Checkbox** | Booleans in lists | Rarely used: prefer Toggle. |
| **FormRow** | Label · control · help · `:set` name · error | The unit of every form and of Settings. |

## E · Data display

| Component | Purpose | Notes |
|---|---|---|
| **ObjectRef** | Inline reference to any object (`p123 Polgár Nr. 102`) | Short id in mono + title; click/`Enter` opens; hover/focus shows **MiniBoard** preview after 300 ms. |
| **Chip** | A tag, a filter term, a state | Variants: `tag` (left border in the tag field's colour), `filter`, `state` (solved/missed/new). Provenance mark for detected tags (`◇` auto, `◌` suggested): what set it is shown in the Inspector, not only on hover. Removable (`×`, or `Backspace` when focused). |
| **Badge** | Small count or status | On ModeTabs, Pulse, PaneTabs. |
| **List** | Keyboard-navigable rows | Cursor row (accent bar left), selection mark (`▣`), row actions shown on the cursor row only. Virtualised over 200 rows. |
| **Table** | Dense data with columns | Sticky header, sortable columns (`s` then column key), column chooser, cursor + selection like List, right-aligned numbers, mono for ids. |
| **CardGrid** | Objects as cards | Responsive column count from pane width; cursor moves in 2D (`h j k l`). |
| **ObjectCard** | One object in a grid | MiniBoard · title · ObjectRef · Chips · 1–2 metrics; variants per object (see matrix below). |
| **PropertyList** | Key/value pairs | Two columns, labels muted; values can be inline-editable (Enter edits). |
| **Stat** (KPI tile) | One number with context | label · value (large, tabular figures) · delta (`▲ 12 vs last week`) · Sparkline? · drill-down command. |
| **Meter** | Progress towards a goal | bar · current/target · label (`212 / 250`) · optional projection tick. |
| **StageBar** | Distribution over stages (new/learning/young/mature) | Stacked horizontal bar with legend; each segment is a drill-down. |
| **Ladder** | Mastery level | 6 steps (Learning → Master), current filled, what the next needs as text. |
| **Timeline** | Ordered events (milestones, activity log, undo list) | Date column · event · ObjectRefs. |
| **EmptyState** | A view with no content | One sentence + 1–3 KeyButtons. No illustration. |
| **Skeleton** | Loading placeholder | Same geometry as the content. Shown only after 300 ms. |
| **InlineMessage** | Info / warning / error inside a pane | Icon · text · KeyButton? |
| **Kbd table** | Keys reference (Help) | Groups of Keycap · description. |

## F · Chess

Details of the board's behaviour are in 06. These are the visual components.

| Component | Purpose | Notes |
|---|---|---|
| **Board** | The interactive board | Sizes: `fill` (fit pane, square), `md`, `sm`. Layers: play · setup · entry (06). Overlays: last move, check, legal-move dots, selection, drawings (arrows, circles, squares in 4 colours), engine arrows (fading by rank), annotation badges on squares, hint highlight, result flash (good/bad). Frame colour shows the board layer (setup = indigo, variation = amber, solving = none). |
| **MiniBoard** | Static small board | Server-rendered SVG (python-chess renderer) as an `<img>`: `{% miniboard fen size=120 %}`. Its URL carries a hash of the theme's square colours, so it is cached forever and switching the theme only swaps URLs. 64–256px; used in cards, previews, hover. No JS. |
| **Diagram** | Static board for print/export | Same renderer as MiniBoard, any size, with caption. (Publishing is out of scope for now; the renderer is shared.) |
| **EvalBar** | Engine evaluation next to the board | Vertical, white/black split, value label, mate shown as `M3`. Click = toggle engine. Hidden while solving. |
| **EngineLines** | Best lines | Per line: eval · depth · moves (each move an ObjectRef-like token: click adds the line up to it). Header: engine name, depth, nodes/s, settings ⚙. |
| **MoveTree** (book style) | The analysis as text | Main line as flowing text, variations as indented blocks with letters (A, B …) and their mark colour as left border, comments in place, move tags as small chips after the move, NAG glyphs, fold carets. Cursor = current move (accent background); path to the cursor tinted. Puzzle markup: start framed, solver moves underlined, answer lines dotted, draft pale. |
| **MoveTable** (columns) | Compact two-column move list (like lichess) | For games and for small panes; variations shown as an expandable row under their move. Switch with `␣ u m`. |
| **VariationGraph** | The move tree as a graph | Nodes = moves (dot coloured by mark, size by subtree), edges = continuations; main line horizontal, variations branch below. Cursor shared with MoveTree. Good for seeing the shape of a big analysis and the puzzle's answer lines at once. Read-only; `h j k l` navigates. |
| **EvalGraph** | Evaluation over a game or a position's main line | Area chart centred on 0 (white above), clipped at ±5; mistakes marked (`?`, `??` and drops of 1.5 or more: dots); click to go to a move, the analysis keys move the cursor. Shared cursor with the board. The values come from `:evaluate` (the engine over the main line, stored per move). |
| **MoveInput** | Typed move entry | Inline field on the board footer; live candidate preview as an arrow; ambiguity list (`Nbd2 / Nfd2`); English and German letters. |
| **SetupPalette** | Board editor pieces | 6 pieces × 2 colours + eraser + hand; keys `1`–`6`, `c` colour, `x` eraser; shows what a click places now. |
| **PositionMeta** | Side to move, castling, en passant, move number | Compact controls under the board in Setup; each with a key. |
| **PuzzlePrompt** | What to do | `White to play` · objective (`Mate in 2`) · optional task text. Large in Train, small in previews. |
| **SolveFeedback** | Result of an attempt | ✓/✗ · time · schedule change (`next in 9 days`) · solution line · Chips · actions. Colours `good`/`bad`, never colour alone (icon + word). |
| **Clock** | Storm timer and per-puzzle time | Large tabular digits; shows each change (`+4.1s`, `−10s`) for 800 ms. Warning colour under 30 s. |
| **ComboMeter** | Storm combo | Level (×1…×5), progress to the next level, what a right answer is worth. |
| **Lives** | Streak lives | `♥ ♥ ♡`. Losing one: 300 ms shake (reduced-motion: colour only). |
| **MaterialBalance** | Captured pieces / imbalance | `+2 ♗♙`, next to the board edge. Optional. |
| **NagPicker** | Annotation symbols | `!  ?  !!  ??  !?  ?!  □` with keys `1`–`7` directly; the full set (position and evaluation symbols `+−  ±  =  ∞` …) in the `a` menu. Shifted digits are not used: they give different characters on QWERTY and QWERTZ. |
| **MarkPicker** | Good/dubious/bad/colour | Keys `m g`, `m d`, `m b`, `m c`, `m x`. |
| **PlayerRef**, **ResultBadge**, **EcoLabel** | Game metadata | `@tal`, `1-0` / `½` / `0-1` coloured from the subject's perspective, `B90 Najdorf`. |

## G · Charts

Charts are **server-rendered SVG** with tokens as colours (no chart library; `stats/charts.py`). Interaction (cursor,
read-out) is one small shared JS island (`core/charts.js`) that reads the points from the figure's `data-points`.
The EvalGraph and VariationGraph are the exception: they are drawn in the browser (`islands/graphs.js`) from the tree
Analyse already has, so they follow the cursor without requests.

Rules for all charts:
- A chart is focusable; `h/l` moves a cursor along the data points, the value shows in a read-out row above the chart
  (no floating tooltip needed); `Enter` drills down; `t` switches to the table view of the same data.
- Colours come from the categorical palette tokens (`chart-1` … `chart-6`) and the semantic tokens (`good`, `bad`).
  Never more than 6 categories; more are grouped as "other".
- Axes are minimal: baseline + 2–4 ticks, labels in `text-sub`. No gridlines except a faint zero line.
- Every chart has a one-line title that says what it shows and the period.

| Chart | Used for |
|---|---|
| **Sparkline** | Trends inside a Stat tile or a table row |
| **LineChart** | Pattern library over time, retention, Storm scores |
| **BarChart** (+ stacked) | Points per week, time per puzzle (result screen), cards by stage per day |
| **Histogram** | Solve times, difficulty distribution |
| **CalendarHeatmap** | Training/activity days over 53 weeks |
| **StageBar** | Card stages (also listed in E) |
| **Ladder grid** | Mastery per tag: rows = tags, columns = levels |
| **Funnel** | Collect → analysed → puzzle → mature: how material moves through the app |
| **EvalGraph**, **VariationGraph** | Chess-specific (listed in F) |

## H · Feedback and reward

| Component | Purpose | Notes |
|---|---|---|
| **Flash** | Instant confirmation of a key or a result | 100–150 ms background pulse on the element that changed (button pressed, row tagged, board correct/incorrect). |
| **Ticker** | A number that changes | Counts up/down over 300 ms (score, pattern library), tabular figures so nothing shifts. |
| **AchievementChip** | Record, milestone, level-up | `▲ new best Storm 5′: 47` · `Pattern library 250` · `Gabel: Solid → Strong`. Shown in the result screen and once in the status line; listed in Stats → Timeline. |
| **Banner** | Milestone announcement on Home | One line at the top of a pane, dismiss with `x`. |
| **ResultScreen** | End of a session | Pattern from 04 · Train · Result; built from Stat, BarChart, List, AchievementChip. |

Sound is optional (off by default): short click on move, soft tone on correct, low tone on wrong, a chord on a record.

---

## Object × representation matrix

Every object has the same set of representations, so it looks and behaves the same wherever it appears.

| Object | ObjectRef | Row (List/Table) | ObjectCard | Detail (Inspector section) | Preview (hover / linked pane) | Default commands |
|---|---|---|---|---|---|---|
| Position | `p123 Title` | id · MiniBoard(sm) · title · tags · difficulty · solution? · source | MiniBoard · title · tags · stars | meta, tags, source, notes, puzzles | Board + prompt | `Enter` analyse · `T` train · `t` tag · `y` FEN · `d` trash |
| Game | `g12 White–Black 1956` | date · White · result · Black · event · ECO · positions | header + EvalGraph thumbnail | headers, players, positions taken | Board at final position + EvalGraph | `Enter` analyse · `y` PGN · `d` trash |
| Move | `12…Nf6` | ply · SAN · NAG · eval · tags | — | comment, tags, mark, drawings, puzzle role | Board after the move | `c` comment · `t` tag · `1–7` · `m` |
| Puzzle | `z45 Polgár 102` | start position · objective · lines · cards · status | MiniBoard · prompt · stages | solution tree, cards, stats | Board + prompt | `Enter` train · `a` analyse · `r` ready |
| Card | `c45.2` | line · stage · due · ease · accuracy | — | schedule, attempts history | Board + line | `Enter` train once · `R` reset |
| Session | `r88 Storm 5′` | date · mode · score · accuracy · time | Stat tiles | ResultScreen | — | `Enter` open result · `r` run again |
| Tag | `#gabel` Chip | name · field · count · mastery · auto/manual | — | tag editor (names, parent, weights) | Library query `tag:gabel` | `Enter` filter · `T` train · `o` edit in a split |
| Source | `s7 Polgár` | title · type · positions · last page | — | metadata, coverage (diagram numbers present/missing) | Library query `source:s7` | `Enter` filter · `c` collect from it |
| Player | `@tal` | name · role · games · score | — | records, openings, opponents | Library query `player:tal` | `Enter` games · `T` train positions |
