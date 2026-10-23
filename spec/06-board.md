# 06 · The board

The board is the one place where the mouse comes first. It must feel like lichess: instant, animated, precise.
Everything on it also has a keyboard path, but the keyboard path is secondary.

## 1 · Board layers

A board pane is always in one of these layers (shown by its frame colour and in its footer):

| Layer | Frame | Mouse | Keys |
|---|---|---|---|
| **Play** (default) | none (amber in a side variation) | click-click or drag to move; right-drag arrow; right-click circle | `f` flip, `i` move entry, `S` setup, `y`/`Y` copy |
| **Setup** | indigo | click places the palette piece; Shift+click the other colour; right-click empties; drag moves freely | palette keys, see §4 |
| **Move entry** | teal | (as Play) | type a move, see §5 |
| **Solving** (Train) | none, coordinates subdued | as Play, but wrong moves are rejected and scored | `h` hint, `s` solution, `i` entry |
| **Read-only** (previews, pinned comparisons) | dashed | right-drag drawings only (not saved) | `f`, `y` |

## 2 · Moving pieces

- Click-click and drag-and-drop both work, in every layer that allows moves.
- Legal destinations are shown as dots (capture: ring) when a piece is picked up; illegal moves snap back.
- **Client-side legality**: move generation runs in the browser (chess.js), so a move never waits for the server.
  The server (python-chess) is the authority when the move is saved and rejects anything that disagrees.
- Promotion: a small 4-piece picker on the promotion square (`q r b n` keys, or click). Holding `Alt` while
  dropping auto-queens (setting, default off).
- Animation: `motion-board` token (default 150 ms), 0 under reduced motion.
- Last move and check are highlighted (tokens `sq-lastmove`, `sq-check`).
- In Analyse, playing a move that exists in the tree goes there; a new move creates a variation (or extends the line
  at the end). The status line says `new variation C` with its undo key.

## 3 · Drawing (lichess conventions)

| Action | Result |
|---|---|
| Right-drag from square to square | arrow |
| Right-click a square | circle |
| `Shift` / `Alt` / `Shift+Alt` held | red / blue / yellow instead of green |
| Same drawing again | removes it |
| Left-click on the board (empty spot, no move) | clears drawings (setting: *only with* `Backspace` *on the board*) |
| Toolbar tool **Square** (`q` on the board footer) | right-click fills the square instead of circling it |

- In Analyse, drawings **save to the current move** automatically (debounced, undoable as one step per move).
- Engine arrows, hint arrows and the move-entry preview are separate overlay layers with their own tokens; they
  never mix with the user's drawings.
- Keyboard path: `:arrow e2e4 red`, `:circle f7`, `:clear drawings`. Drawing references in comments
  (`[[arrow:e2e4]]`) are created from the CommentEditor's *Drawing* button.

## 4 · Board editor (Setup layer)

Used in Collect, and in Analyse to correct a position (`S`).

| Key | Action |
|---|---|
| `1`–`6` or `p n b r q k` | choose pawn, knight, bishop, rook, queen, king (German `b s l t d k`: later, as a setting) |
| `c` | switch the colour of the chosen piece |
| `x` | eraser · `h` hand (drag pieces freely) |
| `X` | clear the board · `I` initial position |
| `w` | side to move (white/black) |
| `o` | castling rights menu (`K Q k q` toggle one right each) |
| `e` | en passant square (only plausible squares are offered) |
| `f` | flip · `M` mirror (swap colours and sides: train the same idea as the other colour) |
| `D` | diagram: allow an illegal position |
| `a` | apply the automatic fixes (impossible castling rights, impossible en passant, side to move) |
| `S`, `Esc` | leave Setup (refused while the position is illegal and not a diagram) |

- **Live validation**: the FenField under the board shows the FEN and any problem (`two white kings`, `side not to
  move is in check`, `castling K (rook not on h1) impossible · a: fix`). `a` fixes what can be fixed. (The fix key
  is `a`, not `f`: `f` flips.)
- **Diagrams** (illustrations) may be illegal; a toggle `Diagram` (`D`) turns validation into warnings.
- **Duplicates** are checked live against the library (canonical FEN incl. legal en passant only). The status line
  shows `duplicate of p1873 · g d go there`.
- The SetupPalette shows which piece and colour a click places, always.

## 5 · Move entry (typing moves)

`i` on any board in Play or Solving. On by default in **blind** training.

- Accepts SAN (`Nf3`, `exd5`, `O-O`, `0-0`, `e8=Q`, `e8Q`), German SAN (`Sf3`, `Lb5`, `Txe1`, `Dh5`), and UCI
  (`g1f3`). Case-insensitive for files; piece letters are upper case or unambiguous.
- While typing, the **candidate moves are previewed** as arrows (one arrow when unique, faint arrows for all
  candidates when ambiguous) and listed in the footer: `Nbd2  Nfd2`.
- `Enter` plays the move when it is unique, `Tab` cycles candidates, `Backspace` edits, `Esc` leaves.
- In Solving, `Enter` submits the move as the answer (wrong = scored as wrong, same as with the mouse).

## 6 · Copy and paste

| Key | Where | Does |
|---|---|---|
| `y` | board, Analyse, library cursor | copy FEN of the shown position |
| `Y` | Analyse, game rows | copy PGN (with comments, NAGs, drawings as `[%cal]`/`[%csl]`, and the root comment) |
| `:lichess` | Analyse | open the position in lichess (no key) |
| `Mod+V` | anywhere outside a text field | **paste detection**: FEN (also a bare placement), lichess analysis/editor link, PGN (one or many games), a list of FENs. The status line describes it and offers what fits, each with its key: `b show on a board · a analyse · c collect · i import` (offers of later phases are shown, disabled with their phase). This is the browser's own paste event, not a key binding, so the clipboard needs no permission. |
| `:paste` | anywhere | the same, reading the clipboard (the browser may ask for permission) |
| the PGN/FEN view | its field + `Mod+Enter` | the same, for text you type or edit first |

A lichess **game** link can't be read without the network: the app says so and asks for the PGN.

PGN paste into an existing analysis that would replace moves needs an inline confirmation (it is undoable, but
large).

## 7 · Engine

- `e` toggles the engine for the focused board's link group. It analyses every position the cursor moves to and
  stops when the mode is hidden or the pane closes.
- Shown in: EvalBar (next to the board), EngineLines pane, arrows for the top lines (fading by rank, setting).
- `Enter` plays the best move; clicking a move in EngineLines adds the line up to it.
- Hidden in Solving and Feedback until the puzzle is finished.
- Engine settings (depth, lines, threads, hash, arrows) in the EngineLines header ⚙ and in Settings → Engine.
- Where it runs: Stockfish WASM in a Web Worker by default; the local Stockfish binary through the server when it
  is configured (stronger, deeper). The EngineLines header shows which one is running.

## 8 · Look

All tokens, see 07 · Board tokens: square colours, highlight colours, arrow colours, coordinates (inside / outside /
off), piece set, board border, animation speed, legal-move dots on/off, last-move highlight on/off, annotation badges
on/off, blindfold (pieces invisible), silhouette (all pieces of one colour look the same, for training).

As built in phase 1: the squares are a CSS conic gradient of `sq-light`/`sq-dark` (a theme change needs no image);
coordinates sit inside the board (ranks on the right edge, files along the bottom) in the colour of the other
square; `board-coords = off` hides them (`outside` comes with the board settings in phase 6). Square highlights from
the square tool are chessground custom square classes (under the pieces), not SVG shapes.

## 9 · Library choice

| Option | Pros | Cons |
|---|---|---|
| **chessground** (lichess) | Exactly the lichess feel: drawing, animations, premove-ready, battle-tested | GPL-3.0 (fine for a personal app; matters if the app is ever distributed); needs a small build step or the prebuilt ESM file |
| **cm-chessboard** (used in the old app) | MIT, small, extensions for arrows and markers | Drawing interactions have to be written ourselves; less polished animation |

**Decision: chessground.** The app is free and GPL-3.0 (10 · decision 13), so its licence fits. It is wrapped in our
own `board` island, so the rest of the app never touches its API and the library could still be replaced later
without changes elsewhere.
