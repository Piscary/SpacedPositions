# 12 · Packs and sources as collections (plan)

Status: **plan**, not built. The order of work is at the end (§7). It builds on 09 §12 (packs), 11 (data model, query
language) and 04 (Train, Stats, Library).

## 1 · What we want

A typical week: you train *Chess Monkeys level 1*, get bored, switch to level 2 for a week, and then see that your
retention there is low, so you go back to level 1 for a while. To do that you need three things the app doesn't
give you yet:

1. **See where a puzzle comes from**, everywhere: which pack and which book, at a glance.
2. **Train one collection** (a pack, or a book you entered yourself) without losing track of the rest.
3. **Compare collections**: retention, mastery and progress per pack or book, side by side.

And people who make packs (you for your students, later other coaches) need to see what they are about to share:

4. **The composition of a pack**: which motifs, which difficulties, which sources, how much own analysis.
5. **Good-citizen checks**: a clear warning when a pack looks like it copies a large part of one published book, so
   people don't share what they shouldn't, without the app pretending to be a lawyer.

A **collection** below means either a received **pack** (`Position.pack`) or a **source** (`Position.source`, a book
or a website). Many positions have both: the pack they came with and the book they are from.

## 2 · Where a puzzle comes from (visible everywhere)

- One line, the same everywhere: **`Chess Monkeys 1 · p. 12, Nr. 47 · pack "Monkeys" from Anna for Ben`**: the book
  with its page and diagram number first (that is what a player looks up), then the pack it came with.
- Shown in: Library rows (list and grid already show the citation; the table gets a *Collection* column), Train's
  feedback after each puzzle, the Inspector's position section, the result screen's list.
- The Library gets a **Collections** tab (`7`): one row per pack and per book, with how many positions and puzzles,
  due today, retention (30 days), last trained. `↵` shows its positions; `T` trains it; `s` shows its stats.
- The filter pane gets a **Pack** facet next to *Source*.

Query language: `pack:"Monkeys"` (a received pack, by title or `pack:k12`) next to `src:` (11 §3). Today `src:` with
the pack's title finds its positions too (a pack has its own source row); `pack:` makes it explicit, and `in:` stays
for saved queries.

## 3 · Training one collection

- **Train launcher**: a *Collections* section, one row each, with its due and new counts and its retention: `↵`
  starts a Review of that collection, `1`–`3` a Storm, `4` a Streak. A custom session can already take any search
  (`src:"Chess Monkeys 1"`); this makes it one key.
- **Focus** (optional): "Review only this collection for now". The other cards keep their schedule and simply become
  due; nothing is lost. When the focus ends, the status line says how many cards are waiting elsewhere, and Review
  takes the most overdue first (the scheduler already handles overdue cards: they are due, and a solve pushes them out
  as usual).
- The **new cards per day** limit counts across collections; with a focus, new cards come from the focused one only.

Data: a session already stores its options; it also stores its **scope** (the query) so the history can be split by
collection later (§4). A focus is a setting (`training.focus = <query>`), shown in the Train launcher and on Home as
a chip with `✕` to end it.

## 4 · Statistics per collection

Stats gets a **scope**: everything (default), or one collection (a pack, a book, any saved search). Every chart then
counts only the attempts and cards inside it: retention, mastery per motif, card stages, activity, records.

A **comparison** section lists the collections side by side:

| Collection | Puzzles | Learned | Retention 30 d | Accuracy 7 d | Due | Last trained |
|---|---|---|---|---|---|---|
| Chess Monkeys 1 | 412 | 64 % | 91 % | 88 % | 14 | today |
| Chess Monkeys 2 | 389 | 18 % | 72 % ⚠ | 70 % | 31 | 3 days ago |

with a hint where it helps: *"Retention in Chess Monkeys 2 is low (72 %): fewer new cards a day, or a focus on it
for a week, usually helps."* Every number drills down, as elsewhere in Stats.

Technically, attempts already point to cards → puzzles → positions, which carry `pack` and `source`; the scope is a
filter on positions (the compiled query of 11 §3) applied before the metrics. Retention per collection needs enough
attempts: below ~20 reviews the value shows as "too few reviews yet" instead of a misleading percentage.

## 5 · The composition of a pack

Before a pack is written (`e` → *Pack*, `:pack-export`), and for any collection in the Library (`i` on a
Collections row), a **composition** panel shows:

- **Size**: positions, puzzles, games; how many have own analysis (comments, variations) and how many are bare
  diagrams with a solution only.
- **Motifs**: the tags by field as a bar list (top 10 motifs with their share), how many motifs are covered, and
  positions without any motif tag.
- **Difficulty**: a histogram 1–5, and the phase split (opening, middlegame, endgame).
- **Sources**: each source with its count and share, and positions without a source.
- **Packs it came from**: positions that came from other people's packs, and under which licence (13 §2).

The same numbers go into the pack's manifest (`composition`), so a receiver sees them in the import preview: "38
puzzles · forks 40 %, pins 25 % · difficulty mostly 2–3".

## 6 · Good-citizen checks

Positions and moves are facts and can't be copyrighted; a **book as a collection** (the selection, the order, the
texts) can be. The checks look for the patterns that make a pack *look like a copy of a book*, and say so plainly.
They warn, they never block: the person exporting decides. When there is a warning, the export offers **personal use**
(the default) or **share anyway**, and the manifest records the choice (`sharing: "personal" | "share"`), which the
receiver's import preview shows.

| Check | Rule (defaults) | What the app says |
|---|---|---|
| **One book dominates** | more than **20 %** of the pack, or more than **50 positions**, from one source of kind *book* | "34 % of this pack (68 positions) is from *Chess Monkeys 1*. A large part of one book is probably protected as a collection: keep this pack for yourself, or ask the publisher." |
| **A book in its order** | from one book, more than 30 positions whose diagram numbers form a run (e.g. 1–40 with few gaps) | "These positions follow the book's order (Nr. 1–40): that is the book's own selection." |
| **The author's words** | comments or descriptions on positions from a book (text longer than a few words) | "42 positions from books have comments. Only share comments you wrote yourself." |
| **Someone else's pack** | positions from a received pack whose licence doesn't allow passing it on (13 §2) | left out of the export, with a note: "17 positions from *Monkeys* (for Ben) stay out: its licence doesn't allow passing it on." (Personal copies are already left out today.) |
| **No source** | positions without a source | "12 positions have no source. If they come from a book, add it: the checks can only help with what they know." |
| **Public domain** | lichess puzzles (CC0), old games, your own games and analysis | no warning; the composition shows them as free to share |

The thresholds are constants in one place (`library/composition.py`), documented in the export panel ("Why am I
seeing this?" opens the guide). Sources get a **rights** field (*unknown*, *public domain*, *own work*, *permission
given*): a book marked *permission given* by the person exporting doesn't trigger the first three checks, and the
manifest says so.

This is guidance, not legal advice, and the panel says so. Other criteria (quotation rules, teaching exceptions,
national law) stay with the person; the README's *Packs and copyright* and the guide explain the main ones.

## 7 · Order of work and what "done" means

1. **Where it comes from** (§2): the citation line everywhere, `pack:` in the query language, the Pack facet.
   *Done when* every place that shows a puzzle shows its book and pack, and `pack:` finds them.
2. **Collections in the Library and Train** (§2, §3): the Collections tab, the Train launcher section, sessions store
   their scope. *Done when* a collection trains with one key from the launcher.
3. **Stats scope and comparison** (§4). *Done when* the Chess Monkeys story of §1 can be told from the Stats screen.
4. **Composition** (§5) in the export panel and the import preview (manifest field).
5. **Good-citizen checks** (§6) with the rights field on sources.
6. **Focus** (§3), if the test group asks for it: it is the most opinionated part.

Each step gets its guide text (`?`), its keys, tests and translations, as everything else.
