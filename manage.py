#!/usr/bin/env python
"""Development entry point. Uses `<repo>/.data` and DEBUG unless set otherwise; end users start the app with `spos`."""

import os
import sys
from pathlib import Path


def main():
    repo = Path(__file__).resolve().parent
    os.environ.setdefault("SPOS_DATA_DIR", str(repo / ".data"))
    os.environ.setdefault("SPOS_DEBUG", "1")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "spaced_positions.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
