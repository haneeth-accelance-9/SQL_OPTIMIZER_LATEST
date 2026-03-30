"""
Django settings for SQL License Optimizer.
Security-hardened; supports DJANGO_ENV=production for strict mode.
Optional: use settings package with DJANGO_SETTINGS_MODULE=sql_license_optimizer.settings.development
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("true", "1", "yes")


def _require_env(name: str, message: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(message)
    return value


DEBUG = _env_bool("DJANGO_DEBUG", default=True)
_IS_PRODUCTION = os.environ.get("DJANGO_ENV", "").strip().lower() == "production" or not DEBUG

if _IS_PRODUCTION:
    SECRET_KEY = _require_env(
        "DJANGO_SECRET_KEY",
        "DJANGO_SECRET_KEY must be set in production.",
    )
    ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not ALLOWED_HOSTS:
        raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production.")
else:
    SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-dev-only")
    ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "optimizer",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "optimizer.middleware.RequestIdMiddleware",
]

ROOT_URLCONF = "sql_license_optimizer.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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
WSGI_APPLICATION = "sql_license_optimizer.wsgi.application"

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "uploads/"
MEDIA_ROOT = BASE_DIR / "uploads"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DATA_UPLOAD_MAX_MEMORY_SIZE = 52_428_800
FILE_UPLOAD_MAX_MEMORY_SIZE = 52_428_800

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 86400 * 2
if _IS_PRODUCTION:
    SESSION_COOKIE_SECURE = True

LOGIN_URL = "optimizer:login"
LOGIN_REDIRECT_URL = "optimizer:home"
LOGOUT_REDIRECT_URL = "optimizer:login"

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if _IS_PRODUCTION:
    SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

CSRF_TRUSTED_ORIGINS = [
    f"https://{h.strip()}"                                                                                                                                     
    for h in os.environ.get("ALLOWED_HOSTS", "localhost").split(",")                                                                                           
    if h.strip() and h.strip() not in ("localhost", "127.0.0.1")                                                                                               
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4").strip() or "gpt-4"
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview").strip() or "2024-02-15-preview"
AZURE_OPENAI_TIMEOUT = int(os.environ.get("AZURE_OPENAI_TIMEOUT", "60"))

EXCEL_SHEET_INSTALLATIONS = os.environ.get("EXCEL_SHEET_INSTALLATIONS", "MVP - Data 1 - Installation")
EXCEL_SHEET_DEMAND = os.environ.get("EXCEL_SHEET_DEMAND", "MVP - Data 2 - Demand Results")
EXCEL_SHEET_PRICES = os.environ.get("EXCEL_SHEET_PRICES", "MVP - Data 3 - Prices")
EXCEL_SHEET_OPTIMIZATION = os.environ.get("EXCEL_SHEET_OPTIMIZATION", "MVP - Data 4 - Optimization potential")
EXCEL_SHEET_HELPFUL_REPORTS = os.environ.get("EXCEL_SHEET_HELPFUL_REPORTS", "MVP - Data 5 - Helpful Reports")

OPTIMIZER_AI_REPORT_ENABLED = _env_bool("OPTIMIZER_AI_REPORT_ENABLED", True)
OPTIMIZER_CHARTS_ENABLED = _env_bool("OPTIMIZER_CHARTS_ENABLED", True)
OPTIMIZER_ANALYSIS_TTL_SECONDS = int(os.environ.get("OPTIMIZER_ANALYSIS_TTL_SECONDS", "86400"))
OPTIMIZER_UPLOAD_RETENTION_DAYS = int(os.environ.get("OPTIMIZER_UPLOAD_RETENTION_DAYS", "7"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"optimizer": {"handlers": ["console"], "level": "DEBUG" if DEBUG else "INFO", "propagate": False}},
}
