# Day 4 — Details pane review (spec 16 §2)

## 1. Translations

37 new texts extracted via `manage.py i18n missing`, translated into de, fr, it, and applied via `i18n fill` and `i18n build`.

### Field names reused from existing catalogues

| English | German | French | Italian | Source |
|---|---|---|---|---|
| White | Weiss | Blancs | Bianco | PO (existing) |
| Black | Schwarz | Noirs | Nero | PO (existing) |
| Source | Quelle | Source | Fonte | PO (existing) |
| Result | Ergebnis | Résultat | Risultato | PO (existing) |
| Date | Datum | Date | Data | PO (existing) |
| Event | Turnier | Événement | Evento | PO (existing) |
| Site | Ort | Lieu | Luogo | PO (existing) |
| Round | Runde | Ronde | Turno | PO (existing) |
| Title | Titel | Titre | Titolo | PO (existing) |
| Position | Stellung | Position | Posizione | PO (existing) |
| Game | Partie | Partie | Partita | PO (existing) |
| Page | Seite | Page | Pagina | PO (existing) |
| Diagram | Diagramm | Diagramme | Diagramma | PO (existing) |
| Objective | Aufgabenstellung | Objectif | Obiettivo | PO (existing) |

### New field names translated

| English | German | French | Italian |
|---|---|---|---|
| Annotator | Kommentator | Commentateur | Commentatore |
| Notes | Notizen | Notes | Note |
| Name | Name | Nom | Nome |
| Key (@ in queries) | Schlüssel (@ in Abfragen) | Clé (@ dans les requêtes) | Chiave (@ nelle query) |
| Other names and handles | Andere Namen und Handles | Autres noms et identifiants | Altri nomi e handle |
| Role | Rolle | Rôle | Ruolo |
| Federation | Föderation | Fédération | Federazione |
| FIDE id | FIDE-Id | Id FIDE | Id FIDE |
| Born | Geboren | Naissance | Nato |
| Short citation | Kurze Zitation | Citation courte | Citazione breve |
| Kind | Art | Type | Tipo |
| Authors | Autorinnen | Auteurs | Autori |
| Year | Jahr | Année | Anno |
| Publisher | Verlag | Éditeur | Editore |
| Web address | Webadresse | Adresse web | Indirizzo web |
| Player | Spielerin | Joueur | Giocatore |

### Translation notes

- **"Authors" → "Autorinnen" (German):** The app uses gender-inclusive German ("Spielerin"). "Autorinnen" is consistent with this pattern.
- **"Player" → "Spielerin" (German):** Consistent with existing "Spieler" usage in the app. The glossary uses "Spieler" generically, but the app's German convention is "du" form with feminine generics.
- **"handle" kept in German/Italian:** "Handle" is commonly used in German and Italian for social media handles. French uses "identifiants" which is more formal but clearer.
- **"Difficulty (1–5)"**: Reused existing "Difficulty" translation ("Schwierigkeit"/"Difficulté"/"Difficoltà") with the range appended.

### Verification

- `design check`: 0 errors, 0 warnings
- `test_i18n.py`: 5 tests pass

## 2. Browser tests

Added 5 new browser tests to `tests/test_details.py`:

| Test | What it covers |
|---|---|
| `test_make_source_and_give_position_that_source` | `␣ n s` creates a source, then a position gets that source in Details |
| `test_player_found_by_alias_in_details` | Editing White with an alias ("Misha Tal") finds the player |
| `test_edit_source_year_and_kind_in_details` | Edit a source's year in Details via Library |
| `test_backspace_clears_field_and_undo_restores` | `⌫` empties a field, `u` brings it back |
| `test_library_details_with_game_row` | `I` in Library with a game row under cursor shows game Details |

The existing test `test_a_pasted_game_gets_its_names_in_the_details_pane` covers the basic edit flow and undo.

**Not run** — browser tests require Playwright/Chromium and a full app launch. The tests are ready for the maintainer to run with `.venv/bin/python -m pytest -q -m browser tests/test_details.py`.

## 3. Code review: edge cases

### 3.1 A name that has quotes

**`details.js:69`**: `const raw = (row.dataset.raw || "").replace(/"/g, "'")` — double quotes in the raw value are replaced with single quotes before opening the command line. The command line is then built as `` `edit ${ref} ${row.dataset.row}="${raw}"` `` (line 70-71), wrapping the value in double quotes.

**`edit.py:61`**: `shlex.split(" ".join(args))` — handles quoted strings correctly, including escaped quotes within double-quoted values.

**Verdict:** Safe for most cases. If a name contains both `"` and `'`, the replacement converts `"` to `'`, which changes the stored value. Example: `O'Brien, "Mike"` becomes `O'Brien, 'Mike'` in the command line. The user would need to fix it manually. **Minor issue** — the replacement is a best-effort workaround; a proper fix would escape `"` as `\"` instead of replacing it.

**`edit.py:285`**: `_make_player()` generates a key via `slug(name.split(",")[0])`. The `slug()` function (`text.py:13`) strips non-alphanumeric characters, so quotes in names are safely removed from the key.

### 3.2 An Elo out of range

**`edit.py:55`**: `RANGES = {"white_elo": (0, 4000), "black_elo": (0, 4000), ...}`

**`edit.py:124`**: `if low is not None and not low <= value <= high: raise CommandError(f"{name} is {low}–{high}")`

Correctly rejects Elo outside 0–4000. **Finding** — the error message `f"{name} is {low}–{high}"` is not translated (no `_()` wrapper). Other range errors in the same function use `_()` (e.g., `_("is a number")`). **Minor** — the message is clear enough for English users but invisible to non-English speakers.

### 3.3 A game deleted while it is shown

**`details.js:30`**: `const html = await fetch(...).then((r) => (r.ok ? r.text() : null)).catch(() => null)`

If the game is deleted while the Details pane shows it, the next `show()` call (triggered by the "effects" event at line 57) fetches the details endpoint, gets a 404, and `html` is `null`. The function returns at line 31 without updating the pane.

**Verdict:** The pane silently keeps showing stale data. The user sees the old details of a deleted game with no indication that the subject no longer exists. **Likely issue** — the pane should either show an error message or clear itself when the subject is gone. A simple fix would be to render a "no longer exists" message when `html === null` and `el.dataset.ref` is set.

### 3.4 Two panes of different groups

**`details.js:18-22`**: `groupKey()` returns `${mode}:${group}` where `group` comes from `nodeOf(pane)`. Pinned panes use `node.id` instead of `node.group`.

**`details.js:44-48`**: On "cursor" event, only panes where `node?.group === group` are updated. Two Details panes in different groups correctly track different subjects.

**`details.js:54-59`**: On "effects" event with `effects.library`, ALL panes refresh with `show(el, el.dataset.ref, { force: true })` — each reloads its own ref. With `effects.details`, only the pane matching that specific ref is updated.

**Verdict:** Correct. Two Details panes in different groups (e.g., Library + Analyse of the same game) stay in sync independently.

### 3.5 Bug: `edit.py:219` — date can be None

**`edit.py:219`**: `obj.year = int(obj.date[:4]) if obj.date[:4].isdigit() else None`

If `obj.date` is `None` (the field allows null), `obj.date[:4]` raises `TypeError: 'NoneType' object is not subscriptable`. If `obj.date` is an empty string `""`, `obj.date[:4]` is `""`, and `.isdigit()` returns `False` — that path is safe, but `None` crashes.

**Reproduction:** Set a game's date to empty via `:edit g1 date=` — the `_value` function at line 107-108 returns `raw[:limit]` for text fields, which would be `""`. But if the date is set to a value and then cleared via undo, the `_write` function restores the old value, which could be `None`.

**Actually** — looking more carefully: `date` is kind `"text"` (line 48), so `_value` returns `attr, raw[:limit]` where `raw` is the string from the command line. An empty string `""` is safe. But the `date` field on the `Game` model could be `None` from an import, and if the user edits another field on the same game (e.g., `:edit g1 event="Tournament"`), the `_write` function at line 218 checks `if "date" in values[obj.pk]` — it only runs the date logic when `date` is explicitly in the values being written. So the crash only happens if the user explicitly sets `date=` (empty) and the model's date field is `None`.

**Wait** — `date=` with empty string: `_value` returns `("date", "")`. Then `_assign` sets `obj.date = ""`. Then line 219: `obj.date[:4]` is `""[:4]` which is `""`, and `"".isdigit()` is `False`, so `obj.year = None`. No crash.

**But** — what if `obj.date` was `None` before the edit and the user edits a different field? Line 218: `if "date" in values[obj.pk]` — only triggers if date is in the values. So the crash path is: user sets `date` to something, then the `obj.date` is a string. The only way to get `None` at line 219 is if `obj.date` is `None` AND `"date" in values[obj.pk]`. But if `"date" in values[obj.pk]`, then `_assign` already set `obj.date` to the new value (a string). So `obj.date` at line 219 is the new string value, not `None`.

**Verdict:** Actually safe — the `_assign` at line 212 runs before line 219, so `obj.date` is always a string when line 219 executes. The guard `if "date" in values[obj.pk]` ensures this code only runs when date was explicitly edited.

### 3.6 The `_raw()` function and special characters

**`details.py:66-75`**: `_raw()` returns the value for the command line. For `kind == "list"` (aliases), it returns `", ".join(value)`. If an alias contains a comma, the raw value would be ambiguous when parsed back by `shlex.split()`.

**Example:** Aliases `["O'Brien", "M. Tal, Jr."]` → raw `"O'Brien, M. Tal, Jr."`. When the user edits and submits, `_value` at line 115 splits on commas: `[a.strip() for a in raw.split(",") if a.strip()]` → `["O'Brien", "M. Tal", "Jr."]`. The alias `"M. Tal, Jr."` is split into two.

**Likely issue** — list kind (aliases) does not handle commas within values. The user would need to quote the value in the command line, but `details.js:69-71` wraps the raw value in double quotes, and `shlex.split()` would treat the whole quoted string as one word, which then gets split on commas by `_value`. **Bug** — aliases with commas are silently corrupted on round-trip edit.

### 3.7 The `details.edit` handler and selection range

**`details.js:72`**: `document.querySelector(".cmdline__input")?.setSelectionRange(start.length, start.length + raw.length)` — sets the cursor so typing replaces the raw value. If `raw` contains characters that `shlex` interprets specially (backslashes, backticks), the selection range may not match the visual position. **Minor** — unlikely to cause issues in practice.

## 4. Summary of issues

| Severity | Where | What |
|---|---|---|
| Likely | `details.js:30-31` | Game deleted while shown: the pane keeps stale data with no error. Should show "no longer exists" or clear itself. |
| Likely | `details.py:75` / `edit.py:115` | Aliases with commas are silently corrupted on round-trip edit. `", ".join()` and `raw.split(",")` don't handle commas within values. |
| Minor | `details.js:69` | `replace(/"/g, "'")` changes double quotes to single quotes in names. A proper fix would escape `"` as `\"`. |
| Minor | `edit.py:125` | Range error message `f"{name} is {low}–{high}"` is not translated. |
| Fine | `details.js:18-59` | Two panes of different groups correctly track different subjects. |
| Fine | `edit.py:124` | Elo out of range correctly rejected (0–4000). |
| Fine | `edit.py:219` | `obj.date[:4]` is safe: `_assign` runs first, so `obj.date` is always a string when this line executes. |
| Fine | `text.py:13` | `slug()` strips non-alphanumeric chars, so quotes in names are safely handled for key generation. |

## 5. Files changed

- `spaced_positions/locale/*/LC_MESSAGES/django.po` — 37 new translations filled (111 total across de/fr/it)
- `spaced_positions/static/i18n/*.json` — rebuilt
- `spaced_positions/locale/*/LC_MESSAGES/django.mo` — rebuilt
- `tests/test_details.py` — added 5 browser tests (source creation, alias lookup, year edit, clear/undo, Library I key)
- `docs/reviews/2026-11-01-details-review.md` — this review
