# Known Issues

This list documents known problems so testers don't report them again. If you encounter something not on this list,
please report it — it might be new.

## App security warnings on first install

**macOS:** The app may show a "damaged" or "cannot be opened" warning because it is not signed by Apple.
This is expected for a free, open-source app. The README explains how to open it anyway
(right-click → Open, or `xattr -d com.apple.quarantine` in the terminal).

**Windows:** Windows Defender or other antivirus software may flag the app as a "trojan" or "potential threat".
This is a false positive — the app is open source and builds are public on GitHub. The README explains what to do.

**Why:** Code signing costs money (Apple: 99 USD/year, Windows: certificate fees). We plan to add signing before
the public release, but the test version is unsigned.

## The `:feedback` command is not ready yet

The command line accepts `:feedback`, but the feedback form is not built yet. Use email or a chat group to give
feedback instead. This will be ready before the public release.

## Updating the app

Updating from one test version to the next is not fully automated yet. The maintainer will guide you through
the update process. An in-app update button and the `spos update` command are planned.

## Backups and restore

Daily backups are created automatically in the app's data folder. The `spos restore` command can restore from
a backup, but this has not been tested extensively yet. Don't worry — your data is saved locally and is not
at risk of being lost.

## What's not built yet (and won't confuse you)

The following features are planned but not in this test version. If you don't see them, that's expected:

- **Progress reports** a student can send to a coach
- **Password protection** on shared puzzle packs
- **Phone and tablet layouts** — this is a desktop/laptop app for now
- **Playing against the engine** — the engine is for analysis only
- **Online accounts or sync** — everything stays on your computer

## Minor quirks

- **First launch takes a moment.** The very first time you start the app, it creates its database and loads the
  starter pack. This can take 10–20 seconds. Subsequent launches are fast.
- **Keyboard shortcuts use vim-style keys.** By default, `j` and `k` move up and down (like arrow keys). If you
  prefer arrows, they work too. You can change any key binding in Settings.
- **The app opens in your browser.** This is normal — the app runs locally on your computer, and the browser
  is just the display. No data leaves your machine.
