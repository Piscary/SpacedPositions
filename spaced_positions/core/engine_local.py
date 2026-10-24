"""A local UCI engine through the app (spec 06 §7): stronger and deeper than Stockfish in the browser. The browser
sends UCI commands (`POST /engine/local/`) and reads the engine's lines (`GET /engine/local/?after=n`, which waits a
moment for new ones), so the engine module can treat it like its worker.

One engine process for the app, started on the first command with `engine.path` (an executable file) or `stockfish`
on the PATH, ended with the app. Only the user sets `engine.path` (imported settings can't), so nothing pasted can
choose a program to run."""

from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

KEEP = 2000  # lines kept for readers
WAIT_S = 0.5  # how long a read waits for new lines


class Engine:
    def __init__(self, program: str):
        self.program = program
        self.proc = subprocess.Popen(
            [program], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        self.lines: deque[tuple[int, str]] = deque(maxlen=KEEP)
        self.seq = 0
        self.changed = threading.Condition()
        threading.Thread(target=self._read, daemon=True, name="engine-local").start()

    def _read(self):
        for line in self.proc.stdout:
            with self.changed:
                self.seq += 1
                self.lines.append((self.seq, line.rstrip("\n")))
                self.changed.notify_all()
        with self.changed:
            self.changed.notify_all()

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    def send(self, commands: list[str]) -> int:
        """Write commands; returns the line number they start after."""
        with self.changed:
            start = self.seq
        for cmd in commands:
            self.proc.stdin.write(cmd.replace("\n", " ") + "\n")
        self.proc.stdin.flush()
        return start

    def read(self, after: int) -> tuple[list[str], int]:
        with self.changed:
            if self.seq <= after and self.alive:
                self.changed.wait(WAIT_S)
            return [text for n, text in self.lines if n > after], self.seq

    def close(self):
        if self.alive:
            try:
                self.send(["quit"])
                self.proc.wait(1)
            except (OSError, subprocess.TimeoutExpired, ValueError):
                self.proc.kill()


_engine: Engine | None = None
_lock = threading.Lock()


def program() -> tuple[str | None, str]:
    """(path, problem): the configured engine, else stockfish on the PATH."""
    from . import settings

    configured = str(settings.get("engine.path") or "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path), ""
        return None, f"engine.path {configured} is not a program (Settings → Engine)"
    found = shutil.which("stockfish")
    return (found, "") if found else (None, "no stockfish on the PATH: install it, or set engine.path (Settings → Engine)")


def engine() -> Engine:
    global _engine
    with _lock:
        path, problem = program()
        if path is None:
            raise RuntimeError(problem)
        if _engine is None or not _engine.alive or _engine.program != path:
            if _engine is not None:
                _engine.close()
            _engine = Engine(path)
        return _engine


@atexit.register
def _shutdown():
    if _engine is not None:
        _engine.close()


@require_http_methods(["GET", "POST"])
def local(request):
    try:
        if request.method == "POST":
            commands = json.loads(request.body or b"{}").get("commands") or []
            if not isinstance(commands, list) or not all(isinstance(c, str) for c in commands):
                return JsonResponse({"ok": False, "message": "commands: a list of UCI commands"}, status=400)
            e = engine()
            return JsonResponse({"ok": True, "after": e.send(commands), "program": Path(e.program).name})
        try:
            after = int(request.GET.get("after", 0))
        except ValueError:
            after = 0
        if _engine is None or not _engine.alive:
            return JsonResponse({"ok": False, "message": "the local engine is not running"})
        lines, seq = _engine.read(after)
        return JsonResponse({"ok": True, "lines": lines, "next": seq})
    except (RuntimeError, OSError) as e:
        return JsonResponse({"ok": False, "message": str(e)})
