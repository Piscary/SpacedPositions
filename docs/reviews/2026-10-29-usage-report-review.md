# Usage report review — 2026-10-29

## Goal

Review the usage report feature (`:test-report`) for privacy, correctness, and edge cases before the M0 test group
arrives. The report is the app's only data export — testers will send it to the maintainer.

## Files reviewed

- `core/usage.py` — server-side counting and report generation
- `static/js/core/usage.js` — browser-side counting and flush
- `static/js/core/commands.js` — command execution with source tracking
- `static/js/core/keys.js` — keyboard key handling (source: "key")
- `static/js/core/hints.js` — hint label navigation (source: "hint")
- `static/js/core/cmdline.js` — command line execution (source: "cmdline")
- `core/models.py` — UsageCount model
- `templates/help/settings.html` and `templates/settings/rows.html` — UI entry points

## Findings

### 1. No personal data can leak into the report (Confirmed — Good)

**What I checked:** Every output line in `report()` (usage.py:88-159).

**Result:** The report contains only:
- Aggregate counts (puzzles per day, solved/missed, minutes)
- Command IDs and their sources (key/click/hint/cmdline) — no arguments
- Error counts (JS and server) — no error messages
- System info (OS version, CPU architecture, app version, language code)
- Dates (install date, days used, ISO week numbers)

**What is excluded:** No positions, no FENs, no comments, no tags, no names, no notes, no free text of any kind.
The `UsageCount` model stores only `(user, day, name, source, count)` — all fixed-schema fields.

**Verdict:** ✅ No risk. The report is safe to share.

### 2. Commands counted once per user action (Confirmed — Good)

**What I checked:** The counting chain from user action to database.

**Flow:**
1. User presses a key → `keys.js` calls `run(id, args, { source: "key" })`
2. User clicks a button → `commands.js:209` calls `run(id, args, { source: ctx.viaHint ? "hint" : "mouse" })`
3. User types a command → `cmdline.js:320` calls `run(id, args, { source: "cmdline" })`
4. A command runs another command → `run(id, args, { source: "code" })` (default)
5. Undo/redo → `run(id, args, { source: "undo" })`
6. Repeat → `run(id, args, { source: "repeat" })`

**The filter:** `usage.js:9` — `COUNTED = new Set(["key", "mouse", "hint", "cmdline"])`
Only these four sources pass through. "code", "undo", and "repeat" are excluded.

**Result:** When command A runs command B internally (source: "code"), B is not counted.
When the user presses a key, only that one key press is counted — not any sub-commands it triggers.

**Verdict:** ✅ Correct. No double-counting.

### 3. Server-side validation prevents free text (Confirmed — Good)

**What I checked:** `usage.py:39-54` (the `record` endpoint).

**Validation:**
- Only known command IDs are accepted (checked against `registry.commands()`)
- Only known sources are accepted: `("key", "mouse", "hint", "cmdline")` plus `"error"` for error tracking
- Count must be an integer between 1 and 10,000
- Anything else is silently ignored

**Verdict:** ✅ Even if the browser sent malicious data, the server rejects it.

### 4. The `_system()` function reveals OS version and CPU architecture (Low risk — Intentional)

**What I checked:** `usage.py:73-79`.

**Output examples:**
- macOS: `"macOS 14.0 arm64"`
- Windows: `"Windows 10 (22631) AMD64"`
- Linux: `"Linux 6.1.0 AMD64"`

**Assessment:** This is standard for usage reports — it helps the maintainer understand the tester environment.
No personal identifiers (hostname, username, MAC address) are included.

**Verdict:** ✅ Acceptable. This is standard diagnostic info, not personal data.

### 5. Imported sessions are excluded from the report (Confirmed — Good)

**What I checked:** `usage.py:92-93`.

```python
attempts = list(Attempt.objects.filter(origin="").values_list("at", "success", "ms"))
sessions = list(Session.objects.filter(origin="").exclude(ended_at=None).values_list("mode", "duration_s"))
```

Only attempts and sessions with `origin=""` (locally created) are included. Imported data
(from packs, PGN files, etc.) has a non-empty origin and is excluded.

**Verdict:** ✅ Correct. The report reflects only the tester's own training, not imported content.

### 6. Edge case: No data at all (Confirmed — Handled)

**What I checked:** The report with empty databases.

**Result:**
- `per_day` is empty → `"none yet"` is shown
- `weeks` is empty → `"none yet"` is shown
- `commands` is empty → the "Commands used most" section is skipped
- `first_solved` is None → `"No puzzle solved yet"` is shown
- `installed` is None → date shows as `"?"`

**Verdict:** ✅ Graceful degradation. No crashes, no confusing output.

### 7. Edge case: Session without duration (Confirmed — Handled)

**What I checked:** `usage.py:93` — `exclude(ended_at=None)` filters out incomplete sessions.
`usage.py:132` — `if d` filters out zero-duration sessions from the median calculation.

**Verdict:** ✅ Correct. A session that was started but not ended is excluded.

### 8. Edge case: A year of data (Minor — Table width)

**What I checked:** `usage.py:82-85` (`_table` function) and the weekly command table.

**Observation:** With a year of daily data, the "Training per day" table will have ~365 rows.
The "How commands were started, per week" table will have ~52 rows.
The "Commands used most" table is capped at 40 (`MOST_USED = 40`).

**Assessment:** The report could be ~400+ lines long. This is fine for a text file — it's meant to be
read by the maintainer, not displayed in the app. No truncation is needed.

**Verdict:** ⚠️ Minor note. The report is unbounded in length but that's acceptable for its purpose.

### 9. The flush mechanism is robust (Confirmed — Good)

**What I checked:** `usage.js:29-42`.

**Mechanism:**
- Flushes every 30 seconds via `setInterval`
- Flushes on tab hide via `visibilitychange`
- Uses `keepalive: true` so the request completes even if the tab closes
- Silently catches errors — lost counts are better than a crash

**Verdict:** ✅ Good. Counts are rarely lost, and the system never crashes from a failed flush.

### 10. The `:test-report` command flushes before generating (Confirmed — Good)

**What I checked:** `usage.js:44-51`.

```javascript
handle("app.testreport", async () => {
  await flush()
  // ... then download the report
})
```

**Verdict:** ✅ The last 30 seconds of counts are included in the report.

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | No personal data can leak | — | ✅ Good |
| 2 | Commands counted once per user action | — | ✅ Good |
| 3 | Server validates all incoming counts | — | ✅ Good |
| 4 | OS version in report | Low | ✅ Intentional |
| 5 | Imported sessions excluded | — | ✅ Good |
| 6 | No data edge case handled | — | ✅ Good |
| 7 | Session without duration handled | — | ✅ Good |
| 8 | Year of data — long report | Minor | ⚠️ Acceptable |
| 9 | Flush mechanism robust | — | ✅ Good |
| 10 | Flush before report generation | — | ✅ Good |

**Overall assessment:** The usage report is well-designed. Privacy is strong — nothing personal or free-text
can enter the report. Command counting is correct — each user action is counted once, programmatic actions
are excluded. Edge cases are handled gracefully. The only minor note is that a year of daily data produces
a long report, but this is acceptable for its purpose.

## Test coverage

The usage report has no dedicated tests yet. The following areas would benefit from tests:

1. `test_record_rejects_unknown_commands` — verify the server rejects unknown command IDs
2. `test_record_rejects_unknown_sources` — verify the server rejects unknown sources
3. `test_report_with_no_data` — verify the report handles empty databases
4. `test_report_excludes_imported_sessions` — verify `origin!=""` sessions are excluded
5. `test_count_aggregation` — verify multiple counts for the same command on the same day are summed

These are low priority since the code is simple and well-validated, but they would add confidence.

## Files changed

None. This is a review report only.
