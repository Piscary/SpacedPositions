"""manage.py starter <lichess_db_puzzle.csv> [--per-band N]: build the starter pack (library/starter.py) again."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from spaced_positions.library import starter


class Command(BaseCommand):
    help = "Build library/data/starter.sppack from the lichess puzzle database (CSV, from https://database.lichess.org/#puzzles)."

    def add_arguments(self, parser):
        parser.add_argument("csv", type=Path)
        parser.add_argument("--per-band", type=int, default=4, help="puzzles per motif and rating band (4 bands)")

    def handle(self, *args, csv, per_band, **options):
        if not csv.is_file():
            raise CommandError(f"no such file: {csv}")
        manifest = starter.build(csv, per_band=per_band)
        size = starter.PATH.stat().st_size
        self.stdout.write(f"wrote {starter.PATH.name}: {manifest['puzzles']} puzzles, {size / 1024:.0f} kB, version {manifest['version']}")
