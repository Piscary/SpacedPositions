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
graph · `l` library · `q` queue · `c` chart · `n` notes · `p` PGN/FEN text · `t` tags.

---

## Lists, tables, grids (any view)

| Key | Command |
|---|---|
| `j k` / `↓ ↑` | Cursor down / up (grids: `h l` / `← →` too) |
| `g g` / `G` | First / last |
| `↵` | Open (default command of the object, see 05 matrix) |
| `o` | Open in a split to the right (linked) |
| `x` | Toggle selection of the cursor row |
| `v` | Visual (range) selection |
| `mod+a` | Select all results |
| `t` | Tag (selection or cursor row) |
| `d` | Move to trash / delete (undoable) |
| `y` | Copy (FEN for positions, PGN for games) |
| `T` | Train these |
| `a` | Analyse these (as a subject list, `n`/`N` in Analyse) |
| `e` | Export |
| `s` | Sort: then the column's key shown in the header |
| `z` / `Z` | Fold the group under the cursor / all groups |

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
| `r` | Review |
| `1`–`6` | Quick sessions (Storm 3′, Storm 5′, Streak, Streak ♥3, weakest motifs, again) |
| `a` | Continue the last analysis |
| `c` | Continue collecting (last source) |
| `p` | Focus the paste box |

## Train

**Launcher**, pane *Sessions*: `r` Review · `1` `2` `3` Storm 3′/5′/10′ · `4` Streak · `5` Streak ♥3 · `6` Blind
streak · `7` Weakest motifs · `8` Again.
**Launcher**, pane *Custom* (rows mirror keyboard rows): Mode `1 2 3` · Look `q w e` · Side `a s d f` · Lives
`z x c v` · `o` first move only · `/` filter · `↵` start.

**Solving**

| Key | Command |
|---|---|
| mouse | Play the move |
| `i` | Type the move (on by default in blind) |
| `h` | Hint (1st: piece, 2nd: move); counts as missed |
| `s` | Show the solution (give up) |
| `f` | Flip |
| `⎋` | Pause line: `↵` resume · `q` quit · `r` restart (Storm: `quit? y / n`) |

**Feedback**

| Key | Command |
|---|---|
| `↵` | Next puzzle |
| `← →` | Replay the solution |
| `a` / `A` | Analysis in a linked split / go to Analyse mode |
| `t` | Tag the position |
| `!` | Flag the puzzle as broken |
| `e` | Edit the puzzle in Analyse |
| `r` | Retry (not scored) |

**Result**

| Key | Command |
|---|---|
| `r` | Run the same session again |
| `j k`, `↵` | Puzzles of the session, open one in Analyse |
| `m` | Review the missed ones |
| `a` | Analyse the missed ones (subject list) |
| `l` | Back to the launcher |
| `y` | Copy the result as text |

## Analyse

Mode-level: these work whether the board, the moves or the inspector pane has focus (not in Insert).

| Key | Command |
|---|---|
| `h l` / `← →` | Back / forward |
| `j k` / `↓ ↑` | Other variation at this move |
| `g g` / `G` | Start position / end of the line |
| `g p` / `g n` | Previous / next branch point |
| `M` | Back to the main line |
| `n` / `N` | Next / previous subject (when opened from a list) |
| `1`–`7` | `!  ?  !!  ??  !?  ?!  □` (toggle) |
| `a` | Annotation menu: all move, position and evaluation symbols (`+−  ±  ⩲  =  ∞  ⩱  ∓  −+` …) |
| `m` | Mark: `g` good · `d` dubious · `b` bad · `c` colour · `x` clear |
| `c` / `C` | Comment on this move / on the position (root) |
| `t` / `T` | Move tags / position tags |
| `⇧↑ ⇧↓` | Move the variation up / down |
| `P` | Promote to main line |
| `d` | Delete from here (undoable) |
| `p` | Puzzle: `s` start here · `x` solution ends here · `a` also correct · `o` all answers count · `r` ready for training · `d` discard puzzle |
| `f` | Flip |
| `e` | Engine on / off |
| `↵` | Play the engine's best move |
| `S` | Setup (correct the position) |
| `i` | Type a move |
| `q` | Square-drawing tool on/off |
| `⌫` | Clear the drawings on this move |
| `y` / `Y` | Copy FEN / PGN |

Without a key, command line only: `:detect` (detect tags), `:lichess` (open in lichess), `:new position` (position
from this move of a game), `:paste pgn`.

## Collect

| Key | Where | Command |
|---|---|---|
| `S` | board | Switch Setup ↔ Solution |
| Setup keys | board, Setup | 06 §4 |
| `⌫` | board, Solution | Take back the last solution move |
| `mod+↵` | anywhere in Collect | Save & next |
| `mod+shift+↵` | anywhere in Collect | Save & open in Analyse |
| `g d` | board | Go to the duplicate |
| `s` | session pane | Source (combobox) |
| `+` / `-` | session pane | Page up / down |
| `↑ ↓` | session pane | Diagram number |
| `t` | session pane | Title pattern |
| `1`–`9` | session pane | Toggle tag preset N |
| `r` | session pane | Ready for training on/off |

## Library

| Key | Command |
|---|---|
| `1`–`6` | Positions · Games · Puzzles/cards · Players · Sources · Tags |
| `/` | Query bar |
| all list keys | above |
| Filters pane: `↵` | Toggle the facet (adds/removes the query term) |
| Filters pane: `-` | Exclude the facet (`-tag:…`) |

## Stats

| Key | Command |
|---|---|
| `j k` | Previous / next chart |
| `h l` | Step through the data points of the focused chart |
| `↵` | Drill down |
| `t` | Table view of the chart |
| `1`–`5` | Period: 7d · 30d · 90d · 1y · all |

## Settings

| Key | Command |
|---|---|
| `j k` | Rows |
| `h l` | Change the value (segmented, stepper, list with live preview) |
| `↵` | Edit / apply |
| `/` | Filter settings |
| `K` | Keymap editor |

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
| `1`–`6` · `p n b r q k` | Piece to place |
| `c` | Switch colour · Shift+click places the other colour |
| `x` / `h` | Eraser / hand |
| `X` / `I` | Clear / initial position |
| `w` · `o` · `e` | Side to move · castling rights · en passant square |
| `f` / `M` | Flip / mirror |
| `D` | Diagram (allow an illegal position) |
| `a` | Fix what can be fixed |
| `S` / `Esc` | Done |

## Paste offers (after a paste, in the status line)

`b` show on a board · `a` analyse (phase 3) · `c` collect (phase 4) · `i` import (phase 4) · `Esc` dismiss. Any other
key dismisses the offer and does what it always does.

See 06 for the board layers: Setup §4, Move entry §5, Solving §1.
