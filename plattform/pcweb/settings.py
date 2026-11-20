"""Einstellungen der Planungsplattform.

Alles Betriebsrelevante kommt aus Umgebungsvariablen (Render), lokal gibt es sichere Standards.
Feature-Flags (Briefing: Rollen/Freigaben von Anfang an mitdenken, im MVP deaktivierbar):
  FEATURE_FREIGABE        1/0  Freigabe-Workflow an/aus (aus: Forecasts gelten sofort als freigegeben)
  FEATURE_ZWEITE_STUFE    1/0  zweite Freigabestufe an/aus
  FEATURE_ROLLEN          1/0  Freigaben nur durch die unten genannten Benutzer
  FREIGABE_STUFE1 / FREIGABE_STUFE2   kommagetrennte Benutzernamen (Basic Auth)
"""
import os
import sys
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))  # pcpoc (Rechenkern) liegt im Repo-Root


def env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "ja", "yes", "on")


DEBUG = env_bool("DJANGO_DEBUG", False)
TESTING = "test" in sys.argv
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or ("dev-only-not-secret" if DEBUG or "test" in sys.argv else None)
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY fehlt")
ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,.onrender.com").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "https://*.onrender.com").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.messages",
    "django.contrib.humanize",
    "planung",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "planung.auth.BasicAuthMiddleware",       # vor WhiteNoise: auch statische Dateien sind geschützt
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "pcweb.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request",
                                       "django.contrib.messages.context_processors.messages", "planung.views.nav_context"]},
}]
WSGI_APPLICATION = "pcweb.wsgi.application"

DATABASES = {"default": dj_database_url.config(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=60)}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "de-de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True

MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Vorab gerechneter Bericht und Präsentationen (Docker-Build) liegen hier und werden unter /bericht/ ausgeliefert
PUBLISHED_DIR = Path(os.environ.get("PUBLISHED_DIR", BASE_DIR / "published"))
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))
# Rohdateien über eine austauschbare Schnittstelle: heute Dateisystem, später z. B. S3 (nur diese Zeile ändern)
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": str(MEDIA_ROOT)}},
            "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"}}
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
X_FRAME_OPTIONS = "DENY"

# Planung
PARAMS_FILE = Path(os.environ.get("PARAMS_FILE", REPO_DIR / "config" / "params.yaml"))
FEATURES = {
    "freigabe": env_bool("FEATURE_FREIGABE", True),
    "zweite_stufe": env_bool("FEATURE_ZWEITE_STUFE", False),
    "rollen": env_bool("FEATURE_ROLLEN", False),
}
FREIGABE_STUFE1 = [u.strip() for u in os.environ.get("FREIGABE_STUFE1", "").split(",") if u.strip()]
FREIGABE_STUFE2 = [u.strip() for u in os.environ.get("FREIGABE_STUFE2", "").split(",") if u.strip()]
# Quelle für Importe: "datei" (MVP). "rest" ist vorbereitet, aber nicht angebunden (Briefing: nur architektonisch).
DATENQUELLE = os.environ.get("DATENQUELLE", "datei")

LOGGING = {"version": 1, "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": "INFO"}}
