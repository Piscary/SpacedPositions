# French & Italian translation audit — 2026-10-29

## Goal

Comprehensive review of all French and Italian translations before the M0 test group arrives. The M0 readiness
checklist (spec/14-test-programme.md §8) explicitly requires "Review of the French and Italian translations by
native speakers." This audit checks for: wrong meanings, inconsistent terminology, unnatural phrasing, English
intrusions, and missing translations.

Reference glossary from `.junie/guidelines.md`:

| English | German | French | Italian |
|---|---|---|---|
| pane | Bereich | panneau | riquadro |
| link group | Verknüpfungsgruppe | groupe lié | gruppo collegato |
| button / key | Knopf / Taste | bouton / touche | pulsante / tasto |
| Space | Leertaste | barre d'espace | barra spaziatrice |
| layout | Anordnung | disposition | disposizione |
| Home | Start | Accueil | Home |
| Train | Training | Entraînement | Allenamento |
| Analyse | Analyse | Analyse | Analisi |
| Collect | Erfassen | Saisie | Inserimento |
| Library | Bibliothek | Bibliothèque | Biblioteca |
| Stats | Statistik | Statistiques | Statistiche |
| Settings | Einstellungen | Réglages | Impostazioni |
| board | Brett | échiquier | scacchiera |
| move tree | Zugbaum | arbre des coups | albero delle mosse |
| engine | Engine | moteur | motore |
| puzzle | Aufgabe | exercice | esercizio |
| card | Karte | carte | scheda |
| solver | lösende Seite | camp qui résout | chi risolve |

## Methodology

1. Ran `manage.py i18n missing` — **0 missing translations** in either language.
2. Scanned all 1,982 French and 1,982 Italian msgid/msgstr pairs for:
   - Empty translations (none found)
   - msgstr == msgid on user-facing text (74 FR, 38 IT — all intentional: proper names, code identifiers, piece set names)
   - English word intrusions (none found — all matches were code identifiers like `:settings-export`, `has:puzzle`)
   - Mode name translations (all correct per glossary)
3. Reviewed key user-facing areas for naturalness and accuracy: puzzle pane, solver/trainer terminology,
   "Also correct" / "All answers count", "the start" noun, starter pack, Home mode, error messages.
4. Checked JS i18n files (`static/i18n/fr.json`, `it.json`) — 2,041 strings each, no empty values.

## Findings

### 1. "solver" glossary term is very awkward (Both languages — High impact)

**Where:** Every occurrence of "solver" in puzzle-related text (13+ entries per language).

**Glossary says:** FR: "camp qui résout", IT: "chi risolve"

**Problem:** These are extremely awkward and unnatural. "Camp qui résout" literally means "the side that solves" —
it's a word-for-word construction that no native French speaker would use. "Chi risolve" in Italian means "whoever
solves" — it sounds like a philosophical statement, not a UI term.

In chess puzzle context, the "solver" is the player solving the puzzle. Natural translations would be:
- **French:** "le joueur" (the player) or "celui/celle qui résout" — but "le joueur" is much clearer
- **Italian:** "il giocatore" (the player) or "chi risolve" could work in context, but "il giocatore" is clearer

**Impact:** Every puzzle-related screen uses this term. Testers will find it confusing and unnatural.

**Suggested fix:** Change the glossary entry and all translations:
- FR: solver → "le joueur"
- IT: solver → "il giocatore"

This would change "the solver's move" from "le coup du camp qui résout" to "le coup du joueur" and
"chi risolve" to "il giocatore" — much more natural.

**Confidence:** Confirmed — this is a glossary-level decision that affects ~26 entries across both languages.

---

### 2. "Also correct" — unnatural in both languages (Both languages — Medium impact)

**Where:** `templates/analysis/puzzle.html`, `analysis/puzzles.py`, and related help text.

**Current translations:**
- FR: "Aussi correct" — This is a direct calque from English. While grammatically acceptable, it's not natural
  French. A French speaker would say "Également correct" or "Accepté aussi".
- IT: "Anche corretta" — Gender agreement problem. "Corretta" is feminine singular, but there's no feminine noun
  it agrees with. As a standalone label, the masculine default "Anche corretto" would be correct, or better:
  "Accettata anche" (Also accepted).

**Occurrences:** 9 entries in each language.

**Suggested fix:**
- FR: "Also correct" → "Également correct" (or "Accepté aussi" for buttons)
- IT: "Also correct" → "Anche corretto" (or "Accettata anche" for buttons)

**Confidence:** Confirmed — these are button labels and help text that testers will see frequently.

---

### 3. "illegal solver move" translated as "solution move" (Both languages — Medium impact, potential bug)

**Where:** Error message `illegal solver move {uci} in {value}`

**Current translations:**
- FR: "coup de solution illégal {uci} dans {value}"
- IT: "mossa della soluzione illegale {uci} in {value}"

**Problem:** The English says "solver move" (the move the player/solver is expected to make). The translations
say "solution move" (a move in the solution line). These are different concepts: a solver move is what the player
must find; a solution move is what the puzzle author defined. If the error message is about an illegal move in the
solution definition, then the English should say "solution move". If it's about the solver's expected move, the
translations are wrong.

**Investigation needed:** Check the Python code that generates this error to confirm which concept it refers to.

**Suggested fix:** Depending on the code:
- If it's about the solution: change English to "illegal solution move" and translations are correct
- If it's about the solver: change FR to "coup du joueur illégal" and IT to "mossa del giocatore illegale"

**Confidence:** Likely a translation bug — the English source says "solver" but both translations render it as
"solution", suggesting the translator interpreted rather than translated.

---

### 4. "trainer" in Italian — "allenatore" means "coach" (Italian — Low impact)

**Where:** 5 entries where "trainer" appears (the system that plays the opponent's moves in a puzzle).

**Current translation:** "l'allenatore"

**Problem:** In Italian, "allenatore" primarily means "sports coach" — a human person. In the puzzle context,
"trainer" is the program/system that responds to the player's moves. Using "allenatore" could confuse users into
thinking there's a human coach involved.

**Suggested fix:** "il programma" (the program) or keep "l'allenatore" if the metaphor of a training partner is
intentional. The French "l'entraîneur" has the same metaphor and works better in French where "entraîneur" is more
commonly used for training systems.

**Confidence:** Low impact — the context usually makes it clear, but worth noting for consistency.

---

### 5. "All answers count" — acceptable but could be clearer (Both languages — Low impact)

**Where:** Puzzle setup, button label and help text.

**Current translations:**
- FR: "Toutes les réponses comptent" — Acceptable, clear enough
- IT: "Tutte le risposte contano" — Acceptable, clear enough

**Note:** These are functional but slightly literal. In French, "Toutes les réponses valent" (All answers are valid)
might be slightly clearer. In Italian, "Tutte le risposte sono valide" would be more explicit. But the current
translations are not wrong.

**Confidence:** Minor — current translations are acceptable.

---

### 6. "Home" in Italian — used as "la Home" (Italian — Low impact, intentional)

**Where:** 3 entries where Home mode is referenced in Italian text.

**Current usage:** "la Home mostra", "nella Home"

**Assessment:** The glossary explicitly says Home stays "Home" in Italian. "La Home" is very common in Italian UI
text and is natural. No change needed.

**Confidence:** No issue — this is correct per glossary and natural Italian.

---

### 7. "starter pack" consistency (Both languages — Verified OK)

**Where:** 5 entries in each language.

**Translations:**
- FR: "pack de départ" — consistent across all 5 entries ✓
- IT: "pacchetto iniziale" — consistent across all 5 entries ✓

**Assessment:** Both are consistent and natural. No issue.

---

### 8. Mode names — all correct per glossary (Both languages — Verified OK)

| Mode | FR | IT | Status |
|---|---|---|---|
| Home | Accueil | Home | ✓ Correct |
| Train | Entraînement | Allenamento | ✓ Correct |
| Analyse | Analyse | Analisi | ✓ Correct |
| Collect | Saisie | Inserimento | ✓ Correct |
| Library | Bibliothèque | Biblioteca | ✓ Correct |
| Stats | Statistiques | Statistiche | ✓ Correct |
| Settings | Réglages | Impostazioni | ✓ Correct |
| Review | Révision | Ripasso | ✓ Correct |
| Storm | Storm | Storm | ✓ Intentional (brand names) |
| Streak | Streak | Streak | ✓ Intentional (brand names) |

---

### 9. "The start" (noun) disambiguation (Both languages — Verified OK)

Claude's commit correctly split "Start" into noun and verb contexts with msgctxt. The translations are:
- FR: noun = "Départ", verb = "Démarrer" ✓
- IT: noun = "Inizio", verb = "Avvia" ✓

All occurrences of "the start position" correctly use "la position de départ" / "la posizione iniziale".

---

### 10. "panneau" / "riquadro" glossary terms — used consistently (Both languages — Verified OK)

Automated scan confirmed no English "pane" or "panel" appears in translations. All instances use the glossary terms.

---

### 11. "exercice" / "esercizio" for puzzle — used consistently (Both languages — Verified OK)

No English "puzzle" found in any translation. All instances correctly use the glossary terms. Code references
like `has:puzzle` and `:puzzle` are intentionally kept as code.

---

### 12. CSS class names in translations (Both languages — Verified OK)

Two entries contain `.board__frame` — these are CSS class names in custom CSS settings, not UI text. Correctly
kept as-is.

---

## Summary

| # | Finding | Languages | Severity | Status |
|---|---|---|---|---|
| 1 | "solver" glossary term is very awkward | FR, IT | **High** | Needs glossary change |
| 2 | "Also correct" unnatural / gender issue | FR, IT | **Medium** | Needs rewording |
| 3 | "illegal solver move" → "solution move" | FR, IT | **Medium** | Needs code check |
| 4 | "trainer" = "allenatore" (coach) in IT | IT | Low | Consider alternative |
| 5 | "All answers count" could be clearer | FR, IT | Low | Acceptable as-is |
| 6–12 | Verified OK areas | — | — | No issues |

## Recommendations

1. **Before M0:** Fix findings #1 and #2. The "solver" term is the most visible issue — every puzzle screen uses it,
   and testers will find it unnatural. "Also correct" is a button label seen frequently.
2. **Before or after M0:** Investigate finding #3 (check the code) and decide on #4.
3. **Glossary update:** If "solver" is changed, update `.junie/guidelines.md` glossary accordingly.

## What was checked and found fine

- All 1,982 entries in each language have non-empty translations
- No missing translations (`i18n missing` returns empty)
- No English word intrusions (all matches were code identifiers)
- Mode names correctly translated per glossary
- "The start" noun/verb disambiguation working correctly
- "starter pack" consistent in both languages
- "panneau"/"riquadro" used consistently (no English "pane")
- "exercice"/"esercizio" used consistently (no English "puzzle")
- JS i18n files have 2,041 strings each, no empty values
- Piece set names (cburnett, merida, etc.) correctly kept as-is
- Command names (:settings-export, :puzzle, :theme, :analyse) correctly kept as code

## Verification

| Check | Result |
|---|---|
| Python tests (151) | 150 pass, 1 fails — `test_catalogues_are_complete_and_built` fails because Claude's uncommitted `:test-report` feature added 27 new untranslated strings. This is a **pre-existing** failure from Claude's active work, not from this audit. |
| JS unit tests (12) | All pass, 0 failures |
| `design check` | 6 errors — all from Claude's uncommitted `:test-report` strings (26 untranslated + 1 not yet extracted per language). Pre-existing. |
| `i18n missing` | 27 missing strings per language — all from Claude's `:test-report` feature |

## Files changed

None. This is a review report (`docs/reviews/2026-10-29-translation-audit.md`). Corrections should be made by the maintainer or Claude after reviewing these findings.

## Notes for Claude

- Finding #1 (solver) is a glossary-level decision. The current "camp qui résout" / "chi risolve" was chosen to
  distinguish the puzzle solver from the chess engine solver, but it's very unnatural. "Le joueur" / "il giocatore"
  would be clearer and more natural. The context (puzzle pane, training) already makes it clear we're talking about
  the player, not the engine.
- Finding #3 needs a code check: look at where `illegal solver move` is raised in Python to confirm whether it
  refers to the solver's expected move or a move in the solution definition.
- The overall translation quality is good. The main issues are with the "solver" concept (a design decision that
  prioritized precision over naturalness) and "Also correct" (a calque from English).

---

## Resolution (Claude, 2026-10-29)

| # | Decision |
|---|---|
| 1 solver | French: **joueur** ("le coup du joueur", "le joueur trouve la solution"); the opponent's moves stay "réponses". Italian: keep **chi risolve** (ordinary Italian: "chi risolve l'esercizio"); "il giocatore" would not tell the two sides apart. Glossary updated. |
| 2 also correct | French: **Également correct**. Italian: keep **Anche corretta**: the button marks a move (la mossa), so the feminine agrees. |
| 3 illegal solver move | The message is about a solver move in a stored solution (the next message covers the answers): FR "coup du joueur illégal {uci} dans {value}", IT "mossa di chi risolve illegale {uci} in {value}". |
| 4 allenatore | Keep: the same training-partner metaphor as the French "entraîneur". |
| 5 All answers count | Keep. |

The native-speaker review before the public beta (spec 10, M1) can still change any of these.
