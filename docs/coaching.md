# Coaching: a coach's how-to

Spaced Positions lets a chess coach prepare lessons, give homework, and see the results that come back. Everything travels as files — no server is needed.

## Getting started

Turn on the Coach mode: **Settings → Packs → I teach**. A new tab appears in the app's modes bar.

## Making a lesson

A lesson is an ordered list of positions, puzzles or games, each with your private note (what to ask, what to point out).

1. Go to the **Library**. Select the rows you want (positions with puzzles, games, or analysed positions).
2. Press `L` (*To a lesson*). Type the lesson's title, for example "Forks". A new title creates a new lesson; an existing one adds to it.
3. In the **Coach** mode, the **Lessons** pane lists your lessons. The lesson under the cursor shows in the **Lesson** pane beside it: its items, your notes, and any homework results.
4. In the Lesson pane, `j`/`k` move the cursor, `J`/`K` move an item up or down, `c` edits the note, `⌫` removes an item (`u` brings it back).

You can also add from **Analyse**: open a position and press `L` to add it (a game at the cursor's move).

## Giving homework

1. In the Coach mode, select a lesson in the Lessons pane.
2. Press `H` (*Homework*). The command line asks which items are homework (default: the lesson's puzzles), your instructions, and optionally a due date (`due=2026-11-14`).
3. The app writes a `.sppack` file. Send it to your students by email, messenger, or however you usually communicate.

Each student imports the pack like any other pack: drop the file on the window or use `:import`. On **Home**, a **Homework** section appears at the top, showing the puzzle count, your name, and the due date. The student presses `↵` to start.

## The student's side

The student sees the homework on Home, starts it with `↵`, and solves the puzzles. Progress is kept across days. When finished (or whenever), the student goes to **Home → Homework → Send results**: the app writes a `.spresult` file and shows what is in it. The student or a parent sends it back to the coach.

## Receiving results

Drop the `.spresult` file(s) on the Coach window. The Lesson pane updates with a results table: students × puzzles, with ✓ (solved at the first try), ✗ (missed), and · (not done). Press `↵` on a cell to open the puzzle at the student's wrong move, so you can discuss it in the next lesson.

## Key terms

| English | German | French | Italian |
|---|---|---|---|
| Lesson | Lektion | Leçon | Lezione |
| Homework | Hausaufgabe | Devoirs | Compito |
| Coach | Coach | Coach | Coach |
