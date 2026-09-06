"""Django settings for OSIRIS.

The application owns only its central configuration database. Sensor databases are
registered as named Django aliases from a protected JSON file or environment variable
and are accessed read-only through explicit adapters.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
ENVIRONMENT = os.getenv("OSIRIS_ENV", "development").strip().lower()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEBUG = env_bool("OSIRIS_DEBUG", ENVIRONMENT == "development")
SECRET_KEY = os.getenv("OSIRIS_SECRET_KEY", "").strip()
if not SECRET_KEY:
    if ENVIRONMENT == "production":
        raise ImproperlyConfigured("OSIRIS_SECRET_KEY is required in production")
    SECRET_KEY = "development-only-change-me-before-production"

ALLOWED_HOSTS = env_list(
    "OSIRIS_ALLOWED_HOSTS", "" if ENVIRONMENT == "production" else "127.0.0.1,localhost"
)
if ENVIRONMENT == "production" and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("OSIRIS_ALLOWED_HOSTS is required in production")
CSRF_TRUSTED_ORIGINS = env_list("OSIRIS_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "aplicaciones.core",
    "aplicaciones.dashboard",
    "aplicaciones.sensor_config",
    "aplicaciones.satellite",
    "aplicaciones.automatizacion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "aplicaciones.core.middleware.ClientContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
if ENVIRONMENT == "production":
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "osiris_dev.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "aplicaciones.core.context_processors.client_context",
            ],
        },
    }
]

WSGI_APPLICATION = "osiris_dev.wsgi.application"
ASGI_APPLICATION = "osiris_dev.asgi.application"


def central_database() -> dict[str, object]:
    """Return the OSIRIS-owned database configuration."""

    name = os.getenv("OSIRIS_DB_NAME", "").strip()
    if not name:
        if ENVIRONMENT == "production":
            raise ImproperlyConfigured("OSIRIS_DB_NAME is required in production")
        sqlite_path = Path(os.getenv("OSIRIS_SQLITE_PATH", "osiris.sqlite3"))
        if not sqlite_path.is_absolute():
            sqlite_path = BASE_DIR / sqlite_path
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": sqlite_path,
        }

    sslmode = os.getenv("OSIRIS_DB_SSLMODE", "prefer")
    if sslmode not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
        raise ImproperlyConfigured("OSIRIS_DB_SSLMODE is invalid")
    options: dict[str, object] = {
        "connect_timeout": int(os.getenv("OSIRIS_DB_CONNECT_TIMEOUT", "5")),
        "sslmode": sslmode,
        "application_name": "osiris-platform",
    }
    if os.getenv("OSIRIS_DB_SSLROOTCERT"):
        options["sslrootcert"] = os.environ["OSIRIS_DB_SSLROOTCERT"]

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": os.getenv("OSIRIS_DB_USER", "osiris_app"),
        "PASSWORD": os.getenv("OSIRIS_DB_PASSWORD", ""),
        "HOST": os.getenv("OSIRIS_DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("OSIRIS_DB_PORT", "5432"),
        "CONN_MAX_AGE": int(os.getenv("OSIRIS_DB_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": options,
    }


def load_client_databases() -> dict[str, dict[str, object]]:
    """Load named sensor databases without persisting credentials in Django Admin."""

    config_path = os.getenv("OSIRIS_CLIENT_DATABASES_FILE", "").strip()
    raw_config = os.getenv("OSIRIS_CLIENT_DATABASES_JSON", "").strip()

    if config_path:
        try:
            raw_config = Path(config_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise ImproperlyConfigured(
                f"Could not read OSIRIS_CLIENT_DATABASES_FILE: {exc}"
            ) from exc

    if not raw_config:
        return {}

    try:
        payload = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured("Client database configuration is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ImproperlyConfigured("Client database configuration must be a JSON object")

    databases: dict[str, dict[str, object]] = {}
    allowed_engines = {"django.db.backends.postgresql"}

    for alias, config in payload.items():
        if alias == "default" or not re.fullmatch(r"[a-z][a-z0-9_]{1,62}", alias):
            raise ImproperlyConfigured(f"Invalid client database alias: {alias!r}")
        if not isinstance(config, dict):
            raise ImproperlyConfigured(f"Configuration for {alias!r} must be an object")

        engine = config.get("ENGINE", "django.db.backends.postgresql")
        if engine not in allowed_engines:
            raise ImproperlyConfigured(f"Unsupported database engine for {alias!r}")

        required = ("NAME", "USER", "PASSWORD", "HOST")
        missing = [field for field in required if not config.get(field)]
        if missing:
            raise ImproperlyConfigured(
                f"Client database {alias!r} is missing: {', '.join(missing)}"
            )

        sslmode = str(config.get("SSLMODE", "prefer"))
        if sslmode not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
            raise ImproperlyConfigured(f"Invalid SSLMODE for client database {alias!r}")
        database_options: dict[str, object] = {
            "connect_timeout": int(config.get("CONNECT_TIMEOUT", 5)),
            "options": "-c default_transaction_read_only=on",
            "sslmode": sslmode,
            "application_name": "osiris-dashboard",
        }
        if config.get("SSLROOTCERT"):
            database_options["sslrootcert"] = str(config["SSLROOTCERT"])

        databases[alias] = {
            "ENGINE": engine,
            "NAME": config["NAME"],
            "USER": config["USER"],
            "PASSWORD": config["PASSWORD"],
            "HOST": config["HOST"],
            "PORT": str(config.get("PORT", "5432")),
            "CONN_MAX_AGE": int(config.get("CONN_MAX_AGE", 60)),
            "CONN_HEALTH_CHECKS": True,
            # Defense in depth: adapters cannot mutate a client database even if
            # the configured PostgreSQL role was granted excessive privileges.
            "OPTIONS": database_options,
        }

    return databases


DATABASES = {"default": central_database(), **load_client_databases()}
DATABASE_ROUTERS = ["aplicaciones.core.db_router.ClientDatabaseRouter"]

CACHES = {
    "default": {
        "BACKEND": os.getenv(
            "OSIRIS_CACHE_BACKEND",
            "django.core.cache.backends.filebased.FileBasedCache",
        ),
        "LOCATION": os.getenv("OSIRIS_CACHE_LOCATION", str(BASE_DIR / "django_cache")),
        "TIMEOUT": int(os.getenv("OSIRIS_CACHE_TIMEOUT", "120")),
        "OPTIONS": {"MAX_ENTRIES": int(os.getenv("OSIRIS_CACHE_MAX_ENTRIES", "2000"))},
    }
}

DASHBOARD_CACHE_TTL = int(os.getenv("OSIRIS_DASHBOARD_CACHE_TTL", "120"))
DASHBOARD_MAX_POINTS = int(os.getenv("OSIRIS_DASHBOARD_MAX_POINTS", "720"))
DASHBOARD_MAX_TABLE_ROWS = int(os.getenv("OSIRIS_DASHBOARD_MAX_TABLE_ROWS", "100"))

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = os.getenv("OSIRIS_TIME_ZONE", "America/Bogota")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "osiris_dev" / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if ENVIRONMENT == "production"
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "login"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if ENVIRONMENT == "production":
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("OSIRIS_SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(os.getenv("OSIRIS_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{asctime} | {levelname} | {name} | {message}",
            "style": "{",
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}},
    "root": {"handlers": ["console"], "level": os.getenv("OSIRIS_LOG_LEVEL", "INFO")},
}
