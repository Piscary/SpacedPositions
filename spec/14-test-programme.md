# 14 · The test group (plan)

Status: **plan** for milestone M0 (13 §6): a small group uses the test version for four to six weeks. No marketplace,
no licensed packs: the starter pack and packs from you.

## 1 · What we want to learn

Two promises have to hold:

- **For a beginner, it explains itself.** Someone who has never used a terminal installs it, fills it and trains
  without help from outside the app, and understands what it does for them.
- **For an experienced user, it gets fast and pleasant.** After a week the keys are in the fingers: collecting a book,
  training and searching feel quick, and nothing breaks the flow.

And: does spaced repetition with real books keep people training after the first excitement (week 3 and 4)?

## 2 · Who

6–10 people, chosen so that every kind of user is there at least twice:

| Group | Count | Why |
|---|---|---|
| Beginners and juniors (with a parent if young) | 2–3 | the "explains itself" promise |
| Club players who train from books | 2–3 | the main audience: books, collecting, Review |
| Coaches (you included) | 1–2 | packs for students, the Library |
| Keyboard people (vim, power users) | 1–2 | the "gets fast" promise, key design |

Mixed: macOS and Windows, German, French, Italian and English, laptop and desktop. Each tester gets a short written
note: what the test is, what it costs them (about 15 minutes a day, three short surveys, one conversation), that
everything stays on their computer, and that the usage report (§5) is voluntary and contains no positions.

## 3 · Timeline

| Week | What testers do | What you do |
|---|---|---|
| 0 | install alone, following the README; the first session is the **first-run task list** (§4) | one observed session per group by video call, if they agree: watch, don't help, note where they hesitate |
| 1–2 | train daily; the **weekly tasks** (§4) | read the feedback daily; fix blockers within days, ship an update (this also tests updating) |
| 3–4 | use it the way they want | weekly pulse survey; collect the usage reports |
| end | final survey and a 20-minute conversation | the summary (§7) and the go / no-go for M1 |

## 4 · Tasks

Each task has a **success measure**. After each one, testers answer one question: *How easy was this?* (1 very hard –
7 very easy, the "single ease question").

**First run** (week 0, alone):

1. Download, install, start the app. *Success:* running in under 5 minutes; note where the macOS / Windows warning
   confused them.
2. Switch to their language. *Success:* found without help.
3. Load the starter pack and solve the first puzzle. *Success:* under 10 minutes from download to the first solved
   puzzle.
4. Find out what a key does, using `?`. *Success:* they open the guide of the pane they are in.

**Week 1:**

5. Train Review every day. *Measure:* days trained (usage report).
6. Enter 10 diagrams from one of their books in Collect. *Measure:* time and mistakes; beginners vs keyboard people.
7. Turn a moment of one of their own games into a puzzle (Analyse, `p s`, `p r`).

**Week 2:**

8. In the Library, find the positions of their book that still need a solution, and work through them (the work
   list of 04 · Library).
9. Remove a tag from a puzzle and add another one (the tag picker).
10. Coaches: make a pack for one student; the student imports it.
11. Update to the new version you shipped. *Success:* done with the in-app notice alone, nothing lost.

**Keyboard people, additionally:** do tasks 6, 8 and 9 without the mouse, and say which key felt wrong.

## 5 · Data

Nothing is collected automatically: the app sends nothing (09 §11). Testers send three things:

- **Surveys**: the single ease question per task (§4); a **weekly pulse** of five questions (§6); at the end the
  **System Usability Scale** (10 standard questions, scored 0–100) and the conversation.
- **The usage report**, a file the app writes on request (`:test-report`, Settings → Data, `R` in Settings; built:
  `core/usage.py`, `static/js/core/usage.js`): counts only,
  never positions, names or texts. Version, platform, language; days used; puzzles trained per day; solved / missed;
  minutes per session; how often each command was run **by key, by click or by the command line** (this shows whether
  people move from clicks to keys over the weeks); time from install to the first solved puzzle; errors the app
  caught. Testers look at it before they send it.
- **Feedback anytime**: a short form (or a chat group) for "this confused me", "this broke", "I wish". The app gets a
  `:feedback` command that opens it with the version and the current mode filled in.

## 6 · The questions

**Weekly pulse** (2 minutes):

1. How many days did you train this week? (0–7)
2. What did you use most? (Review, Storm, Streak, Collect, Analyse, Library, other)
3. What was the most annoying moment? (free text)
4. What did you enjoy? (free text)
5. How likely are you to still use it in a month? (0–10)

**Final conversation** (20 minutes, the same order for everyone):

- What do you think the app is for, in one sentence? (Do they get the idea of spaced repetition?)
- Walk me through what you do in a typical session. (Their real workflow)
- When did you last need help that the app didn't give? Where did you look?
- Beginners: which word or screen didn't make sense?
- Keyboard people: which keys feel natural, which ones did you rebind or avoid, what is still slow?
- Coaches: would you give packs to your students this way? What is missing?
- What would make you recommend it to a chess friend? What would stop you?

## 7 · Keeping track

Every piece of feedback becomes one row in the feedback log (`docs/testing/feedback-log.csv`):

| Column | Meaning |
|---|---|
| id | F001, F002 … |
| date | when it came in |
| tester | a short code (T1 … T10), not a name |
| group | beginner, club, coach, keyboard |
| source | form, chat, survey, conversation, report, observed |
| area | install, first run, train, collect, analyse, library, packs, stats, settings, help, keys, update |
| kind | bug, confusion, wish, praise |
| severity | blocker (can't go on), major (works around it), minor, cosmetic |
| description | what happened, in their words |
| count | how many testers said the same (merge duplicates into one row) |
| status | new, planned, fixed in version …, won't do (with why) |

**Weekly triage** (30 minutes): merge duplicates, set severity, fix blockers first; anything mentioned by three or
more testers is planned whatever its severity.

**The scoreboard** at the end:

| Measure | Goal for M1 |
|---|---|
| Download → first solved puzzle, alone | under 10 minutes for every tester |
| Single ease question, first-run tasks | average 5.5 or more |
| System Usability Scale | 75 or more (beginners and keyboard people both above 68) |
| Testers still training in week 4 | at least 5 |
| Keyboard share of commands, week 4 vs week 1 | rising for every group |
| Open blockers / data-loss bugs | none |

## 8 · Ready to start?

- [ ] Release builds for macOS and Windows, tested on clean machines (a fresh user account), install to first puzzle
- [ ] An update from one test version to the next tested, data kept (also `spos update`)
- [ ] Backups and `spos restore` tried once
- [x] `:test-report` built (§5): commands counted per day by key, click, hint label or command line (only what the
  user did, not what commands run themselves), the errors caught in the browser and in the app, kept in the app's
  database (`UsageCount`), sent nowhere
- [ ] `:feedback` built (§5)
- [ ] The tester note, the form, the surveys and the feedback log ready
- [ ] A known-issues list, so testers don't report the same things
- [ ] Dates fixed: the observed first sessions, the weekly pulses, the conversations
