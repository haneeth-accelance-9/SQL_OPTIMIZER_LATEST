# Stress Testing Guide — SQL License Optimizer (MVP-6-ACCELANCE)

## Table of Contents
1. [Overview](#overview)
2. [Test Objectives & KPIs](#test-objectives--kpis)
3. [Test Types](#test-types)
4. [Architecture Under Test](#architecture-under-test)
5. [Test Scenarios](#test-scenarios)
6. [Performance Thresholds](#performance-thresholds)
7. [Environment Setup](#environment-setup)
8. [Running Tests](#running-tests)
9. [Monitoring & Metrics](#monitoring--metrics)
10. [Reporting](#reporting)
11. [Known Bottlenecks & Risks](#known-bottlenecks--risks)

---

## Overview

This guide covers stress, load, spike, and soak testing for the **SQL Server License Optimizer** platform — a Django web application backed by Azure PostgreSQL, Azure OpenAI, and an Agentic AI agent with Cosmos DB integration.

**Components Covered:**
| Component | Technology | Test Tool |
|---|---|---|
| Web Application | Django 4.2, Gunicorn | Locust |
| REST API / Auth | JWT + Azure AD | Locust / k6 |
| Database Layer | Azure PostgreSQL Flexible | pgbench + pytest |
| File Upload | Excel processing (openpyxl, pandas) | Locust |
| Report Generation | PDF/DOCX/XLSX (reportlab, python-docx) | Locust |
| AI Agent | Agentic AI SDK + Azure OpenAI | Custom Python |
| Rule Engine | Python rules evaluator | pytest-benchmark |
| Cosmos DB | Agent conversation memory | Custom Python |

---

## Test Objectives & KPIs

### Primary Objectives
- Validate the system can handle **50 concurrent users** with acceptable response times
- Identify the **breaking point** (max load before degradation)
- Verify **report generation** completes under 30 seconds for typical datasets
- Confirm **file uploads** (≤10 MB Excel) process within SLA
- Ensure the **AI agent** maintains throughput under concurrent requests
- Validate **multi-tenant isolation** holds under load

### Key Performance Indicators (KPIs)

| KPI | Target | Critical Limit |
|---|---|---|
| Dashboard page load (P95) | < 2 seconds | < 5 seconds |
| Authentication (login) P95 | < 1 second | < 3 seconds |
| Analysis session creation P95 | < 5 seconds | < 15 seconds |
| Excel file upload (5 MB) P95 | < 10 seconds | < 30 seconds |
| PDF report generation P95 | < 15 seconds | < 45 seconds |
| AI agent response P95 | < 20 seconds | < 60 seconds |
| DB query (complex analysis) P95 | < 3 seconds | < 10 seconds |
| Error rate (all endpoints) | < 1% | < 5% |
| Throughput (req/sec) | ≥ 20 rps | — |
| CPU (web server) under load | < 70% | < 90% |
| Memory (web server) under load | < 70% | < 85% |

---

## Test Types

### 1. Load Test
Simulate **expected peak traffic** — verify the system handles normal load with acceptable performance.

- **Users:** 25–50 concurrent
- **Ramp-up:** 5 users/minute
- **Duration:** 30 minutes steady state
- **Goal:** All KPI targets met

### 2. Stress Test
Push **beyond normal capacity** to find the breaking point.

- **Users:** Ramp from 10 → 200 concurrent
- **Ramp-up:** 10 users/minute
- **Duration:** Until error rate > 10% or response time > 3× target
- **Goal:** Identify breaking point and failure mode

### 3. Spike Test
Simulate a **sudden traffic burst** (e.g., end-of-month reporting).

- **Users:** 5 baseline → spike to 100 in 30 seconds → back to 5
- **Duration:** 10-minute baseline, 2-minute spike, 10-minute recovery
- **Goal:** System recovers within 2 minutes of spike end

### 4. Soak Test
Run at **sustained moderate load** to detect memory leaks, connection pool exhaustion, and slow degradation.

- **Users:** 20 concurrent
- **Duration:** 4 hours
- **Goal:** No performance degradation over time; no memory growth > 20%

### 5. Endurance Test (AI Agent)
Test the AI agent under **sustained concurrent requests** to detect token quota exhaustion, Cosmos DB connection limits, and memory growth.

- **Concurrent agent requests:** 5–10
- **Duration:** 1 hour
- **Goal:** Consistent response times; no rate-limit errors

---

## Architecture Under Test

```
[Users] ─→ [Load Balancer / Azure App Service]
               │
               ▼
         [Django/Gunicorn]
          /      |      \
[PostgreSQL] [Azure AD] [File Storage]
               │
               ▼
         [AI Agent Server]
          /           \
[Azure OpenAI]   [Cosmos DB]
               │
               ▼
         [Grafana / App Insights]
```

### Critical Paths to Test
1. **Auth → Dashboard → Analysis** (primary user flow)
2. **Upload Excel → Process → Generate Report** (data pipeline)
3. **Trigger AI Agent → Get Recommendations** (AI pipeline)
4. **Multi-tenant data isolation** (security + correctness under load)
5. **Scheduler jobs** (APScheduler concurrency)

---

## Test Scenarios

### Scenario 1: Standard User Journey (Load Test)

```
Step 1:  POST /login/            → JWT token
Step 2:  GET  /dashboard/        → Tenant dashboard
Step 3:  GET  /servers/          → Server list
Step 4:  POST /analysis/create/  → New analysis session
Step 5:  GET  /analysis/{id}/    → Analysis results
Step 6:  GET  /reports/          → Report list
Step 7:  POST /reports/export/   → Generate PDF report
Step 8:  GET  /logout/           → End session
```

**Concurrency:** 25 users cycling through this flow
**Think time:** 1–3 seconds between steps (realistic user behavior)

---

### Scenario 2: Heavy File Upload

```
Step 1:  POST /login/
Step 2:  POST /upload/           → Upload 5 MB Excel (CPU metrics file)
Step 3:  GET  /upload/{id}/status → Poll until complete
Step 4:  POST /analysis/from-upload/{id}/ → Trigger analysis
Step 5:  GET  /analysis/{id}/results/
```

**Concurrency:** 10 users uploading simultaneously
**File sizes:** 1 MB, 5 MB, 10 MB variants

---

### Scenario 3: Report Generation Storm

```
Step 1:  POST /login/
Step 2:  GET  /analysis/{id}/    → Existing completed analysis
Step 3:  POST /reports/export/pdf/   → PDF export
Step 4:  POST /reports/export/docx/  → DOCX export
Step 5:  POST /reports/export/xlsx/  → XLSX export
```

**Concurrency:** 15 simultaneous report generation requests
**Dataset size:** Small (50 servers), Medium (500 servers), Large (2000 servers)

---

### Scenario 4: AI Agent Load

```
Step 1:  POST /agent/chat/       → "Analyze license optimization for tenant X"
Step 2:  GET  /agent/status/{id} → Poll for completion
Step 3:  POST /agent/chat/       → "Generate detailed rightsizing report"
Step 4:  GET  /agent/history/    → Fetch conversation history (Cosmos DB)
```

**Concurrency:** 5–10 concurrent agent sessions
**Prompt sizes:** Short (~50 tokens), Medium (~200 tokens), Long (~1000 tokens)

---

### Scenario 5: Multi-Tenant Isolation Under Load

```
Tenant A users (10): Access Tenant A analysis data
Tenant B users (10): Access Tenant B analysis data
Verify:  Zero cross-tenant data leakage in all responses
Check:   Database query times remain stable per tenant
```

---

### Scenario 6: Rule Engine Stress

```
Input: Dataset with 5000 servers across 50 tenants
Action: POST /analysis/batch-rules/  → Trigger full rule evaluation
Rules: rightsizing, Azure PAYG, retired devices (all active)
Measure: Total processing time, memory usage, CPU per rule
```

---

### Scenario 7: Spike Recovery

```
Phase 1 (5 min):   5 users — baseline
Phase 2 (2 min):   Spike to 100 users instantly
Phase 3 (10 min):  Hold 100 users
Phase 4 (2 min):   Drop back to 5 users
Phase 5 (5 min):   Measure recovery — response times should normalize
```

---

## Performance Thresholds

### Response Time Thresholds (HTTP)

| Endpoint | P50 | P90 | P95 | P99 | FAIL |
|---|---|---|---|---|---|
| `GET /dashboard/` | 500ms | 1.5s | 2s | 4s | >5s |
| `POST /login/` | 200ms | 800ms | 1s | 2s | >3s |
| `GET /servers/` | 300ms | 1s | 2s | 3s | >5s |
| `POST /analysis/create/` | 2s | 4s | 5s | 10s | >15s |
| `POST /upload/` (5MB) | 5s | 8s | 10s | 20s | >30s |
| `POST /reports/export/pdf/` | 8s | 12s | 15s | 30s | >45s |
| `POST /agent/chat/` | 10s | 15s | 20s | 40s | >60s |

### Resource Utilization Thresholds

| Resource | Warning | Critical |
|---|---|---|
| Web server CPU | 70% | 90% |
| Web server memory | 70% | 85% |
| PostgreSQL connections | 80% of pool | 95% of pool |
| PostgreSQL CPU | 60% | 80% |
| Cosmos DB RU consumption | 70% of provisioned | 90% |
| Azure OpenAI TPM | 70% of quota | 90% of quota |
| Gunicorn worker queue depth | 5 | 20 |

---

## Environment Setup

### Prerequisites

```powershell
# Install Locust
pip install locust faker

# Install k6 (Windows)
winget install k6

# Install pgbench (comes with PostgreSQL)
# Ensure psql is available in PATH

# Install pytest-benchmark
pip install pytest pytest-benchmark

# Install monitoring client
pip install psutil azure-monitor-opentelemetry
```

### Environment Variables for Tests

Create `stress-testing/.env.stress`:

```ini
# Target Environment
STRESS_BASE_URL=https://your-app.azurewebsites.net
STRESS_DB_URL=postgresql://user:password@your-db.postgres.database.azure.com/optimizer

# Test Credentials (dedicated stress-test accounts)
STRESS_TEST_USER_1=stress_test_user1@yourdomain.com
STRESS_TEST_PASSWORD_1=<password>
STRESS_TEST_TENANT_1=tenant-uuid-1

STRESS_TEST_USER_2=stress_test_user2@yourdomain.com
STRESS_TEST_PASSWORD_2=<password>
STRESS_TEST_TENANT_2=tenant-uuid-2

# Agent
AGENT_BASE_URL=https://your-agent.azurewebsites.net

# Reporting
RESULTS_DIR=./results
```

> **IMPORTANT:** Run stress tests against a **dedicated staging environment**, never production.
> Create dedicated test tenants with isolated test data.

### Test Data Setup

```bash
# From project root — seed test data for stress testing
python manage.py seed_license_rules --tenant stress_test_tenant_1
python manage.py seed_license_rules --tenant stress_test_tenant_2

# Generate synthetic server data (500 servers per tenant)
python stress-testing/scripts/generate_test_data.py --servers 500 --tenants 2
```

---

## Running Tests

### Quick Smoke Test (5 minutes)

```powershell
cd stress-testing
locust -f locustfile.py --host=https://your-app.azurewebsites.net \
  --users 5 --spawn-rate 1 --run-time 5m --headless \
  --html results/smoke_test.html
```

### Load Test (30 minutes)

```powershell
locust -f locustfile.py --host=https://your-app.azurewebsites.net \
  --users 50 --spawn-rate 5 --run-time 30m --headless \
  --html results/load_test_$(Get-Date -Format "yyyyMMdd_HHmm").html \
  --csv results/load_test
```

### Stress Test (ramp to breaking point)

```powershell
locust -f locustfile.py --host=https://your-app.azurewebsites.net \
  -f locustfile_stress.py --headless \
  --html results/stress_test.html \
  --csv results/stress_test
```

### File Upload Stress

```powershell
locust -f locustfile_uploads.py --host=https://your-app.azurewebsites.net \
  --users 10 --spawn-rate 2 --run-time 15m --headless \
  --html results/upload_stress.html
```

### AI Agent Stress

```powershell
python stress-testing/agent_stress_test.py \
  --concurrent 10 --duration 3600 --output results/agent_stress.json
```

### Soak Test (4 hours)

```powershell
locust -f locustfile.py --host=https://your-app.azurewebsites.net \
  --users 20 --spawn-rate 2 --run-time 4h --headless \
  --html results/soak_test.html --csv results/soak_test
```

### Run All Tests

```powershell
.\stress-testing\run_all_tests.ps1
```

---

## Monitoring & Metrics

### During Test Execution — What to Watch

#### Azure Portal / App Insights
- **Response Time** — P50, P90, P95, P99 per endpoint
- **Request Rate** — requests/second
- **Failed Requests** — count and rate
- **Dependency calls** — PostgreSQL, OpenAI, Cosmos DB latency
- **CPU / Memory** — App Service plan utilization
- **Live Metrics Stream** — real-time health

#### PostgreSQL (Azure Monitor)
```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';

-- Slow queries (during test)
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC LIMIT 20;

-- Lock waits
SELECT * FROM pg_locks WHERE NOT granted;

-- Connection pool usage
SELECT numbackends, xact_commit, xact_rollback, blks_hit, blks_read
FROM pg_stat_database WHERE datname = 'optimizer';
```

#### Locust Web UI
Access at `http://localhost:8089` during interactive runs:
- Real-time RPS chart
- Response time percentiles
- Error log
- Worker status (if distributed)

### Metrics Collection Script

```python
# Run alongside tests to capture system metrics
python stress-testing/collect_metrics.py --duration 1800 \
  --output results/system_metrics.json
```

---

## Reporting

### Test Result Structure

After each test run, the following files are generated:

```
results/
├── load_test_20260521_1430/
│   ├── load_test.html          # Locust HTML report
│   ├── load_test_stats.csv     # Per-endpoint statistics
│   ├── load_test_failures.csv  # Failed requests detail
│   ├── load_test_history.csv   # Time-series data
│   ├── system_metrics.json     # CPU/Memory over time
│   └── summary.md              # Human-readable summary
```

### Pass/Fail Criteria

A test **PASSES** if ALL of the following are true:
- [ ] P95 response time ≤ threshold for all endpoints
- [ ] Error rate < 1% overall
- [ ] No 5xx errors during steady state
- [ ] Memory usage stable (no upward trend in soak test)
- [ ] PostgreSQL connection pool < 90% utilized
- [ ] Zero cross-tenant data leakage detected

A test **FAILS** if ANY of the following occur:
- [ ] P95 response time > critical limit for any endpoint
- [ ] Error rate > 5%
- [ ] Any 500 errors on core endpoints (login, dashboard, analysis)
- [ ] Memory grows > 20% over 4 hours in soak test
- [ ] Cross-tenant data leakage detected
- [ ] Application crash or restart required

---

## Known Bottlenecks & Risks

### High-Risk Areas

| Area | Risk | Mitigation |
|---|---|---|
| **Report Generation** | PDF/DOCX generation is CPU-intensive and synchronous | Move to Celery background task queue |
| **Excel Processing** | Large pandas DataFrames consume significant memory | Chunk processing; file size limits |
| **AI Agent (OpenAI)** | Azure OpenAI TPM/RPM quota exhaustion under concurrent load | Implement request queuing + retry with backoff |
| **Cosmos DB** | RU consumption spikes with complex conversation history queries | Index optimization; partition key design |
| **Rule Engine (5000+ servers)** | O(n) rule evaluation without caching | Add Redis caching layer for rule results |
| **Gunicorn Workers** | Long-running requests (report gen, AI) block workers | Increase worker count; async views |
| **PostgreSQL Connections** | Connection pool exhaustion with 50+ concurrent users | PgBouncer connection pooling |
| **Multi-tenant Queries** | Missing tenant filter → full table scan | Audit all queries for tenant_id WHERE clause |

### Scaling Recommendations

1. **Immediate (before 50 concurrent users):**
   - Configure PgBouncer or increase max connections
   - Move report generation to Celery + Redis task queue
   - Add response caching (Redis) for dashboard queries

2. **Medium-term (before 200 concurrent users):**
   - Horizontal scaling: multiple Gunicorn instances behind load balancer
   - Read replica for PostgreSQL (analysis/report queries)
   - Azure OpenAI capacity reservation

3. **Long-term:**
   - CDN for static assets
   - Database query optimization (indexes, query analysis)
   - Async Django views for I/O-heavy endpoints

---

## Appendix: Test Data Volumes

| Entity | Small | Medium | Large |
|---|---|---|---|
| Tenants | 2 | 10 | 50 |
| Servers per tenant | 50 | 500 | 2000 |
| Analysis sessions | 10 | 100 | 1000 |
| Excel file rows | 1,000 | 10,000 | 100,000 |
| Report pages | 5 | 20 | 80 |
| Agent conversation turns | 3 | 10 | 50 |
