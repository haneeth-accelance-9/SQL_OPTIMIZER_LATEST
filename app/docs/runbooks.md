# Runbooks

## Clear stuck sessions

Users who see "Analysis not found" or expired messages can upload a new file. To clear server-side session data:

- Expired or old `AnalysisSession` rows can be pruned with a one-off query or a custom management command (e.g. delete where `created_at` older than TTL and status completed).
- Session store is DB-backed; `python manage.py clearsessions` removes expired session rows.

## Re-run migrations

```bash
python manage.py migrate
```

Do not run migrations automatically from application startup in production; run them as a separate deployment step.

## Rotate secrets

1. Generate a new `DJANGO_SECRET_KEY` (e.g. `python -c "import secrets; print(secrets.token_urlsafe(50))"`).
2. Update the secret in your environment or secrets manager.
3. Restart the application. All existing sessions will be invalidated when SECRET_KEY changes.

## Inspect logs

- Logging is configured in `settings.LOGGING`. Optimizer logger name: `optimizer`.
- In development, level is DEBUG; in production, set INFO. Do not log PII or file contents.
- Request ID is set by `RequestIdMiddleware` and can be added to log formatters for correlation.

## Upload retention and cleanup

- Set `OPTIMIZER_UPLOAD_RETENTION_DAYS` (default 7). Run periodically:

```bash
python manage.py cleanup_uploads
```

- Dry run: `python manage.py cleanup_uploads --dry-run`

## Health and readiness

- `GET /health/` — liveness (returns 200 if app is running).
- `GET /ready/` — readiness (checks DB connectivity; returns 503 if DB is down).

Use these for load balancer and orchestrator probes.
