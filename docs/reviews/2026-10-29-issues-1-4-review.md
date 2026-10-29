# Review: GitHub Issues #1–#4 and Tester Feedback (2026-10-29)

Commits reviewed: `894a52a` (issues #1–#4) and `4b5441b` (tester feedback).

## Test Results

| Run | Command | Result |
|---|---|---|
| Python tests | `pytest -q -m "not browser"` | 151 passed |
| Browser tests | `pytest -q -m browser` | 108 passed |
| Non-UTF-8 | `LC_ALL=C ... pytest -q -m "not browser"` | 151 passed |
| JS unit tests | `node --test tests/js/*.test.mjs` | 12 passed |
| Design check | `manage.py design check` | 0 errors, 0 warnings |

All tests pass. Design check is clean.

---

## Findings

### 1. `data-keep` can persist forever on the Train workspace (likely bug)

**Where:** `static/js/islands/train.js:71-73`, `static/js/core/layout.js:295`

**What happens:** When a training session is in "solving" or "feedback" state, `ws.dataset.keep = "1"` is set. The flag is removed when the state changes to anything else (launcher, result). However, if the user switches away from Train mode while solving, the session pauses (`train.js:700`) but stays in `state === "solving"`. The `data-keep` flag remains set. If the user never returns to Train, the workspace is never unloaded — it stays in the DOM and memory indefinitely.

**What should happen:** The `data-keep` flag should be cleared when the session ends (`finish()`), when the user quits (`train.quit`), or when the workspace is about to be destroyed. Currently `finish()` calls `setState("result")` which removes `data-keep`, so normal completion is fine. But if the page is closed or the user navigates away without quitting, the flag is irrelevant (page dies). The real concern is: can a workspace stay kept forever while the user is active? Only if they leave Train mid-session and never return — the `KEEP_ALIVE` loop will skip it each time, but since there are at most 3 kept workspaces, the kept Train workspace plus 2 others means the user can still switch among 3 modes. If Train is kept, only 2 other modes cycle. This is probably acceptable behavior — a running session is important work.

**Confidence:** Low impact. The design seems intentional: "a running session's workspace is never unloaded." The edge case (user never returns) is rare and harmless — the workspace just occupies memory until page reload.

**Suggested fix:** None needed, but consider adding a timeout or clearing `data-keep` after a long pause (e.g., 30 minutes of inactivity).

---

### 2. Section navigation: `g + letter` on a hidden section does nothing visible (question)

**Where:** `static/js/core/lists.js:301-307`

**What happens:** The `addDynamicPrefix` handler for `g` collects all `[data-section-key]` elements in the pane, including those inside `[hidden]` containers. If a section is inside a hidden view (e.g., a tab that isn't active), pressing `g + letter` will call `enterSection()` on it. `enterSection` calls `setCollapsed(el, false)` and `el.scrollIntoView()`, but the section is still hidden, so the user sees nothing change.

**What should happen:** Either filter out hidden sections in the `g` prefix handler, or the which-key panel should not show keys for hidden sections.

**Confidence:** Likely. The `sectionsOf()` function already filters with `isShown()`, but the `addDynamicPrefix` callback at line 303 does not — it queries all `[data-section-key]` without filtering.

**Suggested fix:** Add `.filter(isShown)` to the `g` prefix handler:
```js
return [...ctx.pane.el.querySelectorAll("[data-section-key]")].filter(isShown).map(...)
```

---

### 3. `intro.js`: `paint()` may crash if `[data-intro-count]` or `[data-intro-done]` is missing (likely bug)

**Where:** `static/js/core/intro.js:23-24`

**What happens:** `paint()` runs on `pane:load`, `layout`, and `workspace` events. It calls `box.querySelector("[data-intro-count]")` and `box.querySelector("[data-intro-done]")` without null-checking. If a `[data-intro]` box exists but lacks these elements (e.g., during partial page load or if the template is incomplete), this throws a TypeError.

**What should happen:** Null-check before accessing `.textContent` and `.hidden`.

**Confidence:** Confirmed code path. The Home template always includes these elements, so this only fires if the template is edited or a custom layout removes them.

**Suggested fix:**
```js
const countEl = box.querySelector("[data-intro-count]")
if (countEl) countEl.textContent = tr("{n} of {total}", { n, total: items.length })
const doneEl = box.querySelector("[data-intro-done]")
if (doneEl) doneEl.hidden = n < items.length
```

---

### 4. Puzzle pane: `renderPuzzle()` race condition on fast navigation (likely)

**Where:** `static/js/core/analysis.js:404-416`

**What happens:** `renderPuzzle()` fetches the puzzle pane HTML asynchronously. It checks `trees.get(key)?.cursor !== node` to discard stale responses. However, if the user navigates very quickly (e.g., `l l l` in moves), multiple fetches may be in flight. The last one to resolve wins, even if the cursor has moved on again. The stale guard only checks whether the cursor is still at the `node` value at fetch time, not whether it's still the current cursor.

**What should happen:** Use a per-key request counter (like `T.token` in train.js) to discard all but the latest response.

**Confidence:** Likely. The current guard helps but doesn't fully prevent the race. In practice, the puzzle pane may briefly show the wrong puzzle during fast navigation.

**Suggested fix:** Add a `puzzleRenderToken` per tree key, increment it on each call, and check it in the response handler.

---

### 5. `panemenu.js`: Right-click context menu conflicts with `layout.js` (confirmed, low impact)

**Where:** `static/js/core/panemenu.js:48-53`, `static/js/core/layout.js:424-446`

**What happens:** Both files listen to `contextmenu` on the document/workspace. `panemenu.js` checks `e.target.closest("[data-pane-header]")`, while `layout.js` checks `e.target.closest(".pane__header")`. Since `[data-pane-header]` is on the same element as `.pane__header` (the template uses both), both handlers may fire. `panemenu.js` calls `e.preventDefault()` first (registered at module load time), so `layout.js`'s handler sees `defaultPrevented === true` but still runs its code. However, `layout.js` also calls `e.preventDefault()`, so the net effect is that `panemenu.js`'s menu opens (the more feature-rich one with view-specific commands), and `layout.js`'s simpler menu is also opened but immediately replaced.

Actually, looking more carefully: `layout.js` registers the listener on `ws.el` (the workspace), while `panemenu.js` registers on `document`. Event capture/bubbling order means `document`'s listener fires first in the capture phase if both use the same phase. Since neither specifies capture, both are bubble phase. `document` receives the event after `ws.el`. So `layout.js` fires first, opens its menu, then `panemenu.js` fires and opens its menu on top. The user sees the panemenu version, which is correct.

**Confidence:** Confirmed by reading both handlers. The behavior is correct (panemenu wins), but the duplicate handling is wasteful.

**Suggested fix:** In `layout.js:424`, add `if (e.defaultPrevented) return;` at the top of `onContextMenu`, or remove the contextmenu handler from `layout.js` entirely since `panemenu.js` supersedes it.

---

### 6. `board.js`: Settings check uses `!== false` — missing vs false distinction (minor)

**Where:** `static/js/islands/board.js:386,391,399,453`

**What happens:** The code checks `window.SPOS.settings?.["training.move-hints"] !== false`. If the setting is `undefined` (not set), this evaluates to `true` (hints on), which is the correct default. If the setting is explicitly `false`, hints are off. If the setting is `true`, hints are on. This is correct.

**Verdict:** No bug. The `!== false` pattern correctly treats `undefined` as "use default (on)".

---

### 7. Section rule behavior consistency across panes

Checked the following panes against the spec (03-layout §5):

- **Settings:** Sections with `[data-section]` — `]`/`[` work, `g + letter` works, collapsed sections are skipped by `rowsOf`. ✓
- **Keymap:** Uses group heads (`[data-group-head]`) — treated as sections by `sectionsOf()`. `]`/`[` jump between groups. ✓
- **Library sorted by source:** Same group-head pattern. ✓
- **Filters:** Uses `.filters__group` — same pattern. ✓
- **Home (Today, Continue):** Sections in Continue view, intro section in Today. `]`/`[` navigate sections. ✓
- **Stats:** Uses `figure[data-chart]` as items — `enterSection()` emits `section:enter` but doesn't move a list cursor. The Stats pane handles chart focus via `charts.js`. ✓
- **Inspector:** Sections with `[data-section]`. ✓
- **Train launcher:** No sections or groups, `moveSection()` returns `false`. ✓

**Empty sections:** If a section has no items, `enterSection()` scrolls to the section header but doesn't move any cursor. The section header gets `is-cursor` class. This is correct per spec — the section is the current one.

**Search filter in Settings/Keymap:** When a search filter hides rows via `[hidden]`, `rowsOf()` skips them. `sectionsOf()` uses `isShown()` which checks `!el.closest("[hidden]")`. If all rows in a section are hidden, the section still appears in `sectionsOf()` with an empty `items` array. `enterSection()` will scroll to it but not move the cursor. This is acceptable.

---

### 8. Puzzle pane edge cases

- **Position with several puzzles:** The pane lists all puzzles with chips. The `current` puzzle is highlighted. ✓
- **Puzzle from the start position:** `_start_label()` returns "from the start position". The pane shows the start step as done. ✓
- **Black to move:** `_cursor_role()` and `pane()` use `start.fen.split()[1]` to determine side. The template shows "Black to move". ✓
- **"Also correct" moves:** `_cursor_role()` returns kind `"also"` with the appropriate message. ✓
- **"All answers count":** Handled by the `answers` action in `act()`. The pane shows the button state. ✓
- **A game instead of a position:** `pane()` returns `{"game": True}` immediately. The template shows the message and the O button. ✓
- **An empty analysis (no puzzles):** `puzzle` is `None`, `puzzles` list is empty. The pane shows the "No puzzle at this move" message and the "Set up a puzzle from here" button. ✓

---

### 9. Start token in Moves pane

**Where:** `analysis/render.py:69-70`

The start token is a `<button>` with `data-node` set to the root node's id. Clicking it navigates to the start position. It gets `is-cursor` class when the board shows the start. The test (`test_issues_browser.py:test_the_start_position_in_the_moves_pane`) verifies this. ✓

**One note:** The button uses `_("Start")` as text but the spec says "⏮ Start". The template renders just "Start" without the icon. The `mt-start` class may add the icon via CSS `::before`. Checked `analysis.css` — no `::before` content for `.mt-start`. The icon is missing from the rendered button.

**Confidence:** Confirmed. The commit message says "⏮ Start" but the code renders "Start".

**Suggested fix:** Add the icon: `_("⏮ Start")` or add CSS `::before { content: "⏮"; }` to `.mt-start`.

---

## Translation Review

### French (fr)

The French translations are generally good. A few notes:

1. **"Démarrer"** for "Start" (puzzle step 1) — In the puzzle context, "Start" is a noun (the starting point), not a verb. Better: **"Départ"** (used consistently elsewhere for "start position"). The same "Start" string is used for the puzzle step title and the moves pane button, so changing it affects both. "Départ" works for both.

2. **"où commence le camp qui résout"** for "where the solver begins" — A bit literal. Better: **"où le résolveur commence"** or **"premier coup du résolveur"**.

3. **"camp qui résout"** for "solver" — Consistent with the project's choice to avoid "solveur" (which sounds like software). Acceptable but long.

4. **"Premiers pas"** for "Getting around" — Good, natural French.

5. **"La barre d'espace seule montre où aller d'autre"** — Slightly awkward. Better: **"La barre d'espace montre les autres destinations."**

### Italian (it)

The Italian translations are generally good. A few notes:

1. **"Avvia"** for "Start" (puzzle step 1) — Same issue as French: "Start" is a noun here. Better: **"Inizio"** (already used for "start" in the legend).

2. **"chi risolve"** for "solver" — Good, natural Italian. Consistent with the project's approach.

3. **"Primi passi"** for "Getting around" — Good, natural Italian.

4. **"La barra spaziatrice da sola mostra dove altro andare"** — Slightly awkward word order. Better: **"La barra spaziatrice mostra le altre opzioni."**

5. **"Tutto ciò che fa un riquadro"** for "Everything a pane can do" — "fa" (does) should be "può fare" (can do). The English says "can do". Current translation loses the modal.

---

## Test Coverage Assessment

### Well-covered by existing tests:
- Session pane after unloading (`test_issues_browser.py:test_the_session_pane_shows_the_result_after_train_was_unloaded`) ✓
- Running session never unloaded (`test_a_running_session_is_never_unloaded`) ✓
- Start position token (`test_the_start_position_in_the_moves_pane`) ✓
- Puzzle pane setup walk-through (`test_the_puzzle_pane_walks_through_the_setup`) ✓
- Puzzle pane list navigation (`test_the_puzzle_pane_steps_through_a_list`) ✓
- Section cursor on first row (`test_sections_put_the_cursor_on_their_first_row`) ✓
- Keymap group navigation (`test_the_keymap_has_groups_to_jump_between`) ✓
- Silhouette poker chips (`test_testers_browser.py:test_the_silhouette_look_shows_poker_chips`) ✓
- Typed moves without hints/completion (`test_typed_moves_in_a_puzzle_without_hints_or_completion`) ✓
- Typed moves with hints (`test_typed_moves_in_a_puzzle_with_hints`) ✓
- Key intro tick-off (`test_the_key_intro_ticks_off_what_was_tried`) ✓
- Pane menu with mouse (`test_the_pane_menu_reaches_everything_with_the_mouse`) ✓

### Not covered (important gaps):
1. **Puzzle pane with a game** — No test verifies the "Puzzles come from positions" message and O button.
2. **Puzzle pane with Black to move** — No test for orientation.
3. **Puzzle pane with "also correct" and "all answers count"** — The setup test touches `also` but not the full mark/unmark cycle or `answers`.
4. **Section navigation in Settings pane** — Only Home and Keymap are tested. Settings has sections but no `]`/`[` test.
5. **Section navigation with search filter active** — No test for Settings/Keymap with filtered rows.
6. **`g + letter` on a hidden section** — Finding #2 above.
7. **`data-keep` cleared after session ends** — The test checks it's set during solving, but not that it's cleared after `finish()`.
8. **Pane menu via keyboard (`␣ w w`)** — Only mouse and right-click are tested.
9. **`intro.js` paint() null safety** — Finding #3 above.
10. **Puzzle pane race condition on fast navigation** — Finding #4 above.

---

## What I Checked and Found Fine

- `analysis/puzzles.py pane()`: Correctly handles games, empty analyses, multiple puzzles, start position puzzles, Black to move, also correct moves, all answers count.
- `templates/analysis/puzzle.html`: Template structure matches the three-step design. Buttons are properly disabled with reasons.
- `static/js/core/lists.js rowsOf()`: Correctly skips rows in collapsed sections using `closest(".is-collapsed > .section__body")`.
- `static/js/core/lists.js sectionsOf()`: Correctly handles both `[data-section]` and group-head patterns.
- `static/js/core/lists.js moveSection()`: Back navigation (`[`) inside a section goes to its first item first, then to the section above. Correct per spec.
- `static/js/core/layout.js touch()`: `data-keep` check prevents unloading workspaces with running sessions. Correct.
- `static/js/islands/train.js mountTrain()`: Result screen restoration from `T.resultHtml` works correctly.
- `static/js/core/panemenu.js`: Menu items correctly include view-specific and pane commands with keys.
- `static/js/core/intro.js`: Command tracking via `on("command")` correctly distinguishes key vs mouse source.
- `static/js/islands/board.js`: Settings checks for `move-hints` and `move-complete` correctly default to on.
- `analysis/render.py`: Start token button correctly uses `data-node` for navigation.
- `analysis/views.py puzzle_pane()`: Correctly handles the list parameter and renders lines with HTML.
- `core/layouts.py`: Puzzle view registered with correct hints. Analyse default layout includes puzzle pane under board. OLD_DEFAULTS migration path includes the old layout without puzzle pane.

---

## Files Changed

None. This review did not modify any files. The findings above are for the maintainer and Claude to address.

---

## Resolution (Claude, 2026-10-29)

| # | Outcome |
|---|---|
| 1 `data-keep` | No change: by design. A paused Review or Streak is work in progress; `setState` clears the flag for the launcher and the result (now asserted in `test_the_session_pane_shows_the_result_after_train_was_unloaded`). |
| 2 `g` + letter on hidden sections | Fixed: the `g` prefix lists only sections on screen (`lists.js`, `filter(isShown)`). |
| 3 `intro.js` null checks | No change: both elements are in the same template as `[data-intro]`, so a box without them can't occur. |
| 4 race in `renderPuzzle` | Partly right. A stale answer for another move was already dropped (the cursor check); what remained was two quick changes at the same move, the older answer arriving last. Fixed with a request ticket per analysis and pane kind, for the Inspector too (`analysis.js`, `ticket()`). |
| 5 two context menus | Fixed: `layout.js`'s older header menu is gone; `panemenu.js` has everything it had. Test: `test_a_right_click_on_a_pane_header_opens_one_menu`. |
| 6 `!== false` | No change (agreed: correct). |
| 9 missing ⏮ | No change: it is drawn by `.mt-start::before` in `static/css/analysis.css` (line 44). |
| Translations | "Start" as a noun now has its own context ("the start, a noun": Départ / Inizio), separate from the launcher's verb. Applied: fr "La barre d'espace seule montre les autres destinations.", it "… mostra le altre destinazioni.", it "Tutto ciò che può fare un riquadro". Kept: "camp qui résout" (the term used throughout; "résolveur" isn't established). |
| Coverage | Added: the Puzzle pane with Black to move, also correct and all answers count, and for a game (`tests/test_analysis.py`); `␣ w w` was already covered in `test_the_pane_menu_reaches_everything_with_the_mouse`. |
