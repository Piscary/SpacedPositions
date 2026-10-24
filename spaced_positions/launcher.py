"""`spos`: start Spaced Positions and open it in the browser, like `jupyter notebook` (spec 09 §11).

    spos                 start (or, if already running, just open the browser)
    spos --no-browser    start without opening a browser
    spos --port 9000     use this port
    spos --data-dir DIR  use another data folder
    spos --lan           also listen on the home network (token still required)
    spos list            show where the running instance is
    spos stop            stop the running instance
"""

import argparse
import json
import os
import secrets
import signal
import socket
import sqlite3
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

from spaced_positions import __version__

DEFAULT_PORT = 8765
RUNTIME = "runtime.json"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="spos", description="Spaced Positions: chess puzzle training.")
    parser.add_argument("action", nargs="?", default="start", choices=["start", "list", "stop", "import-csm"])
    parser.add_argument("path", nargs="?", help="import-csm: the chess-study-manager database (db.sqlite3)")
    parser.add_argument("--dry-run", action="store_true", help="import-csm: show what would be added, change nothing")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser")
    parser.add_argument("--port", type=int, help=f"port to use (default {DEFAULT_PORT} or the next free one)")
    parser.add_argument("--data-dir", help="use this data folder instead of the default one")
    parser.add_argument("--lan", action="store_true", help="also listen on the home network")
    parser.add_argument("--version", action="version", version=f"Spaced Positions {__version__}")
    args = parser.parse_args(argv)

    if args.data_dir:
        os.environ["SPOS_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())
    from spaced_positions import paths

    data = paths.data_dir()
    running = _running_instance(data)

    if args.action == "list":
        print(f"Running at {running['url']}" if running else "Not running.")
        print(f"Data folder: {data}")
        return
    if args.action == "stop":
        if not running:
            print("Not running.")
            return
        os.kill(running["pid"], signal.SIGTERM)
        (data / RUNTIME).unlink(missing_ok=True)
        print("Stopped.")
        return

    if args.action == "import-csm":
        return _import_csm(data, args)

    if running:
        print(f"Already running: {running['url']}")
        if not args.no_browser:
            webbrowser.open(running["url"])
        return

    _serve(data, args)


def _running_instance(data: Path):
    """The instance recorded in runtime.json, if its process is alive and answers."""
    path = data / RUNTIME
    if not path.exists():
        return None
    try:
        info = json.loads(path.read_text())
        os.kill(info["pid"], 0)
    except (OSError, ValueError, KeyError):
        path.unlink(missing_ok=True)  # the process is gone: a stale file from a crash
        return None
    for _ in range(20):  # alive: wait briefly in case it is still starting up
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{info['port']}/healthz", timeout=1) as response:
                if response.status == 200:
                    return info
        except OSError:
            time.sleep(0.25)
    sys.exit(f"Another Spaced Positions process ({info['pid']}) holds {data} but doesn't answer. Stop it first.")


def _free_port(host: str, wanted: int | None) -> int:
    candidates = [wanted] if wanted else range(DEFAULT_PORT, DEFAULT_PORT + 50)
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    if wanted:
        sys.exit(f"Port {wanted} is in use.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def _serve(data: Path, args):
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    port = _free_port(host, args.port)
    token = secrets.token_urlsafe(24)
    os.environ.update(
        DJANGO_SETTINGS_MODULE="spaced_positions.settings",
        SPOS_TOKEN=token,
        SPOS_LAUNCHED="1",
        SPOS_ALLOWED_HOSTS="*" if args.lan else "127.0.0.1,localhost",
    )

    import django

    django.setup()
    _migrate(data)

    from waitress.server import create_server

    from spaced_positions.wsgi import application

    server = create_server(application, host=host, port=port, threads=8, ident="spos")
    url = f"http://127.0.0.1:{port}/?token={token}"
    runtime = data / RUNTIME
    runtime.write_text(json.dumps({"pid": os.getpid(), "port": port, "url": url, "started": time.time()}))
    runtime.chmod(0o600)

    print(f"Spaced Positions {__version__} is running.")
    print(f"  Open:        {url}")
    if args.lan:
        print(f"  On the LAN:  http://{_lan_address()}:{port}/?token={token}")
    print(f"  Data folder: {data}")
    print("  Stop with Ctrl+C (or :quit in the app).")
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, args=[url]).start()

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.unlink(missing_ok=True)
        print("\nStopped.")


def _migrate(data: Path):
    """Apply pending migrations, after backing up the database (spec 09 §11)."""
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if not plan:
        return
    db = data / "db.sqlite3"
    if db.exists() and db.stat().st_size:
        backups = data / "backups"
        backups.mkdir(exist_ok=True)
        target = backups / f"db-before-migrate-{datetime.now():%Y-%m-%d_%H-%M-%S}.sqlite3"
        connection.ensure_connection()
        dest = sqlite3.connect(target)
        connection.connection.backup(dest)  # a consistent copy, also of a WAL database
        dest.close()
        print(f"  Backup:      {target}")
    call_command("migrate", interactive=False, verbosity=0)


def _import_csm(data: Path, args):
    """`spos import-csm <db.sqlite3>`: the migration from chess-study-manager (spaced_positions/csm.py)."""
    if not args.path:
        sys.exit("spos import-csm: which database? e.g. spos import-csm ~/chess-study-manager/db.sqlite3")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "spaced_positions.settings")
    import django

    django.setup()
    _migrate(data)
    from spaced_positions import csm

    try:
        report = csm.run(args.path, dry_run=args.dry_run)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(f"spos import-csm: {e}")
    if report.backup:
        print(f"  Backup:      {report.backup}")
    print(("  Would add:   " if args.dry_run else "  Added:       ") + (", ".join(report.lines()) or "nothing new"))
    for problem in report.problems:
        print(f"  ! {problem}")


def _lan_address() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("192.0.2.1", 80))  # TEST-NET address: nothing is sent
            return sock.getsockname()[0]
        except OSError:
            return socket.gethostname()


def quit_soon():
    """Stop the server shortly after the current response has gone out (`:quit`)."""

    def _stop():
        time.sleep(0.4)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_stop, daemon=True).start()

