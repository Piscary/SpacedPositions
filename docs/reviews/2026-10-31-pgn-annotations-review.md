# Day 2 — PGN annotations review (spec 15 §1–§3)

## 1. Translation review

### Settings → Engine → "Computer comments"

| English | German | French | Italian |
|---|---|---|---|
| Computer comments | Computerkommentare | Commentaires de l'ordinateur | Commenti del computer |

**Verdict:** Fine. "Computerkommentare" is a natural compound. "Commentaires de l'ordinateur" and "Commenti del computer" are correct.

### Setting values (show · fold · hide)

| English | German | French | Italian |
|---|---|---|---|
| show | zeigen | montrer | mostra |
| fold | zusammenklappen | réduire | riduci |
| hide | ausblenden | masquer | nascondi |

**Verdict:** Fine. All consistent with existing UI vocabulary.

### Setting description

> lichess's judgements in an analysed game ("Inaccuracy. Nf5 was best."): in full, folded to the judgement, or hidden

| German | French | Italian |
|---|---|---|
| Die Urteile von lichess in einer analysierten Partie («Inaccuracy. Nf5 was best.»): ganz, auf das Urteil zusammengeklappt oder ausgeblendet | Les jugements de lichess dans une partie analysée (« Inaccuracy. Nf5 was best. ») : en entier, réduits au jugement ou masqués | I giudizi di lichess in una partita analizzata («Inaccuracy. Nf5 was best.»): per intero, ridotti al giudizio o nascosti |

**Verdict:** Fine. The English example text ("Inaccuracy. Nf5 was best.") is kept in English in all translations, which is correct — it's a literal example of what lichess writes.

### Inspector labels

| English | German | French | Italian |
|---|---|---|---|
| clock {time} | Uhr {time} | pendule {time} | orologio {time} |
| used {time} | gebraucht {time} | utilisé {time} | usato {time} |
| engine {value} | Engine {value} | moteur {value} | motore {value} |

**Finding — "gebraucht" (German):** `analysis/views.py:229` — "gebraucht {time}" is awkward German for time used on a clock. Better: "verwendet {time}" or "verbraucht {time}". "gebraucht" means "used" in the sense of second-hand/employed, not "consumed". **Likely issue** — suggest "verwendet".

**Finding — "pendule" (French):** `analysis/views.py:228` — "pendule" is a wall clock. In chess the word for the clock is "chronomètre" or "temps restant". "pendule {time}" reads oddly. **Likely issue** — suggest "temps {time}" or "horloge {time}".

**Finding — "orologio" (Italian):** `analysis/views.py:228` — "orologio" is fine for a chess clock in Italian. No issue.

**Finding — "Engine" (German):** `analysis/views.py:221` — "Engine {value}" keeps the English word, matching the glossary ("board, move tree, engine" → "Brett, Zugbaum, Engine"). Consistent.

### Moves guide tip

> A game from lichess brings its evaluations and clocks: the inspector shows them for the move at the cursor, the moves stay clean. lichess's computer comments (⚙ Inaccuracy …) are folded to the judgement; Settings → Engine shows them in full or hides them.

| German | French | Italian |
|---|---|---|
| Eine Partie von lichess bringt ihre Bewertungen und Uhrzeiten mit: der Inspektor zeigt sie für den Zug am Cursor, die Züge bleiben übersichtlich. Die Computerkommentare von lichess (⚙ Inaccuracy …) sind auf das Urteil zusammengeklappt; Einstellungen → Engine zeigt sie ganz oder blendet sie aus. | Une partie de lichess apporte ses évaluations et ses pendules : l'inspecteur les montre pour le coup sous le curseur, les coups restent lisibles. Les commentaires de l'ordinateur de lichess (⚙ Inaccuracy …) sont réduits au jugement ; Réglages → Moteur les montre en entier ou les masque. | Una partita da lichess porta le sue valutazioni e i suoi orologi: l'ispettore li mostra per la mossa al cursore, le mosse restano pulite. I commenti del computer di lichess (⚙ Inaccuracy …) sono ridotti al giudizio; Impostazioni → Motore li mostra per intero o li nasconde. |

**Finding — "Uhrzeiten" (German):** "Uhrzeiten" means "times of day" (like 3:00 PM). For chess clocks, "Uhrzeiten" is misleading. Better: "Uhrstände" (clock readings) or "Zeitkontrollen". **Likely issue**.

**Finding — "pendules" (French):** Same issue as above — "pendules" is wrong for chess clocks. **Likely issue** — suggest "chronomètres" or "temps".

**Finding — "o" (German):** "Einstellungen → Engine zeigt sie ganz oder blendet sie aus" — the "oder" before "aus" is split oddly. Should be "oder blendet sie aus" (correct) but reads as "shows them fully or hides them". The English says "shows them in full or hides them" — the German captures this. Fine.

## 2. Code findings

### Bug: `evals_from()` never detects chess.com from Site header

`spaced_positions/analysis/tree.py:73-77` — `evals_from()` checks `owner.headers` for "lichess.org" and "chess.com", but `Site` and `Annotator` are in `ROSTER` (importer.py:33), so they're stored in `game.site` and `game.annotator`, not in `game.headers`. The function can only detect lichess via `ChapterURL` (not in ROSTER), which is a lichess-study-specific header.

**Impact:** A normal lichess game export (Site: "https://lichess.org/…") will show "PGN" instead of "lichess". A chess.com game will always show "PGN".

**Fix:** `evals_from()` should also check `getattr(owner, "site", "")` and `getattr(owner, "annotator", "")`.

**Confirmed** by test `test_chesscom_export_imports_correctly` which documents the gap.

### The `evals_from()` check is case-sensitive

`tree.py:77` — `"chess.com" in where` is case-sensitive. A Site header like "Chess.com" (capital C) won't match. Even if the bug above were fixed, "Chess.com" would not be detected.

**Fix:** Use `.lower()` on both sides: `"chess.com" in where.lower()`.

## 3. Test fixtures added

Four new fixtures in `tests/fixtures/pgn/`:

- **chessbase-export.pgn** — ChessBase-style `[%eval 0.25,23]` with depth, `[%emt]` elapsed time, no lichess headers. Source label: "PGN".
- **lichess-game-with-clocks.pgn** — lichess game with `[%clk]` on every move, `TimeControl "180+2"`, `ChapterURL` for source detection. Verifies clock storage and "used" computation.
- **nested-variations-eval.pgn** — Game with nested variations carrying `[%eval]`. Verifies evals on variation nodes.
- **chesscom-export.pgn** — Chess.com export with `Url` header. Verifies game import; documents the `evals_from` gap.

Four new tests added to `tests/test_pgn_annotations.py`:

- `test_chessbase_pgn_has_eval_depth_and_emt_and_pgn_source`
- `test_lichess_game_with_clocks_computes_used_time_for_both_sides`
- `test_nested_variations_carry_evals`
- `test_chesscom_export_imports_correctly`

## 4. Verification

- All 154 Python tests pass (`pytest -q -m "not browser"`).
- `design check`: 0 errors, 0 warnings.
- Manual visual check of the move tree in the browser: **not performed** (no browser access). The programmatic tests verify the tree HTML contains no `[%eval` commands and shows the computer comment marker.

## 5. Summary of issues

| Severity | Where | What |
|---|---|---|
| Bug | `tree.py:73-77` | `evals_from()` checks `headers` dict only; Site/Annotator are in ROSTER → stored in model fields. Can't detect lichess from Site or chess.com at all. |
| Bug | `tree.py:77` | `"chess.com" in where` is case-sensitive; "Chess.com" won't match. |
| Translation | `views.py:229` de | "gebraucht" → suggest "verwendet" for time consumed. |
| Translation | `views.py:228` fr | "pendule" → suggest "temps" or "chronomètre" for chess clock. |
| Translation | `help/moves.html` de | "Uhrzeiten" → suggest "Uhrstände" for clock readings. |
| Translation | `help/moves.html` fr | "pendules" → same as above. |

## Files changed

- `tests/fixtures/pgn/chessbase-export.pgn` — new fixture
- `tests/fixtures/pgn/lichess-game-with-clocks.pgn` — new fixture
- `tests/fixtures/pgn/nested-variations-eval.pgn` — new fixture
- `tests/fixtures/pgn/chesscom-export.pgn` — new fixture
- `tests/test_pgn_annotations.py` — 4 new tests added
- `docs/reviews/2026-10-31-pgn-annotations-review.md` — this review
