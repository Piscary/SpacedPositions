"""manage.py design build | check  (spec 07 §8). check also checks the translations (manage.py i18n check)."""

import sys

from django.conf import settings
from django.core.management.base import BaseCommand

from spaced_positions.design import check, lib


class Command(BaseCommand):
    help = "Build the generated design files (build) or lint the design system (check)."
    requires_system_checks = []  # build must run before the registry exists

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["build", "check"])

    def handle(self, *args, action, **options):
        package = settings.PACKAGE_DIR
        docs = settings.REPO_DIR / "docs"
        if action == "build":
            for path in lib.build(settings.DESIGN_DIR, settings.DESIGN_OUT, docs):
                self.stdout.write(f"wrote {path.relative_to(settings.REPO_DIR)}")
            return

        from spaced_positions.core import server_commands

        problems = check.run_all(
            design_dir=settings.DESIGN_DIR,
            out_dir=settings.DESIGN_OUT,
            docs_dir=docs,
            templates_dir=package / "templates",
            js_dir=package / "static" / "js",
            css_dir=package / "static" / "css",
            pyproject=settings.REPO_DIR / "pyproject.toml",
            vendor_dir=package / "static" / "vendor",
            server_handlers=set(server_commands.handlers()),
            pieces_dir=package / "static" / "pieces",
        )
        for problem in problems:
            self.stdout.write(str(problem))
        from spaced_positions.core import i18n_catalog

        translation_problems = i18n_catalog.check()
        for problem in translation_problems:
            self.stdout.write(f"error: translations: {problem}")
        warnings = sum(p.level != "error" for p in problems)
        errors = len(problems) - warnings + len(translation_problems)
        self.stdout.write(f"design check: {errors} error(s), {warnings} warning(s)")
        if errors:
            sys.exit(1)
