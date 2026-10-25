# 11 · Data model and the query language

What the app stores and how the Library finds it. Phases 0–3 built Position (minimal), Puzzle, Card, Session,
Attempt and the analysis tree (Node, JournalEntry); this document is the contract for phase 4 (Library + Collect),
which completes the objects of 04 · *Objects the modes work with*. Phase 7 (migration) maps the old app onto it.

Rules for every model:

- **Short ids** for people: `p123`, `g12`, `z45`, `c45.2`, `r88`, `s7`, `@tal`, `#gabel`, `q:name` (04). They are
  the integer primary key with a prefix (tags, players and queries use their key). UUIDs stay for packs (09 §12).
- **Nothing the user made is deleted by a cascade.** Deleting moves things to the **trash** (`deleted_at`);
  emptying the trash (by hand only, `:trash empty`, decision 19) is the only permanent delete and needs a
  confirmation (02 §7). Training history (Attempt,
  Session) is never deleted: models that history points to use `PROTECT`.
- Every change from the Library or Collect goes through a command with an inverse (09 §5), so `u` undoes bulk edits.

## 1 · Objects

### Position

What phase 2 built, plus:

| Field | |
|---|---|
| `description` | The task as shown with the diagram (Markdown); `objective` stays the one-line task (`Mate in 2`) |
| `notes` | Private working notes (Markdown) |
| `source` → Source, `source_page`, `source_ref` | Where it is from: page(s) in a book, puzzle id or URL path on a website. Replaces the text field `source` (kept as `source_text` for what can't be matched) |
| `tags` (through PositionTag) | See *Tags* |
| `difficulty_override`, `difficulty_auto`, `difficulty` | 1–5. `difficulty` is the override, else the automatic value (the highest `base_difficulty` of its objective and motif tags; phase 5 adds how hard it was to solve) |
| `diagram` | An illustration: shown, never trained, may be illegal |
| `game` → Game, `game_node` → Node | When it was taken from a game, the move it was taken at |
| `deleted_at` | In the trash |
| `updated_at` | |

Derived on save, indexed for the query language: `side` (w/b), `material` (e.g. `KQRvKR`), `pieces` (count).
`has:analysis`, `has:puzzle`, `has:comment` and `is:flagged` (a puzzle flagged in Train) are subqueries, so they are
never out of date. `task` is the objective line: `objective` when set, else the task of its objective tag for the
side that solves (`White to play and mate in 2`).

The analysis tree (Node) and `canonical` stay as built in phase 3.

### Game

| Field | |
|---|---|
| `white`, `black` → Player (nullable) and `white_name`, `black_name` (as in the PGN) | |
| `white_elo`, `black_elo`, `result` (`1-0`, `0-1`, `1/2-1/2`, `*`), `date` (PGN form, `1956.??.??`), `event`, `site`, `round`, `eco`, `annotator` | The seven-tag roster and the common extras |
| `headers` | All other PGN headers, as they were |
| `start_fen` | `SetUp`/`FEN` games start elsewhere |
| `pgn` | The PGN as imported (for the export and for re-import checks) |
| `source` → Source, `source_ref`, `notes`, `tags` (through GameTag), `deleted_at`, `created_at`, `updated_at` | |

A game has a move tree like a position. **Node gets a `game` foreign key next to `position`; exactly one of the two
is set** (a check constraint), and `tree.py` works on "the owner" of a tree. The journal (JournalEntry) gets the same
pair. Analyse opens a game like a position (05 · MoveTree), with the game's headers in the Inspector and the eval
graph (phase 5) below the board.

Each node can hold the engine's evaluation of the position after it (`eval_cp` or `eval_mate` from white's side,
`eval_depth`): `:evaluate` fills them for the main line, the eval graph shows them. They are not part of the journal
(the engine can always compute them again).

`:new position` (08) on a move of a game makes a Position from the FEN after that move, with `game` and `game_node`
set; its own analysis starts empty (`:new position --with-moves` copies the game's continuation as its main line).

### Tags

Tags are grouped in **fields**. The starter vocabulary is the old app's (decision 18): 10 fields, 205 tags,
German names with English names and aliases for search (decision 6: English UI, German tags).

| Model | Fields |
|---|---|
| `TagField` | `key` (`motif`, `mate`, `goal`, `phase`, `strategy`, `endgame`, `technique`, `level`, `moment`, `custom`), `name`, `name_en`, `selection` (single: one tag of the field per object · multi), `on_positions`, `on_moves`, `color` (a chart/chip token, `--chart-1` … `--chart-6`), `order` |
| `Tag` | `field`, `key` (slug, unique, from the old app: `fork`, `knight-fork`), `name` (German: `Gabel`), `name_en` (`Fork`), `aliases` (more search terms, any language), `parent` → Tag (hierarchy: Doppelangriff → Gabel → Springergabel), `description`, `task` and `task_en` (for objective tags: the printed task, `{side}` = the side to move), `base_difficulty` (1–5), `weight` and `analysis_weight` (for the automatic difficulty), `order` |
| `TagDismissal` | A tag the user removed from a position or a move: `position` or `node`, `tag` (detection respects it) |
| `Position` (search fields) | `search` (the folded title, task, description, notes and citation, kept up to date on save), `page_number` and `ref_number` (the first number of the page and of the reference: sorting a book in its order) |
| `PositionTag`, `NodeTag`, `GameTag` | the link, plus `origin` (`manual` · `auto` · `suggested`), `detector` (which detector set it), `evidence` (`Ne5 forks Kg8, Qd7`); the unique (owner, tag) index is the only index on the owner |
| `TagPreset` | A named set of tags for Collect (`1`–`9` in the entry session): `name`, `tags`, `order` |

- **Names**: a query or `:tag` takes the key, the German or English name or an alias (`motif:gabel`, `motif:fork`);
  completions put exact matches first.
- **Hierarchy**: a query for a tag matches its descendants (`motif:gabel` finds Springergabel too); `=` matches the
  tag alone (`motif:=gabel`). Chips show the tag's name; the path shows on hover and in the completion.
- `single` fields: setting a tag replaces the other tag of that field (Phase: Opening → Endgame).
- Objective tags (`goal`) fill `objective` when it is empty (`Matt in 2`, from `task`).
- **Detection** (`:detect`, and on every Collect save and imported puzzle): python-chess looks at the position and
  the main line of its analysis (`library/detect.py`, `sequences.py`: phase, endgame type, objective, mating
  patterns, motifs). Reliable findings become tags with `origin = auto` and their evidence; the others are
  *suggestions* (`origin = suggested`), shown dashed with a `?` until accepted (a click, or `:tag`). The rules of
  storing: a tag the user removed is never detected there again (`TagDismissal`, also for move tags; adding it back
  by hand lifts it; undoing a tag is not a dismissal), a manual tag is never touched, and detection withdraws only the
  tags it set itself. The solution's first moves get move tags too.
- **Moments** (`:moments` in Analyse, phase 6; `library/moments.py`): the key moments of a game's or an analysis's
  main line as move tags of the `moment` field, from the old app's three detectors. The engine, Lichess style, in
  winning chances (wc = 2 / (1 + e^(−0.00368208·cp)) − 1 for the mover): a drop of ≥ 0.3 blunder, ≥ 0.2 mistake,
  ≥ 0.1 inaccuracy; a missed win (≥ 0.6 → ≤ 0.2); a turning point (≥ +0.3 → ≤ −0.3); with the local engine (two
  lines a position) also the only move (best by ≥ 0.3 and played, with at least 4 legal moves), the critical
  moment (missed) and the brilliant move (an only move that sacrifices, the game not yet won). Without a local engine
  the evaluations `:evaluate` stored are used. python-chess adds a missed mate in one, a move that allows mate in one
  when it could be avoided, and tactical explosions (3 captures in 4 plies); the annotator's symbols become moments
  too (`!!` brilliant … `□` only move) and win over the other sources. Stored with `detector = moments` by the
  rules above (dismissals respected, manual tags untouched, only its own tags withdrawn).
- **Editing** (phase 6): tags, sources and players are edited in the Library (04 · Library): new tags, names,
  aliases, the hierarchy (no loops), weights and base difficulty; deleting only what nothing uses.
- **Difficulty** (automatic): the weighted base difficulty of the position's tags (`weight`), plus at most one step
  from the move tags of its analysis (`analysis_weight`, each tag once, auto tags at 0.8); rounded to 1–5. The
  override wins. Both weights come with the starter vocabulary.

### Source

One model instead of the old Book/Website split:

| Field | |
|---|---|
| `kind` | `book` · `website` · `own` (own analysis) · `public` (public domain, no source needed) · `course` |
| `title`, `authors`, `year`, `publisher`, `isbn`, `url`, `notes`, `short` | `short` is the citation stem (`Polgár 5334`), shown in lists |

Positions and games point to a source with `page` and `ref`. The Collect entry session remembers source, page and
the next diagram number (04 · Collect).

### Player

`name` (`Tal, Mikhail`), `aliases` (other spellings and online handles), `role` (`me` · `student` · `model` (role
model) · `opponent` · empty), `title` (GM, IM …), `federation`, `fide_id`, `born`, `notes`. Imported games are
matched to players by name and aliases (case and diacritics ignored, `Tal, M.` matches `Tal, Mikhail` when the
initial fits); unmatched names stay text on the game until `:player-link` (`is:unlinked` lists those games).

### Saved query

`SavedQuery`: `key` (`q:gabel-hard`), `name`, `collection` (positions, games, puzzles …), `query` (the string),
`order`. A saved query works anywhere a query does: in the Library (`/q:gabel-hard`), as the filter of a custom
training session, and in other queries (`in:q:gabel-hard`).

## 2 · Duplicates

- **Positions** are the same when their `canonical` FENs are equal (placement, side, castling, legal en passant).
  Collect checks while you set up (the board's strip and the entry session say `duplicate of p1873`, `g d` goes
  there); saving a duplicate asks `m` merge · `s` save anyway · `g` go there · `Esc` (a question, answered with
  HTTP 200, not an error). Merging adds tags, the source (if the position has none) and the new solution as a line.
- **Games** are the same when the players' names, the result and the first 40 plies agree (a hash), or when the PGN
  is identical. Import marks them and skips them unless chosen.
- **Puzzles** in an import are duplicates when their position is and their main line starts with the same move.

## 3 · The query language

The query string is the single source of truth of a Library search: the filter pane writes into it, the QueryBar
tokenises it (05 · QueryBar), saved queries store it.

### Grammar

```
query    = term { " " term }                    -- terms are AND-ed
term     = [ "-" ] ( keyterm | tagterm | text )  -- "-" negates
keyterm  = key ":" [ op ] values                 -- motif:gabel  diff:>=3  white:tal
values   = value { "," value }                   -- motif:gabel,spiess = gabel OR spiess
op       = ">" | ">=" | "<" | "<=" | "="         -- numbers and dates; "=" for an exact tag
range    = number ".." number                    -- diff:2..4  year:1950..1960
tagterm  = "#" tagkey                            -- #gabel = a tag in any field
text     = word | '"' words '"'                  -- title, task, description, notes, citation, source, tags, comments
group    = "(" query { " or " query } ")"        -- (motif:gabel or mate:anastasia) diff:>=3
```

Matching is case- and accent-insensitive (`spiess` finds Spieß). Unknown keys and values are underlined with the
reason and ignored, so a half-typed query still shows results. `sort:` is a term too.

**Words** (phase 7 cleanup): each word, or quoted phrase, must occur somewhere: the title, task, description, notes or
citation (the position's folded `search` column), the source (title, short name, authors, publisher), a tag (name,
English name, alias; not suggestions) or a comment of the analysis. Two words need not be next to each other
(`only good`); a quoted phrase must (`"only good"`). A `*` is ignored (`fork*` = `fork`): words match anywhere already.

**Sources**: `src:` with a source's whole title or short name (`src:"Chess Monkeys Level 1"`), or its id (`src:s5`),
is exactly that source: the filter pane and the completion write this form. Any other value matches every source
that has all its words, in any order, in its title, short name, authors or publisher (`src:monkeys`, `src:polgar`,
`src:"monkeys 2"`); a citation that is only text (an import that matched no source) is matched by all the words too.

### Keys

| Key | Collections | Meaning |
|---|---|---|
| *field key* (`motif`, `mate`, `goal`, `phase`, `strategy`, `endgame`, `technique`, `level`, `moment`, `custom`) | positions, games, puzzles | A tag of that field (with descendants) |
| `tag`, `#` | positions, games, puzzles | A tag of any field |
| `diff` | positions, puzzles | Difficulty 1–5 |
| `side` | positions, puzzles | `w` / `b`: the side to move |
| `src`, `page`, `ref` | positions, games | Source (exactly, or by its words: above), page, reference |
| `has`, `no` | positions | `solution` (a puzzle in training), `analysis`, `puzzle` (also drafts), `comment`, `source`, `tags`, `game` |
| `is` | all | `diagram`, `flagged`, `trash` (only in the trash), `draft` (puzzles not in training) |
| `material`, `pieces` | positions | `material:KRvKR` (white first), `pieces:<=7` |
| `fen` | positions | Placement prefix or full FEN |
| `created`, `updated` | all | Dates: `created:>2026-10-01`, `created:<7d` (days ago) |
| `white`, `black`, `player` | games | Player name or `@key`; `player` is either colour |
| `result`, `eco`, `event`, `year`, `elo` | games | `result:1-0`, `eco:B9`, `elo:>=2600` (either player) |
| `due`, `state`, `lapses`, `success`, `last`, `attempts` | puzzles, cards | Training: `due:today`, `state:new`, `lapses:>=2`, `success:<50%`, `last:>30d`, `attempts:0` |
| `game` | positions | Taken from this game (`game:g12`) |
| `in` | all | In a saved query (`in:q:name`) or a pack (phase 8) |
| `sort` | all | positions: `created` (default newest first), `updated`, `difficulty`, `title`, `source` (title, then page, then diagram number: a book in its order), `diagram`, `page`; puzzles: the same plus `due`, `success`, `lapses`, `last`; games: `year`, `white`, `black`, `event`; players `name`, `role`; sources `title`, `kind`; tags `name`, `field`. `-` reverses (`sort:-difficulty`). Page and diagram numbers sort as numbers (Nr. 9 before Nr. 10) |

The Library's collections: `1` positions · `2` games · `3` puzzles (one row per puzzle, its cards inside) · `4`
players · `5` sources · `6` tags. Players, sources and tags take text and `sort:` only.

### Implementation

`library/query.py` parses the string into a small AST (with positions for the QueryBar's underlines), then compiles
it to Django `Q` objects per collection. The parser is pure Python and unit-tested on its own; completions come from
`GET /library/complete/?q=…&at=…` (keys, tag keys and names, sources, players). Counts per facet for the filter pane
come from the same compiled query without the facet's own term; the status counts are one query (filtered counts).
Conditions on related rows (tags, moves, puzzles, cards) compile to `IN (subquery)`, not `EXISTS` per row: SQLite
computes the subquery once (4–20× faster at 50,000 positions). `T` (train these) and `a` (analyse these) keep the
query's order when it has a `sort:`; the Library's results are grouped (and foldable) when the sort is a field with
few values (difficulty, source, year, a player, event, role, kind, field).

## 4 · PGN import

- `Mod+V` or `:import` with a PGN (one game or a file of thousands) opens the **Import** state in Collect (04): a
  list of what was found, with duplicates marked; `x` (de)selects, `Enter` imports.
- A game keeps variations, comments, NAGs and lichess drawings (`[%cal Ge2e4]`, `[%csl Rd5]`) in its tree.
- Games with a `FEN` header and a short main line (≤ 16 plies) and no players are offered as **puzzles**: a
  Position with the FEN, the line as its analysis, and a puzzle starting at the root (a draft unless `r` marks the
  import ready for training).
- Headers map onto Game fields; `Annotator`, `PlyCount` and others stay in `headers`. Players are matched (§1).
- An import runs while the status line says *Importing…* (up to 5,000 games or 20 MB at once, with the list to
  choose from). A bigger file, or a paste with more games (asked first), is uploaded as it is into the data folder
  and imported **in the background** (phase 7): a game at a time, in batches of 200 in short transactions so the app
  stays usable, duplicates left out; the status line shows how far it is. Afterwards the Library shows what arrived
  (`created:<1d`). An import is one step of the undo stack: `u` moves what it added to the trash (`U` brings it back).
- Text that holds neither moves nor a `FEN` header isn't a game and is skipped.

## 5 · From the current models (phase 4 migrations)

- `Position.source` (text) → `source_text`; `Position.tag_names` → real tags, matched by name or alias against the
  vocabulary (unmatched names become `custom` tags).
- `:puzzle` now makes its puzzle through the analysis (the line becomes the main line from the start, the solution
  ends where the line ends); the same line again returns the same puzzle, a different line on a position that has
  a puzzle is refused (edit it in Analyse). There were no older `:puzzle` puzzles to convert.
- Untouched default layouts move to the new defaults (`core/layouts.OLD_DEFAULTS`): a saved layout that is exactly
  an earlier default (the Library with its demo list) becomes the current one; changed layouts stay.
- Node and JournalEntry get the `game` owner (§1 Game).
- All migrations are additive; `spos` backs up the database before migrating (09 §11).

## 6 · From chess-study-manager (phase 7)

`spaced_positions/csm.py`, run with `spos import-csm <db.sqlite3> [--dry-run]`, `manage.py import_csm`, or from
Settings → Data (the path is filled in when an old database sits next to the app; `⌘↵` shows what would be added,
`y` imports it). The old database is copied (with what is still in its WAL) and only that copy is read; this app's
database is backed up first (`<data folder>/backups/db-before-csm-…`).

| Old | New |
|---|---|
| `sources_book`, `sources_website` | `Source` (kind book/website); a phase 4 source titled "Authors, Title" is matched and gets the title and the authors in their own fields |
| `positions_player` | `Player` (aliases kept; matched by name) |
| `positions_game` + its `variationnode`s | `Game` with its tree (headers, Elo, the original PGN, notes and source notes) |
| `positions_position` + its `variationnode`s | `Position` with its tree: comments, NAGs, drawings, marks, colours; the citation as source, page and `Nr. <ref>`; a position from a game keeps its game and move |
| `positiontag` · `nodetag` | `PositionTag` · `NodeTag` with origin, detector and evidence; tags the vocabulary doesn't have are named in the report and left out |
| `tagsuggestion` open · dismissed | a suggested tag · a `TagDismissal` |
| `boards_board`/`column`/`positioninboard` | not migrated: the pipeline is the filters here (`has:analysis`, `has:solution`, `is:draft` …); the tags an earlier import made of it are removed by migration `library 0007` |
| `trainingpuzzle` · `trainingcard` | `Puzzle` (made through the analysis, as `:puzzle` does) · its cards, matched by their line |
| `trainingsession` · `trainingattempt` | `Session` (custom → review with the old options) · `Attempt` |
| `core_activityevent` (analysis, annotation, drawing, board moves) | `stats.ActivityLog`, counted in Stats' activity; positions and games count by their creation date |
| milestones | found again from the joined history (`sync_achievements`), logged as seen |

Every object keeps its origin (`csm-position:12`, `csm-attempt:5378` …), so the import can run again and adds only
what is new in the old app since. It never deletes or overwrites what was done here: an analysis changed here (its
journal) keeps its moves, otherwise old moves that are missing are added; empty text fields are filled in; a tag
removed here stays removed; a card trained in both apps takes the schedule of the app that saw it last, and its
counters are counted again from the joined attempt log. Publishing (documents) is not migrated (out of scope).
