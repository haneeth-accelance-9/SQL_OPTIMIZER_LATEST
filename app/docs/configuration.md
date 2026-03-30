# Configuration

All configuration is via environment variables. Use `.env` in development (optional, with python-dotenv); in production use the host or container environment. Never commit secrets.

## Required (production)

| Variable | Description |
|----------|-------------|
| `DJANGO_SECRET_KEY` | Secret key for signing; generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `ALLOWED_HOSTS` | Comma-separated list of FQDNs (e.g. `app.example.com`) |

Set `DJANGO_ENV=production` and `DJANGO_DEBUG=false` in production.

## Optional (all environments)

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_DEBUG` | true | Set to false in production |
| `DJANGO_ENV` | — | Set to `production` for strict checks and secure defaults |
| `ALLOWED_HOSTS` | localhost,127.0.0.1 | Comma-separated hosts (dev) |
| `SECURE_SSL_REDIRECT` | true (prod) | Redirect HTTP to HTTPS in production |
| `OPTIMIZER_ANALYSIS_TTL_SECONDS` | 86400 | Result TTL in seconds; 0 = no expiry |
| `OPTIMIZER_UPLOAD_RETENTION_DAYS` | 7 | Delete uploads older than N days; 0 = no auto-delete |
| `OPTIMIZER_AI_REPORT_ENABLED` | true | Enable AI report generation |
| `OPTIMIZER_CHARTS_ENABLED` | true | Enable dashboard charts |

## Excel sheet names

| Variable | Default |
|----------|---------|
| `EXCEL_SHEET_INSTALLATIONS` | MVP - Data 1 - Installation |
| `EXCEL_SHEET_DEMAND` | MVP - Data 2 - Demand Results |
| `EXCEL_SHEET_PRICES` | MVP - Data 3 - Prices |
| `EXCEL_SHEET_OPTIMIZATION` | MVP - Data 4 - Optimization potential |

## Azure OpenAI (optional)

| Variable | Description |
|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_API_KEY` | API key (never commit) |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name (default gpt-4) |
| `AZURE_OPENAI_API_VERSION` | API version (default 2024-02-15-preview) |
| `AZURE_OPENAI_TIMEOUT` | Request timeout in seconds (default 60) |

If not set or on failure, the app uses a fallback template report.
