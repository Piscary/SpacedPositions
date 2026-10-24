"""manage.py import_csm PATH: the migration from chess-study-manager (spaced_positions/csm.py, spec 10 · phase 7).

Reads a snapshot copy of the old database and adds everything that isn't here yet; it can run again later and adds
only what is new. This database is backed up first; --dry-run shows what would be added without changing anything."""

from django.core.management.base import BaseCommand, CommandError

from spaced_positions import csm


class Command(BaseCommand):
    help = "Migrate a chess-study-manager database (read from a copy; adds only what isn't here yet)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="chess-study-manager db.sqlite3")
        parser.add_argument("--dry-run", action="store_true", help="do it all, then roll it back: shows what would be added")
        parser.add_argument("--no-schedule", action="store_true", help="keep the schedules of this app's cards as they are")

    def handle(self, path, dry_run, no_schedule, **options):
        try:
            report = csm.run(path, dry_run=dry_run, schedule=not no_schedule)
        except (FileNotFoundError, ValueError) as e:
            raise CommandError(str(e)) from None
        if report.backup:
            self.stdout.write(f"Backup: {report.backup}")
        self.stdout.write(("Would add: " if dry_run else "Added: ") + (", ".join(report.lines()) or "nothing new"))
        for problem in report.problems:
            self.stderr.write(f"  {problem}")
