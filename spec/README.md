# Spaced Positions: UI/UX System Specification

Status: **draft 1** (2026-10-23), kept in step with the build: phases 0–5 are built (see 10 for the status of
each phase). This folder is the contract that the design system, the front-end and the screens get built against.

This is a new, independent project. `chess-study-manager/` served as inspiration, and its database is read-only
test data. We do not copy its data model one to one.

## What we are building

A chess app for **collecting, solving and training puzzles** and making that process rewarding. It also handles
analysing positions and games and tracking progress. Built with Django + HTMX and as little JavaScript as possible,
spent only where it pays off (board, keymap, charts that need interaction).

The UI system follows four ideas:

1. **Keys first, mouse complete.** Every action is a *command*. Keys and buttons are two ways to call the same
   command, and every button shows its key. The board is the one place where the mouse comes first.
2. **Modes, not pages.** As in nvim, you are always *in* a mode (Train, Analyse, Collect, ...) and in an input layer
   (Normal, Insert, Command, ...). Both are always shown on screen.
3. **Panes and splits.** The workspace is a tree of panes, and each pane shows one *view* (board, moves, engine,
   library ...). `:vsplit engine` works here the way `:vsplit` works in nvim.
4. **Nothing hidden, nothing wasted.** All state is visible: mode, layer, pending keys, selection, what a click
   will do. The layout is dense, uses the full width and has no decorative margins.

## Documents

| # | File | Contents |
|---|---|---|
| 1 | [01-principles.md](01-principles.md) | Design principles, performance budgets, vocabulary |
| 2 | [02-interaction-model.md](02-interaction-model.md) | Modes, input layers, the command system, key grammar, focus rules |
| 3 | [03-layout.md](03-layout.md) | Shell, workspace, panes, splits, links between panes, persistence |
| 4 | [04-modes.md](04-modes.md) | Each mode: purpose, default layout (wireframes), states, keys |
| 5 | [05-components.md](05-components.md) | The component catalogue: anatomy, variants, states, keys |
| 6 | [06-board.md](06-board.md) | Board, board editor, move entry, drawing, FEN/PGN in and out |
| 7 | [07-design-tokens.md](07-design-tokens.md) | Tokens, themes, user customisation, the design pipeline and CI |
| 8 | [08-keymap.md](08-keymap.md) | The full default keymap, with the rules it has to follow |
| 9 | [09-architecture.md](09-architecture.md) | How the system maps onto Django + HTMX + small JS islands; Jupyter-style launch, puzzle packs, licences |
| 10 | [10-roadmap-and-questions.md](10-roadmap-and-questions.md) | Build order, what is out of scope, decisions taken, open questions |
| 11 | [11-data-model.md](11-data-model.md) | Positions, games, tags, sources, players, saved queries; duplicates; the query language; PGN import |

## Reading order

For the overall picture, read 01 → 02 → 03 → 04. To build components, read 05 → 07 → 09. For the Library and
Collect, read 11. 08 is a reference.
