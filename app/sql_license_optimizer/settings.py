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
    "optimizer",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "optimizer.middleware.JWTAuthMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "optimizer.middleware.RequestIdMiddleware",
    "optimizer.middleware.PayloadEncryptionMiddleware",
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
        "OPTIONS":  {"sslmode": os.environ.get("DB_SSL_MODE", "require"), "connect_timeout": 10} if "azure.com" in _db_host else {},
        "CONN_MAX_AGE": 60,
    }
}
# Rate-limit sliding-window counters are stored here.
# Run once after deploy: python manage.py createcachetable
# For Redis, swap BACKEND to "django.core.cache.backends.redis.RedisCache"
# and set LOCATION to your Redis URL.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "rate_limit_cache",
        "TIMEOUT": 3600,
        "OPTIONS": {"MAX_ENTRIES": 50000},
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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = int(os.environ.get("SESSION_COOKIE_AGE_SECONDS", str(86400 * 2)))
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
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# ── JWT (OAuth2 Bearer tokens for API clients) ────────────────────────────────
# Uses SECRET_KEY as fallback so dev works without extra config.
# In production set JWT_SECRET_KEY to an independent high-entropy secret.
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "").strip() or SECRET_KEY
JWT_ALGORITHM = "HS256"
# Access token lifetime in seconds (default 1 hour)
JWT_ACCESS_TOKEN_LIFETIME = int(os.environ.get("JWT_ACCESS_TOKEN_LIFETIME", "3600"))
# Refresh token lifetime in seconds (default 7 days)
JWT_REFRESH_TOKEN_LIFETIME = int(os.environ.get("JWT_REFRESH_TOKEN_LIFETIME", str(86400 * 7)))

# ── Payload Encryption (AES-256-GCM for API clients) ─────────────────────────
# Generate key: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
# Leave empty to disable payload encryption (middleware becomes a no-op).
PAYLOAD_ENCRYPTION_KEY = os.environ.get("PAYLOAD_ENCRYPTION_KEY", "").strip()

AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
AZURE_OPENAI_DEPLOYMENT = (
    os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "").strip()
    or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
    or "gpt-4"
)
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview").strip() or "2024-02-15-preview"
AZURE_OPENAI_TIMEOUT = int(os.environ.get("AZURE_OPENAI_TIMEOUT", "60"))

# Azure API Management gateway — routes LLM calls through APIM instead of directly to Azure OpenAI.
# When set, AZURE_APIM_ENDPOINT overrides AZURE_OPENAI_ENDPOINT for the AzureOpenAI client.
# AZURE_APIM_SUB_KEY is sent as Ocp-Apim-Subscription-Key on every request.
AZURE_APIM_ENDPOINT = os.environ.get("AZURE_APIM_ENDPOINT", "").strip()
AZURE_APIM_SUB_KEY = os.environ.get("AZURE_APIM_SUB_KEY", "").strip()

# Demand API (USU) — fetched by `python manage.py fetch_demand_data`
# Override via environment variables or set directly here.
DEMAND_API_BASE_URL = os.environ.get("DEMAND_API_BASE_URL", "https://lima.bayer.cloud.usu.com")
DEMAND_API_START_URI = os.environ.get(
    "DEMAND_API_START_URI",
    "/prod/index.php/api/customization/v1.0/demanddetails?$skip=0&$top=10000",
)
DEMAND_API_AUTH_HEADER = _require_env(
    "DEMAND_API_AUTH_HEADER",
    "DEMAND_API_AUTH_HEADER must be set (e.g. 'Basic <base64(user:pass)>').",
)

# USU API — used by fetch_usu_data management command (weekly sync)
USU_API_BASE_URL  = os.environ.get("USU_API_BASE_URL",  "https://lima.bayer.cloud.usu.com")
USU_API_USERNAME  = _require_env(
    "USU_API_USERNAME",
    "USU_API_USERNAME must be set.",
)
USU_API_PASSWORD  = _require_env(
    "USU_API_PASSWORD",
    "USU_API_PASSWORD must be set.",
)
# Output file path — defaults to BASE_DIR/response_full.json
DEMAND_API_OUTPUT_FILE = os.environ.get("DEMAND_API_OUTPUT_FILE", str(BASE_DIR / "response_full.json"))

OPTIMIZER_AI_REPORT_ENABLED = _env_bool("OPTIMIZER_AI_REPORT_ENABLED", True)
OPTIMIZER_CHARTS_ENABLED = _env_bool("OPTIMIZER_CHARTS_ENABLED", True)
OPTIMIZER_ANALYSIS_TTL_SECONDS = int(os.environ.get("OPTIMIZER_ANALYSIS_TTL_SECONDS", "86400"))

# ── License Optimizer Agent (A2A server) ──────────────────────────────────────
# Base URL of the running liscence-optimizer A2A agent (default: local dev port)
AGENT_A2A_ENDPOINT = os.environ.get("AGENT_A2A_ENDPOINT", "http://localhost:8000").strip().rstrip("/")
# Timeout for A2A /generate-report calls (seconds)
AGENT_A2A_TIMEOUT = int(os.environ.get("AGENT_A2A_TIMEOUT", "120"))
# Max retries on 429/5xx before falling back to Azure OpenAI direct report
AGENT_A2A_MAX_RETRIES = int(os.environ.get("AGENT_A2A_MAX_RETRIES", "2"))

# ── Logging — JSON formatter + daily per-level file rotation ─────────────────
# JSON record shape (one line per record):
#   {"time": "...", "level": "...", "logger": "...", "request_id": "...", "message": "..."}
#
# Log level controlled by LOG_LEVEL env var (default INFO).
# Files written to logs/YYYY-MM-DD/<level>.log via DailyLevelFileHandler.
_LOG_DIR  = str(BASE_DIR / "logs")
_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    # ── Formatters ────────────────────────────────────────────────────────────
    "formatters": {
        # Human-readable text for the console — includes %(request_id)s
        "standard": {
            "format":   "%(asctime)s [%(levelname)-8s] [%(request_id)s] %(name)s — %(message)s",
            "datefmt":  "%Y-%m-%d %H:%M:%S",
        },
        # Structured JSON for file handlers — {"time","level","logger","request_id","message"}
        "json": {
            "()": "optimizer.logger.JsonFormatter",
        },
    },

    # ── Filter ────────────────────────────────────────────────────────────────
    # RequestIdFilter lives in middleware.py (co-located with RequestIdMiddleware).
    # It is also attached to logging.root by RequestIdMiddleware.__init__, so
    # ALL loggers carry request_id automatically — the entry here covers any
    # handler that is NOT rooted through the root logger.
    "filters": {
        "request_id": {
            "()": "optimizer.middleware.RequestIdFilter",
        },
        # Redacts email addresses (including notified_to_email) from console output
        "pii_redact": {
            "()": "optimizer.middleware.PiiRedactingFilter",
        },
    },

    # ── Handlers ──────────────────────────────────────────────────────────────
    "handlers": {
        # Console — human-readable with %(request_id)s; level follows LOG_LEVEL
        "console": {
            "class":     "logging.StreamHandler",
            "formatter": "standard",
            "filters":   ["request_id", "pii_redact"],
            "level":     _LOG_LEVEL,
        },

        # logs/YYYY-MM-DD/debug.log
        "file_debug": {
            "()": "optimizer.logger.DailyLevelFileHandler",
            "log_dir": _LOG_DIR,
            "filename": "debug.log",
            "min_level": "DEBUG",
            "formatter": "json",
            "filters": ["request_id"],
            "level": "DEBUG",
        },

        # logs/YYYY-MM-DD/info.log
        "file_info": {
            "()": "optimizer.logger.DailyLevelFileHandler",
            "log_dir": _LOG_DIR,
            "filename": "info.log",
            "min_level": "INFO",
            "formatter": "json",
            "filters": ["request_id"],
            "level": "INFO",
        },

        # logs/YYYY-MM-DD/warning.log
        "file_warning": {
            "()": "optimizer.logger.DailyLevelFileHandler",
            "log_dir": _LOG_DIR,
            "filename": "warning.log",
            "min_level": "WARNING",
            "formatter": "json",
            "filters": ["request_id"],
            "level": "WARNING",
        },

        # logs/YYYY-MM-DD/error.log
        "file_error": {
            "()": "optimizer.logger.DailyLevelFileHandler",
            "log_dir": _LOG_DIR,
            "filename": "error.log",
            "min_level": "ERROR",
            "formatter": "json",
            "filters": ["request_id"],
            "level": "ERROR",
        },
    },

    # ── Loggers ───────────────────────────────────────────────────────────────
    "loggers": {
        # All optimizer app modules — level gated by LOG_LEVEL
        "optimizer": {
            "handlers": ["console", "file_debug", "file_info", "file_warning", "file_error"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },

        # Django internal warnings / errors
        "django": {
            "handlers": ["console", "file_warning", "file_error"],
            "level": "WARNING",
            "propagate": False,
        },

        # Every 4xx / 5xx response → error.log
        "django.request": {
            "handlers": ["file_error"],
            "level": "ERROR",
            "propagate": False,
        },

        # Slow-query / DB warnings
        "django.db.backends": {
            "handlers": ["file_warning"],
            "level": "WARNING",
            "propagate": False,
        },
    },

    # Root — catch-all for third-party libs; level follows LOG_LEVEL
    "root": {
        "handlers": ["console", "file_warning"],
        "level": _LOG_LEVEL,
    },
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

# How far back each hourly fetch looks.
# 'now-2h' = a 2-hour overlap window so a delayed run never misses data.
# Duplicate snapshots are silently ignored (ignore_conflicts=True in bulk_create).
# Override via env var for one-off catch-up runs, e.g. GRAFANA_FETCH_RANGE=now-48h.
GRAFANA_FETCH_RANGE = os.environ.get("GRAFANA_FETCH_RANGE", "now-2h")

# Prometheus query resolution step.
# '5m' = one data point per 5 minutes = 12 snapshot rows per metric per server per hour.
# Use '1m' for near-real-time granularity (5x more rows); use '1h' to reduce volume.
GRAFANA_STEP = os.environ.get("GRAFANA_STEP", "5m")

# How many days to keep raw GrafanaMetricSnapshot rows before the monthly
# rollup job (rollup_grafana_metrics) purges them to save DB space.
GRAFANA_SNAPSHOT_RETENTION_DAYS = int(
    os.environ.get("GRAFANA_SNAPSHOT_RETENTION_DAYS", "90")
)

# ── Scheduled jobs via APScheduler (Django-native, no external infra) ─────────
# Scheduling is handled by APScheduler started inside OptimizerConfig.ready().
# The scheduler runs as a background thread in the same Django/Gunicorn process.
# Configuration lives in optimizer/scheduler.py.
#
# Schedules (all UTC):
#   fetch_usu_data         → every Saturday at 02:00
#   fetch_java_usu_data    → every Saturday at 02:30
#   fetch_grafana_metrics  → every hour, Monday–Friday
#   rollup_grafana_metrics → 1st of every month at 03:00
#
# To disable the scheduler (e.g. during migrations or one-off commands):
#   RUN_SCHEDULER=false python manage.py <command>

# Ensure the logs directory exists
Path(BASE_DIR / "logs").mkdir(exist_ok=True)
