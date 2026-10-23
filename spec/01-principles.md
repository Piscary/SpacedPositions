# 01 · Principles

## P1 · Keys first, mouse complete

- Every action the app can perform is a **command** with a stable id (`board.flip`, `train.reveal`,
  `pane.split.vertical`). Keys, buttons, menu items and the command line all call commands. No action exists
  only as a click handler.
- **Every button shows its key** as a keycap, in the button itself: `Flip  f`, never in a tooltip. A button without a
  key is allowed only for commands that have none (rare, and the keymap lint reports them, see 07).
- The mouse can do everything the keys can. The **board is the exception the other way round**: moving pieces,
  drawing arrows and painting squares are mouse-first. They still have keyboard paths (typed moves, `:arrow e2e4`),
  but those are secondary.
- Keys are **learnable**. The command line shows each command's key, the which-key panel shows what comes next after
  a prefix, and the optional *teach keys* setting says "`f` flips the board" when you click a button that has a key.

## P2 · Everything visible

Every interaction and state is shown somewhere on screen, without hover:

| State | Where it is shown |
|---|---|
| Current mode and input layer | Status line, left (`TRAIN · NORMAL`), coloured per layer |
| Focused pane | Accent border and inverted header; its number in the status line |
| Pending key sequence | Status line (`␣ w …`) + which-key panel listing the next keys |
| Selection (lists, library) | Row marks + count in the status line (`12 selected`) |
| What a board click will do | Board pane footer (`click: move · right-drag: arrow · setup: ♘ white`) |
| Background work (engine, save, import) | Status line activity area, with a stop key |
| Unsaved / failed writes | Status line (`● saving` / `⚠ 1 failed · r retry`) |
| Links between panes | Link glyph and link-group colour in the pane header |

## P3 · Density

- **Full width.** No centred max-width column and no side gutters beyond 1 spacing unit. Panes meet at 1px rules,
  like tmux or nvim splits.
- **Compact type**: 13px base by default (user-adjustable), line height 1.35, 4px spacing unit.
- **No decoration that carries no information**: no hero images, no illustrations, no shadows for depth (borders
  carry structure), no "card" padding beyond what grouping needs.
- **Collapse, don't hide**: a section that is not needed now collapses to its one-line header (still visible, still
  with its key), it does not disappear.

## P4 · Modes, not pages

You don't navigate between pages, you switch what you are doing. Each mode remembers its layout and its object, so
switching away and back returns you exactly where you were, instantly (see 03 · Persistence).

## P5 · Speed

The app has to feel at least as fast as nvim or monkeytype. Budgets (measured on a mid-range laptop, local server):

| Interaction | Budget | How |
|---|---|---|
| Key → visible reaction (focus move, highlight, layer change) | < 16 ms (1 frame) | client-side only, no request |
| Move on the board (legal check, animation start) | < 16 ms | client-side chess logic |
| Next puzzle after a solved one | < 50 ms | queue prefetched, no request in the hot path |
| Mode switch to a mode visited before | < 50 ms | its workspace is kept in the DOM |
| Mode switch, first visit / pane swap | < 150 ms | one HTMX request, server partial < 80 ms |
| Library query (2,000 positions) | < 150 ms | server search, results stream into the list |
| Save (comment, tag, mark) | 0 ms perceived | optimistic UI, write in background, retry queue |

No spinners for anything under 300 ms. Over that, skeletons in place of the content (same size, no layout shift).

## P6 · One grammar everywhere

The same key means the same thing everywhere it makes sense: `j/k` next/previous, `Enter` open/confirm, `Esc` back
out, `t` tag, `/` search, `y` copy (yank), `x` select, `d` delete. A user who has learnt the library has already
learnt half of the training queue. Context-specific keys (annotations `1`–`7` in analysis) exist only where the
context makes them unambiguous.

## P7 · Rewarding, not noisy

Progress is made visible: the pattern library grows, records fall, mastery levels rise, streaks continue. The
feedback is short and precise (a 150 ms flash, a counter that ticks up, a result screen like monkeytype's), never a
modal you have to dismiss. It is configurable and respects *reduced motion*.

## P8 · Configurable within a system

Users change **tokens** (colours, fonts, sizes, board, pieces) and **bindings** (keys to commands), not individual
components. That keeps every theme and every keymap consistent. Settings are also commands (`:set theme=nord`).

---

## Vocabulary

These terms are used throughout the spec and later in the code. Use them exactly.

| Term | Meaning | nvim analogy |
|---|---|---|
| **Mode** | What you are doing: Home, Train, Analyse, Collect, Library, Stats, Settings. Has its own default layout, keys and remembered state. | (none; closest is a tabpage) |
| **Layer** | How keys are interpreted right now: Normal, Insert, Command, Search, Visual, Pending, Hint, plus board layers (Setup, Move entry). | mode |
| **Command** | A named action with an id, a title, default keys, a *when* condition, and a handler. | `:command` / mapping target |
| **Binding** | A key or key sequence mapped to a command in a context. | `:map` |
| **Workspace** | The area between the app bar and the status line, holding the layout of the current mode. | tabpage |
| **Layout** | The tree of splits that fills the workspace. | window layout |
| **Pane** | One rectangle in the layout. Has a header, a body showing one view, and an optional footer. | window |
| **View** | A kind of content a pane can show: Board, Moves, Engine, Inspector, Library, Queue, Chart ... | buffer (type) |
| **Subject** | The object a view is about: a position, game, puzzle, card, session, query ... | buffer contents |
| **Link group** | Panes that share one subject and cursor (e.g. board + moves + engine). Moving in one moves all. | `scrollbind` |
| **Section** | A titled, collapsible group *inside* a pane. | fold |
| **Cursor** | The current item in a view: current move in the move tree, current row in a list. | cursor |
| **Selection** | A set of items marked for a bulk command. | visual selection |
