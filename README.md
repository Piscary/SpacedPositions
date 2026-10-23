# Spaced Positions

Collect, solve and train chess puzzles: keyboard first, with spaced repetition. Free software (GPL-3.0-or-later).

**Status: phase 0 (foundation).** The shell, panes and splits, the command and key system, the design tokens and
themes, the style guide and the launcher work. The chess modes (Train, Analyse, Collect, Library, Stats) are laid
out with placeholder panes that name the phase that builds them. The specification is in [spec/](spec/README.md).

## Start it

```bash
pipx install .        # or: pip install -e . in a virtual environment
spos                  # starts the app and opens the browser
```

`spos` works like `jupyter notebook`: it picks a free port (8765 or the next one), opens the browser with a one-time
token, and keeps running until `Ctrl+C`, `:quit` in the app, or `spos stop`. Running `spos` again just opens the
browser at the running instance. `spos list` shows where it runs; `--no-browser`, `--port`, `--data-dir` and `--lan`
are the options. Data lives in the platform's user-data folder (`~/Library/Application Support/Spaced Positions/`
on macOS), with a backup before every migration.

## Try in phase 0

| Keys | |
|---|---|
| `␣` | Leader: the which-key panel lists what can follow |
| `␣ h` `␣ t` `␣ a` `␣ c` `␣ l` `␣ s` `␣ ,` · `␣ ␣` | Modes · back to the previous mode |
| `⇥` · `␣ 1`–`␣ 9` · `␣ w h/j/k/l` | Focus the next pane · pane N · by direction |
| `␣ w v` / `␣ w s` | Split (then pick a view) · `␣ w q` close · `␣ w m` maximise · `␣ w c` collapse |
| `␣ w <` `>` `+` `-` | Resize (sticky: keep pressing, `Esc` ends) · or drag a gutter |
| `:` | Command line: `:vsplit notes`, `:theme ink`, `:set main=#e2b714`, `:set density=compact`, `:layout-save study` |
| `F` | Hint labels: click anything by keyboard |
| `u` / `U` | Undo / redo (layout and settings) |
| `?` | Every key that works here |
| `:ui` | The style guide: every component, plus a linked list and preview |

## Develop

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python manage.py runserver 8020        # development: data in .data/, DEBUG on
.venv/bin/python manage.py design build          # after changing anything in design/
.venv/bin/python manage.py design check          # the design lint (also runs in CI)
.venv/bin/python -m pytest -m "not browser"      # Python tests
node --experimental-default-type=module --test tests/js/
.venv/bin/python -m playwright install chromium && .venv/bin/python -m pytest -m browser
```

### Where things are

```
design/                  source of truth for the design system
  tokens.toml            tier 1 tokens (types, defaults, ranges)
  derived.css            tier 2 tokens (derived in CSS)
  themes/*.toml          paper, ink
  commands/*.toml        every command: title, args, when, handler
  keymap/default.toml    bindings by context
  licences.toml          licences of vendored files
spaced_positions/
  launcher.py            the `spos` command
  design/                build + lint (`manage.py design build|check`)
  core/                  shell views, layouts, server commands, token middleware, template tags
  static/design/         generated: tokens.css, themes.json, commands.json (committed)
  static/css/            components (cascade layers; no literal colours or sizes)
  static/js/core/        keys, commands, layout, command line, hints, help, lists, menu
  templates/             shell, components, views
docs/keymap.md           generated keymap reference
tests/                   pytest (design, shell, launcher, browser journeys) and tests/js (node)
```

Rules the lint enforces: every command has a client or server handler; every `{% cmd %}` and `data-cmd` names a
real command; no key is both a command and a prefix in one context; global keys are reserved; browser-owned keys are
never bound; built-in themes pass the contrast checks; component CSS uses tokens only; dependencies and vendored files
have GPL-compatible licences; the generated files are up to date.
