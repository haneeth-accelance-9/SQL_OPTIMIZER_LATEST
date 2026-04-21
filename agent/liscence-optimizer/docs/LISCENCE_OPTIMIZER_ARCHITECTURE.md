# Liscence Optimizer Agent — Architecture, Data Flow, and Integration Guide

This document explains **how the `liscence-optimizer` agent is structured**, **how it is intended to run**, **what inputs it expects**, **how data is processed**, and **what outputs look like**—with emphasis on the executive-summary + rules workflow added for this project.

> Note: In this repository copy, the agent lives at:
>
> `agent_vm/agent/liscence-optimizer/`

---

## High-level purpose

The agent is configured (via `configs/config.yaml`) as a **phased orchestration** agent whose goal is to:

1. **Evaluate optimization / licensing rules** against normalized inventory/VM records (YAML-driven rules in `configs/rules.base.yaml`).
2. **Generate an executive summary scaffold** that combines:
   - upstream **strategy results** (from your backend / upstream pipelines), and
   - optional **rules evaluation JSON** (from step 1).

The “LLM writes polished prose” part is expected to happen **inside the normal agent execution** (SDK + model), while the **rules evaluation** is designed to be **deterministic** (Python), driven by YAML.

---

## Runtime entrypoints (how the process starts)

### CLI / local dev

The AgenticAI CLI runs the entry script configured in `.agenticai.yaml`:

- **Entry**: `src/a2a_server.py`
- **Config**: `configs/config.yaml` (default)

`.agenticai.yaml` documents the canonical paths:

```yaml
paths:
  entry: "src/a2a_server.py"
  tools: "src/tools"
  configs: "configs"
  default_config: "configs/config.yaml"
```

### What `src/a2a_server.py` does

`src/a2a_server.py` starts the SDK A2A server:

- constructs `A2AFactory()`
- loads configuration via the SDK `ConfigLoader` (from `CONFIG_PATH` or defaults)
- runs the server

It also imports `src/tools/__init__.py` as `tools` so **tool modules register** (`@tool_registry.register(...)` side effects).

---

## Configuration: what controls behavior

### `configs/config.yaml` (primary)

This file defines:

- **LLM gateway** (`llm.config.*`)
- **Memory** (`memory.*`) — Cosmos-backed session history in this template
- **Observability** (`observability.*`)
- **Executor** (`executor.*`) — **phased orchestration**, tools list, system prompt, and per-phase instructions

#### Phased orchestration flow (as configured)

The executor is:

- `executor.type: phased_orchestration`

Phases (simplified):

```mermaid
flowchart TD
  A[Incoming A2A request] --> B[Phase 1: Analysis]
  B --> C[Tool: evaluate_optimization_rules]
  C --> D[Tool: store_phase_result]
  D --> E[Phase 2: Report Generation]
  E --> F[Tool: get_phase_result(phase_number=1)]
  F --> G[Tool: report_generator]
  G --> H[Optional: export_report]
  H --> I[Final assistant response / tool outputs]
```

**Important integration note:** the phased instructions describe *how the agent should behave*, but your **backend still supplies the actual payload** (message text, attachments, structured JSON embedded in the prompt, etc.—depending on how you call A2A).

### `configs/rules.base.yaml` (business rules as data)

This YAML defines:

- `defaults.column_names`: logical field → physical column mapping (snake_case columns in records)
- `rules`: a list of rule objects (`filter` vs `recommendation`)

The intent is: **add new rules by extending this list**, and only add Python when a rule needs a complex “engine”.

### `configs/config.v1.1.0.yaml`

Alternate pinned config version shipped with the template (useful if you maintain multiple config variants).

### Environment variables (`.env.development`)

The SDK loader substitutes `${VAR}` placeholders in YAML. If a placeholder has **no default** (`${VAR}` instead of `${VAR:default}`), startup fails when the variable is missing.

You already saw a real example:

- `llm.config.endpoint: "${AZURE_OPENAI_ENDPOINT}"` requires `AZURE_OPENAI_ENDPOINT`

For local bootstrapping, either:

- export the required variables in your shell, or
- add safe defaults in YAML (dev-only), or
- ensure `.env.development` is loaded for your CLI mode

---

## Request and tool payload formats

How you **shape the user message** and **tool arguments** matters as much as the business data. The executor runs tools through **JSON-RPC-style** calls: very large or badly escaped strings inside a tool parameter can make the **whole call invalid** before Python runs (for example `Unterminated string` errors). Follow the patterns below so Phase 1 → Phase 2 does not break.

### 1) Put machine-readable JSON in the **user message** using markers

For **Postman / A2A** clients that send one text payload, wrap payloads so the model can extract them reliably:

| Block | Markers | Content must be |
|------|---------|-------------------|
| VM / inventory rows | `RECORDS_JSON_START` … `RECORDS_JSON_END` | A single valid **JSON array** (`[ ... ]`) of objects. **Only** JSON between the markers—no commentary, no markdown fences, no trailing commas, no `//` comments. |
| Upstream strategy output | `STRATEGY_RESULTS_JSON_START` … `STRATEGY_RESULTS_JSON_END` | A single valid **JSON object** (`{ ... }`). Same strictness as above. |

Use **double-quoted keys and strings** (standard JSON). If a value needs quotes inside a string, escape them as `\"` inside the JSON text.

### 2) Tool parameters are **strings of JSON**, not “raw” objects

The tools expect **string** arguments whose **text** is JSON:

- `evaluate_optimization_rules(records_json=...)` — `records_json` is one string whose content is exactly the JSON array text (the same text you placed between the records markers).
- `report_generator(strategy_results_json=...)` — `strategy_results_json` is one string whose content is exactly the JSON object text (the same text you placed between the strategy markers).

The model (or your client) must not substitute Python dict literals or YAML where the tool schema says `str`.

### 3) Phase handoff: store structured Phase 1 output, avoid re-pasting it in Phase 2

**Phase 1 (Analysis):** after `evaluate_optimization_rules`, parse the tool’s returned JSON and persist it with:

- `store_phase_result(phase_number=1, phase_name="Analysis Phase", result_data=<dict>)`  
  where `<dict>` is the **parsed object** (`success`, `evaluation`, `summary`, …), not a truncated copy-paste.

**Phase 2 (Report):** orchestration storage is keyed by **integer** phase number:

- Use `get_phase_result(phase_number=1)` — **not** a phase name string (that is not a valid SDK overload).

**`report_generator` and `rules_evaluation_json`:** prefer **omitting** `rules_evaluation_json` or passing an **empty** string so the tool can load rule evaluation from `get_phase_result(1)` when the session still has Phase 1 data. That avoids embedding a **full** Phase 1 JSON string inside another JSON tool call, which is the main source of truncation and escaping failures.

If you must pass `rules_evaluation_json`, keep it **small** (for example only a `summary` subtree) and ensure it is **valid JSON** as a single string.

### 4) Column names and numeric conventions

Records must use the **physical** column names implied by `defaults.column_names` in `configs/rules.base.yaml`. CPU/memory utilization fields used by rules are expected as **fractions** (e.g. `0.15` = 15%); normalize percents before calling `evaluate_optimization_rules` (see [Percent / fraction convention](#percent--fraction-convention-critical)).

### 5) What commonly disrupts the flow

- Pasting **huge** stringified JSON into `rules_evaluation_json` in one tool call (escaping breaks the outer JSON).
- **Invalid JSON** inside marker blocks (the model then forwards broken text into tools).
- **Markdown code fences** (` ```json `) **inside** the marker region (markers should wrap bare JSON only).
- Calling `get_phase_result` with a **string** phase name instead of `phase_number=1`.

---

## Tools: where “work” happens in this repo

Tools live in `src/tools/` and are imported in `src/tools/__init__.py` to ensure registration.

### Tool registration pattern

This repo uses the SDK decorator:

- `@tool_registry.register(...)`

Example reference tool: `src/tools/export_report_tool.py`.

### Tools shipped / relevant to this workflow

#### 1) `evaluate_optimization_rules` (`src/tools/evaluate_optimization_rules.py`)

**Purpose:** evaluate `configs/rules.base.yaml` against a list of normalized records.

**Input (tool parameters):**

- `records_json` (**string** containing JSON): must be a JSON **array** of objects
- `rules_path` (optional string): override path to a rules YAML file
- `override_rules_yaml` (optional string): YAML snippet merged on top of base rules
- `max_examples_per_rule` (int): caps examples per rule in the compact summary

**Output (tool return value):**

A JSON **string** (not a Python dict) of the form:

```json
{
  "success": true,
  "evaluation": { "...": "..." },
  "summary": { "...": "..." }
}
```

**What `evaluation` contains (conceptually):**

- `rules_version`
- `matched_counts`: counts per `rule.id`
- `per_rule`: detailed per-record outcomes keyed by rule id

**What `summary` contains:**

A reduced structure intended for prompts / reporting:

- per-rule `matched_count`
- small `examples` list (bounded by `max_examples_per_rule`)

#### 2) `report_generator` (`src/tools/report_generator.py`)

**Purpose:** build a markdown “scaffold” for an executive summary and embed grounding JSON for the model.

**Prompt template file:**

- `prompts/executive_summary.base.md`

**Input (tool parameters):**

- `usecase_id` (string)
- `strategy_results_json` (**string** containing JSON): must be a JSON **object** (dict)
- `rules_evaluation_json` (optional string containing JSON): small override only if needed. **Recommended for phased runs:** omit it or leave it empty so the tool loads Phase 1 evaluation from `get_phase_result(1)` (see [Request and tool payload formats](#request-and-tool-payload-formats)). If you pass it, keep the payload valid JSON and modest in size.
- `notes` (optional string)
- `prompt_path` (optional string): override prompt template path

**Output (tool return value):**

JSON string:

```json
{
  "success": true,
  "usecase_id": "...",
  "markdown": "# ... markdown ...",
  "prompt_path": "C:\\\\...\\\\prompts\\\\executive_summary.base.md"
}
```

**What the markdown contains (by design):**

- A human-facing scaffold (`## Executive summary`)
- The **instruction template** text (from `executive_summary.base.md`)
- A fenced JSON block (`## Grounding JSON`) that includes:
  - `usecase_id`
  - `strategy_results`
  - `rules_evaluation`
  - `notes`

This makes the “dynamic prompt context” explicit and traceable.

#### 3) `export_report` (`src/tools/export_report_tool.py`)

**Purpose:** save markdown content to a `.md` file in the process working directory.

Typical usage pattern:

1. `report_generator` → parse JSON → take `markdown`
2. `export_report(content=markdown, filename="executive_summary.md", title="...")`

#### SDK built-in tools (enabled in `configs/config.yaml`)

These are not defined in this repo, but are enabled for phased workflows:

- dataframe ingestion / SQL helpers (`upload_dataframe`, `execute_sql_query`, etc.)
- phase communication (`store_phase_result`, `get_phase_result`, ...)

They matter because your **backend integration** might choose to attach a CSV instead of sending JSON rows directly.

---

## Rules engine (deterministic processing)

### Files

- `src/tools/rules_loader.py`
  - loads `configs/rules.base.yaml`
  - optional merge with `override_rules_yaml`
- `src/tools/rules_evaluator.py`
  - evaluates `when:` expressions (`all`, `any`, ops)
  - runs recommendation `engine:` functions for UC 3.x style policies

### Rule types

#### `type: filter`

Evaluates `when:` against each record → `{ matched: true/false, reasons: [...] }`

#### `type: recommendation`

Three-stage evaluation:

1. `applies_when` (gate)
2. branch selection via `branches[].when`
3. `candidate_when` (optimization candidacy)
4. `recommend.engine` dispatches to a Python engine function (versioned)

### Column mapping contract

Rules refer to logical columns (`hosting_zone`, `env`, ...), which are mapped to physical columns via:

- `defaults.column_names` in `configs/rules.base.yaml`

Example:

- logical `env` → physical `environment`

**Backend responsibility:** either:

- produce records already using physical column names, or
- ensure mapped physical columns exist for all required logical fields

### Percent / fraction convention (critical)

The rules YAML comments and engines assume **fractions** for CPU/memory utilization fields:

- `0.15` means 15%

If your upstream data is `15` meaning 15%, you must normalize before evaluation.

---

## Strategy results contract (what your backend should send)

There are **two complementary** inputs in this design:

### A) `records_json` (for deterministic rules)

A JSON array of objects (rows). Minimal example shape:

```json
[
  {
    "environment": "PROD",
    "u_hosting_zone": "Public Cloud",
    "inventory_status_standard": "BYOL",
    "no_license_required_product": 0,
    "install_status": "active",
    "avg_cpu_12m": 0.12,
    "peak_cpu_12m": 0.55,
    "current_vcpu": 8,
    "avg_free_mem_12m": 0.42,
    "min_free_mem_12m": 0.25,
    "current_ram_gib": 32
  }
]
```

**Important:** keys must match the physical columns implied by `defaults.column_names`.

### B) `strategy_results_json` (for executive summary narrative)

A JSON object (dict) summarizing each upstream “strategy” output. This is intentionally flexible, but should be **stable** across releases.

Example:

```json
{
  "uc_1_1_azure_byol_to_payg": {
    "row_count": 123,
    "matched_count": 45,
    "top_examples": []
  },
  "uc_1_2_retired_device_installs": {
    "row_count": 999,
    "matched_count": 12,
    "top_examples": []
  },
  "upstream_metadata": {
    "generated_at": "2026-04-17T12:34:56Z",
    "source": "backend-job-123"
  }
}
```

**Guideline:** keep `strategy_results` as **aggregates + small examples**, not full datasets.

---

## Output: what the backend receives

At the A2A protocol level, the “output” is the **agent response** produced by the SDK server, which includes:

- assistant text (reasoning + narrative)
- tool call results (JSON strings)

For your integration, the most stable artifacts are:

1) JSON output from `evaluate_optimization_rules`
2) JSON output from `report_generator`, especially:
   - `markdown` (string)
   - `prompt_path` (for traceability)

If you need a downloadable artifact, also capture `export_report` JSON output (`path`, `filename`).

---

## Packaging notes (what gets shipped with the agent)

`pyproject.toml` includes package data globs for:

- `configs/*.yaml`
- `prompts/*.md`

This helps ensure `rules.base.yaml` and `executive_summary.base.md` are present in packaged environments (depending on your build pipeline).

---

## “Where is the prompt?”

There are **two prompt layers** in this design:

1) **Orchestrator system prompt + phased instructions** in `configs/config.yaml`
   - controls tool usage, reasoning format, and phase goals

2) **Executive summary instruction template** in:
   - `prompts/executive_summary.base.md`

`report_generator` reads (2) and embeds dynamic JSON into markdown.

---

## Operational checklist (integration-minded)

1. Ensure required env vars exist for config substitution (Azure OpenAI at minimum).
2. Follow [Request and tool payload formats](#request-and-tool-payload-formats) for marker blocks, tool string arguments, and Phase 1/2 handoff so JSON-RPC tool calls stay valid.
3. Decide your backend payload strategy:
   - attach CSV + let agent build `records_json`, **or**
   - send `records_json` directly inside the user message (still a string the model must pass to tools correctly), **or**
   - precompute strategy outputs server-side and only send `strategy_results_json` for narrative summarization
4. Keep `strategy_results` stable and version it (`schema_version` field recommended).
5. Keep rules in YAML; add engines in `rules_evaluator.py` when policies become branchy.

---

## File map (this repo copy)

### Top-level

- `README.md`: template documentation + setup notes
- `pyproject.toml`: dependencies + packaging metadata
- `Dockerfile`, `.dockerignore`: container build
- `.agenticai.yaml`: CLI metadata (entrypoint/config paths)
- `.env.example`, `.env.development` (if used): environment variables

### Runtime / server

- `src/a2a_server.py`: starts A2A server; imports tools package for registration side effects

### Tools

- `src/tools/__init__.py`: imports tools to register them
- `src/tools/example_tool.py`: template example tool
- `src/tools/read_file_tool.py`: reads attached files from session context
- `src/tools/export_report_tool.py`: writes markdown to disk
- `src/tools/rules_loader.py`: YAML load/merge
- `src/tools/rules_evaluator.py`: deterministic evaluation + engines
- `src/tools/evaluate_optimization_rules.py`: tool wrapper returning JSON string
- `src/tools/report_generator.py`: tool wrapper returning JSON string + markdown scaffold

### Rules + prompts

- `configs/rules.base.yaml`: rule definitions + column mapping
- `prompts/executive_summary.base.md`: executive summary instruction template

### Infrastructure / ops (template)

- `terraform/**`: deployment modules and environments
- `cli/**`: optional CLI commands for infra/docker helpers

---

## Known sharp edges / decisions to make explicitly

1. **Percent representation** (fractions vs 0–100) must be consistent across backend + rules YAML.
2. **Environment classification** (`environment` values) must align with PROD vs non-PROD branching.
3. **Tool arguments are strings** containing JSON — your integration should standardize escaping / embedding.
4. **Large datasets** should not be passed through the LLM; prefer aggregates + samples.

---

## Suggested “schema_versioned” request wrapper (recommended)

Even though the SDK transport is A2A, your *application payload* should be explicit:

```json
{
  "schema_version": 1,
  "usecase_id": "license-optimizer",
  "records": [ { "...": "..." } ],
  "strategy_results": { "...": "..." },
  "notes": "Optional context for the report"
}
```

You can embed this JSON as the user message body (or attach as a `.json` file and read via `read_file_content`).
