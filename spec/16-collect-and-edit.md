# 16 · Collect and edit: games, players, sources

Plan (2026-10-31). Collect gets material in fast, but only positions. A pasted game without names can't be fixed,
players can't be created or edited outside the Library's bulk edit, and a source can only be made while entering a
position. This plan turns Collect into the place where **anything is made or corrected**, with one form pattern for
every kind, reachable from wherever the thing shows up.

## 1 · What exists (and stays)

- The models have the fields already: `Game` (white, black, Elo, event, site, date, round, result, ECO, headers),
  `Player` (name, aliases, role me · student · role model · opponent, title, federation, FIDE id, born, notes),
  `Source` (kind, title, short citation, authors, year, publisher, ISBN, URL, notes), `Position` (title, source,
  page, diagram, objective, difficulty). Only `Game` gains the header fields of spec 15 §5.
- `library.edit` edits selected players, sources and tags in bulk; Collect's entry session makes positions with a
  source, page and diagram number. Both stay.

## 2 · One pattern: the Details pane

A new view **Details** (`d` in the view picker) shows the fields of **one thing**: the subject of its link group
(the Library row under the cursor, the open analysis, the game of the board). It is built like Settings (spec 04 ·
Settings), so it needs no new habits:

- one **row per field**: `j`/`k` move, `↵` edits (the command line opens with the value, completion for choices),
  `h`/`l` step choices (result, role, kind), `⌫` clears, `u` undoes; a click on a value edits it in place;
- fields that point to another thing (a game's White, a position's Source) use the **picker** of the tag picker
  (type to search, `↵` picks); its last row is always **+ New "…"** (makes the player or source with what was typed,
  then the Details pane can edit it: `Tab` jumps there and `Esc` comes back);
- sections by purpose (`]` / `[`, spec 03 §5): a game has *Players · Event · Result and opening · Source · More
  headers*; a player *Name and spellings · Role · Rating and federation · Notes*;
- every change is a journal entry (`u` / `U`, spec 09), the Library and the tree update at once.

The Inspector keeps what is about the **move**; the Details pane is about the **thing**. The Inspector's position
section (*source · objective · FEN*) links to it: `I` (*info*, or a click on the section's title) focuses the Details pane,
or opens it in a split when there is none.

## 3 · Collect mode, reorganised

The default layout of Collect becomes:

```
┌─ Board · SETUP ─────────┬─ Entry session ─────────┐
│                         │ (as today: source, page,│
│                         │  diagram, presets)      │
│                         ├─ Details ───────────────┤
│                         │ the thing being made:   │
│                         │ position, game, player, │
│                         │ source                  │
└─────────────────────────┴─────────────────────────┘
```

New commands (all in `:` with completion; `␣ n` is the *new* prefix everywhere, `I` the details of what is selected —
free keys in every context today, `n` and `E` are not: the board editor's knight, Analyse's next subject and
evaluate):

| Command | Keys | What it does |
|---|---|---|
| `collect.new source` | `␣ n s` | an empty source in Details; it becomes the entry session's source |
| `collect.new player` | `␣ n p` | an empty player in Details |
| `collect.new game` | `␣ n g` | a game from the board's position (or the start), White and Black to fill in; the board plays its moves |
| `collect.new position` | `␣ n o` | today's save, as a command of its own |
| `library.details` | `I` where a thing is selected | focus the Details pane of that thing |

The entry session's **Source** field uses the same picker: typing a title that doesn't exist offers *+ New book
"Tactics Manual"*, so a source can be made before its first position, and edited in Details later.

## 4 · Fixing what came in incomplete

- After a paste or import, a game **without names** says so in the status line: `White and Black unknown · I adds
  them`. The Library lists such games under the facet *Status → Incomplete* (`is:incomplete`: no players, no
  date, or no source for a position from a book).
- **Players from PGN names**: importing matches names to existing players by name and aliases (as today); a new
  name makes a player. Details can **merge** a player into another (`m`: pick the one to keep; games and aliases
  move over, undoable), for "Carlsen, M." and "Magnus Carlsen".
- **Me**: Settings → *Who you are* picks the player with role *me* (or makes one); games pasted from lichess with
  the user's handle are linked to it (the handle is an alias).

## 5 · The Library

- The Players and Sources tabs get `␣ n p` / `␣ n s` (new) and `I` (details) like every list; Games get `I` too.
- A source's row shows its counts (positions, puzzles, games); `↵` on it filters the Library to it, as today.

## 6 · Tests, guides, translations

Browser journeys (Junie writes the tests from §3–§4 once the views exist): paste a game without names → `I` → set
White by making a new player → the Library finds the game under `@` that player; make a source first, then enter
two positions into it; merge two players and undo. Guides: `help/details.html`, Collect's guide updated; every new
text in de, fr, it.

## 7 · Order of work

1. The Details view for games (fields, picker with + New, journal) and `I` from the Library and Analyse. *Claude*
2. Players and sources in Details; `collect.new …`; the entry session's source picker. *Claude*
3. Incomplete facet, merge, *Who you are*. *Claude*
4. Tests, guide, translations, screenshots of the new Collect. *Junie*
