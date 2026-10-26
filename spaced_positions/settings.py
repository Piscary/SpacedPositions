"""Django settings. Everything that differs per run comes from environment variables set by the launcher
(`spos`) or by `manage.py` for development."""

import os
from pathlib import Path

from spaced_positions import paths

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parent
DATA_DIR = paths.data_dir()

DEBUG = os.environ.get("SPOS_DEBUG") == "1"
SECRET_KEY = paths.secret_key()

# The launcher sets a random token; requests need it once (as ?token=) and then carry a cookie (core.middleware).
SPOS_TOKEN = os.environ.get("SPOS_TOKEN", "")
SPOS_LAUNCHED = os.environ.get("SPOS_LAUNCHED") == "1"
ALLOWED_HOSTS = os.environ.get("SPOS_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "whitenoise.runserver_nostatic",  # WhiteNoise serves static files in development too
    "django.contrib.staticfiles",
    "spaced_positions.core",
    "spaced_positions.design",
    "spaced_positions.training",
    "spaced_positions.analysis",
    "spaced_positions.library",
    "spaced_positions.stats",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "spaced_positions.core.middleware.TokenMiddleware",
    "spaced_positions.core.i18n.LanguageMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "spaced_positions.urls"
WSGI_APPLICATION = "spaced_positions.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [PACKAGE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "spaced_positions.core.context_processors.shell",
            ],
            "builtins": ["spaced_positions.core.templatetags.ui", "django.templatetags.i18n", "django.templatetags.static"],
            "string_if_invalid": "",
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        # IMMEDIATE: a transaction takes the write lock when it starts, so saves that arrive together queue (up to
        # `timeout` seconds) instead of one overwriting what the other just read.
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
        },
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("de", "Deutsch"), ("fr", "Français"), ("it", "Italiano")]
LOCALE_PATHS = [PACKAGE_DIR / "locale"]
USE_I18N = True
TIME_ZONE = "UTC"
USE_TZ = True

def _static_build(folder: Path) -> str:
    """A stamp of the installed static files (names, sizes, times): it changes with every update."""
    import hashlib

    digest = hashlib.sha1()
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            stat = path.stat()
            digest.update(f"{path.relative_to(folder)}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return digest.hexdigest()[:10]


# The static files live under a path with the build's stamp (/static/<stamp>/js/app.js). ES modules import each other
# by relative names, so every module of an update has a new address: the browser can keep files for good and never
# runs old JavaScript with a new page. In development the files change while the app runs: plain /static/, no caching.
STATIC_URL = "/static/" if DEBUG else f"/static/{_static_build(PACKAGE_DIR / 'static')}/"
STATICFILES_DIRS = [PACKAGE_DIR / "static"]
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_MAX_AGE = 0 if DEBUG else 365 * 24 * 3600

CSRF_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_SAMESITE = "Strict"
X_FRAME_OPTIONS = "DENY"

# Design system sources (repository only; an installed app uses the generated files in static/design).
DESIGN_DIR = REPO_DIR / "design"
DESIGN_OUT = PACKAGE_DIR / "static" / "design"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
