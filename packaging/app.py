"""What the installed app runs (spec 09 §11). A double click starts the server in the background (if it isn't
running yet), waits until it answers, opens the browser and exits, so every later double click just opens the
browser again. The background server stops by itself once no tab has been open for a while. With arguments it
is the `spos` command (`Spaced Positions start --no-browser`, `… stop`, …)."""

import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

LOG = "app.log"


def alert(message: str):
    """There is no console: say it in a dialog."""
    try:
        if sys.platform == "darwin":
            script = f'display dialog {json.dumps(message)} with title "Spaced Positions" buttons {{"OK"}} with icon caution'
            subprocess.run(["osascript", "-e", script], check=False)
        elif sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "Spaced Positions", 0x30)
    except Exception:
        pass


def answers(info) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{info['port']}/healthz", timeout=1) as response:
            return response.status == 200
    except (OSError, KeyError):
        return False


def double_click():
    from spaced_positions import paths

    data = paths.data_dir()
    runtime = data / "runtime.json"
    info = None
    if runtime.exists():
        try:
            info = json.loads(runtime.read_text())
        except ValueError:
            info = None
    if not (info and answers(info)):
        runtime.unlink(missing_ok=True)
        log = open(data / LOG, "ab")
        options = {"stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
        if sys.platform == "win32":
            options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, __file__]
        server = subprocess.Popen(command + ["start", "--no-browser", "--double-click"], **options)
        deadline = time.time() + 120  # the first start creates the database
        info = None
        while time.time() < deadline:
            if server.poll() is not None:
                alert(f"Spaced Positions could not start. The details are in {data / LOG}.")
                sys.exit(1)
            try:
                info = json.loads(runtime.read_text())
                if answers(info):
                    break
            except (OSError, ValueError):
                pass
            info = None
            time.sleep(0.2)
        if info is None:
            alert(f"Spaced Positions is taking too long to start. The details are in {data / LOG}.")
            sys.exit(1)
    webbrowser.open(info["url"])


def main():
    if getattr(sys, "frozen", False) and sys.stdout is None:  # a windowed build: print() and logging need a stream
        sys.stdout = sys.stderr = open(os.devnull, "w")
    elif not sys.stdout.isatty():  # the background server writes app.log: line by line, not when it stops
        sys.stdout.reconfigure(line_buffering=True)
    args = [a for a in sys.argv[1:] if not a.startswith("-psn_")]  # old macOS adds a process serial number
    if not args:
        return double_click()
    from spaced_positions.launcher import main as spos

    spos(args)


if __name__ == "__main__":
    main()
