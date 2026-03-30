# Enterprise Golden Standards — Implementation Walkthrough

This document summarizes the changes made to align the SQL License Optimizer application with enterprise-level standards. It serves as a walkthrough of what was implemented and where to find it in the codebase.

---

## 1. Security

### 1.1 Secrets and Configuration


| Change                                 | Where                               | What was done                                                                                                                                                                |
| -------------------------------------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **No default secrets in production**   | `sql_license_optimizer/settings.py` | When `DJANGO_ENV=production` (or `DEBUG=False`), the app requires `DJANGO_SECRET_KEY` and `ALLOWED_HOSTS` from the environment; startup fails with a clear error if missing. |
| **Azure OpenAI from environment only** | `sql_license_optimizer/settings.py` | API endpoint, key, deployment, and version are read from env vars only; no hardcoded keys. Optional `AZURE_OPENAI_TIMEOUT` added.                                            |
| **Root settings file**                 | Project root `settings.py`          | Contains only comments directing configuration to `sql_license_optimizer.settings` and `.env`; no secrets or overrides.                                                      |


### 1.2 Authentication and Authorization


| Chang                                      | Where                                     | What was done                                                                                                                                                                 |
| ------------------------------------------ | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Login required for all optimizer flows** | `optimizer/views.py`                      | All views except `health`, `ready`, and `logout_view` are protected with `@login_required`.                                                                                   |
| **Custom login view**                      | `optimizer/views.py`, `optimizer/urls.py` | `OptimizerLoginView` uses unified `optimizer/auth.html` (Sign in \| Create account), redirects authenticated users to home.                                                     |
| **Unified auth (Sign in \| Create account)** | `optimizer/forms.py`, `templates/optimizer/auth.html` | Single auth page with Sign in and Create account tabs. Signup form: username, optional email, password + confirm; CSRF on both; no PII in logs. |
| **Signup**                                | `optimizer/urls.py`, `optimizer/views.py` | `signup/`: GET redirects to `login/?tab=signup`; POST creates user, redirects to login with success message. |
| **Login / logout URLs**                    | `optimizer/urls.py`                       | `login/` and `logout/` are wired; logout accepts both GET and POST so the “Log out” link works without a form.                                                                |
| **Session security**                       | `sql_license_optimizer/settings.py`       | `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`, `SESSION_COOKIE_AGE` set; `SESSION_COOKIE_SECURE = True` in production.                                                 |
| **Nav by auth state**                      | `templates/base.html`                     | “Results Dashboard”, “Executive Report”, and “Log out” are shown only when the user is authenticated; dashboard/report links also require `optimizer_analysis_id` in session. |


### 1.3 Input Validation and Hardening


| Change                              | Where                | What was done                                                                                                                                      |
| ----------------------------------- | -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| **File upload validation**          | `optimizer/views.py` | After saving the file, magic-byte validation ensures `.xlsx` (ZIP) and `.xls` (OLE) content; invalid files are deleted and the user sees an error. |
| **Filename sanitization**           | `optimizer/views.py` | `_sanitize_filename()` strips path separators and control characters; used for stored upload names and `Content-Disposition`.                      |
| **Whitelisted download parameters** | `optimizer/views.py` | `report_download` and `download_rule_data` allow only `format_type` in `{pdf, docx}` and `rule_id` in `{rule1, rule2}`; others get 400.            |
| **Safe Content-Disposition**        | `optimizer/views.py` | `_safe_content_disposition()` builds attachment headers using the sanitized filename only.                                                         |
| **CSRF on upload**                  | `optimizer/views.py` | The upload view is wrapped with `@csrf_protect`; forms use `{% csrf_token %}`.                                                                     |


### 1.4 Security Headers and Debug


| Change                  | Where                               | What was done                                                                                                                                                              |
| ----------------------- | ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Security headers**    | `sql_license_optimizer/settings.py` | `SECURE_BROWSER_XSS_FILTER`, `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS = "DENY"`. In production: `SECURE_SSL_REDIRECT`, HSTS (seconds, include subdomains, preload). |
| **DEBUG in production** | `sql_license_optimizer/settings.py` | `DEBUG` is driven by `DJANGO_DEBUG` (default `True` in dev); in production it must be set to `False` via env.                                                              |


---

## 2. Configuration and Environment


| Change                                  | Where                                                                                                    | What was done                                                                                                                                                                                   |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Single source for Excel sheet names** | `optimizer/services/analysis_service.py` (`get_sheet_config()`), `optimizer/services/excel_processor.py` | Sheet names come from Django settings (`EXCEL_SHEET_*`); `ExcelProcessor` receives them from the caller or reads from settings. Duplicate module-level constants in the processor were removed. |
| **Feature flags**                       | `sql_license_optimizer/settings.py`                                                                      | `OPTIMIZER_AI_REPORT_ENABLED`, `OPTIMIZER_CHARTS_ENABLED` (env-driven, default `True`). Used in the analysis service and dashboard view to enable/disable AI report and charts.                 |
| **TTL and retention settings**          | `sql_license_optimizer/settings.py`                                                                      | `OPTIMIZER_ANALYSIS_TTL_SECONDS` (default 24h), `OPTIMIZER_UPLOAD_RETENTION_DAYS` (default 7).                                                                                                  |
| **.env.example**                        | `.env.example`                                                                                           | Documents required and optional env vars (secret key, hosts, Azure OpenAI, sheet names, TTL, retention) without real secrets.                                                                   |


---

## 3. Session and State Management


| Change                              | Where                 | What was done                                                                                                                                                                                                  |
| ----------------------------------- | --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **AnalysisSession model extended**  | `optimizer/models.py` | Added `user` (ForeignKey to User), `result_data` (JSONField). Migration `0002_analysissession_result_user` created and applied.                                                                                |
| **Session stores only analysis ID** | `optimizer/views.py`  | After a successful run, the session stores `optimizer_analysis_id`; legacy keys (`optimizer_results`, `optimizer_file_path`, `optimizer_file_name`) are cleared.                                               |
| **Results loaded from DB**          | `optimizer/views.py`  | `_get_analysis_context(request)` loads the `AnalysisSession` by `optimizer_analysis_id`, checks ownership (user), and TTL; returns `result_data` or redirects with a message.                                  |
| **Result payload persisted in DB**  | `optimizer/views.py`  | On successful analysis, the full context (rule_results, license_metrics, report_text, etc.) is converted to JSON-serializable form via `_make_json_serializable()` and saved in `AnalysisSession.result_data`. |
| **JSON serialization for SQLite**   | `optimizer/views.py`  | `_make_json_serializable()` recursively converts numpy/pandas types (scalars, arrays, NA, Timestamp) to native Python so `result_data` satisfies SQLite’s `JSON_VALID` constraint.                             |
| **TTL enforced on load**            | `optimizer/views.py`  | If `OPTIMIZER_ANALYSIS_TTL_SECONDS` > 0 and the analysis is older than that, the user is redirected to home with an “analysis expired” message.                                                                |


---

## 4. Error Handling and User Feedback


| Change                                | Where                                                                       | What was done                                                                                                                                                                                                   |
| ------------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Django messages for upload errors** | `optimizer/views.py`                                                        | Upload validation and analysis failures call `messages.error()` (and optionally `messages.info()` for expiry); templates can show these in the UI.                                                              |
| **Structured errors from analysis**   | `optimizer/services/analysis_service.py`                                    | `run_analysis()` catches rule and metrics exceptions, logs them, and returns `{success: False, error: "..."}` instead of raising; the view shows the error and does not persist a failed analysis as completed. |
| **Fallback report message in UI**     | `optimizer/services/analysis_service.py`, `templates/optimizer/report.html` | When the AI report is not used, context includes `report_used_fallback = True`; the report template shows a short notice that the report was generated without AI.                                              |
| **Missing or expired analysis**       | `optimizer/views.py`                                                        | When analysis is missing, not owned, or expired, the user is redirected to home with an informational message instead of a 500 or raw 404.                                                                      |


---

## 5. Logging and Observability


| Change                            | Where                                                          | What was done                                                                                                                                                        |
| --------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Request ID middleware**         | `optimizer/middleware.py`, `sql_license_optimizer/settings.py` | `RequestIdMiddleware` sets `request.request_id` (short UUID) and adds `X-Request-ID` to the response for correlation in logs and support.                            |
| **Structured logging**            | `sql_license_optimizer/settings.py`                            | Optimizer logger level is DEBUG in dev and INFO when not DEBUG; no PII or file content is logged.                                                                    |
| **Audit-style log on completion** | `optimizer/views.py`                                           | After a successful analysis, a log line records `analysis_id`, `user_id`, and `request_id`.                                                                          |
| **Health and ready endpoints**    | `optimizer/views.py`, `optimizer/urls.py`                      | `GET /health/` returns 200 "ok" (liveness). `GET /ready/` checks DB connectivity and returns 200 "ready" or 503 "not ready" for load balancer / orchestrator probes. |


---

## 6. Code Structure and Maintainability


| Change                         | Where                                    | What was done                                                                                                                                                                                         |
| ------------------------------ | ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Analysis service**           | `optimizer/services/analysis_service.py` | `run_analysis(file_path, file_name)` runs the full pipeline (Excel load, rules, metrics, AI or fallback report) and returns `{success, error, context}`. Views no longer contain this business logic. |
| **Presentation helper**        | `optimizer/services/analysis_service.py` | `build_dashboard_context(context, request_id)` builds template context with flat integers (`azure_payg_count`, `retired_count`, `total_demand_quantity`) and optional `request_id`.                   |
| **Sheet config centralised**   | `optimizer/services/analysis_service.py` | `get_sheet_config()` returns the four sheet names from settings; used by the analysis service and by the Excel processor when no names are passed.                                                    |
| **Views delegate to services** | `optimizer/views.py`                     | Upload calls `run_analysis()` and persists the result to `AnalysisSession`; results/report use `_get_analysis_context()` and `build_dashboard_context()` where appropriate.                           |


---

## 7. Data and File Handling


| Change                                   | Where                                                                  | What was done                                                                                                                                                                     |
| ---------------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Upload retention and cleanup**         | `optimizer/management/commands/cleanup_uploads.py`, `docs/runbooks.md` | Management command `cleanup_uploads` deletes files in `MEDIA_ROOT` older than `OPTIMIZER_UPLOAD_RETENTION_DAYS`; `--dry-run` lists what would be deleted. Documented in runbooks. |
| **Export filenames include analysis ID** | `optimizer/views.py`                                                   | Report download uses names like `sql_license_optimization_report_{analysis_id}.pdf`; rule data export appends analysis ID to the filename when available for traceability.        |
| **No server path in session**            | `optimizer/views.py`, `optimizer/models.py`                            | Only the analysis ID is stored in session; `AnalysisSession.file_path` stores a relative/basename reference, not an absolute path.                                                |


---

## 8. API and Integration (Azure OpenAI)


| Change                    | Where                                                                            | What was done                                                                                                 |
| ------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **Reused Azure client**   | `optimizer/services/ai_report_generator.py`                                      | A module-level cached client is built once via `_get_client()` and reused for all report generation requests. |
| **Timeout from settings** | `optimizer/services/ai_report_generator.py`, `sql_license_optimizer/settings.py` | `AZURE_OPENAI_TIMEOUT` (default 60) is read from settings and passed into the chat completion call.           |


---

## 9. Documentation


| Change                   | Where                             | What was done                                                                                                                                                             |
| ------------------------ | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **README**               | `README.md`                       | Project purpose, features, prerequisites, install, env vars summary, run (dev/prod), test, deploy, and reference to configuration docs.                                   |
| **Architecture**         | `docs/architecture.md`            | High-level flow (upload → process → session → results/report), main components, data flow, and security notes.                                                            |
| **Runbooks**             | `docs/runbooks.md`                | How to clear stuck sessions, re-run migrations, rotate secrets, inspect logs, run upload cleanup, and use health/ready.                                                   |
| **Configuration**        | `docs/configuration.md`           | All environment variables (required in production, optional, sheet names, Azure OpenAI) with short descriptions and defaults.                                             |
| **Enterprise checklist** | `docs/ENTERPRISE_IMPROVEMENTS.md` | Summary checklist updated to reflect implemented items (security, config, session, errors, logging, tests, code structure, data, API, deploy, docs, audit, dependencies). |


---

## 10. Deployment and Dependencies


| Change                       | Where                  | What was done                                                                                                                                                   |
| ---------------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Dockerfile**               | `Dockerfile`           | Multi-stage build; non-root user `app`; gunicorn with bind and workers; document that migrations and static/media should be handled in the deployment pipeline. |
| **Gunicorn in requirements** | `requirements.txt`     | Added `gunicorn` for production WSGI serving.                                                                                                                   |
| **Python version**           | `pyproject.toml`       | `requires-python = ">=3.10"` for the project.                                                                                                                   |
| **Dev/test requirements**    | `requirements-dev.txt` | Includes pytest and pytest-django; references main `requirements.txt`.                                                                                          |


---

## 11. Testing


| Change                            | Where                                      | What was done                                                                                                                        |
| --------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Unit tests (analysis service)** | `optimizer/tests/test_analysis_service.py` | Tests for `get_sheet_config()` (four keys, string values) and `build_dashboard_context()` (flat integers, handling of missing keys). |
| **View tests**                    | `optimizer/tests/test_views.py`            | Tests for `GET /health/` (200), `GET /ready/` (200 when DB is up), and anonymous `GET /` redirecting to login.                       |
| **Pytest configuration**          | `pytest.ini`                               | `DJANGO_SETTINGS_MODULE` and pytest options so `pytest` runs the Django app tests.                                                   |


---

## 12. Fixes Applied During Implementation


| Issue                                                    | Fix                                                                                                                                                                                                                        |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **SQLite JSON_VALID failure on `result_data`**           | Numpy/pandas types in the context were not valid JSON. Introduced `_make_json_serializable()` to recursively convert scalars, arrays, NA, and timestamps to native Python before saving to `AnalysisSession.result_data`.  |
| **ValueError when converting arrays (pd.isna on array)** | `pd.isna(obj)` on a numpy array returns an array of booleans, causing “truth value of an array is ambiguous”. Conversion logic was reordered so array-like values are handled (via iteration) before any `pd.isna()` call. |
| **405 Method Not Allowed on GET /logout/**               | Django’s `LogoutView` allows only POST. Replaced it with a custom `logout_view` that accepts both GET and POST, calls `auth_logout(request)`, and redirects to login so the “Log out” link works without a form.           |


---

## Quick Reference: Key Files Touched


| Area              | Main files                                                                                                                                                                |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Settings & config | `sql_license_optimizer/settings.py`, `.env.example`                                                                                                                       |
| Auth & session    | `optimizer/views.py`, `optimizer/urls.py`, `templates/base.html`, `templates/optimizer/login.html`                                                                        |
| Persistence & TTL | `optimizer/models.py`, `optimizer/views.py` (`_get_analysis_context`, `_make_json_serializable`), migrations                                                              |
| Business logic    | `optimizer/services/analysis_service.py`, `optimizer/services/excel_processor.py`                                                                                         |
| Logging & health  | `optimizer/middleware.py`, `optimizer/views.py` (health, ready, audit log)                                                                                                |
| Cleanup           | `optimizer/management/commands/cleanup_uploads.py`                                                                                                                        |
| Docs              | `README.md`, `docs/architecture.md`, `docs/runbooks.md`, `docs/configuration.md`, `docs/ENTERPRISE_IMPROVEMENTS.md`, `docs/ENTERPRISE_CHANGES_WALKTHROUGH.md` (this file) |
| Deploy & test     | `Dockerfile`, `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `optimizer/tests/`, `pytest.ini`                                                              |


---

*This walkthrough reflects the state of the implementation as of the enterprise golden-standards pass. For the full list of recommendations (including optional or future work), see `docs/ENTERPRISE_IMPROVEMENTS.md`.*