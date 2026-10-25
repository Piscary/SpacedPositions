"""manage.py i18n extract | build | check | missing | fill <file.json>: the translation catalogues (core/i18n_catalog.py)."""

import json
import sys

from django.core.management.base import BaseCommand, CommandError

from spaced_positions.core import i18n_catalog as catalog


class Command(BaseCommand):
    help = "Translation catalogues: extract the texts, build the compiled files, check them."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["extract", "build", "check", "missing", "fill"])
        parser.add_argument("path", nargs="?", help="fill: a JSON file of translations")

    def handle(self, action, path=None, **options):
        if action == "extract":
            found = catalog.extract()
            for lang in catalog.LANGUAGES:
                added, dropped = catalog.merge(lang, found)
                self.stdout.write(f"{lang}: {len(found)} texts ({added} new, {dropped} dropped)")
        elif action == "build":
            for p in catalog.build():
                self.stdout.write(f"wrote {p}")
        elif action == "check":
            errors = catalog.check()
            for e in errors:
                self.stdout.write(e)
            if errors:
                raise CommandError(f"{len(errors)} problem(s)")
            self.stdout.write("translations: ok")
        elif action == "missing":
            json.dump(catalog.missing(), sys.stdout, ensure_ascii=False, indent=1)
        elif action == "fill":
            if not path:
                raise CommandError("fill: which JSON file?")
            n = catalog.fill(json.loads(open(path).read()))
            self.stdout.write(f"filled {n} translations")
