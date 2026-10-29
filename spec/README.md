# Spaced Positions: UI/UX System Specification

Status: **version 0.1**, kept in step with the build (10 has the status of each area, what comes next and the
decisions taken). This folder is the contract that the design system, the front-end and the screens are built
against.

## What we are building

A chess app for **collecting, solving and training puzzles** and making that process rewarding. It also handles
analysing positions and games and tracking progress. Built with Django + HTMX and as little JavaScript as possible,
spent only where it pays off (board, keymap, charts that need interaction).

The UI system follows four ideas:

1. **Keys first, mouse complete.** Every action is a *command*. Keys and buttons are two ways to call the same
   command, and every button shows its key. The board is the one place where the mouse comes first.
2. **Modes, not pages.** You are always *in* a mode (Train, Analyse, Collect, ...) and in an input layer
   (Normal, Insert, Command, ...). Both are always shown on screen. This is inspired by editors like nvim, but the app
   explains everything on screen so you don't need to know nvim to use it.
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
| 9 | [09-architecture.md](09-architecture.md) | How the system maps onto Django + HTMX + small JS islands; local launch, puzzle packs, licences, languages |
| 10 | [10-roadmap-and-questions.md](10-roadmap-and-questions.md) | Status, what comes next, what is out of scope, decisions taken |
| 11 | [11-data-model.md](11-data-model.md) | Positions, games, tags, sources, players, saved queries; duplicates; the query language; PGN import |
| 12 | [12-packs-as-collections.md](12-packs-as-collections.md) | Plan: where a puzzle comes from, training and stats per pack or book, pack composition, good-citizen checks |
| 13 | [13-licensing-and-marketplace.md](13-licensing-and-marketplace.md) | Plan: licences in the pack format, author submissions, the review, the marketplace, milestones M0–M4 |
| 14 | [14-test-programme.md](14-test-programme.md) | Plan: the test group: who, tasks, questions, data, tracking, readiness |

## Reading order

For the overall picture, read 01 → 02 → 03 → 04. To build components, read 05 → 07 → 09. For the Library and
Collect, read 11. 08 is a reference.
