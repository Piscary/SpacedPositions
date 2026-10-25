# 08 · Default keymap

The default keymap, by context. Once the registry exists this file is generated from `design/keymap/default.toml`
(07 §8). Until then it is the reference that the registry has to match. Rules: 02 §4–5.

## Notation

| In the UI (keycaps) | In config files | Meaning |
|---|---|---|
| `␣` | `space` | Space (leader) |
| `↵` | `enter` | Enter |
| `⎋` | `esc` | Escape |
| `⇥` / `⇧⇥` | `tab` / `shift+tab` | Tab |
| `⌫` | `backspace` | Backspace (and Delete) |
| `← → ↑ ↓` | `left right up down` | Arrows |
| `⌘` (macOS) / `Ctrl` | `mod+` | Platform modifier |
| `⌥` / `Alt` | `alt+` | Matched on the physical key |
| `U` | `U` | Upper case letter = Shift + letter (matched on the character) |
| `␣ w v` | `"space w v"` | A sequence: keys separated by spaces |

Keymap overrides use the same notation: `"space o" = "train.start storm 5"` (a command with arguments).

---

## Global (reserved: no view can rebind these)

| Key | Command | |
|---|---|---|
| `⎋` | `layer.escape` | One step towards Normal (02 §2) |
| `:` | `cmdline.open` | Command line |
| `/` | `search.open` | Search in the focused view (or library search) |
| `?` | `help.context` | Keys of the current context (inside: `a` all contexts, `/` search) |
| `F` | `hint.open` | Hint labels on every clickable element |
| `u` / `U` | `undo` / `redo` | Also `mod+z` / `mod+shift+z` |
| `.` | `repeat` | Repeat the last repeatable command |
| `⇥` / `⇧⇥` | `pane.focus.next` / `.prev` | Cycle pane focus (inside a form: next field) |
| `mod+v` | (the browser's paste event) | Paste FEN / PGN / link anywhere outside a text field (06 §6); not bound, so the browser's paste still fires |
| `␣` | leader | Opens the leader menu (which-key) |

## Leader `␣`

| Keys | Command |
|---|---|
| `␣ h` · `␣ t` · `␣ a` · `␣ c` · `␣ l` · `␣ s` · `␣ ,` | Mode: Home · Train · Analyse · Collect · Library · Stats · Settings |
| `␣ ␣` | Previous mode |
| `␣ 1` … `␣ 9` | Focus pane N |
| `␣ r` | Start a Review now (from anywhere) |
| `␣ f` | **Find anything**: fuzzy finder over positions, games, tags, sources, players, saved queries, commands |
| `␣ n` | New … : `p` position (Collect) · `g` import PGN · `t` tag · `s` source |
| `␣ w` | Window menu (below) |
| `␣ u` | UI toggles: `b` app bar · `k` key strips · `v` library display (table/list/grid) · `m` move list style (book/table) · `z` zen (hide app bar and footers) · `t` light/dark pair of the theme · `p` piece set (live preview, `↵` keeps, `Esc` back; also `:pieces <set>`) |

## Window `␣ w`

| Keys | Command |
|---|---|
| `v` / `s` | Split vertically / horizontally (opens the view picker) |
| `h j k l` | Focus pane left / down / up / right |
| `q` | Close pane |
| `o` | Only this pane (others become hidden buffers) |
| `b` | List hidden buffers |
| `e` | Change this pane's view (view picker) |
| `m` | Maximise / restore |
| `c` | Collapse / expand |
| `x` | Swap with the next pane |
| `r` | Rotate the split |
| `=` | Equal sizes |
| `< >` `+ -` | Resize (sticky: repeat without `␣ w`, `⎋` ends) |
| `g` | Cycle link group (A → B → none) |
| `p` | Pin / unpin (keep subject and cursor) |
| `L` | Layouts: save, load, reset |

View picker (after `v`, `s`, `e`): `b` board · `m` moves · `e` engine · `i` inspector · `g` eval graph · `r` variation
graph · `l` library · `f` filters · `s` entry session · `q` queue · `c` stats · `h` today · `o` continue · `n` notes ·
`p` PGN/FEN text · `t` tags.

---

## Lists, tables, grids (any view)

| Key | Command |
|---|---|
| `j k` / `↓ ↑` | Cursor down / up (grids: `h l` / `← →` too) |
| `g g` / `G` | First / last |
| `↵` | Open (default command of the object, see 05 matrix) |
| `o` | Open beside the list: a board and its move tree, linked to each other (Library, phase 7) |
| `s` | Sort by a column (a menu; the same column again reverses: the query's `sort:` term) |
| `z` / `Z` | Fold or open the group at the cursor / all groups (results sorted by a field with few values) |
| `x` | Toggle selection of the cursor row |
| `v` | Visual (range) selection |
| `mod+a` | Select all results |
| `t` | Tag (selection or cursor row) |
| `d` | Move to the trash (undoable); `r` restores (in `is:trash`) |
| `y` | Copy the FENs (positions, puzzles); games copy as PGN with `e` |
| `T` | Train these |
| `a` | Analyse these (as a subject list, `n`/`N` in Analyse) |
| `e` | Export as PGN (a download): the selection, or everything the query found |
| `␣ u v` | Results as table · list (with boards) · grid |

Sorting is a query term (`sort:-difficulty`), also chosen with `s`; sorted by difficulty, source, year, a player,
event, role, kind or field, the rows come in foldable groups. Grids move with `j k` in reading order.

## Any pane (context `pane`)

| Key | Command |
|---|---|
| `j k` / `↓ ↑` | Scroll a little (lists: cursor) |
| `J K` | Half a page |
| `PgDn PgUp` | A page |
| `g g` / `G`, `Home` / `End` | Top / bottom (lists: first / last item) |
| `]` / `[` | Next / previous section |
| `z` / `Z` | Fold the section under the cursor / all |
| `g` + letter | Jump to a section (its letter is in its header) |
| `i` | Edit the pane's text field (Insert layer) |

`[` and `]` need AltGr on QWERTZ: accepted because QWERTY is the primary layout (`[layout] accept` in the keymap).

---

## Home

| Key | Command |
|---|---|
| `r` | Review (the Today pane) |
| `1`–`6` | Quick sessions (Storm 3′, Storm 5′, Streak, Streak ♥3, weakest motifs, again) |
| `x` | Dismiss the announcement banner |
| `a` | Continue the last analysis (the Continue pane) |
| `c` | Continue collecting (last source, next diagram) |
| `i` | Focus the paste box (`p` would collide with Analyse's puzzle keys when the pane is placed there) |

## Train

The Train keys live in state contexts (`state.launcher`, `state.solving`, `state.feedback`, `state.result`): one
context per Train state, checked after layers and before the focused view (02 §5).

**Launcher** · Sessions: `r` Review · `1` `2` `3` Storm 3′/5′/10′ · `4` Streak · `5` Streak ♥3 · `6` Blind streak ·
`7` Weakest motifs (phase 5) · `8` Again. Global: `␣ r` starts a Review from anywhere.
**Launcher** · Custom (rows mirror keyboard rows): Mode `b n m` (Review, Storm, Streak) · Look `q w e` · Side
`a s d f` · Lives `z x c v` · `o` first move only · `↵` start. (Mode moved from `1 2 3`, which start Storms.)

**Solving**

| Key | Command |
|---|---|
| mouse | Play the move |
| `i` | Type the move (on by default in blind) |
| `h` | Hint (1st: the piece, 2nd: the move); counts as missed |
| `s` | Show the solution (give up) |
| `f` | Flip |
| `Q` | Stop the session now and see the result (also the Stop button, `:stop`); the card on the board isn't counted, the cards not reached stay due |
| `⎋` | Pause line: `↵` resume · `q` quit · `r` restart (Storm: `quit? y / n`) |

**Feedback**

| Key | Command |
|---|---|
| `↵` | Next puzzle |
| `← →` / `h l` | Replay the solution |
| `r` | Retry (not scored) |
| `!` | Flag the puzzle as broken |
| `a` · `A` | The puzzle's analysis beside the board, in Train (closed by the next puzzle) · in Analyse, at the puzzle's start |
| `t` · `e` | Tag · edit (Analyse with the Puzzle section open) |
| `Q` | Stop the session and see the result (also the Stop button) |
| `⎋` | `↵` next · `q` end the session and see the result |

**Result**

| Key | Command |
|---|---|
| `r` | Run the same session again |
| `j k` | Puzzles of the session (the linked board shows each) |
| `↵` | Open the puzzle under the cursor in Analyse (`n`/`N` there step through the session's puzzles) |
| `m` | Review the missed ones |
| `a` | Analyse the missed ones (a subject list) |
| `l` | Back to the launcher |
| `y` | Copy the result as text |

`:puzzle` (on any board) makes a puzzle from the line played so far: the side to move at the start solves. It is made
through the analysis of the position (the line becomes its main line), so it can be edited in Analyse.

**Tags**: `t` in feedback tags the puzzle's position (`:tag` with completion). In Analyse `T` tags the position,
`t` the move; the Inspector's Tags section shows both (a click on a chip removes it).

## Analyse

Mode-level: these work whether the board, the moves or the inspector pane has focus (not in Insert).

| Key | Command |
|---|---|
| `h l` / `← →` | Back / forward |
| `j k` / `↓ ↑` | Other variation at this move |
| `g g` / `G` | Start position / end of the line |
| `g p` / `g n` | Previous / next branch point |
| `M` | Back to the main line |
| `z` / `Z` | Fold or open the variation (in a variation: that one; on the main line: the alternatives to this or the next move) / fold or open all; the cursor never hides in a folded variation |
| `n` / `N` | Next / previous subject (when opened from a list) |
| `1`–`7` | `!  ?  !!  ??  !?  ?!  □` (toggle) |
| `a` | Annotation menu: all move, position and evaluation symbols (`+−  ±  ⩲  =  ∞  ⩱  ∓  −+` …) |
| `m` | Mark: `g` good · `d` dubious · `b` bad · `c` colour · `x` clear |
| `c` / `C` | Comment on this move / on the position (root) |
| `t` / `T` | Move tags / position tags (phase 4) |
| `⇧↑ ⇧↓` | Move the variation up / down |
| `P` | Promote to main line |
| `d` | Delete from here (undoable) |
| `p` | Puzzle: `s` start here · `x` solution ends here · `a` also correct · `o` all answers count · `r` ready for training · `d` discard puzzle |
| `e` | Engine on / off (also in the Engine pane, in any mode but Train) |
| `↵` | Play the engine's best move (also in the Engine pane) |
| `y` / `Y` | Copy FEN / PGN |
| `u` / `U` | Undo / redo: every change of the analysis, also after a reload (the journal, 09 §5) |

With the board pane focused, its own keys (06): `f` flip · `S` setup (correcting the position keeps the analysis when
its moves stay legal, else asks `y / n` before dropping them) · `i` type a move · `q` square tool · `⌫` clear the
drawings on this move. In the comment field (Insert): `⌥K Q R B N P` insert ♔ ♕ ♖ ♗ ♘ ♙ (with `⇧` the black
pieces), `mod+↵` saves and leaves the field (leaving it saves too). In the Engine pane, clicking a move adds the
line up to it to the analysis.

Without a key, command line only: `:analyse <title>` (open a position; the completions search titles and sources),
`:engine.lines <1–5>`, `:new-position` (the position after this move becomes a position of its own, linked to its
game; `:new-position moves` takes the continuation along), `:untag-move`, `:detect` (python-chess tag detection, also
on a Library selection), `:evaluate [depth]` (the engine over the main line, for the eval graph), `:moments` (the
key moments of the main line as move tags: the local engine or the stored evaluations, python-chess, the
annotator's symbols; 11 §1), `:lichess` (open the position in lichess).

## Collect

| Key | Where | Command |
|---|---|---|
| `S` | board | Switch Setup ↔ Solution |
| Setup keys | board, Setup | 06 §4 |
| `h` | board, Solution | Back a move (a new move replaces the rest of the line) |
| `mod+↵` | anywhere in Collect | Save & next (diagram + 1, an empty board in Setup) |
| `mod+shift+↵` | anywhere in Collect | Save & open in Analyse |
| `g d` | anywhere in Collect | Go to the duplicate |
| `s` | session pane | Source: completion from the sources; a new name makes a new source |
| `+` / `-` | session pane | Page up / down |
| `↑ ↓` | session pane | Diagram number |
| `i` | session pane | Edit page, diagram number or the title pattern (`{source} Nr. {n}`, `{page}`) |
| `t` / `⌫` | session pane | Add a tag for the next positions / remove the last one |
| `1`–`9` | session pane | Toggle tag preset N (`:preset-save <name>` keeps the session's tags) |
| `r` | session pane | Ready for training on/off |

A save of a duplicate asks: `m` merge into it (tags, source, the solution as a variation) · `s` save anyway · `g` go
there · `Esc`. Pasting (`mod+v`) offers `c`: one FEN goes onto the board in Setup, a list of FENs is saved at once
with the session's source and tags, `i` imports a PGN (below).

**Import** (a pasted PGN, `i`; or `:import` with a file): `j k` move · `x` (de)select · `a` all / none · `r` puzzles
straight into training · `↵` import · `Esc` cancel. Duplicates are marked and left out. `u` afterwards moves what
was imported to the trash.

## Library

| Key | Command |
|---|---|
| `1`–`6` | Positions · Games · Puzzles/cards · Players · Sources · Tags |
| `/` | Query bar |
| all list keys | above |
| `t T d r a y e` | Bulk keys (lists above); on players, sources and tags `d` deletes the ones nothing uses |
| `c` | Edit the selected players, sources or tags (`:edit field=value …`) |
| `↵` | Positions and puzzles open in Analyse (the results are the subject list), games too; a player, source or tag shows its positions or games |
| Filters pane: `↵` | Toggle the facet (adds/removes the query term) |
| Filters pane: `-` | Exclude the facet (`-motif:…`) |

In the query bar: `⇥` takes the completion (keys, tags with their place in the hierarchy, sources, players, saved
queries), `↑ ↓` choose one, `↵` goes to the results, `Esc` leaves the bar. `:save-query <name>`, `:trash-empty`,
`:import`, `:edit`, `:new-tag`, `:new-player`, `:new-source`, `:delete`, `:player-link "<name>" [@player]` (04 ·
Library).

## Stats

| Key | Command |
|---|---|
| `j k` | Previous / next chart (the focused chart has the accent border) |
| `h l` · `H L` | Step through the data points of the focused chart · first / last point (the read-out row shows it) |
| `↵` | Drill down: a tag, source or difficulty → the Library; a weak spot → a Streak on it |
| `t` | Table view of the chart |
| `1`–`5` | Period: 7d · 30d · 90d · 1y · all (kept with the mode's state) |
| `] [` · `g <key>` | Sections: `o` overview · `l` pattern library · `c` card stages · `r` retention · `m` mastery · `w` weak spots · `b` records · `a` activity · `k` collection · `t` timeline |

## Settings

| Key | Command |
|---|---|
| `j k` | Rows (on a theme: live preview) |
| `h l` | Step the value (on/off, a choice, a number) |
| `↵` | Edit on the command line (`:set name=…`) · on a theme: choose it |
| `⌫` | Reset to the default |
| `/` | Filter settings |
| `K` | Keymap editor |
| Keymap editor: `↵` | Record new keys for the command (up to three, `↵` keeps, `Esc` cancels) |
| Keymap editor: `⌫` | Remove your binding, or unmap the default one |

Command line: `:set <name>=<value>` (tokens and settings), `:unset <name>`, `:theme-save <name>`,
`:theme-delete <name>`, `:theme-export`, `:map [@context] <keys> <command> [args]`, `:unmap [@context] <keys>`,
`:map-reset [keys]`.

## Board (any board pane)

| Key | Command |
|---|---|
| `h l` / `← →` | Back / forward through the line |
| `g g` / `G` | Start position / last move |
| `f` | Flip |
| `i` | Type a move (Move entry layer: `↵` play, `⇥` next candidate, `⌫` edit, `Esc` done) |
| `S` | Board editor (Setup layer) |
| `q` | Square tool: right-click fills a square |
| `⌫` | Clear the drawings of this move |
| `y` / `Y` | Copy FEN / PGN (also in the PGN/FEN view) |

## Board editor (layer `setup`)

| Key | Command |
|---|---|
| `1`–`6` · `p n b r q k` | Piece to place (`board.letters = de`: `b s l t d k`) |
| `c` | Switch colour · Shift+click places the other colour |
| `x` / `h` | Eraser / hand |
| `X` / `I` | Clear / initial position |
| `w` · `o` · `e` | Side to move · castling rights · en passant square |
| `f` / `M` | Flip / mirror |
| `D` | Diagram (allow an illegal position) |
| `a` | Fix what can be fixed |
| `S` / `Esc` | Done |

## Paste offers (after a paste, in the status line)

`b` show on a board · `a` analyse (a new position; a game's moves become its main line) · `c` collect (phase 4) · `i` import (phase 4) · `Esc` dismiss. Any other
key dismisses the offer and does what it always does.

See 06 for the board layers: Setup §4, Move entry §5, Solving §1.
