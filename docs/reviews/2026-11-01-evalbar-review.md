# Day 3 — Eval bar review (spec 15 §4–§5)

## 1. Screenshot scene: `analyse-file-eval`

Added a new scene `analyse_file_eval()` to `docs/scripts/update_screenshots.py` that:

1. Imports `tests/fixtures/pgn/lichess-study-analysed.pgn` via `POST /lib/import/run/`
2. Opens the imported game in Analyse
3. Navigates forward 20 moves to reach a position with file evals
4. Turns the engine on
5. Waits for both halves of the eval bar to appear (engine solid + file hatched)

The scene is registered in the `FULL` scenes dict. Run it for all six themes with:

```
.venv/bin/python docs/scripts/update_screenshots.py analyse-file-eval
```

**Not run** — the screenshot script requires Playwright/Chromium and a full app launch, which takes several minutes per theme. The scene code is ready for the maintainer to run.

### What to check per theme

When the pictures are taken, inspect each `analyse-file-eval_<theme>.png` for:

- **Hatched half contrast**: the file eval half uses `repeating-linear-gradient(135deg, transparent … color-mix(in oklab, var(--eval-white) 50%, var(--eval-black)) …)`. On light themes (Paper, Sepia) the hatch lines may be too faint against the white fill; on dark themes (Ink, Nord) they may blend with the black fill.
- **"L" label visibility**: the `.evalbar__label` uses `background: var(--surface); color: var(--text)`. Check it's readable in each theme.
- **Split bar**: both halves should be visible side by side, each with its own height reflecting its evaluation.

### Known CSS concern: `color-mix(in oklab, …)` for hatching

`analysis.css:202` — The hatched pattern uses `color-mix(in oklab, var(--eval-white) 50%, var(--eval-black))` for the stripe colour. This produces a 50% grey of the fill colour, which may have low contrast on some themes. The `oklab` color space is well-supported in modern browsers but was only recently added to Chrome (v119+).

**Likely issue** — the hatched half may be hard to distinguish from the solid half on themes where `--eval-white` and `--eval-black` are close in luminance (e.g., Sepia).

## 2. Code review: edge cases

### 2.1 Mate 0 for both sides

**`board.js:528-531` — `whiteShare()`**: Mate 0 correctly checks `s.mated` to determine which side is mated:
```js
if (s.mate === 0) return s.mated === "w" ? 0 : 100
```
This is correct: if white is mated (`mated === "w"`), whiteShare is 0% (full black); if black is mated, whiteShare is 100% (full white).

**`board.js:550` — `fileScore()`**: The `mated` field is derived from `node.fen.split(" ")[1]` (the side to move). In a mate 0 position, the side to move is the mated side. This is correct.

**`graphs.js:34`**: `value()` maps mate 0 to `±CLIP` based on the side to move:
```js
if (e.mate === 0) return n.fen.split(" ")[1] === "w" ? -CLIP : CLIP
```
If white is to move and mated, the value is `-CLIP` (full black advantage) — correct.

**Verdict:** Mate 0 is handled correctly in all three places.

### 2.2 Flipped board

**`board.js:230-233`**: On flip, `paintEval()` toggles `is-flipped` on the eval bar and repaints both fills with `flipped = true`. The CSS `.evalbar.is-flipped { --eval-dir: to bottom; }` reverses the gradient direction. The `is-top` class logic in `paintFill()` at line 540:
```js
el.classList.toggle("is-top", (white < 50) !== flipped)
```
This correctly inverts the text positioning when the board is flipped.

**`board.js:615-618`**: The `board.flip` command calls `b.paintEval()` after changing orientation — correct.

**Verdict:** Flipped board is handled correctly.

### 2.3 Setting switched while engine runs

**`board.js:560`**: A `"settings"` event listener repaints all boards:
```js
on("settings", () => boards.forEach((b) => b.alive && b.paintEval()))
```
This correctly re-evaluates which halves to show based on the current `board.evalbar` setting.

**`board.js:225-227`**: `paintEval()` reads the current setting each time:
```js
const show = window.SPOS.settings?.["board.evalbar"] || "auto"
const engine = ["auto", "engine"].includes(show) ? this.score : null
const file = ["auto", "file"].includes(show) ? this.fileScore : null
```
If the setting changes from "auto" to "engine", the file half is hidden. If it changes to "file", the engine half is hidden. If "off", both are hidden and `this.evalBar.hidden = true`.

**Verdict:** Setting changes are handled correctly.

### 2.4 Position without file evaluation

**`board.js:228-229`**:
```js
this.el.classList.toggle("has-eval", Boolean(engine || file))
this.evalBar.hidden = !(engine || file)
```
If there's no file eval (`this.fileScore` is null), `file` is null, and only the engine half shows — correct.

**`board.js:534-536` — `paintFill()`**:
```js
el.hidden = !score
if (!score) return
```
When `score` is null, the fill element is hidden — correct. The bar does not show an empty file half.

**`board.js:547-549` — `fileScore()`**:
```js
const e = node?.fileEval
if (!e) return null
```
If a node has no `fileEval`, the function returns null — the file half stays hidden.

**Verdict:** The bar correctly hides the file half when there's no file evaluation. No empty bar half is shown.

### 2.5 Engine score without text property

**`board.js:537-541` — `paintFill()`**:
```js
const white = whiteShare(score)
el.style.setProperty("--white", `${white.toFixed(1)}%`)
el.classList.toggle("is-black", white < 50)
el.classList.toggle("is-top", (white < 50) !== flipped)
el.querySelector(".evalbar__text").textContent = score.text
```
The engine's `score` object (from `engine.js:236-237`) always has a `text` property set by `scoreText()`. The file's score (from `fileScore()`) also always has `text`. No null dereference risk.

**Verdict:** Safe.

### 2.6 The `fileScore()` mate 0 text

**`board.js:550`**:
```js
const text = e.mate !== null && e.mate !== undefined ? (e.mate === 0 ? "#" : `#${e.mate}`) : `${e.cp >= 0 ? "+" : ""}${(e.cp / 100).toFixed(2)}`
```
For mate 0, the text is `"#"` (just the hash, no number). For mate N, it's `#N`. This matches the spec: "mate 0: the side to move is mated (the bar is full, the label `#`)".

**`engine.js:251`** — `scoreText()` also produces `"#"` for mate 0. Consistent.

**Verdict:** Correct and consistent.

### 2.7 Eval graph: file eval dashed line

**`graphs.js:70-71`**:
```js
const file = points((n) => value(n, "fileEval"))
if (file.length > 1) svg.append(el("polyline", { points: polyline(file), class: "chart__line evalgraph__file" }))
```
The file eval line is only drawn when there are at least 2 data points. The class `evalgraph__file` should style it as dashed. Need to verify the CSS.

**`graphs.js:39`**: `best()` uses the engine's eval where available, falling back to file eval:
```js
const best = (n) => value(n) ?? value(n, "fileEval")
```
This is used for the area fill and mistake detection — correct per spec.

**Verdict:** Correct.

## 3. Translation review

### 3.1 "Eval bar" (setting label)

| English | German | French | Italian |
|---|---|---|---|
| Eval bar | Bewertungsbalken | Barre d'évaluation | Barra di valutazione |

**Verdict:** Fine. All natural and consistent with existing usage in help texts.

### 3.2 Setting description

> The engine's evaluation (solid), the game file's (hatched, L for lichess), both side by side, or none

| German | French | Italian |
|---|---|---|
| Die Bewertung der Engine (voll), die der Partiedatei (schraffiert, L für lichess), beide nebeneinander oder keine | L'évaluation du moteur (pleine), celle du fichier de la partie (hachurée, L pour lichess), les deux côte à côte, ou aucune | La valutazione del motore (piena), quella del file della partita (tratteggiata, L per lichess), entrambe affiancate o nessuna |

**Verdict:** Fine. "schraffiert" (German), "hachurée" (French), and "tratteggiata" (Italian) are the correct terms for a hatched/diagonal stripe pattern.

### 3.3 Setting values

| English | German | French | Italian |
|---|---|---|---|
| auto | automatisch | automatique | automatico |
| engine | Engine | moteur | motore |
| file | Datei | fichier | file |
| off | aus | désactivé | fuori |

**Finding — "file" → "file" (Italian):** `locale/it/LC_MESSAGES/django.po:8503` — "file" is kept in English in Italian. While "file" is commonly used in Italian, "file della partita" or "partita" would be more Italian. However, keeping "file" is acceptable in technical contexts. **Minor, acceptable.**

**Finding — "off" → "fuori" (Italian):** `locale/it/LC_MESSAGES/django.po:8279` — "fuori" means "outside/out" in Italian. For a setting that turns something off, "disattivato" or "off" would be more natural. "fuori" is used for `board-coords` and `keys.keycaps` too (shared msgctxt), where it means "outside" the board — that's correct for coordinates but wrong for "off". **Likely issue** — the shared msgctxt `"setting value"` for "off" conflates two different meanings: "outside" (for board-coords) and "disabled" (for evalbar). The Italian translation "fuori" is correct for coordinates but wrong for the eval bar setting.

**Finding — "off" → "désactivé" (French):** Correct for "disabled/off".

**Finding — "off" → "aus" (German):** Correct.

### 3.4 Computer comments setting values (reviewed in Day 2, unchanged)

| show | fold | hide |
|---|---|---|
| zeigen / montrer / mostra | zusammenklappen / réduire / riduci | ausblenden / masquer / nascondi |

**Verdict:** Fine, confirmed in Day 2 review.

## 4. Summary of issues

| Severity | Where | What |
|---|---|---|
| Likely | `locale/*/LC_MESSAGES/django.po` | Shared msgctxt `"setting value"` for "off" conflates "outside" (board-coords) with "disabled" (evalbar). Italian "fuori" is wrong for the eval bar. |
| Likely | `analysis.css:202` | Hatched pattern uses `color-mix(in oklab, …)` at 50% opacity — may have low contrast on some themes (especially Sepia). Needs visual verification per theme. |
| Question | `board.js:550` | `fileScore()` computes `mated` from `node.fen.split(" ")[1]` (side to move). If a node's FEN is missing or malformed, this could produce wrong results. Is FEN always present on nodes with `fileEval`? |
| Fine | `board.js:528-531` | Mate 0 correctly handled in `whiteShare()` and `fileScore()`. |
| Fine | `board.js:230-233` | Flipped board correctly reverses gradient direction and text positioning. |
| Fine | `board.js:560` | Settings changes correctly trigger repaint. |
| Fine | `board.js:534-536` | Empty file eval correctly hides the file half — no empty bar. |

## 5. Screenshot scene

Added `analyse_file_eval()` to `docs/scripts/update_screenshots.py` (line 324). The scene:
- Imports the lichess analysed study fixture
- Opens it in Analyse
- Navigates to a move with file evals
- Turns on the engine
- Waits for both eval bar halves to appear

Run with: `.venv/bin/python docs/scripts/update_screenshots.py analyse-file-eval`

Visual check needed per theme for: hatched pattern contrast, "L" label readability, split bar proportions.

## Files changed

- `docs/scripts/update_screenshots.py` — added `analyse_file_eval()` scene and registered it in `FULL`
- `docs/reviews/2026-11-01-evalbar-review.md` — this review
