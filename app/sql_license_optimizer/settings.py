"""
Django settings for SQL License Optimizer.
Security-hardened; supports DJANGO_ENV=production for strict mode.
Optional: use settings package with DJANGO_SETTINGS_MODULE=sql_license_optimizer.settings.development
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

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
    "django.contrib.postgres",
    "django_crontab",
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
                "optimizer.context_processors.notification_context",
            ],
        },
    },
]
WSGI_APPLICATION = "sql_license_optimizer.wsgi.application"

_db_host = os.environ.get("DB_HOST", "localhost")
DATABASES = {
    "default": {
        "ENGINE":   "django.db.backends.postgresql",
        "NAME":     os.environ.get("DB_NAME", "mvp6"),
        "USER":     os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST":     _db_host,
        "PORT":     os.environ.get("DB_PORT", "5432"),
        "OPTIONS":  {"sslmode": "require", "connect_timeout": 10} if "azure.com" in _db_host else {},
        "CONN_MAX_AGE": 60,
    }
}
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

# Demand API (USU) — fetched by `python manage.py fetch_demand_data`
# Override via environment variables or set directly here.
DEMAND_API_BASE_URL = os.environ.get("DEMAND_API_BASE_URL", "https://lima.bayer.cloud.usu.com")
DEMAND_API_START_URI = os.environ.get(
    "DEMAND_API_START_URI",
    "/prod/index.php/api/customization/v1.0/demanddetails?$skip=0&$top=10000",
)
DEMAND_API_AUTH_HEADER = os.environ.get(
    "DEMAND_API_AUTH_HEADER",
    "Basic dXN1ZGF0YXVzZXI6QlVFUFdFZkw2JCM5eVEh",
)

# USU API — used by fetch_usu_data management command (weekly sync)
USU_API_BASE_URL  = os.environ.get("USU_API_BASE_URL",  "https://lima.bayer.cloud.usu.com")
USU_API_USERNAME  = os.environ.get("USU_API_USERNAME",  "myusudata")
USU_API_PASSWORD  = os.environ.get("USU_API_PASSWORD",  "test123Usu")
# Output file path — defaults to BASE_DIR/response_full.json
DEMAND_API_OUTPUT_FILE = os.environ.get("DEMAND_API_OUTPUT_FILE", str(BASE_DIR / "response_full.json"))

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

# ── Grafana / Mimir (Prometheus remote-read) ──────────────────────────────────
#
# What is Mimir?
#   Grafana Mimir is a horizontally scalable, multi-tenant Prometheus backend.
#   Instead of querying the Grafana UI (frontend proxy), we talk directly to the
#   Mimir Prometheus HTTP API — faster and doesn't need a datasource UID.
#
# How authentication works:
#   Step 1 — HTTP Basic Auth:
#     username = GRAFANA_USER  (numeric ID, e.g. 2834315)
#     password = GRAFANA_TOKEN (glc_eyJ… service account token)
#
#   Step 2 — Tenant routing header:
#     X-Scope-OrgID = GRAFANA_TENANT_ID
#     Mimir uses this header to route the query to the correct tenant's data.
#     Without it the request is rejected or returns data from the wrong tenant.
#
# Query endpoint used by fetch_grafana_metrics:
#   GET {GRAFANA_BASE_URL}/api/prom/api/v1/query_range
#       ?query=<PromQL>  &start=<RFC3339>  &end=<RFC3339>  &step=<duration>

# The Mimir cluster URL for this environment (prod-eu-west-5 region)
GRAFANA_BASE_URL = os.environ.get(
    "GRAFANA_BASE_URL",
    "https://prometheus-dedicated-64-prod-eu-west-5.grafana.net",
)

# Mimir tenant ID — sent as X-Scope-OrgID header on every request.
# Without this header Mimir returns 401 or empty results.
GRAFANA_TENANT_ID = os.environ.get("GRAFANA_TENANT_ID", "")

# Numeric Grafana user ID — used as the Basic Auth username
GRAFANA_USER = os.environ.get("GRAFANA_USER", "")

# Grafana service account token (glc_eyJ…) — used as the Basic Auth password
GRAFANA_TOKEN = os.environ.get("GRAFANA_TOKEN", "")

# HTTP request timeout in seconds — Mimir queries can be slow for large ranges
GRAFANA_TIMEOUT = int(os.environ.get("GRAFANA_TIMEOUT", "30"))

# Label stored on each GrafanaMetricSnapshot.dashboard field.
# 'primary' = production dashboard; change to 'testing' for staging.
GRAFANA_DASHBOARD = os.environ.get("GRAFANA_DASHBOARD", "primary")

# How far back each daily fetch looks. 'now-24h' means the last 24 hours.
# Increase (e.g. 'now-48h') only for catch-up runs after a missed day.
GRAFANA_FETCH_RANGE = os.environ.get("GRAFANA_FETCH_RANGE", "now-24h")

# Prometheus query resolution step.
# '1h' = one data point per hour = 24 snapshot rows per metric per server per day.
# Use '30m' for finer granularity (doubles row count).
GRAFANA_STEP = os.environ.get("GRAFANA_STEP", "1h")

# How many days to keep raw GrafanaMetricSnapshot rows before the monthly
# rollup job (rollup_grafana_metrics) purges them to save DB space.
GRAFANA_SNAPSHOT_RETENTION_DAYS = int(
    os.environ.get("GRAFANA_SNAPSHOT_RETENTION_DAYS", "90")
)

# ── Weekly USU data sync via django-crontab ───────────────────────────────────
# Runs every Monday at 02:00 AM.
# Cron syntax: minute hour day-of-month month day-of-week
# Register  : python manage.py crontab add
# Remove    : python manage.py crontab remove
# Show      : python manage.py crontab show
CRONJOBS = [
    # ── USU data sync — every Monday at 02:00 ─────────────────────────────────
    (
        "0 2 * * 1",
        "django.core.management.call_command",
        ["fetch_usu_data"],
        {},
        ">> " + str(BASE_DIR / "logs" / "usu_sync.log") + " 2>&1",
    ),
    # ── Grafana metrics fetch — every day at 01:00 ────────────────────────────
    # Pulls the last 24 h of Prometheus metrics and saves raw snapshots to DB.
    (
        "0 1 * * *",
        "django.core.management.call_command",
        ["fetch_grafana_metrics"],
        {},
        ">> " + str(BASE_DIR / "logs" / "grafana_fetch.log") + " 2>&1",
    ),
    # ── Grafana rollup + purge — 1st of every month at 03:00 ─────────────────
    # Aggregates previous month's snapshots into monthly rollups, deletes
    # raw rows older than GRAFANA_SNAPSHOT_RETENTION_DAYS (90 days).
    (
        "0 3 1 * *",
        "django.core.management.call_command",
        ["rollup_grafana_metrics"],
        {},
        ">> " + str(BASE_DIR / "logs" / "grafana_rollup.log") + " 2>&1",
    ),
]

# Ensure the logs directory exists so the cron log file can be written
import pathlib
pathlib.Path(BASE_DIR / "logs").mkdir(exist_ok=True)
