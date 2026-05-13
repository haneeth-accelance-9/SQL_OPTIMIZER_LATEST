# Performance Baseline

**Version:** 1.0.0 (draft — [TBC] fields pending first instrumented run)
**Last Updated:** 2026-05-13
**Status:** Draft

---

## Change History

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0.0 (draft) | 2026-05-13 | Initial commit — [TBC] fields pending first instrumented run |

---

## Pipeline Overview

Each agent run triggered via `POST /api/agent-runs/trigger/` passes through four measurable phases:

| Phase | What happens | Code location |
|---|---|---|
| Data load | USU installations queried from DB via `_build_installations_df()` | `db_analysis_service.py` |
| Rule evaluation | PAYG, Retired Devices, Rightsizing rules applied via `compute_db_metrics()` | `db_analysis_service.py` |
| LLM call | Agent `/generate-report` called — includes rules engine + Azure OpenAI request | `ai_report_generator.py` → `a2a_server.py` |
| Total | End-to-end wall-clock duration | `ai_report_generator.py` |

---

## Phase Timing Baseline (P50 / P95)

> **[TBC]** = to be filled after first instrumented run.
> Run `python manage.py update_performance_baseline --days 30` to generate updated values.

| Phase | P50 (s) | P95 (s) | Alert Threshold | Notes |
|---|---|---|---|---|
| Data load | [TBC] | [TBC] | > 10s | USU + demand + prices DB queries |
| Rule evaluation | [TBC] | [TBC] | > 5s | In-memory rule processing |
| LLM call | [TBC] | [TBC] | > 60s | Agent + Azure OpenAI via APIM |
| Total | [TBC] | [TBC] | > 180s | End-to-end |

---

## Alert Thresholds

| Phase | Warning | Critical | Action |
|---|---|---|---|
| Data load | > 5s | > 10s | Check DB query plans; USU table indexes |
| Rule evaluation | > 3s | > 5s | Profile rule engine; check DataFrame size |
| LLM call | > 45s | > 60s | Check APIM gateway; Azure OpenAI quota |
| Total | > 120s | > 180s | Escalate to Saksham; check all phases |

---

## Where Timings Are Stored

Every completed `AgentRun` record stores phase timings in `input_file_versions`:

```json
{
  "prompt_version": "1.0.0",
  "phase_timings": {
    "data_load_sec": 1.4,
    "rule_eval_sec": 0.8,
    "llm_call_sec": 12.3,
    "total_sec": 14.5
  }
}
```

Query via Django shell:
```python
from optimizer.models import AgentRun
AgentRun.objects.filter(status='completed').last().input_file_versions
```

---

## Monthly Update Procedure

Run on the first working day of each month:

1. Run the extraction command:
   ```
   python manage.py update_performance_baseline --days 30
   ```
2. Copy the printed Markdown table and replace the **Phase Timing Baseline** table above.
3. Bump the version (patch increment: `1.0.0` → `1.0.1`).
4. Update **Last Updated** date and add a row to **Change H`is`tory**.
5. Commit:
   ```
   git commit -m "perf-baseline: YYYY-MM update"
   ```
6. If any P95 value has increased > 20% vs the previous month, raise an alert to Saksham.

**Due:** First working day of each month.
