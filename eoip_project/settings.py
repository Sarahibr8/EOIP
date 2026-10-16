"""Django settings for the EOIP project (Expo Operations Intelligence Platform, local MVP).

One SQLite file holds everything:
  * Django's own tables (users = employees, sessions, admin) - created by `python manage.py migrate`
  * EOIP's operational tables (zones, alerts, incidents, decisions, ...) - created from eoip/schema.sql
    by the same `migrate` command (post_migrate hook in eoip/apps.py)

Environment variables (all optional):
  EOIP_DB              path of the SQLite file (default: <project>/db.sqlite3)
  EOIP_SECRET_KEY      Django secret key (default: generated once into <project>/.secret_key)
  EOIP_DEBUG=1         Django debug pages (never during the demo)
  EOIP_COOKIE_SECURE=1 send session/CSRF cookies over HTTPS only
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _secret_key():
    env = os.environ.get("EOIP_SECRET_KEY")
    if env:
        return env
    path = BASE_DIR / ".secret_key"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(50), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


SECRET_KEY = _secret_key()
DEBUG = os.environ.get("EOIP_DEBUG", "").lower() in {"1", "true", "yes"}
# Local demo: the phone opens the laptop by its Wi-Fi / hotspot IP, which changes from network to network.
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "eoip.apps.EoipConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "eoip.middleware.EmployeeGateMiddleware",   # login required + per-request EOIP DB connection
]

ROOT_URLCONF = "eoip_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "eoip_project.wsgi.application"

# Store the three example cases (already handled earlier in the shift) when a new event starts.
EOIP_EXAMPLES = os.environ.get("EOIP_EXAMPLES", "1").lower() not in {"0", "false", "no"}
# Signing in to the operations center starts a new live event immediately (decision log kept).
EOIP_AUTOSTART = os.environ.get("EOIP_AUTOSTART", "1").lower() not in {"0", "false", "no"}

EOIP_DB = Path(os.environ.get("EOIP_DB", BASE_DIR / "db.sqlite3"))
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": EOIP_DB,
        "OPTIONS": {
            # The EOIP pipeline writes with BEGIN IMMEDIATE on its own connection; Django waits for it.
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
            "init_command": "PRAGMA journal_mode=WAL",
        },
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Employees are Django users: username = employee number (digits), first_name = display name.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.ScryptPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
LOGIN_URL = "/login"

SESSION_COOKIE_AGE = 8 * 60 * 60            # an eight-hour shift
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "eoip_session"
_secure = os.environ.get("EOIP_COOKIE_SECURE", "").lower() in {"1", "true", "yes"}
SESSION_COOKIE_SECURE = _secure
CSRF_COOKIE_SECURE = _secure
CSRF_COOKIE_HTTPONLY = True                 # the pages read the token from <meta name="csrf-token">
CSRF_HEADER_NAME = "HTTP_X_CSRF_TOKEN"      # the front-end sends "X-CSRF-Token"
CSRF_FAILURE_VIEW = "eoip.views.auth.csrf_failure"

LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Riyadh"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Phone camera: frames are raw JPEG bodies; uploaded test videos can be large.
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR"},
                "eoip": {"handlers": ["console"], "level": "INFO"}},
}
