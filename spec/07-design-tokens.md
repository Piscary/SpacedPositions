# 07 · Design tokens, themes, customisation and the design pipeline

## 1 · Token tiers

```
 Tier 1 · BASE        what a theme / the user sets           bg, text, main, sq-light, font-ui, density …   (~35 tokens)
        │
 Tier 2 · SEMANTIC    derived in CSS from the base tokens    text-muted, surface-hover, selection, focus,
        │             (overridable, rarely overridden)       layer-insert, chart-1…6 …
        │
 Tier 3 · COMPONENT   what components read                   pane-header-bg, keycap-border, board-frame-setup …
```

Components **only read tier 2 and 3**. Users and themes **only set tier 1** (plus, in *advanced*, any tier 2 token).
This keeps every theme complete: set ~14 colours and the whole app, including charts and layer colours, follows.

## 2 · Base tokens (tier 1)

### Colours

| Token | Meaning | Example (`ink`) |
|---|---|---|
| `bg` | Workspace background | `#16181d` |
| `bg-alt` | Pane headers, status line, app bar | `#1d2027` |
| `surface` | Inputs, raised elements (keycaps, chips) | `#252932` |
| `line` | Rules between panes, borders | `#2e333d` |
| `text` | Main text | `#d7dae0` |
| `text-sub` | Secondary text, labels, axes | `#7d8590` |
| `main` | Accent: focus, cursor, primary buttons, current mode | `#e2b714` |
| `main-text` | Text on `main` | `#16181d` |
| `good` | Correct, good move, positive delta | `#6cc070` |
| `bad` | Wrong, bad move, negative delta | `#e06c6c` |
| `warn` | Dubious move, warnings | `#e0a050` |
| `info` | Neutral highlights, links, Insert layer | `#61afef` |
| `special` | Rewards: records, milestones, level-ups | `#c678dd` |

### Board

| Token | Meaning |
|---|---|
| `sq-light`, `sq-dark` | Square colours |
| `sq-lastmove`, `sq-selected`, `sq-check`, `sq-hint` | Square overlays (with alpha) |
| `arrow-green`, `arrow-red`, `arrow-blue`, `arrow-yellow` | User drawings (lichess colours by default) |
| `arrow-engine` | Engine arrows (fade by rank via opacity) |
| `board-coords` | `inside` / `outside` / `off` |
| `board-border` | Width of the frame (px) |
| `piece-set` | Name of the piece set (`cburnett`, `merida`, `alpha`, `staunty`, ...) |
| `board-texture` | Optional image name instead of flat colours |

### Type, space, shape, motion

| Token | Meaning | Default |
|---|---|---|
| `font-ui` | Interface font | `Inter, system-ui, sans-serif` |
| `font-mono` | Keycaps, ids, FEN/PGN, clocks | `JetBrains Mono, ui-monospace, monospace` |
| `font-moves` | Move lists (allows a figurine font) | `= font-ui` |
| `font-size` | Base size (px) | `13` |
| `type-ratio` | Modular scale for headings and big numbers | `1.2` |
| `density` | `compact` / `cozy` / `comfortable` → spacing unit 3 / 4 / 5 px | `cozy` |
| `radius` | Corner radius (px), 0 allowed | `3` |
| `rule` | Border width (px) | `1` |
| `motion` | Speed factor: 0 (off) … 1 (default) … 1.5 | `1` |
| `board-motion` | Piece animation (ms) | `150` |
| `figurines` | Moves as `♘f3` instead of `Nf3` | `false` |

## 3 · Derived tokens (tier 2), computed in CSS

```css
@layer tokens {
  :root {
    --space: calc(var(--density-unit) * 1px);               /* 3 / 4 / 5 */
    --text-muted:     color-mix(in oklab, var(--text) 60%, var(--bg));
    --surface-hover:  color-mix(in oklab, var(--surface) 85%, var(--text));
    --selection:      color-mix(in oklab, var(--main) 22%, var(--bg));
    --cursor-row:     color-mix(in oklab, var(--main) 12%, var(--bg));
    --focus:          var(--main);
    --layer-normal:   var(--text-sub);
    --layer-insert:   var(--good);
    --layer-visual:   var(--special);
    --layer-command:  var(--main);
    --layer-setup:    oklch(from var(--info) l c calc(h + 40));   /* indigo-ish */
    --layer-entry:    oklch(from var(--info) l c calc(h - 40));   /* teal-ish */
    --chart-1: var(--main); --chart-2: var(--info); --chart-3: var(--good);
    --chart-4: var(--special); --chart-5: var(--warn); --chart-6: var(--text-sub);
    --row-sm: calc(var(--font-size) * 1.35px + var(--space) * 1);
    --row-md: calc(var(--font-size) * 1.35px + var(--space) * 2);
    --row-lg: calc(var(--font-size) * 1.35px + var(--space) * 4);
    --dur-fast: calc(100ms * var(--motion)); --dur: calc(150ms * var(--motion)); --dur-slow: calc(300ms * var(--motion));
  }
  @media (prefers-reduced-motion: reduce) { :root { --motion: 0; } }
}
```

A theme may override any tier 2 token when the derived value doesn't fit (e.g. a hand-picked `--chart-*` palette).

### Scales

- **Type**: `xs` = base − 2, `sm` = base − 1, `md` = base, `lg` = base × ratio, `xl` = × ratio², `2xl` = × ratio³ (big
  numbers in the result screen and the clock: `3xl`, `4xl`). All numbers use tabular figures.
- **Space**: `0`, `½`, `1`, `2`, `3`, `4`, `6` × `--space`. Nothing else.
- **Layers (z)**: workspace 0 · gutter 10 · pane overlay (help) 20 · which-key / command line 30 · menus 40 ·
  toasts 50 · hint labels 60.
- **No shadows.** Overlays are separated by a `line` border and `bg-alt` background.

## 4 · Themes

A theme is a small TOML file of base tokens. Anything left out is taken from the theme it `extends`.

```toml
# design/themes/nord.toml
name    = "nord"
extends = "ink"          # dark base
[color]
bg = "#2e3440"   bg-alt = "#3b4252"   surface = "#434c5e"   line = "#4c566a"
text = "#eceff4" text-sub = "#a3acbc" main = "#88c0d0"      main-text = "#2e3440"
good = "#a3be8c" bad = "#bf616a"      warn = "#ebcb8b"      info = "#81a1c1"   special = "#b48ead"
[board]
sq-light = "#d8dee9"  sq-dark = "#81a1c1"  piece-set = "cburnett"
```

**Built-in themes** (first set): `paper` (light, default when the OS is light), `ink` (dark, default when the OS is
dark), `nord`, `sepia`, `forest`, `contrast` (high contrast, WCAG AAA text). More can be added by dropping a file in
`design/themes/`.

**User themes** have the same schema, are stored in the database (`UserTheme`: name, label, `extends`, the values
that differ), and can be exported/imported as TOML text (`:theme-export` copies the current theme with your
overrides; paste one into Settings → Data to import it; `:theme-save <name>` keeps the current colours as a theme,
`:theme-delete <name>` removes one). A user theme extends a built-in one, so "nord with my board colours" is 3 lines.
Saving warns about contrast the lint would refuse. Built-in themes: paper, ink, nord, sepia, forest,
contrast (High contrast).

**Switching** is instant: the active theme is a `<style id="theme">` block of custom properties; switching replaces
that block (no reload). Live preview while the cursor moves over the theme list sets the properties directly.

## 5 · What the user can customise

| Area | Settings | Also via |
|---|---|---|
| Theme | Pick a theme; edit any base colour (ColorField with contrast check) | `:theme <name>`, `:set color.bg=#123` |
| Typography | UI font, mono font, move font, base size, figurines | `:set font.ui="IBM Plex Sans"` |
| Density & shape | density, radius, rule width | `:set density=compact` |
| Motion & sound | motion factor, board animation, sounds on/off | `:set motion=0` |
| Board | square colours (or a board theme preset), coordinates, highlights, arrows, legal dots, annotation badges | `:set board.light=#f0d9b5` |
| Pieces | piece set (live preview row) | `:set pieces=merida` |
| Keys | keycap display (full/compact/off), teach keys, which-key on/off, **keymap overrides** | `:map <keys> <command>`, `:unmap <keys>` |
| Layout | per-mode layouts, named layouts | `:layout save/load/reset` |
| Advanced | any tier 2 token (`:set`); your own CSS (Settings → Advanced, `⌘↵` applies, with undo), applied after the theme; hold `Esc` while the app loads, or open it with `?safe`, to start without it | — |

Every setting has a `:set` name, shown in its FormRow. **All settings export as one TOML file** (theme, keymap
overrides, layouts, preferences), so a setup can be backed up or moved to another machine with copy/paste.

```toml
# settings export (excerpt)
theme = "nord"
[color]            # token overrides on top of the theme
main = "#ebcb8b"
[board]
piece-set = "merida"
board-coords = "outside"
[settings]         # behaviour (04 · Settings); engine.path is never exported
"training.storm-pace" = "slow"
"board.letters" = "de"
[keys]
"space o" = "train.storm 5"   # leader o starts a 5-minute Storm from anywhere
[keys.unmap]
"F" = true
[keys.contexts."view.library"]
"ctrl+e" = "library.export"
[themes.my-nord]   # your themes travel along
label = "My nord"
extends = "nord"
values = { main = "#ebcb8b" }
[[layouts]]
name = "wide board"
mode = "analyse"
layout = "{…}"     # the layout tree as JSON
```

Importing checks every value like `:set` and `:map` do, applies what is valid and names the rest. A file with
`extends` and a `[color]` table but no `theme` is a single theme and is imported as one.

## 6 · Fonts and piece sets

- Fonts: a short list of bundled, self-hosted fonts (Inter, IBM Plex Sans, JetBrains Mono, Fira Code, Noto Sans
  Symbols 2 for figurines), plus "any installed font by name". No external font CDN at runtime.
- Piece sets: SVG sets in `static/pieces/<name>/` (`wK.svg` … `bP.svg` + `LICENSE`). The `piece-set` token lists
  them; `design build` writes `static/design/pieces.css`, which switches chessground's piece images by
  `<html data-pieces="…">`, so changing the set needs no reload. MiniBoards are drawn server-side in the same set
  (each piece a `<symbol>` with its internal ids prefixed) and their URL hash includes the set.
- **Bundled**, all from lichess with the licences listed in lila's `COPYING.md`: Cburnett, Merida (GPLv2+),
  MPChess (GPLv3+), Chessnut (Apache 2.0), Fantasy, Spatial, Celtic (MIT), Shapes (CC BY-SA 4.0), RhosGFX (CC0),
  Kiwen-suwi, Totoy, Papercut (CC BY 4.0). Not bundled: the many CC BY-NC-SA sets (staunty, california, maestro,
  cardinal …) and "freeware" sets (alpha, companion, leipzig): their licences don't let anyone redistribute the app.
  AGPL sets (pixel, pirouetti, letter) would be allowed but are left out to keep the licence picture simple.
- `design check` fails for a set without all 12 pieces, without `LICENSE`, without an allowed licence in
  `design/licences.toml`, with scripts or external references in an SVG, or for a folder the token doesn't list.
- **User sets**: any set the user owns, in the data folder: `pieces/<name>/` with the 12 pieces and, if
  wanted, an `about.toml` (`label`, `author`, `licence`). They are checked like the bundled ones (all 12 pieces, no
  scripts or external references, at most 300 kB a piece; a bundled name wins), served by the app
  (`/pieces/<name>/wK.svg`, `/pieces/user.css`), listed in the picker and in Settings, and drawn on MiniBoards.
  They never become part of the app, so their licence is the user's business.
- Silhouette and blind modes are board *looks* (CSS classes on the board), not piece sets.

## 7 · Rules every theme must pass

Checked automatically (§8) for every built-in theme, and as warnings in the theme editor for user themes:

| Check | Minimum |
|---|---|
| `text` on `bg`, `bg-alt`, `surface` | 4.5 : 1 (contrast theme: 7 : 1) |
| `text-sub` on `bg` | 3 : 1 |
| `main-text` on `main` | 4.5 : 1 |
| `good`, `bad`, `warn` on `bg` | 3 : 1, and `good` vs `bad` distinguishable for deuteranopia (ΔE in simulation ≥ 20) |
| `sq-light` vs `sq-dark` | visibly different (ΔL ≥ 15) |
| All required base tokens defined (after `extends`) | — |

State is never shown by colour alone (✓/✗ icons, words, patterns on marks), so even a failing user theme stays
usable.

## 8 · The design pipeline (repository, build, CI)

### Source of truth in the repository

```
design/
  tokens.toml           tier 1 schema: every base token with type, default, range, description
  derived.css           tier 2 derivations (hand-written, short)
  themes/*.toml         built-in themes
  commands/*.toml       the command registry (02 §3), one file per area
  keymap/default.toml   default bindings, by context
  licences.toml         licences of vendored files (09 §13)
  icons.txt             (later) the icon names used; the sprite is built from this list
```

### Build (`python manage.py design build`)

Pure Python, no Node needed:
1. Reads `tokens.toml`, the themes, commands and keymap (`design check` validates them).
2. Writes `static/design/tokens.css` (tier 1 defaults of the non-colour tokens + tier 2).
3. Writes `static/design/themes.json`: every theme resolved to CSS values, plus the token schema. The server
   renders the active theme (and the user's overrides) into the page's `<style id="theme">` block from it; the
   client uses it for `:theme` and `:set` completion.
4. Writes `static/design/commands.json` (registry + keymap + prefixes). The server embeds it in the page; the
   template tags read it, and an unknown id in `{% cmd "board.flp" %}` fails at render time and in `design check`
   (so no generated Python constants are needed).
5. Writes the keymap reference `docs/keymap.md`, so 08 can't drift from the code.
6. (Later, with the first icons) builds the icon sprite from `icons.txt`.

Generated files are committed; CI checks that they are up to date.

### Lint (`python manage.py design check`)

| Check | Fails when |
|---|---|
| Schema | a theme, command or binding doesn't match its schema |
| Contrast | a built-in theme breaks §7 |
| Keymap conflicts | two commands share a key in overlapping contexts; a key is both a command and a prefix in one context; a view rebinds a reserved key (02 §5) |
| Browser-reserved keys | a default binding uses a key from 02 §4 *Keys the app never binds* |
| Layout-safe keys | *warning only*: a default binding needs AltGr/Option on QWERTZ, AZERTY or QWERTY-intl (QWERTY is the primary layout, 10 · Decided) |
| Reachability | a command has no key, no button and is hidden from the command line |
| Template references | a template uses a command id or component that doesn't exist |
| No literals | component CSS contains colours, px sizes or durations outside `@layer tokens` (stylelint rule) |

### Living style guide (`/_ui/`)

A page per component with every variant and state, plus the board in all layers, plus full mode screens with fixture
data (a fixed sample). Theme, density and font size can be switched
on the page. This is where components are built and reviewed, before they are used in a mode.

### Tests in CI

1. `design check` (lint above).
2. Unit tests (Python: commands, search, scheduling; JS: keymap resolution, move entry parsing).
3. **Visual regression**: Playwright screenshots of `/_ui/` for each built-in theme × `compact`/`cozy`; a pull request
   shows the diffs.
4. **Keyboard journeys**: scripted key sequences for the main flows (start a Storm and solve 3 puzzles; tag a
   library selection; split, link and close panes; collect a position and save-next), asserting the state after each
   step. These are the guarantee that "everything works with the keyboard".
5. **Performance budgets** (01 · P5): key → paint and next-puzzle timings measured in the journeys; fail above
   budget × 1.5.
6. Accessibility: axe-core on `/_ui/` pages.

### Versioning

`tokens.toml` has a schema version. When a token is renamed, the build keeps a mapping, and user themes and settings
exports are migrated on load. User data is never broken by a theme change.
