# 03 · Layout: shell, workspace, panes, splits

## 1 · The shell

The screen always has three horizontal bands. Only the workspace changes.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ ♞  ␣h Home  ␣t Train  ␣a Analyse  ␣c Collect  ␣l Library  ␣s Stats │ 14 due · ⚑9d │ ␣, ⚙  ? │  ← app bar (28px)
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                              │
│                                    WORKSPACE (layout of panes)                               │
│                                                                                              │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ ANALYSE │ NORMAL │ 2 Moves │ p123 Polgár Nr. 102 · 12…Nf6 (var B) │ ● saved │ ␣ leader  ? keys │  ← status line (22px)
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

**App bar** (1 line, 28px)
- Mode switcher: each mode is a tab with its leader key as a keycap. The current mode is highlighted. Clicking works.
- Centre/right: a small **pulse** area for things that matter right now: due cards, today's streak, an engine that
  is running, an import in progress. Each item is clickable and has a command.
- Far right: settings (`␣ ,`), help (`?`).
- Can be hidden (`␣ u b`): the status line then shows the mode keys. In fullscreen training it hides by default.

**Status line** (1 line, 22px), left to right:
1. **Mode** (coloured block) and **layer** (its own colour: Normal neutral, Insert green, Visual violet, Command
   accent, Setup indigo, Move entry teal).
2. **Pending keys** (`␣ w …`) while a sequence is open.
3. **Focused pane**: number and view.
4. **Subject + cursor**: `p123 Polgár Nr. 102 · 12…Nf6 (var B)`, or `Library · 38 of 2,002 · 12 selected`.
5. **Messages**: the last command's result with its undo key, errors, inline confirmations (`y / n`), tips.
6. **Activity**: saving, engine depth, import progress, each with a key to stop or open it.
7. Right: `␣ leader · ? keys` (always, so the two entry points are never forgotten).

The **command line** (`:`), **search line** (`/` when the view has no query bar) and **which-key panel** open
directly above the status line and push nothing around: they overlay the bottom of the workspace.

## 2 · Panes

A pane is the only container in the workspace. Each pane shows one view.

```
┌─ 2 ─ Moves ─────────── p123 · ⛓ A ───────────── [⇵ fold  z] [⧉ split  ␣wv] [▢ max  ␣wm] ─┐  ← header (24px)
│                                                                                           │
│  body: the view                                                                           │
│                                                                                           │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ j/k move  h/l var  c comment  t tag  1–7 !?  g/d/b mark                                   │  ← footer (optional)
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

**Header**: pane number · view name · subject (short) · link glyph and group letter (`⛓ A`) or pin glyph `⊙` · the
view's 2–4 most important commands as compact key buttons · window buttons (collapse, split, maximise, close).
The header is the drag handle for moving the pane (drop zones: left/right/top/bottom half of another pane).

**Footer** (optional, per pane, `␣ u k`): the context key strip, or the view's own status (board: *what a click
does*; library: *38 results · sort: added ↓*).

**States**

| State | Look | Trigger |
|---|---|---|
| Normal | 1px rule border | — |
| Focused | accent border (2px inner), header inverted (accent bg) | focus |
| Collapsed | only the header, rotated to a 24px **rail** when in a horizontal split | `␣ w c`, header button |
| Maximised | fills the workspace; the other panes are listed as tabs in its header | `␣ w m` (toggle) |
| Loading | header shows a thin progress line; body keeps old content or a skeleton | request > 150 ms |
| Empty | short sentence + the 1–3 commands that would fill it, as key buttons | no subject |
| Error | inline error row with retry key, old content kept | failed request |

**Sizes**: minimum 160px wide and 3 lines high (header + 2). The **board view keeps a square board** and gives
extra room to its side strips (eval bar, palette), never stretches the board.

## 3 · Splits

- The layout is a tree: each node is a **split** (horizontal or vertical, with ratios) or a **pane**.
- `␣ w v` vertical split (side by side), `␣ w s` horizontal split (above/below). The new pane opens the **view
  picker** (a small list of views with keys: `b` board, `m` moves, `e` engine, `i` inspector, `l` library,
  `q` queue, `c` chart, `n` notes, `p` PGN/FEN text, `t` tags).
- `:vsplit <view> [subject]` / `:split <view> [subject]` do the same in one go: `:vsplit board p456`.
- `␣ w q` close pane, `␣ w o` only this pane (others are kept as hidden *buffers*, `␣ w b` lists them),
  `␣ w =` equal sizes, `␣ w x` swap with the next pane, `␣ w r` rotate the split.
- Resize: drag the 4px gutter (hover shows a resize cursor and highlights the rule), or `␣ w` then `< >` (width) and
  `+ -` (height) in steps of 5%, repeatable while the window prefix is held (sticky window submode, `Esc` ends it).
- Gutters snap at 25 / 33 / 50 / 67 / 75 % when dragged near them.

## 4 · Linking panes

This is what makes splits useful for chess: two boards side by side should be able to show *the same* line or *two
different* lines.

- **Link group**: panes in the same group share a subject and a cursor. Board, Moves and Engine of one analysis are
  in group A by default: stepping in Moves moves the board and restarts the engine. The header shows `⛓ A`, and
  each group has its own colour (a 3px stripe at the header's left edge).
- **Unlinked (pinned)**: a pane can be pinned (`␣ w p`) to keep its subject and cursor. Pinning a board shows a
  frozen position next to the live one, for comparisons. The header shows the pin glyph `⊙`.
- `␣ w g` cycles the pane's group (A → B → none). `:vsplit board` opens a new *linked* board; `:vsplit! board`
  opens a pinned copy.
- A link group can follow the **library cursor**: put the Library in one pane and a Board in a pane linked to it,
  and `j/k` in the list previews each position on the board. This is how browsing works in Library mode.

**Every view in every mode** (phase 7 cleanup). The user may build any arrangement; a view either works wherever
it is, or says plainly why not:
- An **analysis** (Moves, Inspector, Engine, Eval graph, Variation graph, and the boards of its link group) works in
  any mode: `:analyse` opens one into the focused link group's panes when the mode has a move tree there, `o` in the
  Library opens a row beside the list, `a` on Train's feedback the puzzle. While one of these panes has the focus,
  Analyse's keys work (`keys.js` adds the `mode.analyse` context); the engine follows the focused link group's board
  everywhere but in Train (it would show the solutions). Empty, each says what fills it and which link group it
  belongs to; the Filters pane says it needs a Library in its link group.
- **Session** (Train) and **Entry session** (Collect) keep their keys and state in their mode: elsewhere the pane
  shows what it is, that it works in that mode, and a button to go there (`lives_in` in `core/layouts.py`).
- A saved layout that names a view the app no longer has keeps its arrangement; that pane says so and offers to
  pick another view or close it.

## 5 · Sections inside panes

Long views (Inspector, Settings, Stats, Home) are made of **sections**: a 22px header line with a title, a count or
summary, its own key and a collapse caret; the body below.

- `z` toggles the section under the cursor, `Z` collapses/expands all (like folds).
- A collapsed section still shows its summary: `▸ Tags (5) · Gabel, Opfer, Matt in 2 …`.
- Sections can be *pinned open* by the view (e.g. the puzzle prompt in Train) so they can't be collapsed.
- `␣ 1`–`␣ 9` are panes; inside a pane, sections are reached with `g` + their letter (`g t` tags, `g c` comment),
  shown in their header, and stepped through with `]` / `[` (next / previous section).

### Moving inside the focused pane

Every pane can be read and used without the mouse. These keys belong to the `pane` context, so a view can give them
a more specific meaning (a list moves its cursor with `j k`, a board steps through moves with `h l`):

| Keys | Does |
|---|---|
| `j k` / `↓ ↑` | Scroll a little (three lines) |
| `J K` | Half a page |
| `PgDn PgUp` | A page |
| `g g` / `G` (`Home` / `End`) | Top / bottom |
| `]` / `[` | Next / previous section |
| `i` | Edit: focus the pane's text field (the one edited last, else the first) and enter Insert; `Esc` leaves it |
| `F` | Hint labels: reach any button or link in the pane |

Scrolling is instant, as in a terminal: the key's effect shows in the same frame.

### Scrollbars

As thin as the platform allows (`--scrollbar`, 1.5 × the spacing unit, in Chromium and Safari; `thin` in Firefox;
nothing on macOS with overlay scrollbars), in `--scroll-thumb`, brighter while the pointer is over the scroll area.

## 6 · Persistence

| What | Stored where | Lifetime |
|---|---|---|
| Layout tree per mode (splits, ratios, views, link groups, collapsed panes) | server, per user | until changed; `:layout reset` restores the default |
| Named layouts | server | `:layout save <name>`, `:layout load <name>`, listed in `␣ w L` |
| Per-mode subject and cursor | server | so a reload or another device returns to the same move |
| Collapsed sections | server, per view | — |
| Drafts in text fields left with `Esc` | server (debounced) | until submitted or discarded |
| Scroll positions, which-key state | memory | session |

**Mode workspaces stay alive**: switching mode hides the old workspace instead of destroying it. Up to 3 recently
used modes stay in the DOM, so returning is instant (< 50 ms) and engines, timers and scroll positions are as you
left them. An expensive background process (engine) pauses when its mode is hidden.

**URLs**: the URL names the mode and its main subject (`/analyse/p123?n=4517` = position 123 at node 4517,
`/train/session/88`, `/library/positions?q=motif:gabel`). Layout is not in the URL. Back/forward moves between mode
switches and subject changes, not between every move. Any URL can be opened directly and restores the mode's layout.

## 7 · Screen sizes

Desktop and laptop only (10 · decision 9). Phones and tablets are not supported for now.

| Width | Behaviour |
|---|---|
| ≥ 1280px | Full layouts as designed |
| 1024–1279px | Layouts with 3+ columns put the last column into a collapsed rail |
| < 1024px | Not designed for. Panes keep their minimum sizes and the workspace scrolls horizontally instead of breaking. |

Nothing in the system should make mobile impossible later: panes, rails and the tab form of a maximised pane are the
building blocks a phone layout would use.
