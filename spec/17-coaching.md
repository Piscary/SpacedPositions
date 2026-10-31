# 17 · Coaching: lessons, homework, results

Plan (2026-10-31). A chess coach prepares a lesson every week for one child or a group, shows positions in the
lesson, gives homework, and wants to know afterwards what each child solved, missed and asked. Spaced Positions
already has the material (positions, puzzles, games, analysis, tags) and the pack files (09 §12); what is missing is
the coach's workflow around them. No server: everything travels as files, by whatever channel coach and family
already use (email, messenger, a school drive).

Words used in the app, kept plain: a **lesson** is material in an order, with notes; **homework** is a lesson sent
to students to solve; **results** are what a student sends back. Spec 12's *collections* (where a puzzle came from)
stay as they are; a lesson is the coach's own, ordered selection.

## 1 · Who is who

- **Coach view on demand.** Settings → *I teach* (off by default) shows the Coach mode and the coach commands;
  students and adults training alone never see them.
- **Students are players** with the role *student* (spec 16: made in Details, `␣ n p`), with a new field
  **group** ("U10 Thursday"), so homework can go to a group at once.

## 2 · Lessons

A lesson: a title, a group or students, a date, an ordered list of **items**, each a position, a puzzle or a game
(at a move), with a coach's **note** (what to ask, what to point out), and optionally which puzzles are its
homework.

- **Making one**: in the Library, select rows and `L` (*to a lesson*: the picker of lessons, with *+ New lesson*);
  in Analyse, `L` adds the position at the cursor (a game at that move). (`+` is taken: the engine's lines.) A saved query can fill a lesson
  (`motif:fork diff:1..2 !in:lesson`).
- **Coach mode** (new mode, `␣` + a free letter when built): panes *Lessons* (list), *Lesson* (its items, `j`/`k`,
  `J`/`K` move an item, `c` edits its note, `⌫` removes), *Students*, and the board and moves of the item under the
  cursor (link group A, as in the Library).
- **Teaching it live** (*Present*, `p`): the board big, the item's note beside it for the coach only (or hidden for
  screen sharing), `n`/`N` next item, `space` plays the next move of the solution, arrows drawn with the mouse stay
  until the next item. Works on a projector or a shared screen.

## 3 · Homework

1. **Export** (`H` on a lesson): which items are homework (default: its puzzles), **instructions** (a short text),
   a **due date**, how to solve: *once through* (the result is the first try) or *until solved* (wrong ones come back
   in the session), hints allowed or not, *also into their Review* (on by default: the spaced repetition keeps the
   lesson alive). One file for the group (the student types their name on import) or **one file per student**
   (personalised, the name inside).
2. **The student imports it** like any pack (drop the file, `:import`). Home shows a **Homework** section first:
   `Forks · 12 puzzles · from Coach Anna · due Fri` with `↵` to start. The session is a Review of those puzzles with
   the coach's settings, its progress kept across days, the instructions on top.
3. **A question per puzzle** (phase 2): on the feedback screen (spec 04 · Train), a key (chosen when built: `?` is
   help) writes a short question or note for the coach about this puzzle ("Why not Qxd5?").
4. **Send back** (Home → Homework → *Send results*, or at the end of the session): the app writes a **results file**
   (`.spresult`) and shows what is in it first (as the usage report does: spec 14 §5): the student's name, and per
   puzzle solved at the first try or not, tries, time, hints, the first wrong move, the question. Nothing else from
   the student's app (no other training, no other material). The student or a parent sends it.

## 4 · Results, on the coach's side

The coach drops the results files (several at once) into the app:

- **The homework's table**: students × puzzles, each cell ✓ / ✗ / not done, the time, a mark when there is a
  question; columns sorted by how many missed it. `↵` on a cell opens the puzzle in Analyse at the student's wrong
  move (a variation *"Lena's try"*, so it can be discussed).
- **Questions**: the list of all questions with student and puzzle, to answer in the next lesson.
- **Follow-up** (`F`): a new lesson from what was missed (per student or for the group).
- **Per student** over time: homework done on time, accuracy by motif (the puzzles' tags), weak motifs. This is the
  coach's view of spec 10's *progress reports*, built from what students sent back.

## 5 · Files

Pack format 2 (spec 13 §2) gains a `kind`: `pack` (today), `lesson` (items with notes, for another coach),
`homework` (items, instructions, due date, settings, an assignment id, optionally the student), and a new file type
`results` (assignment id, student, per item results). Older apps refuse a homework file with a clear message
(*update the app to do this homework*). A homework's licence defaults to *for my students only* (spec 13: personal
copies, export log).

## 6 · Order of work

**Phase 1 (this week, the core loop):**
1. Lessons: model, `+` from Library and Analyse, Coach mode with the Lessons and Lesson panes. *Claude*
2. Homework export with its settings; the student's import and Homework section on Home; the homework session.
   *Claude*
3. Results file (preview, write) and the coach's import with the homework table. *Claude*
4. Tests of the whole loop with two fake students, guides, translations, a coach's how-to in `docs/`. *Junie*

**Phase 2 (after the week):** Present mode, questions per puzzle, follow-up lessons, the per-student view, groups,
lesson packs for other coaches.
