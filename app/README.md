# SQL License Optimizer

Enterprise-oriented Django application for analyzing SQL Server license demand and optimization opportunities from Excel uploads. Supports Azure PAYG migration candidates, retired-device detection, and AI-generated executive reports.

## Features

- **Upload & process** Excel workbooks (installations, demand, prices, optimization sheets)
- **Rule engine**: Azure PAYG candidates (Rule 1), retired devices with installations (Rule 2)
- **Dashboard** with KPIs and optional charts (matplotlib)
- **AI report** via Azure OpenAI (optional; fallback template if disabled or unavailable)
- **Export** PDF/Word reports and Rule 1/Rule 2 data as Excel
- **Auth**: login required for all optimizer views
- **Persistence**: results stored in DB (AnalysisSession) with TTL; session holds only analysis ID
- **Health/ready** endpoints for load balancers

## Prerequisites

- Python 3.10+
- pip

## Install

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set DJANGO_SECRET_KEY, optional Azure OpenAI and sheet names
python manage.py migrate
python manage.py createsuperuser
```

## Environment variables

See [docs/configuration.md](docs/configuration.md) and `.env.example`. Key options:

| Variable | Description |
|----------|-------------|
| `DJANGO_SECRET_KEY` | Required in production |
| `DJANGO_DEBUG` | Set to `false` in production |
| `DJANGO_ENV` | Set to `production` for strict settings |
| `ALLOWED_HOSTS` | Comma-separated hosts in production |
| `AZURE_OPENAI_*` | Endpoint, API key, deployment, version for AI report |
| `OPTIMIZER_ANALYSIS_TTL_SECONDS` | Result TTL (default 86400) |
| `OPTIMIZER_UPLOAD_RETENTION_DAYS` | Delete uploads older than N days (default 7) |

## Run

**Development**

```bash
python manage.py runserver
```

**Production**

Use gunicorn (or uWSGI) behind a reverse proxy. See [docs/runbooks.md](docs/runbooks.md).

```bash
gunicorn sql_license_optimizer.wsgi:application --bind 0.0.0.0:8000
```

## Test

```bash
pip install pytest pytest-django
pytest
```

## Architecture

See [docs/ARCHITECTURE_DIAGRAMS.md](docs/ARCHITECTURE_DIAGRAMS.md) for current and target architecture diagrams (Mermaid). See [docs/architecture.md](docs/architecture.md) for a short narrative.

## Deploy

- Use Docker: see `Dockerfile`. Do not run as root.
- Run migrations as a separate step; do not run them from app startup in production.
- Serve static/media via reverse proxy or CDN; run `collectstatic` before deploy.

## License

See repository license.
