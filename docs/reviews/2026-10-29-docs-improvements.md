# Documentation improvements — 2026-10-29

## Goal

Make the Spaced Positions documentation and in-app help clear for a new user who doesn't know nvim/vim, and remove references to niche tools (Jupyter) from user-facing material. Support both users who want to understand the principles before using the tool, and users who prefer to explore directly.

## Changes made

### 1. Removed all Jupyter references (9 total)

Jupyter Notebook is a niche tool known mainly to data scientists. A general chess player has never heard of it. Every reference was replaced with plain language.

| File | Line | Before | After |
|---|---|---|---|
| `README.md` | 201 | "like `jupyter notebook`" | removed comparison |
| `README.md` | 219 | "started like Jupyter" | removed comparison |
| `spec/README.md` | 37 | "Jupyter-style launch" | "local launch" |
| `spec/09-architecture.md` | 16 | "started like Jupyter (§11)" | removed comparison |
| `spec/09-architecture.md` | 188 | "## 11 · Starting the app (Jupyter-style)" | "## 11 · Starting the app" |
| `spec/09-architecture.md` | 215 | "like a second `jupyter notebook`" | removed comparison |
| `spec/10-roadmap-and-questions.md` | 90 | "**Jupyter-style start**" | "**One-command start**" |
| `spaced_positions/launcher.py` | 1 | "like `jupyter notebook`" | removed comparison |
| `spaced_positions/core/middleware.py` | 1 | "Jupyter-style access control" | "Local-only access control" |

### 2. Made spec/README.md accessible to non-vim readers

The spec README is the first thing a contributor (or curious user) reads. The "Modes, not pages" principle said "As in nvim" — this was changed to acknowledge the inspiration while making clear that nvim knowledge is not required:

> "This is inspired by editors like nvim, but the app explains everything on screen so you don't need to know nvim to use it."

### 3. Improved in-app help for non-vim users

**`templates/help/pane.html`** — The pane guide:
- Lead text now explains panes as "like windows in a program, but arranged without overlapping" instead of the bare "The workspace is made of panes."
- Link groups explanation changed from "work together" (vague) to "stay synchronized: when you step to the next move in one, the others follow. For example, the board, the move tree and the engine of group A always show the same position." — concrete and self-explanatory.

**`templates/views/today.html`** — The "Getting around" intro on Home:
- Opening text changed from "Everything works with the mouse, and every button shows its key. The keys are what make it fast" to "Everything works with the mouse. The keyboard keys are there to make it fast once you learn them — and every button shows its key, so you learn by clicking." — explicitly addresses the "why keyboard" question and reassures mouse users.
- The modes step now explains what a mode is: "The app has several modes — Train, Analyse, Library — each with its own layout." instead of just "goes to the Library."

### 4. Improved README.md "Mouse or keyboard" section

Added a paragraph explaining modes before the key table:

> "The app is organised into **modes**: Home (what to do now), Train (solving puzzles), Analyse (working on a position), Library (finding and organising), and more. Each mode has its own layout of panes. You switch modes with `space` then a letter, or by clicking the mode name at the top."

This gives the "principles-first" reader the mental model before the key reference.

### 5. Translations

4 new translatable strings, translated into German (Swiss spelling), French, and Italian:
- Pane lead text (panes like windows)
- Link groups explanation (synchronized)
- Getting around intro (why keyboard)
- Modes explanation (what a mode is)

`manage.py i18n extract`, `i18n fill`, `i18n build` all ran successfully.

## Verification

| Check | Result |
|---|---|
| `design check` | 0 errors, 0 warnings |
| Python tests (151) | All pass |
| JS unit tests (12) | All pass |
| Browser tests | Not run (no JS/HTML behavior changed, only text) |

## What was not changed

- **The spec's nvim analogy table** (`spec/01-principles.md` Vocabulary): The `nvim analogy` column is internal developer documentation. It helps developers understand the design decisions. Left as-is.
- **The spec's `Ctrl+^` in vim reference** (`spec/02-interaction-model.md`): Internal developer doc, appropriate context. Left as-is.
- **The spec's `like tmux or nvim splits`** (`spec/01-principles.md` P3): Internal design doc comparing layout density. Left as-is.
- **The spec's `like Vimium`** (`spec/02-interaction-model.md`): Internal doc for the Hint layer. Left as-is.
- **The spec's `vim-style counts`** (`spec/02-interaction-model.md`): Internal design decision about key grammar. Left as-is.
- **`spec/14-test-programme.md`**: No Jupyter references found.

## Files changed

1. `README.md` — Removed 2 Jupyter refs, added modes explanation paragraph
2. `spec/README.md` — Made "Modes, not pages" accessible, removed Jupyter ref
3. `spec/09-architecture.md` — Removed 3 Jupyter refs
4. `spec/10-roadmap-and-questions.md` — Removed 1 Jupyter ref
5. `spaced_positions/launcher.py` — Removed 1 Jupyter ref
6. `spaced_positions/core/middleware.py` — Removed 1 Jupyter ref
7. `spaced_positions/templates/help/pane.html` — Improved pane and link group explanations
8. `spaced_positions/templates/views/today.html` — Improved Getting around intro
9. `spaced_positions/locale/*/LC_MESSAGES/django.po` — Updated by `i18n extract`
10. `spaced_positions/locale/*/LC_MESSAGES/django.mo` — Regenerated by `i18n build`
11. `spaced_positions/static/i18n/*.json` — Regenerated by `i18n build`

## Notes for Claude

- The spec remains the authoritative source for nvim-inspired design decisions. The changes only affect **user-facing** text (README, in-app help) and remove **niche tool references** (Jupyter) that add no value for the target audience.
- The in-app help changes are small but targeted: they add the "why" (why keyboard, what is a mode, what does synchronized mean) without making the guides longer.
- The German translation uses "Fenster" for "pane" in the lead text of the pane help — this is intentional for the analogy, but the rest of the app uses "Rahmen" or "Bereich" for pane. If you prefer consistency, the German could use "Bereiche" instead. The French and Italian translations use the existing terms (panneaux/pannelli).
- No new commands, keys, or settings were added — only text changes.
