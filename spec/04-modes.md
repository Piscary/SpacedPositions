# 04 · Modes

Each mode below has: its purpose, its **default layout** (the user can change it, `:layout reset` brings it back),
its internal states, and its most important keys. The full keymap is in 08. Wireframes are approximate: the numbers
in pane headers are pane numbers (`␣ 1`–`␣ 9`), keycaps are written `k`.

## Objects the modes work with

| Object | What it is | Short id |
|---|---|---|
| **Position** | A FEN with tags, source, notes and a move tree (analysis). May be a *diagram* (illustration, no solution). | `p123` |
| **Game** | A PGN game with players, headers and a move tree. Positions can be taken from any of its moves. | `g12` |
| **Move** (node) | One node of a move tree: SAN, comment, annotation symbols, evaluation, mark (good/dubious/bad/colour), drawings, move tags. The root node is the starting position. | `p123/4517` |
| **Puzzle** | A trainable problem drawn from a position or a game move: start node + solution tree (correct moves, answer lines). | `z45` |
| **Card** | One answer line of a puzzle: the unit of spaced repetition, with its own schedule and history. | `c45.2` |
| **Session** | One training run (Review, Storm, Streak, custom) with its attempts. | `r88` |
| **Tag** | A label in a *field* (motif, mating pattern, objective, phase, ...), possibly hierarchical. On positions and moves. | `#gabel` |
| **Source** | A book, website, own analysis or public domain, with page/diagram numbers. | `s7` |
| **Player** | A person behind game names, with aliases and a role (me, student, role model, opponent). | `@tal` |
| **Query** | A saved library search (`motif:gabel diff:>=3 no:solution`). Usable as a training filter. | `q:name` |

---

## Home  `␣ h`

What to do now. Opens on start.

```
┌─ 1 Today ─────────────────────────────────────┬─ 2 Continue ─────────────────────────────────┐
│ ▾ Due now                                      │ ▾ Analysis   p123 Polgár 102 · 12…Nf6    a   │
│   14 reviews · 6 new         [▶ Review    r]  │ ▾ Collect    Polgár: next Nr. 103 p.41    c   │
│ ▾ Quick start                                  │ ▾ Paste FEN / PGN / link        Mod+V or p  │
│   [Storm 3′  1] [Storm 5′  2] [Streak  3]     │   ┌──────────────────────────────────────┐   │
│   [Streak ♥3  4] [Weakest motifs  5] [Again 6]│   └──────────────────────────────────────┘   │
│ ▾ Today                                        ├─ 3 Recent ───────────────────────────────────┤
│   solved 23 · accuracy 87% · streak 9 days     │  p2002  Lasker–Bauer  #opfer #läuferpaar   │
│   Pattern library  212 / 250 ▓▓▓▓▓▓▓▓░░       │  g12    Byrne–Fischer 1956                  │
│   next milestone in ~6 days                    │  p1998  ...                                  │
└────────────────────────────────────────────────┴──────────────────────────────────────────────┘
```

- `r` review, `1`–`6` quick sessions, `a` continue analysis, `c` continue collecting, `p` focus the paste box.
- **Pasting anywhere** in Home (`Mod+V`, no field needed) detects FEN / PGN / lichess link / list of FENs and offers
  the matching commands in the status line: `Analyse a · Collect as position c · Import game g`.

---

## Train  `␣ t`

The heart of the app. Four states. (As built in phase 2: one layout, Board + Session; the Session pane shows the
launcher, the heads-up display while solving, the feedback and the result, and the board follows the result list.
The app bar hides while solving and during feedback.)

```
Launcher ──Enter/key──▶ Solving ──answer──▶ Feedback ──Enter──▶ Solving … ──end──▶ Result
                          ▲   (Storm skips Feedback: the next puzzle appears at once)   │
                          └──────────────────────── Enter (again) ◀────────────────────┘
```

### Launcher

```
┌─ 1 Sessions ──────────────────────────────────────┬─ 2 Custom session ─────────────────────────────┐
│ Review   14 due · 6 new                  r        │ Mode    [Review 1][Storm 2][Streak 3]         │
│ Storm    3′ 1   5′ 2   10′ 3   best 41/52/80      │ Look    [Normal q][Silhouette w][Blind e]     │
│ Streak   4 · ♥3 5 · blind 6       best 37         │ Side    [To move a][White s][Black d][Random f]│
│ Weakest  Zwischenzug 48% · Spieß 55%      7       │ Lives   [0 z][1 x][3 c][5 v]                  │
│ Again    Storm 5′ medium                  8       │ Filter  motif:gabel diff:2-4      /           │
│                                                   │ First move only                  o           │
│                                                   │ ─────────────────────────────────────────    │
│                                                   │ 86 cards match          [▶ Start  Enter]      │
└───────────────────────────────────────────────────┴──────────────────────────────────────────────┘
```

The custom session is a form of **segmented controls**, each row with its own keys (07 · SegmentedControl). The
builder remembers its last state. `Tab` moves between the two panes.

### Solving

Fullscreen by default (app bar hidden, status line stays). Nothing on screen that does not help solve.

```
┌─ 1 Board ─────────────────────────────────────────────────┬─ 2 Session ───────────────────┐
│ ┃                                                         │  STORM 5′ · medium             │
│ ┃                                                         │  3:12   +4.1s                  │
│ ┃                                                         │  combo ×3  ▓▓▓▓▓░░░ 12 → 20    │
│ ┃                     (board, square,                     │  score 23                      │
│ ┃                      as large as possible)              │  ───────────────────────────── │
│ ┃                                                         │  White to play                 │
│ ┃                                                         │  Mate in 2                     │
│ ┃                                                         │  ───────────────────────────── │
│ ┃ eval bar hidden while solving                           │  last: Polgár 98 ✓ 3.2s        │
├───────────────────────────────────────────────────────────┤                                │
│ click/drag: move · i type move · h hint · s solution     │  [Hint h] [Solution s] [Esc]   │
└───────────────────────────────────────────────────────────┴───────────────────────────────┘
```

- Board: mouse moves, or `i` to type the move (on by default in Blind). Wrong moves: board flashes `bad`, the move
  is taken back (Review/Streak: the solution plays after the miss; Storm: next puzzle).
- `h` hint: first press highlights the piece to move, second shows the move. A hinted puzzle counts as missed for
  scheduling and ends the combo (honest data).
- `s` show solution (= give up), `f` flip, `Esc` opens the **pause line** in the status line:
  `Paused · Enter resume · q quit · r restart` (Storm's clock cannot be paused, `Esc` there asks `quit? y / n`).

### Feedback (Review, Streak, custom)

The side pane switches to the result of this puzzle; the board stays.

```
│  ✓ Solved · 4.2s · card c45.2 → next in 9 days                    │
│  1.Qxh7+! Kxh7 2.Rh3#                     ← → replay              │
│  #opfer #matt-in-2 #arabisches-matt       t tag                   │
│  Polgár: 5334 Problems, Nr. 102, p.41                             │
│  [Next  Enter] [Analyse  a] [Retry  r] [Flag  !] [Edit  e]        │
```

- `Enter` next, `← →` replay the solution on the board, `a` jumps to Analyse at the move where the puzzle starts
  (the session waits in Train: `␣ t` goes back to it).
- `t` tag the position, `!` flag the puzzle as broken (shows up in `Library · is:flagged`), `e` edit the
  puzzle setup in Analyse (its Puzzle section open), `r` retry (not scored).

### Result

Like monkeytype's result screen: big numbers, one chart, everything clickable.

```
┌─ 1 Result ───────────────────────────────────────────────────────────────────────────────────┐
│  STORM 5′   score 47  ▲ new best (41)    accuracy 89%    3.9 / min    best combo ×4 (22)     │
│  ┌───────────────────────── time per puzzle (bars: ✓ green / ✗ red, line: difficulty) ───────┐│
│  │▂▃▂▅▂▃▃▆▂▂▃▄▅▃▇▃▄▅▆▅▃▄▆▇█▅▆▇▆▅▇█▇▆▇█▇▆▅▇▆█▇▆▇█                                         ││
│  └────────────────────────────────────────────────────────────────────────────────────────────┘│
├─ 2 Puzzles ─────────────────────────────────────────────┬─ 3 Board (linked to 2) ────────────┤
│  1 ✓ 2.1s  Polgár 98   #gabel                            │                                    │
│  2 ✗ 9.8s  Polgár 102  #zwischenzug          ← cursor    │      (position of the row under    │
│  ...                                                      │       the cursor, with solution)   │
└──────────────────────────────────────────────────────────┴────────────────────────────────────┘
  r again · Enter open puzzle · m review the missed · a analyse missed · l launcher · y copy result
```

- `j/k` through the puzzles (the board pane follows), `Enter` opens one in Analyse with the session's puzzles as its
  *subject list* (`n`/`N`).
- `m` starts a Review of the missed ones; `a` opens Analyse with only the missed ones as the subject list.
- Records, milestones and level-ups reached in this session are listed at the top as **achievement chips**.

---

## Analyse  `␣ a`

One position or game, board-centred. All panes in link group A.

```
┌─ 1 Board ────────────────────────────────┬─ 2 Engine ── SF 17 · d24 · 2.1M n/s ─── e on ── ⚙ ┐
│▐                                         │ +1.8  1.Qxh7+ Kxh7 2.Rh3+ Kg8 3.Rh8#              │
│▐                                         │ +0.9  1.Rh3 g6 2.Qf4 …                            │
│▐ eval                                    ├─ 3 Moves ─────────────────────────────── ⇵ z ──────┤
│▐ bar        (board)                      │  1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.b4!? Bxb4          │
│▐                                         │    ├ A 4…Nxb4 5.c3 Nc6 6.d4                       │
│▐                                         │    └ B 4…Bb6 5.a4 a6 (good)                       │
│▐                                         │  5.c3 Ba5 6.d4 exd4 7.O-O ▸12…Nf6  ← cursor       │
├──────────────────────────────────────────┤                                                   │
│ var B instead of 12…Nf6 · M main line    ├─ 4 Inspector ─────────────────────────────────────┤
│ right-drag arrow · right-click circle    │ ▾ Move 12…Nf6   ?! · −0.4 · dubious      1–7  m   │
├─ 5 Eval graph (games only, phase 5) ─────┤ ▾ Comment                                   c     │
│ ▁▂▂▃▂▂▁▁▂▅▇▆▅▃▂▁ ▁▂▃▃▂                  │   Threatens e4, but …                             │
└──────────────────────────────────────────┤ ▾ Tags   #zwischenzug (phase 4)              t     │
                                           │ ▸ Puzzle  not set up                        p     │
                                           │ ▸ Position p123 · Polgár 5334 Nr. 102 · diff 3     │
                                           └───────────────────────────────────────────────────┘
```

- **Navigation**: `h/l` or `← →` back/forward, `j/k` or `↓ ↑` other variation at this move, `g g` / `G` start/end,
  `g p` / `g n` previous / next branch point, `M` back to the main line. Stepping needs no request: the whole tree
  is in the browser; the cursor survives reloads.
- **Edit the current move**: `1`–`7` annotation symbols, `m` mark menu (`m g` good, `m d` dubious, `m b` bad,
  `m c` colour, `m x` clear), `c` comment, `t` move tag (phase 4), `Shift+↑/↓` reorder variation, `P` promote to
  main line, `d` delete from here. Every change is a journal entry: `u`/`U` undo and redo it, also after a reload.
- **Board**: `f` flip, `e` engine on/off, `Enter` play the engine's best move, `S` setup (correct the position: the
  analysis stays when its moves are still legal, otherwise `y / n` before they go), `i` type a move, `y` copy FEN,
  `Y` copy PGN, `Mod+V` paste (`a` makes a new position to analyse; on an open analysis, loading a pasted game asks
  before it replaces the moves).
- **Engine**: Stockfish 17.1 lite (WASM, one thread) runs in the browser while Analyse is on screen: MultiPV lines
  (`:engine.lines 1–5`, 3 by default) to depth 24, the best moves as arrows, the eval bar left of the board. Clicking
  a move of a line adds the line up to it.
- **Puzzle**: `p` puzzle menu (which-key): `p s` start here, `p x` solution ends here, `p a` also correct,
  `p o` all answers count, `p r` ready for training, `p d` discard. The solution is the analysis from the start
  move (the old app's walker: main moves, also-correct moves, answer lines, at most 8 solver moves unless an end is
  marked); it is rebuilt after every change, one card per answer line. The move tree shows it: the start framed,
  solver moves underlined, answers dotted, ends with a small square, drafts grey.
- **Subject list**: `n`/`N` next/previous subject when Analyse was opened from a list (library results, missed
  puzzles). The status line shows `3 / 38`.

---

## Collect  `␣ c`

Getting material in, fast. Built for entering a book diagram after diagram (as in the old rapid entry).

```
┌─ 1 Board · SETUP ────────────────────────┬─ 2 Entry session ─────────────────────────────────┐
│ palette: ♙1 ♘2 ♗3 ♖4 ♕5 ♔6  ⇄ c  ⌫ x     │ Source   Polgár: 5334 Problems         s         │
│┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │ Page     41   + / −         Diagram 103   ↑/↓    │
│┃                                      ┃  │ Title    Polgár Nr. {n}                          │
│┃      (board, indigo frame = Setup)   ┃  │ Presets  [Mate-in-2 set ✓] [Kids ✗]     1–9      │
│┃                                      ┃  │ Ready for training ✓                     r        │
│┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │ This diagram: new · source has 102 positions      │
│ white to move  w · castling  KQkq  o      ├─ 3 Just saved ─────────────────────────────────────┤
│ FEN 6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1 │ p2002  Nr. 102 · 1.Rd8#                           │
├──────────────────────────────────────────┤ p2001  Nr. 101 · 1.Qg7+ Kxg7 2.Nf5+              │
│ click: place ♘ white · S solution         └───────────────────────────────────────────────────┘
```

- Board layers: **Setup** (place pieces) ↔ **Solution** (play the solution as the main line), switched with `S`.
- `Mod+Enter` save & next (clears the board, diagram +1), `Mod+Shift+Enter` save & open in Analyse. Both work
  from any pane in Collect. A save makes the position with its source, page, diagram number, title (the pattern
  filled in) and tags; when a solution was played, it becomes the analysis and a puzzle from the start (in training
  when *Ready* is on, else a draft).
- The entry-session keys (`s`, `+ −`, `↑ ↓`, `t ⌫`, `1`–`9`, `r`) work when that pane has focus (`Tab`), because the
  board's Setup layer uses letters and digits for pieces. The session (source, page, number, title, tags, ready) and
  the *Just saved* list survive reloads.
- Paste (`Mod+V`) a FEN, lichess link or PGN at any time: `c` puts one position on the board (a list of FENs is saved
  at once), `i` opens the **Import** list for a PGN: games and puzzles found, duplicates marked and left out, `x` to
  (de)select, `r` puzzles into training, `Enter` imports. `:import` does the same with a file.
- Duplicates are detected live while setting up: the board's strip and the entry session say `duplicate of p1873`
  and `g d` goes there; saving it anyway asks `m` merge · `s` save anyway.

---

## Library  `␣ l`

Find, filter, organise, start training from any search.

```
┌─ 1 Filters ───────────┬─ 2 Results ──────────────────────────────────────────────┬─ 3 Preview ────────┐
│ ▾ Fields              │ [1 Positions][2 Games][3 Puzzles][4 Players][5 Sources]  │  (board linked     │
│   Motif               │ / motif:gabel diff:>=3 no:solution          38 of 2,002   │   to the cursor)   │
│     ▸ Gabel  (122)    │ ─────────────────────────────────────────────────────────│                    │
│     ▸ Fesselung (88)  │ ▢ p1873 ⬛ Polgár Nr. 88    #gabel #opfer   ★★★  ✗ sol  │                    │
│   Mating pattern      │ ▣ p1874 ⬛ Polgár Nr. 89    #gabel           ★★★  ✗ sol  │ Polgár Nr. 89      │
│ ▾ Difficulty  1–5     │ ▢ p1902 ⬛ Nunn Ex. 12      #gabel #matt-in-2 ★★★★ ✗ sol │ White to play      │
│ ▾ Source              │ ...                                                      │ #gabel             │
│ ▾ Status              │                                                          │ no solution yet    │
│   no solution  (231)  │                                                          │                    │
├───────────────────────┴──────────────────────────────────────────────────────────┴────────────────────┤
│ 1 selected · t tag · d trash · T train these · a analyse · y copy FEN · e export PGN · v range        │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- `1`–`6` switch collection (positions, games, puzzles, players, sources, tags), `/` query (11 §3: completion with
  `⇥`, problems underlined below the bar, the count live), `j/k` cursor (the linked board shows the row),
  `Enter` open in Analyse (games too; a player, source or tag opens its games or positions), `x` select, `v` range,
  `Mod+A` all results. `o` open in a split follows in phase 6.
- `␣ u v` cycles the result display: **table** (dense rows) · **list** (row with a mini board) · **grid** (cards
  with boards). All three share cursor, selection and keys.
- The filter pane writes into the query (and the query updates the filters): one source of truth, the query string.
- Bulk commands act on the selection, or on the cursor row if nothing is selected. A bulk bar appears as the pane
  footer while something is selected.
- `T` starts a training session with the puzzles in the results; `:save-query <name>` saves the search (usable as
  `in:q:<name>` and as the filter of a custom training session); `d` moves to the trash, `is:trash` shows it, `r`
  restores, `:trash-empty` deletes for good (positions with training history stay).
- Every bulk change is one step of the undo stack (`u`), replayed exactly: tagging and untagging put back the links
  they changed, trashing restores.

---

## Stats  `␣ s`

Sections of charts and numbers. Every number links somewhere (drill-down).

| Section | Contents |
|---|---|
| Overview | KPI tiles: positions, with solution, games, lines of analysis, cards, pattern library, training days in a row |
| Pattern library | Mature cards over time (line), next milestone, projection ("on course for 250 by Nov 30") |
| Card stages | New / learning / young / mature as a stacked bar over 60 days |
| Retention | 7 / 30 days / all, young vs mature |
| Mastery | Ladder per motif family and per tag: Learning → Familiar → Solid → Strong → Expert → Master |
| Weak spots | Weakest motifs (smoothed accuracy), robustness (white/black, mirrored, side on top) |
| Records | Storm (per length and pace), Streak (per lives), with history charts |
| Activity | Calendar heatmap (53 weeks), points per week by kind (collect, analyse, train) |
| Collection | Positions by field/tag, by source, by difficulty; analysis coverage |

- `j/k` move between charts (the focused chart gets the accent border), `h/l` steps through its data points (a
  cursor line + value read-out: charts are keyboard-inspectable), `Enter` drills down (a tag → Library filtered; a
  weak motif → Streak on it), `t` toggles the chart's table view, `1`–`5` switch the period (7d, 30d, 90d, 1y, all).

---

## Settings  `␣ ,`

One long, searchable list of sections, monkeytype style. Every row: label, control, short explanation, its `:set`
name.

```
┌─ 1 Settings ────────────────────────────────────────────────────────────────────────────────────┐
│ / search settings                                                                                │
│ ▾ Theme         [nord] [serika] [paper] [ink] [+ custom]          ↑↓ preview · Enter apply       │
│ ▾ Colours       bg #2e3440 ■  text #d8dee9 ■  sub #4c566a ■  main #88c0d0 ■  …   theme.bg …     │
│ ▾ Typography    font [Inter ▾]  mono [JetBrains Mono ▾]  size [13]  density [compact|cozy]       │
│ ▾ Board         light ■ dark ■  coordinates [inside|outside|off]  animation 150ms  …              │
│ ▾ Pieces        [cburnett] [staunty] [merida] [alpha] … (live preview row)                        │
│ ▾ Keys          keycaps [full|compact|off] · teach keys ✓ · keymap: 3 overrides  [Edit keymap K]  │
│ ▾ Training      new cards/day 20 · Storm pace [fast|medium|slow] · hints count as miss ✓          │
│ ▾ Engine        threads 6 · hash 256MB · lines 3 · arrows ✓                                       │
│ ▾ Data          export settings y · import settings p · export library e                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- `j/k` rows, `h/l` change the value of a segmented/stepper row, `Enter` edit a field, `/` filter rows.
- Theme and piece set: moving the cursor over an option **previews it live**, `Enter` keeps it, `Esc` reverts.
- **Keymap editor** (`K`): a table of all commands (id, title, context, keys); `Enter` on a row then press the new
  key(s); conflicts are shown at once with the command they collide with.

---

## Help  `?`

An overlay over the focused pane: every key that works right now, grouped (this view, this mode, global), with
`/` to search. Inside it, `a` switches to the full keymap of every context (also `:help keys`).
