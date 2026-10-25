# 02 · Interaction model

Three things decide what a key does: the **mode** (what you're doing), the **layer** (how keys are read right now)
and the **focused pane** (where the cursor is). This document defines all three, the command system they feed into,
and the rules that keep the keymap learnable.

## 1 · Modes

| Mode | Leader key | Purpose |
|---|---|---|
| **Home** | `␣ h` | What to do now: due cards, one-key sessions, capture box, recent work, today's numbers |
| **Train** | `␣ t` | Solve puzzles: Review, Storm, Streak, custom sessions; result screens |
| **Analyse** | `␣ a` | Work on one position or game: moves, variations, comments, tags, engine, puzzle setup |
| **Collect** | `␣ c` | Get material in fast: board editor, paste FEN/PGN/links, rapid entry from a book, imports |
| **Library** | `␣ l` | Find and organise: positions, games, puzzles/cards, players, sources, tags; bulk actions |
| **Stats** | `␣ s` | Progress: collection, analysis and training statistics, records, milestones |
| **Settings** | `␣ ,` | Theme, board, pieces, keymap, training rules, data |

`␣ ␣` (leader twice) toggles between the current and the previous mode, like `Ctrl+^` in vim.

Each mode has its own **default layout** (04), its own remembered state (subject, cursor, layout, collapsed
sections) and may add mode-specific states (Train: *Launcher → Solving → Feedback → Result*). A mode is shown in the
app bar (highlighted tab) and in the status line.

## 2 · Layers

Layers decide how a key press is read. Exactly one is active at a time. The status line shows it in its own colour.

| Layer | Enter with | Leave with | What keys do |
|---|---|---|---|
| **Normal** | `Esc` from anything | — | Keys are commands. Default layer. |
| **Insert** | Focusing a text field (click, `c` comment, `i` in a form, `Tab` into a field) | `Esc` (keeps the text as a draft), `Enter`/`Mod+Enter` (submit) | Keys type. Only `Esc`, `Mod+Enter`, `Tab`/`Shift+Tab` and the field's own shortcuts work. |
| **Command** | `:` | `Esc`, `Enter` (run) | The command line: fuzzy search over all commands, arguments with completion, history `↑ ↓`. |
| **Search** | `/` | `Esc` (back to the results, query kept), `Enter` (jump to the first result) | The focused view's query bar, or the library search when the view has none. |
| **Visual** | `v` in a list | `Esc` (clears), or any bulk command | Range selection: `j/k` extend, `x` toggle single items, then a bulk command. |
| **Pending** | A prefix key (`␣`, `g`, `␣ w`, ...) | the completing key, or `Esc` | The which-key panel lists every key that can follow, with its command. No timeout. |
| **Hint** | `F` | choosing a label, or `Esc` | Every clickable element in the workspace gets a 1–2 letter label (like Vimium). Typing the label clicks it. This makes every mouse-only target reachable by keyboard. |
| **Setup** (board) | `S` on a board pane / Collect mode | `S` again, `Esc` | Board editor: palette keys place pieces (06). |
| **Move entry** (board) | `i` on a board pane; on by default in blind training | `Esc` | Type a move in SAN (English or German letters) or UCI; the matching move is previewed as an arrow; `Enter` plays it (06). |

Rules:
- **`Esc` always moves one step towards Normal**: closes an overlay, leaves a layer, cancels a pending sequence,
  clears a selection, in that order. Pressing `Esc` twice from anywhere lands in Normal with nothing open.
- Layers do not stack except *Pending* (which can start from Normal or Visual and returns to it).
- A mouse click never changes the layer by surprise. The one exception: clicking into a text field enters Insert,
  which the status line shows at once.

## 3 · Commands

A command is the single unit of action. Everything else (keys, buttons, menus, the command line, the hint layer)
is a way to call one.

```toml
# design/commands/board.toml (definition format: see 09 · Command registry)
[board.flip]
title    = "Flip board"
keys     = ["f"]
when     = "view.board"            # context condition
icon     = "flip"
group    = "Board"
repeatable = false

[analysis.annotate]
title    = "Annotate move"
args     = [{ name = "nag", type = "enum", values = ["!", "?", "!!", "??", "!?", "?!", "□"] }]
keys     = { "1" = "!", "2" = "?", "3" = "!!", "4" = "??", "5" = "!?", "6" = "?!", "7" = "□" }
when     = "view.moves && cursor.isMove"
undoable = true
repeatable = true
```

Every command has:

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Stable dotted id (`area.verb[.detail]`). Used in keymaps, buttons, the URL of server handlers, analytics. |
| `title` | yes | Short imperative title, shown in the command line and as the button label. |
| `keys` | no | Default bindings. A command with no key must still be reachable via `:` and a button or menu. |
| `when` | no | Context condition (§5). Absent = global. |
| `args` | no | Typed arguments with completion (`tag`, `position`, `enum`, `int`, `text`, `color`, ...). |
| `undoable` | for mutations | Produces an undo entry (§7). |
| `repeatable` | no | Can be repeated with `.` (§7). |
| `danger` | no | Shows in the danger style; needs confirmation unless undoable. |
| `handler` | yes | `client` (JS function), `server` (HTMX request to `/cmd/<id>`), or `both` (optimistic client + server write). |

### The command line (`:`)

- Opens as one line above the status line, with a fuzzy-filtered list of matching commands above it (max 12 rows,
  scrolls).
- Each row: **title**, its **key(s)** as keycaps, its group, and greyed out if its `when` is false here (with the
  reason, e.g. "needs a move").
- Arguments: `:tag gabel`, `:train storm 5`, `:open p123`, `:vsplit engine`, `:set board.light=#e8dcc0`,
  `:theme nord`. Completion with `Tab`; argument types complete from the server (tags, sources, positions) or locally.
- History with `↑ ↓`, persisted. `:` + `Enter` on an empty line repeats the last command-line command.
- Object references use short ids: `p123` position, `g12` game, `z45` puzzle, `c45.2` card, `s7` source, `@tal`
  player, `#gabel` tag. The same tokens work in the library query and in comments (they become links).

### Buttons and menus

- A button renders from its command: `{% cmd "board.flip" %}` → `[⟲ Flip  f]`. Label, icon, keycap, disabled state
  and its reason all come from the registry, so a button and its key can never disagree.
- When the key is pressed, the matching visible button **flashes** (100 ms pressed state). You see what the key did,
  and you learn which button it was.
- Right-click (or `Shift+F10`/`≡` key) on any item opens a **context menu** of the commands that apply to it, each
  with its key. Menus also accept the item's key directly.

## 4 · Key grammar

| Kind | Form | Examples | Rule |
|---|---|---|---|
| Single key | one key | `f`, `j`, `1`, `Enter` | Context commands. Most frequent actions. |
| Shifted | `Shift+key` | `N`, `U`, `Z` | The reverse or "bigger" version of the lowercase command (`u` undo / `U` redo, `n` next subject / `N` previous, `z` fold one / `Z` fold all). |
| Leader sequence | `␣` + keys | `␣ t`, `␣ w v`, `␣ 3` | Global: modes, panes, toggles, the app. Never depends on the focused view. |
| Go sequence | `g` + key | `g g` (first), `g p` (go to parent move), `g s` (go to source) | Jumps within the focused view. |
| Modifier chord | `Mod+key` | `Mod+Enter`, `Mod+Z`, `Mod+C` | Only where the browser and OS agree with the meaning (submit, undo, copy, paste). |
| Command line | `:` + text | `:split library` | Everything, including commands that have no key. |

`Mod` = `⌘` on macOS, `Ctrl` elsewhere. Keycaps in the UI show the platform's symbol.

**No ambiguity, no timeouts.** A key is either a command or a prefix within one context, never both (the keymap lint
rejects it). So the app never waits to see whether another key follows, and every key reacts at once.

**No counts.** Digits are commands in several contexts (annotations, tabs, segmented controls), so vim-style counts
(`5j`) are not supported. `:` handles numbers where they're needed (`:goto 24`).

**Repeat with `.`**: repeats the last repeatable command with the same arguments on the current cursor. Tag one
position *Gabel*, `j` to the next, `.` tags that one too.

### Keys the app never binds

Browsers or operating systems own these, so the app never binds them: `Mod+W/T/N/Q/L/R/Tab`, `Mod+1–9`, `F5`,
`F11`, `F12`, `Ctrl+Tab`, `Alt+←/→` (history), `Mod+H/J` (history/downloads in some browsers). `Mod+S` and `Mod+P`
may be bound (prevented) if a command really needs them.

### Keyboard layouts

The defaults are designed and tested on **QWERTY** (US/intl), the user's layout. Matching still works on any
layout, so a later switch or a second user on QWERTZ doesn't break anything.
- Printable keys match on the **produced character** (`event.key`), so `?`, `:` and `/` work on any layout, and
  `z`/`y` follow the label on the key. Keycaps show the produced character.
- `Alt`/`Option` chords match on the **physical key** (`event.code`), because macOS turns `Alt+k` into `˚`.
- **Default bindings avoid characters that need AltGr/Option** on common European layouts: no `[ ] { } \ | @ ~`
  in the defaults. Letters, digits, `Space`, `Enter`, `Esc`, `Tab`, arrows, `, . -` and shifted `? : / ;` are allowed.
- In move entry, German piece letters (K D T L S) are accepted next to English (K Q R B N).

## 5 · Context and resolution

The `when` conditions read a small, flat context object kept up to date on the client:

```
mode = "analyse"            layer = "normal"           overlay = null | "cmdline" | "menu" | "help" | ...
pane.view = "moves"         pane.linked = true         subject.kind = "position" | "game" | "puzzle" | ...
analysis.loaded = true      analysis.onMove = true     analysis.hasList = false     engine.ready = true
selection.count = 0         train.state = "solving"    board.layer = "play" | "setup" | "entry"
```

Condition syntax: `view.moves && cursor.isMove`, `mode.train && train.state == 'feedback'`, `!selection.empty`.
`view.x` is short for `pane.view == "x"`, `mode.x` for `mode == "x"`.

**Resolution order** for a key press (first match wins):
1. **Overlay** (command line, menu, help, dialog) if one is open.
2. **Layer** (Insert takes all keys except its escapes; Pending takes the next key; Hint takes labels).
3. **State** of a mode with states (Train: launcher, solving, feedback, result), so `r` can be "review" in the
   launcher, "retry" in feedback and "again" on the result.
4. **Focused pane's view** bindings.
5. **Mode** bindings, before the generic pane keys: in Analyse `j`/`k` switch variations and `g g`/`G` go to the
   start/end from every pane.
6. The generic **pane** bindings (scrolling, sections, `i`).
7. **Global** bindings (leader sequences, `?`, `:`, `/`, `F`, `u`, `U`, `.`).

The same key can therefore mean different things in different views (`d` deletes a move in Moves and moves a row to
the trash in Library), but never two things in the same view. Global keys (7) are *reserved*: a view may not rebind
`␣ : / ? F Esc u U .`.

## 6 · Focus

- Exactly **one pane is focused**. It has the accent border and an inverted header, and its number and view are
  in the status line.
- Move focus: `Tab`/`Shift+Tab` (cycle in reading order), `␣ 1`–`␣ 9` (pane by number, numbers are shown in the
  pane headers), `␣ w h/j/k/l` (by direction), or a click anywhere in a pane.
- Within a pane the **cursor** moves with `j/k` (or `↓ ↑`) and `h/l` (or `← →`) where the view has two dimensions
  (move tree: back/forward; grid: columns).
- The browser's own focus (`document.activeElement`) follows the app's focus for accessibility, but the app does not
  rely on browser tab order for navigation.
- Focus is never lost: when a pane closes, focus goes to its sibling; when an item is deleted, the cursor goes to the
  next item (or the previous, at the end).

## 7 · Undo, repeat, confirmation

- Every mutating command is **undoable** unless that's impossible (an export written to disk). `u` undoes, `U`
  redoes (also `Mod+Z`, `Mod+Shift+Z`). The undo history is global and kept on the server (09 · Command journal),
  so it survives a reload. `:undolist` shows it.
- After a mutation the status line shows what happened, with the undo key: `Moved 12 positions to trash · u undo`.
- Because of undo, **confirmation dialogs are almost never needed**. They are kept for: emptying the trash,
  permanently deleting, bulk operations over 100 items, and dropping moves when a corrected position makes them
  illegal. A confirmation is inline (in the status line: `Delete permanently? y / n`), not a modal.
- **Never interrupt the work** for something that can be done safely and undone: do the safe thing, say so, and
  offer the alternatives as a *suggestion* in the status line (`Added 3 pasted moves · r replace instead · n as a
  new position`): its keys act, any other key closes it and does what it always does. Browsing never changes what
  you are working on: a list previews its rows on the boards of its group, opening is `↵` or `a`.

## 8 · Teaching keys

| Feature | Behaviour | Default |
|---|---|---|
| Keycaps on buttons | Always shown | on, can be reduced to *compact* (icon + key) |
| Which-key panel | Shown immediately after a prefix | on |
| Key flash | The button of a pressed key flashes | on |
| Teach-keys hints | Clicking a button that has a key shows `tip: f flips the board` in the status line | on for the first 30 days, then off |
| Context key strip | Each pane footer can show the 4–8 most useful keys for its current state | per pane, toggle `␣ u k` |
| Help overlay `?` | All keys of the current context, grouped, searchable with `/` | — |
