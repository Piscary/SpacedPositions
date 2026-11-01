# 15 · PGN annotations and the two-source eval bar

Plan (2026-10-31). Games pasted or imported from lichess (and ChessBase, chess.com, Scid) carry more than moves:
evaluations, clocks, drawings, judgement symbols and headers. The app should read all of it, show it where it helps,
keep the move tree clean, and write it back on export. lichess is the role model: its PGN is well documented and its
analysis board shows these things well.

## 1 · What a PGN can carry

| In the PGN | Example | Today | Planned |
|---|---|---|---|
| Evaluation | `{ [%eval 0.25] }`, `{ [%eval #-3] }`, `{ [%eval 0.25,23] }` (ChessBase: depth) | shown as comment text | stored per move (§2), on the eval bar and the eval graph, not in the tree |
| Clock | `{ [%clk 0:04:52] }` (time left after the move) | comment text | stored; Inspector: time left and time used; a time graph (§4) |
| Elapsed move time | `{ [%emt 0:00:08] }` (ChessBase, Scid) | comment text | stored like the clock |
| Drawings | `[%cal Ge2e4,Rd1d8]`, `[%csl Gd5]` | arrows and circles | unchanged |
| Judgement symbols | `$1`…`$6`, `$10`, `$13`, `$14`…`$19`, `$22`, `$36`, `$40`, `$132`, `$138`, `$146` | `$1`–`$7` | all of lichess's set, as symbols (! ? !! ?? !? ?! □ = ∞ ⩲ ⩱ ± ∓ +− −+ ⨀ ↑ → ⇆ ⊕ N) |
| lichess's computer comments | `{ Inaccuracy. Nf3 was best. }` plus a variation | comment and variation | kept; marked as computer comment (§3) |
| Headers | `Site`, `UTCDate`, `UTCTime`, `WhiteElo`, `WhiteRatingDiff`, `WhiteTitle`, `TimeControl`, `Termination`, `Variant`, `ECO`, `Opening`, `Annotator`, `FEN`/`SetUp` | most stored in `Game.headers` | known ones in their own fields (§5) |
| Study headers | `StudyName`, `ChapterName`, `ChapterURL`, `Orientation` | headers | title from the chapter, board orientation from `Orientation` |

A comment keeps its words; only the commands (`[%…]`) leave the text. A comment that held nothing but commands
disappears from the tree.

From a real lichess study export (`tests/fixtures/pgn/lichess-study-analysed.pgn`, names made up):

- lichess writes the judgement as a **suffix** (`27. c3?!`), not as `$6`; both forms are read, the tree shows the
  symbol.
- The computer comment and the evaluation are **two comments** after the move (`{ [%eval -0.8] } { Inaccuracy. Nf5
  was best. }`), followed by the best line as a variation.
- `[%eval #-1]`: mate in one for Black; `[%eval #0]`: the side to move is mated (the bar is full, the label `#`).
- The last comment can carry the outcome (`{ 0-1 Black wins by checkmate. }`) while the header says `Result "*"`
  (a study): the game's result is taken from that comment when the header has none; the comment is shown as the
  end of the game, not as a move comment.
- A study has no clocks; `Annotator` is a lichess profile link, `ChapterURL` the study chapter (both shown as links
  in the Inspector, nothing more is fetched).

## 2 · Data

`Node` gains (migration, all nullable): `pgn_eval_cp`, `pgn_eval_mate`, `pgn_eval_depth` (the evaluation from the
file, from white's side, separate from the engine's `eval_*`), `clock_ms` (time left after the move), `emt_ms` (time
used, when the file says so; otherwise computed from two clocks and the increment of `TimeControl`).
`Position`/`Game` get `evals_from` (text: "lichess", the `Annotator`, or "PGN"), shown as the source's name.

Export (`board.copypgn`, packs, PGN export) writes `[%eval]` and `[%clk]` back after the comment text, so a game
goes out as it came in. Packs carry the fields in their node records (pack format: a new optional key, older apps
ignore it).

## 3 · The move tree and the Inspector

- The tree shows no command text. An evaluation never takes room in the tree.
- **lichess's computer comments** (`Inaccuracy. … was best.`, `Mistake.`, `Blunder.`) are recognised by their exact
  words and shown in a lighter style with a ⚙ mark; a setting `analysis.computer-comments` (show · fold · hide,
  default fold: one line `⚙ Inaccuracy`, the rest on `z`) keeps long analysed games readable. Their variations stay.
- **Inspector**, section *Move*: `eval +0.25 (lichess) · engine +0.31 d24`, `clock 4:52 · used 0:08`.

## 4 · The eval bar with two sources

Two evaluations can belong to a position: the **file's** (lichess's Stockfish when the game was analysed there) and
the **engine's** (the one running now). They can differ (depth, version, settings), and the user must always see
which one the bar shows.

| What is there | The bar |
|---|---|
| engine only | as today: solid fill |
| file only | the same bar, **hatched** fill (a diagonal stripe pattern in the same colours) and a small label at the end away from the number: `L` for lichess, `F` for any other file |
| both | **split lengthwise**: left half the engine (solid), right half the file (hatched), each with its own height; the full bar width is unchanged (spec 06: the board keeps its size) |

- The difference is never colour alone: pattern and label (accessibility, 07 · contrast).
- Hover or the board's status line reads both: `engine +0.31 (d24) · lichess +0.25`.
- Setting `board.evalbar`: `auto` (both when both exist) · `engine` · `file` · `off`.
- The eval graph draws the file's evaluations as a dashed line, the engine's as a solid one; key moments
  (`g m`) use the engine's when there, else the file's.
- A mate shows as today (`#3`), in either half.

## 5 · Headers in their own fields

`Game` already has white, black, Elo, event, site, date, round, result, ECO, annotator; every other header stays in
`headers`, shown in the Inspector and written again on export. Decided on day 3: no new fields until the Details pane
(spec 16) needs them to edit; the Inspector links a header that is a web address (`ChapterURL`, a lichess `Site`).
**Variants**: only standard chess and *From Position* are imported; any other `Variant` (Atomic, Crazyhouse …, and
Chess960 for now: its castling is written differently) is refused with the reason in the import preview.

## 6 · Tests (Junie)

A fixture set in `tests/fixtures/pgn/`: a lichess analysed game (evals, clocks, computer comments, variations), a
lichess study chapter (drawings, `Orientation`), a ChessBase export (`[%eval 0.25,23]`, `[%emt]`), a Chess960 game,
an unsupported variant. Round trip: import → export → import gives the same tree, evals and clocks.

## 7 · Order of work

1. Parsing and storage (§1, §2) with the fixtures and the round trip. *Claude*
2. The tree and Inspector (§3), the computer-comment setting. *Claude*; guides and translations *Junie*
3. The eval bar and graph (§4). *Claude*; screenshots in all themes and a review of the hatched pattern's contrast
   *Junie*
4. Headers (§5). *Claude*
