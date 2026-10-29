# Known Issues

This list documents known problems so testers don't report them again. If you encounter something not on this list,
please report it — it might be new.

## App security warnings on first install

**macOS:** macOS says it can't check the app, because it is not signed by Apple. This is expected for the test
version. macOS 15 and newer: System Settings → Privacy & Security → *Open Anyway*; older macOS: right-click the app →
*Open*. After that, a normal double click works.

**Windows:** a blue window says "Windows protected your PC" (click *More info* → *Run anyway*), and some antivirus
programs may flag the app as a "trojan" or "potential threat". This is a false positive — the app is open source and
its builds are made on GitHub, where anyone can check them. The README's *Is it safe to install?* explains more.

**Why:** Code signing costs money (Apple: 99 USD/year, Windows: certificate fees). We plan to add signing before
the public release, but the test version is unsigned.

## There is no `:feedback` command yet

Give feedback with the form the maintainer sent you, by email or in the chat group. A command that opens the form
from inside the program comes later.

## Updating the app

The program doesn't update itself. If you switch on *Tell me about new versions* (on the Welcome screen, or Settings →
App), a notice tells you when there is a new version. Then download it from the releases page and replace the old
app: your puzzles and training live in their own folder and stay. (Installed with Python: `spos update`.) Updating
during the test is one of the tasks, so tell us how it went.

## Backups

The program makes a compressed backup every day and before every update, in the `backups/` folder of its data folder
(Settings → App shows where). Putting a backup back (`spos restore`) has not been tried by testers yet: if you ever
need it, ask the maintainer first.

## What's not built yet (and won't confuse you)

The following features are planned but not in this test version. If you don't see them, that's expected:

- **Progress reports** a student can send to a coach
- **Password protection** on shared puzzle packs
- **Phone and tablet layouts** — this is a desktop/laptop app for now
- **Playing against the engine** — the engine is for analysis only
- **Online accounts or sync** — everything stays on your computer

## Translations

The French and Italian texts were not yet checked by native speakers. If a word or sentence sounds odd, please tell
us: that is useful feedback, not a nitpick.

## Minor quirks

- **First launch takes a moment.** The very first time you start the app, it creates its database. Later starts
  are faster.
- **Keyboard shortcuts use vim-style keys.** By default, `j` and `k` move up and down (like arrow keys). If you
  prefer arrows, they work too. You can change any key binding in Settings.
- **The app opens in your browser.** This is normal — the app runs locally on your computer, and the browser
  is just the display. No data leaves your machine.
