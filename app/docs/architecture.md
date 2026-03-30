# Architecture

## High-level flow

1. **Upload** — User uploads an Excel file (.xlsx or .xls). File is saved under `MEDIA_ROOT`, validated (magic bytes), then processed.
2. **Process** — `AnalysisService.run_analysis()` loads sheets via `ExcelProcessor`, runs rules via `rule_engine`, computes license metrics, and optionally generates an AI report. Results are stored in `AnalysisSession.result_data`; session stores only `optimizer_analysis_id`.
3. **Results / Dashboard** — User views tabbed dashboard (Rule 1, Rule 2, Global). Context is loaded from `AnalysisSession` by `analysis_id`; TTL and ownership are checked. Charts are generated on demand (or cached by analysis_id if implemented).
4. **Report** — Executive summary page shows AI or fallback report; user can export PDF/Word.
5. **Download** — Rule data and report exports are served from `result_data`; filenames include analysis ID for traceability.

## Main components


| Component                                  | Role                                                                                                                  |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| **optimizer.views**                        | HTTP handling, auth, validation; delegates business logic to services.                                                |
| **optimizer.services.analysis_service**    | Single entry: `run_analysis(file_path, file_name)`; builds full context (rule_results, license_metrics, report_text). |
| **optimizer.services.excel_processor**     | Loads Excel sheets; sheet names from settings. Returns dict with dataframes and `error` if invalid.                   |
| **optimizer.services.rule_engine**         | Runs Rule 1 (Azure PAYG) and Rule 2 (retired devices); returns counts and row lists.                                  |
| **optimizer.services.ai_report_generator** | Calls Azure OpenAI for report text; fallback template if disabled or error.                                           |
| **optimizer.models.AnalysisSession**       | Persists file_name, file_path (relative), status, user, result_data (JSON).                                           |


## Data flow

- **Session**: Only `optimizer_analysis_id` is stored in session.
- **AnalysisSession**: Stores `result_data` (rule_results, license_metrics, report_text, file_name, sheet_names_used). Used for TTL, ownership, and loading dashboard/report/download.
- **Uploaded files**: Stored under `MEDIA_ROOT` with UUID prefix; retention enforced by `cleanup_uploads` management command.

## Security

- All optimizer views (except health/ready) require login.
- File upload: magic-byte validation, filename sanitization, max size (50 MB).
- Report/rule download: whitelisted format_type and rule_id; safe Content-Disposition.
- Production: SECRET_KEY and ALLOWED_HOSTS required; secure session cookies; HSTS/SSL redirect.

