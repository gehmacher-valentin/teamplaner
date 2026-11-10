"""Einstellungen des Teamplaners. Alles Umgebungsabhängige kommt aus Umgebungsvariablen."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    wert = os.environ.get(name)
    if wert is None:
        return default
    return wert.strip().lower() in {"1", "true", "yes", "ja", "on"}


def env_list(name, default=""):
    return [teil.strip() for teil in env(name, default).split(",") if teil.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY muss gesetzt sein.")

DEBUG = env_bool("DJANGO_DEBUG")
# 127.0.0.1 zusätzlich für Aufrufe am Server selbst (Health-Check /gesund/, teamplaner status)
ALLOWED_HOSTS = [*env_list("DJANGO_ALLOWED_HOSTS", "localhost"), "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "axes",
    "django_htmx",
    "kern",
    "verwaltung",
    "projekte",
    "planung",
    "zusammenarbeit",
    "gantt",
    "notizen",
    "bestellungen",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "kern.middleware.SicherheitskopfMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "kern.middleware.NulZeichenMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "kern.middleware.KontoSpracheMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "kern.middleware.AbgemeldetMiddleware",
    "kern.middleware.HtmxMeldungenMiddleware",
    "kern.middleware.SitzungMiddleware",
    "kern.middleware.ZweiFaktorMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "teamplaner.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "verwaltung.context_processors.navigation",
            ],
        },
    },
]

ASGI_APPLICATION = "teamplaner.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "NAME": env("POSTGRES_DB", "teamplaner"),
        "USER": env("POSTGRES_USER", "teamplaner"),
        "PASSWORD": env("POSTGRES_PASSWORD", ""),
        "CONN_MAX_AGE": 0,
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Anmeldung ---
AUTH_USER_MODEL = "kern.Konto"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "kern.auth.KontoBackend",
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "login"
# Gültigkeit von Einladungslinks; Links zum Zurücksetzen eines Passworts deutlich kürzer (kern.hilfen)
PASSWORD_RESET_TIMEOUT = int(env("TEAMPLANER_LINK_GUELTIG_TAGE", "7")) * 24 * 3600
TEAMPLANER_RESET_GUELTIG_STUNDEN = int(env("TEAMPLANER_RESET_GUELTIG_STUNDEN", "2"))

# Sitzungen: angemeldet bleiben bis TEAMPLANER_SITZUNG_TAGE
# nach der Anmeldung (feste Frist, kern.signale). Admins zusätzlich abmelden nach
# TEAMPLANER_ADMIN_INAKTIV_MINUTEN ohne eigene Aktivität (kern.middleware.SitzungMiddleware).
TEAMPLANER_SITZUNG_TAGE = int(env("TEAMPLANER_SITZUNG_TAGE", "30"))
TEAMPLANER_ADMIN_INAKTIV_MINUTEN = int(env("TEAMPLANER_ADMIN_INAKTIV_MINUTEN", "60"))
SESSION_COOKIE_AGE = TEAMPLANER_SITZUNG_TAGE * 24 * 3600

# Sperre nach Fehlversuchen (django-axes)
AXES_FAILURE_LIMIT = int(env("TEAMPLANER_FEHLVERSUCHE", "5"))
AXES_COOLOFF_TIME = int(env("TEAMPLANER_SPERRE_MINUTEN", "15")) / 60
AXES_LOCKOUT_PARAMETERS = ["username"]
# Das Anmeldeformular heißt "username", auch wenn das Konto per E-Mail angemeldet wird
AXES_USERNAME_FORM_FIELD = "username"
# Gezählt wird je E-Mail ohne Groß-/Kleinschreibung, wie bei der Anmeldung (sonst umgehbar)
AXES_USERNAME_CALLABLE = "kern.auth.axes_benutzername"
# Lösch- und Aufbewahrungsfristen (verwaltung.aufraeumen, täglich im Dienst mails_versenden):
# Protokolle und Benachrichtigungen (Protokoll mindestens 365 Tage), deaktivierte Konten
TEAMPLANER_AUFBEWAHRUNG_TAGE = int(env("TEAMPLANER_AUFBEWAHRUNG_TAGE", "365"))
TEAMPLANER_DEAKTIVIERT_TAGE = int(env("TEAMPLANER_DEAKTIVIERT_TAGE", "90"))
# Befehl demodaten (leert die Datenbank, Konten mit bekanntem Passwort) nur in Test-/Demo-Umgebungen
TEAMPLANER_DEMO = env_bool("TEAMPLANER_DEMO")
# Zwei-Faktor-Anmeldung Pflicht für Admin und Bereichsleitung (kern.zwei_faktor)
TEAMPLANER_ZWEI_FAKTOR_PFLICHT = True
# Zusätzlich je IP-Adresse über alle Konten (kern.auth.zu_viele_fehlversuche_von_ip); 0 = aus
TEAMPLANER_FEHLVERSUCHE_JE_IP = int(env("TEAMPLANER_FEHLVERSUCHE_JE_IP", "20"))
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "registration/gesperrt.html"
AXES_VERBOSE = False

# --- Sprache und Zeit ---
LANGUAGE_CODE = "de"
LANGUAGES = [("de", "Deutsch"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Europe/Vienna"
USE_I18N = True
USE_TZ = True

# --- Statische Dateien und Anhänge ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = Path(env("TEAMPLANER_MEDIA_ROOT", str(BASE_DIR / "media")))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if env_bool("TEAMPLANER_STATIC_MANIFEST", not DEBUG)
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}
# Größenlimit für Anhänge
TEAMPLANER_ANHANG_MAX_MB = int(env("TEAMPLANER_ANHANG_MAX_MB", "25"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --- API (nur Teamplaner) ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # Nicht angemeldet → 401 mit code „abgemeldet“, die Oberfläche geht dann zur Anmeldung
    "EXCEPTION_HANDLER": "kern.hilfen.api_ausnahme",
}

# --- Sicherheit hinter Reverse Proxy (nur HTTPS) ---
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = env_bool("TEAMPLANER_COOKIES_SECURE", True)
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
    SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"

# --- E-Mail – ohne EMAIL_HOST wird nichts verschickt ---
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", EMAIL_PORT == 587)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", EMAIL_PORT == 465)
EMAIL_TIMEOUT = 20
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Teamplaner <teamplaner@localhost>")
# Öffentliche Adresse für Links in E-Mails
TEAMPLANER_ADRESSE = env("TEAMPLANER_ADRESSE", "http://localhost:8000")

# --- Version ---
# VERSION entsteht beim Bauen des Pakets aus dem Git-Tag; ohne Datei läuft der Quellcode.
_VERSION_DATEI = BASE_DIR / "VERSION"
TEAMPLANER_VERSION = _VERSION_DATEI.read_text().strip() if _VERSION_DATEI.exists() else ""
# Adresse des Quellcodes (Seite „Über“); bei einer geänderten Fassung auf deren Quellcode zeigen lassen
TEAMPLANER_QUELLCODE = env("TEAMPLANER_QUELLCODE", "https://github.com/gehmacher-valentin/teamplaner")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("TEAMPLANER_LOGLEVEL", "INFO")},
}

# Sperre in axes je Konto (nicht je IP): schützt Konten auch vor verteilten Rateversuchen.
# Die Grenze je IP-Adresse (höher, für geteilte Netze) prüft kern.auth.zu_viele_fehlversuche_von_ip.
SILENCED_SYSTEM_CHECKS = ["axes.W006"]
