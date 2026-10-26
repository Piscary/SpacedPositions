"""How this copy of Spaced Positions was installed, and how it is updated (spec 09 §11).

- `app`: the double-click app (PyInstaller): a new version is downloaded from the releases page.
- `pipx`: `pipx install …`: `spos update` runs `pipx upgrade spaced-positions`.
- `pip`: installed with pip into some Python environment: `spos update` installs it again from where it came from
  (a folder or a git URL), or upgrades it from PyPI.
- `source`: an editable development checkout: `git pull` updates it.

The user's data lives in its own folder (paths.data_dir) and is never touched by an update; the app makes a backup
before it migrates the database to a new version (launcher._migrate)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

DISTRIBUTION = "spaced-positions"
RELEASES = "https://github.com/Piscary/SpacedPositions/releases"  # /latest skips pre-releases


def _direct_url() -> dict:
    """Where pip installed the package from (PEP 610), or {} for an index (PyPI) or an unknown install."""
    # every entry of that name (a build folder's .egg-info may come first): the one that says where it came from
    for dist in metadata.distributions(name=DISTRIBUTION):
        text = dist.read_text("direct_url.json")
        if text:
            try:
                return json.loads(text)
            except ValueError:
                continue
    return {}


def kind() -> str:
    if getattr(sys, "frozen", False):
        return "app"
    origin = _direct_url()
    if origin.get("dir_info", {}).get("editable"):
        return "source"
    if "pipx" in Path(sys.prefix).resolve().parts:
        return "pipx"
    return "pip"


def update_command() -> list[str] | None:
    """The command that updates this copy, or None when it is updated another way (the app, a checkout)."""
    how = kind()
    if how == "pipx":
        pipx = shutil.which("pipx")
        return [pipx, "upgrade", DISTRIBUTION] if pipx else None
    if how == "pip":
        origin = _direct_url()
        url = origin.get("url")
        if not url:  # from PyPI
            return [sys.executable, "-m", "pip", "install", "--upgrade", DISTRIBUTION]
        if "vcs_info" in origin:  # git+https://…
            return [sys.executable, "-m", "pip", "install", "--upgrade", f"{origin['vcs_info'].get('vcs', 'git')}+{url}"]
        # a folder or a file: install what is there now (its version may not have changed)
        source = url.removeprefix("file://")
        return [sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", source]
    return None


def instructions() -> str:
    """One sentence for people: how to update this copy (English: the launcher's console texts)."""
    how = kind()
    if how == "app":
        return f"Download the new version from {RELEASES} and replace the app; your data stays where it is."
    if how == "source":
        return "This is a development checkout: git pull, then start it again."
    if update_command():
        return "In a terminal: spos update (it stops the app, updates it and starts it again)."
    return f"Install the new version as you installed this one; see {RELEASES}."


def run_update() -> int:
    """`spos update`: run the update command; returns its exit code."""
    command = update_command()
    if command is None:
        print(instructions())
        return 1
    print("Updating:", " ".join(command))
    return subprocess.call(command)


def installed_version() -> str:
    """The version installed now (after an update, the new one: read in a new process)."""
    try:
        out = subprocess.run([sys.executable, "-c", "import spaced_positions; print(spaced_positions.__version__)"],
                             capture_output=True, text=True, timeout=60)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
