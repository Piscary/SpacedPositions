# Working on Spaced Positions

Spaced Positions is a free (GPL-3.0) chess trainer: spaced repetition of puzzles, analysis, a library. It is made in
Switzerland for the public, in English, German (Swiss spelling: "ss", never "ß"), French and Italian. Nothing
personal goes into the product: no names, no private data, no telemetry (the app sends nothing).

The specification in `spec/` is the source of truth: `01-principles` to `09-architecture` describe the product,
`10-roadmap-and-questions` the status and what comes next, `14-test-programme` the test group. Read the part that
concerns your task before you start.

## Who does what

- **Claude** (Claude Code): features and architecture, the core development decisions, new functionality.
- **Junie**: testing, code review, documentation, translations (i18n), bug hunting, second opinions.
- **The maintainer** decides, commits when asked to, and pushes to GitHub by hand.

If a task needs a design decision or a change to the architecture (a new model, a new endpoint, a new command, a
change in how panes, keys or the trainer work), don't make it: describe the options in your report and leave the
decision to the maintainer and Claude. Small, local fixes of clear bugs are fine; say what you changed and why.

## Rules that are never broken

- **Never push.** Don't commit either unless the maintainer asks for it in the task. Leave changes uncommitted and
  list them in your report.
- **Don't touch the folders next to this project** (`../chess-study-manager/`, `../piscarys-hub/`), not even to read
  them for this project.
- **`.data/` is the maintainer's real training data.** Never write to `.data/db.sqlite3`, never delete anything
  there. The tests use their own databases. A script that loads the Django settings directly must set
  `SPOS_DATA_DIR` to a scratch folder (for example under `/tmp`), never to `.data`.
- **No downloads** (packages, databases, tools) without asking first. `npx`, `pip install` of something new and
  `playwright install` count as downloads.
- **Don't change the installed app** of the maintainer (the `spos` command, `../chess-study-manager/.venv`): give
  the commands instead.
- **Before you start, run `git status`.** If there are uncommitted changes you didn't make, Claude may be working on
  them: stop and ask, don't build on them or revert them.

## Running things

Python 3.12+, a virtualenv in `.venv` (`pip install -e ".[dev]"`).

| What | Command |
|---|---|
| The app for development | `.venv/bin/python manage.py runserver` (uses `.data/`: look, don't change data you didn't create) |
| Python tests (fast) | `.venv/bin/python -m pytest -q -m "not browser"` |
| Browser tests (Playwright, several minutes) | `.venv/bin/python -m pytest -q -m browser` |
| One file / one test | `.venv/bin/python -m pytest -q -m browser tests/test_issues_browser.py -k start_position` |
| JavaScript unit tests | `node --experimental-default-type=module --test tests/js/*.test.mjs` |
| Tests as on a machine without UTF-8 (Windows-like) | `LC_ALL=C LANG=C PYTHONUTF8=0 PYTHONCOERCECLOCALE=0 .venv/bin/python -m pytest -q -m "not browser"` |
| Design system: rebuild generated files | `.venv/bin/python manage.py design build` |
| Design system: the lint CI runs | `.venv/bin/python manage.py design check` (must say `0 error(s)`) |

A change is done when all four test runs pass and `design check` is clean. CI (`.github/workflows/ci.yml`) runs
them on Linux and Windows.

## How the code is organised

- Django app in `spaced_positions/` (`core/` shell, settings, layouts, registry; `analysis/`, `library/`,
  `training/`, `stats/`), templates in `spaced_positions/templates/`, ES modules without a bundler in
  `spaced_positions/static/js/` (`core/` and `islands/`), CSS in `spaced_positions/static/css/` using the design
  tokens (no literal colours or sizes: `design check` fails on them).
- **Commands and keys** are declared in `design/commands/*.toml` and `design/keymap/default.toml`, then
  `manage.py design build`. Buttons in templates are `{% cmd "id" %}`, keys in help texts `{% key "id" %}`: never
  write a key by hand where a command exists.
- **Generated files are never edited by hand**: `static/design/commands.json`, `docs/keymap.md`,
  `static/i18n/*.json`, `locale/*/LC_MESSAGES/django.mo`. Change the source and rebuild.
- Every pane (view) has its guide in `templates/help/<view>.html` (the `?` key). **Every change to a view ships with
  its guide, its translations, and a key for each new button.**

## Translations

Texts are marked with `{% translate %}` / `{% blocktranslate trimmed %}` in templates, `_()` / `ngettext` in Python,
`tr()` / `trn()` in JavaScript.

1. `.venv/bin/python manage.py i18n extract` (collects the texts)
2. `.venv/bin/python manage.py i18n missing > /tmp/missing.json` (what has no translation yet)
3. Write a JSON file `{"English text": {"de": "…", "fr": "…", "it": "…"}}`; for plurals each language is a list
   `["one", "many"]`; keys with a context look like `"context\u0004text"` exactly as `missing` prints them.
4. `.venv/bin/python manage.py i18n fill /tmp/fill.json`, then `.venv/bin/python manage.py i18n build`
5. `.venv/bin/python manage.py design check` (fails on untranslated texts)

Keep placeholders (`%(name)s`, `{n}`, `{keys}`) exactly. Use the terms already in the catalogues
(`locale/*/LC_MESSAGES/django.po`): puzzle = Aufgabe / exercice / esercizio, card = Karte / carte / scheda.
Short, plain words; the user is addressed with "du" in German, "vous" in French, "tu" in Italian.

## Reports

Write findings to `docs/reviews/YYYY-MM-DD-<topic>.md` (create the folder if needed), most important first. For each
finding: where (`path:line`), what goes wrong (steps or input → what happens → what should happen), how sure you are
(confirmed with a test or by running it / likely / a question), and a suggested fix. Say what you checked and found
fine, too, and what you could not check. End with the list of files you changed, if any.

Tests that show a bug go into `tests/` next to the related tests, marked `@pytest.mark.xfail(reason="…")` when the
fix is not part of your task, so the suite stays green.
