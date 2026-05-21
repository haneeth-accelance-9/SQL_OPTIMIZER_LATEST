# MVP-6 ACCELANCE — PostgreSQL Schema Documentation

```
╔══════════════════════════════════════════════════════════════════════════════════════════════════════╗
║                     MVP-6 ACCELANCE — PostgreSQL Schema Documentation                              ║
║                     Database : mvp6_license_agent_dev  (Azure PostgreSQL)                          ║
║                     Tables   : 15  │  Total Relationships : 18  │  Last Updated : 2026-05-20       ║
╚══════════════════════════════════════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 1 — IDENTITY & ACCESS LAYER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌─────────────────────────────────────────┐          ┌─────────────────────────────────────────┐
  │         Django User  (auth_user)        │          │  Tenant                                 │
  │─────────────────────────────────────────│          │─────────────────────────────────────────│
  │  PK  id            INT (auto)           │          │  PK  id           UUID                  │
  │      username      VARCHAR              │          │      name         VARCHAR(120)  UNIQUE   │
  │      email         VARCHAR              │          │      description  TEXT                  │
  │      password      VARCHAR (hashed)     │          │      is_active    BOOL                  │
  │      is_active     BOOL                 │          │      created_at   TIMESTAMPTZ           │
  │      date_joined   TIMESTAMPTZ          │          │                                         │
  │                                         │          │  Purpose: multi-tenancy root.           │
  │  Purpose: authentication & identity.    │          │  Every TenantAwareModel table carries   │
  │  Managed by Django's built-in auth.     │          │  a tenant_id FK pointing here.          │
  └────────┬────────────────────┬───────────┘          └──────────────────────┬──────────────────┘
           │                   │                                              │
        1:1│                1:N│ (nullable FK, CASCADE)           tenant_id FK│ (on all tables below)
           │                   │                                              │
           ▼                   ▼                                              │
  ┌──────────────────┐  ┌──────────────────────────────────────┐            │
  │  UserProfile     │  │  AnalysisSession                     │            │
  │──────────────────│  │──────────────────────────────────────│            │
  │  PK  id          │  │  PK  id           BIGINT (auto)      │            │
  │  1:1 user        │  │  FK  user_id  →  auth_user (null)    │            │
  │      role        │  │      file_name    VARCHAR(255)       │            │
  │       admin      │  │      file_path    VARCHAR(500)       │            │
  │       editor     │  │      status                          │            │
  │       viewer     │  │        uploaded → processing         │            │
  │      team_name   │  │        → completed / failed          │            │
  │      image_url   │  │      session_key  VARCHAR(40)        │            │
  │      updated_at  │  │      result_data  JSONB              │            │
  │                  │  │      summary_metrics  JSONB          │            │
  │  NOTE: role drives│  │      error_message  TEXT            │            │
  │  UI permissions. │  │      created_at   TIMESTAMPTZ        │            │
  └──────────────────┘  │      completed_at TIMESTAMPTZ        │            │
                        │                                      │            │
                        │  ⚠  No tenant_id (user-scoped only) │            │
                        │  ⚠  No other table references this  │            │
                        └──────────────────────────────────────┘            │
                                                                            │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 2 — SERVER REGISTRY & UTILISATION DATA                             │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│━━━━━━━━━━━━━━━━━━━━━━━
                                                                            │
  ┌─────────────────────────────────────────────────────────────────────────▼──────────────────────┐
  │  Server                                                                                        │
  │────────────────────────────────────────────────────────────────────────────────────────────────│
  │  PK  id                    UUID                                                                │
  │  FK  tenant_id             → Tenant                                                            │
  │                                                                                                │
  │  ── Identity ──────────────────────────────────────────────────────────────────────────────    │
  │      server_key            VARCHAR(512)   UNIQUE per tenant  ← canonical cross-source ID      │
  │      usu_device_key        VARCHAR(512)                      ← from USU API                   │
  │      boones_number         VARCHAR(100)                      ← from Boone's flat file         │
  │      server_name           VARCHAR(255)                                                        │
  │                                                                                                │
  │  ── Classification ────────────────────────────────────────────────────────────────────────    │
  │      environment           VARCHAR(80)     e.g. Production / Non-Prod                         │
  │      hosting_zone          VARCHAR(120)                                                        │
  │      platform              VARCHAR(80)                                                         │
  │      device_type           VARCHAR(120)                                                        │
  │      is_virtual            BOOL                                                                │
  │      criticality           VARCHAR(80)                                                         │
  │      topology_type         VARCHAR(80)                                                         │
  │      cluster_name / cluster_device_key  VARCHAR                                                │
  │      location / country / region        VARCHAR                                                │
  │                                                                                                │
  │  ── Ownership ─────────────────────────────────────────────────────────────────────────────    │
  │      server_owner_email    EMAIL                                                               │
  │      app_owner_email       EMAIL    ← primary notification target                             │
  │      business_owner_email  EMAIL                                                               │
  │      business_division     VARCHAR(120)                                                        │
  │      apps_id / app_name    VARCHAR                                                             │
  │                                                                                                │
  │  ── Source Tracking ───────────────────────────────────────────────────────────────────────    │
  │      beat_ids              TEXT[]          multiple BEAT IDs from USU                         │
  │      source_systems        VARCHAR[]       e.g. ['usu','boones']                              │
  │      installed_status_usu  VARCHAR(80)                                                        │
  │      installed_status_boones VARCHAR(80)                                                      │
  │      is_cloud_device       BOOL                                                                │
  │      cloud_provider        VARCHAR(80)                                                         │
  │      first_seen_at / last_synced_at / is_active   TIMESTAMPTZ / BOOL                         │
  │                                                                                                │
  │  UNIQUE (tenant, server_key)                                                                   │
  │  INDEX  hosting_zone │ environment │ installed_status_usu │ installed_status_boones           │
  └───────────┬────────────────────────────────────────────────────────────────┬──────────────────┘
              │  1:N  (server_id FK on all child tables)                       │
   ┌──────────┼─────────────────────────────────────┐                         │
   │          │                                     │                         │
   ▼          ▼                                     ▼                         │
┌────────────────────────┐  ┌───────────────────────────┐  ┌─────────────────▼──────────────────┐
│  USUInstallation       │  │  USUDemandDetail           │  │  CPUUtilisation                    │
│────────────────────────│  │───────────────────────────│  │────────────────────────────────────│
│  PK  id  UUID          │  │  PK  id  UUID             │  │  PK  id  UUID                      │
│  FK  server_id         │  │  FK  server_id            │  │  FK  server_id                     │
│  FK  tenant_id         │  │  FK  tenant_id            │  │  FK  tenant_id                     │
│                        │  │                           │  │                                    │
│  product_family        │  │  product_family           │  │  source                            │
│  product_group         │  │  product_group            │  │    boones_public                   │
│  manufacturer          │  │  manufacturer             │  │    boones_private                  │
│  product_description   │  │  product_description      │  │    grafana                         │
│  product_edition       │  │  product_edition          │  │  period_month  DATE                │
│  license_metric        │  │  eff_quantity  DECIMAL    │  │  logical_cpu_count  INT            │
│  calc_license_metric   │  │  no_license_required      │  │  avg_cpu_pct   DECIMAL(6,3)        │
│  inv_status_name       │  │  device_purpose           │  │  max_cpu_pct   DECIMAL(6,3)        │
│  inv_status_std_name   │  │  topology_type            │  │  min_cpu_pct   DECIMAL(6,3)        │
│  ignore_usage          │  │  cpu_core_count           │  │                                    │
│  no_license_required   │  │  virt_type                │  │  ── Private cloud only ──          │
│  device_status         │  │  is_cloud_device          │  │  physical_ram_gib                  │
│  cpu_socket_count      │  │  cloud_provider           │  │  avg_free_memory_pct               │
│  cpu_core_count        │  │  cpu_thread_count         │  │  max_free_memory_pct               │
│  hyper_threading_factor│  │  hyper_threading_factor   │  │  min_free_memory_pct               │
│  topology_type         │  │  fetched_at               │  │  allocated_storage_gb              │
│  source_key            │  │                           │  │  used_storage_gb                   │
│  inventory_date        │  │  Used for:                │  │  ingested_at  TIMESTAMPTZ          │
│  creation_date         │  │  UC2 retired-device logic │  │                                    │
│  fetched_at            │  └───────────────────────────┘  │  UNIQUE(server,period_month,source)│
│                        │                                  └────────────────────────────────────┘
│  Used for:             │
│  UC1 license-included  │
│  UC2 retired-device    │
└────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 3 — FILE INGESTION LAYER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌────────────────────────────────────────────┐   1:N   ┌──────────────────────────────────────────┐
  │  BooneFileUpload                           │ ───────▶│  BoonesRawRow                            │
  │────────────────────────────────────────────│         │──────────────────────────────────────────│
  │  PK  id            UUID                    │         │  PK  id          UUID                    │
  │  FK  tenant_id     → Tenant                │         │      row_data    JSONB                   │
  │  FK  uploaded_by   → auth_user (nullable)  │         │                  ← full Excel row as-is  │
  │                                            │         │      ingested_at TIMESTAMPTZ             │
  │      source        boones_public           │         │                                          │
  │                    boones_private          │         │  ⚠  NO tenant_id                        │
  │      file_name     VARCHAR(255)            │         │  ⚠  Schema-free: columns stored          │
  │      file_path     VARCHAR(500)            │         │     as JSON keys — no migration          │
  │      latest_month  DATE                    │         │     needed when file format changes      │
  │      uploaded_at   TIMESTAMPTZ             │         │                                          │
  │      status        uploaded                │         │  INDEX  ingested_at DESC                 │
  │                    processing              │         └──────────────────────────────────────────┘
  │                    completed               │
  │                    failed                  │
  │      rows_ingested INT                     │
  │      error_message TEXT                    │
  │                                            │
  │  INDEX  uploaded_at DESC                   │
  │  INDEX  source, latest_month DESC          │
  └────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 4 — GRAFANA METRICS LAYER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌────────────────────────────────────────────┐  rollup  ┌─────────────────────────────────────────┐
  │  GrafanaMetricSnapshot                     │ ───────▶ │  GrafanaMetricMonthlyRollup             │
  │  (raw — 90-day retention then purged)      │          │  (long-term aggregates, kept forever)   │
  │────────────────────────────────────────────│          │─────────────────────────────────────────│
  │  PK  id            UUID                    │          │  PK  id           UUID                  │
  │  FK  server_id     → Server                │          │  FK  server_id    → Server              │
  │  FK  tenant_id     → Tenant                │          │  FK  tenant_id    → Tenant              │
  │                                            │          │                                         │
  │      dashboard     VARCHAR(80)             │          │      metric_name  VARCHAR(80)           │
  │                    primary / testing       │          │      metric_unit  VARCHAR(30)           │
  │      metric_name   VARCHAR(80)             │          │      period_month DATE                  │
  │      metric_value  DECIMAL(18,6)           │          │      avg_value    DECIMAL(18,6)         │
  │      metric_unit   VARCHAR(30)             │          │      max_value    DECIMAL(18,6)         │
  │      metric_ts     TIMESTAMPTZ             │          │      min_value    DECIMAL(18,6)         │
  │      fetched_at    TIMESTAMPTZ             │          │      sample_count INT                   │
  │                                            │          │      rolled_up_at TIMESTAMPTZ           │
  │  Fetched hourly Mon–Fri via                │          │                                         │
  │  Grafana Mimir PromQL API.                 │          │  UNIQUE (server, metric_name,           │
  │  Purged after 90 days once rolled up.      │          │          period_month)                  │
  │                                            │          │  INDEX  period_month DESC               │
  │  INDEX (server, metric_name, metric_ts)    │          └─────────────────────────────────────────┘
  └────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 5 — AGENT / OPTIMIZATION PIPELINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌──────────────────────────────────────────┐        ┌──────────────────────────────────────────────┐
  │  LicenseRule                             │        │  AgentRun                                    │
  │──────────────────────────────────────────│        │──────────────────────────────────────────────│
  │  PK  id   UUID                           │        │  PK  id              UUID                    │
  │  FK  tenant_id  → Tenant                 │        │  FK  tenant_id       → Tenant                │
  │                                          │        │                                              │
  │      rule_code   VARCHAR(40)             │        │      run_label       VARCHAR(120)            │
  │      use_case    UC1 / UC2 / UC3         │        │      triggered_by    VARCHAR(80)             │
  │      product_family  VARCHAR(120)        │        │      status                                  │
  │      rule_name   VARCHAR(120)            │        │        running → completed                   │
  │      description TEXT                    │        │               → failed / partial             │
  │      conditions  JSONB                   │        │      servers_evaluated  INT                  │
  │      cost_per_core_pair_eur  DECIMAL     │        │      candidates_found   INT                  │
  │      is_active   BOOL                    │        │      llm_model          VARCHAR(80)          │
  │      valid_from / valid_to  TIMESTAMPTZ  │        │      llm_tokens_used    INT                  │
  │      created_by  VARCHAR(80)             │        │      llm_cost_eur       DECIMAL              │
  │      created_at / updated_at             │        │      run_duration_sec   DECIMAL              │
  │                                          │        │      report_markdown    TEXT                 │
  │  UNIQUE (tenant, rule_code)              │        │      rules_evaluation   JSONB                │
  │  Seeded via migration or Django admin.   │        │      knowledge_sources  JSONB                │
  └──────────────────┬───────────────────────┘        │      started_at / finished_at  TIMESTAMPTZ  │
                     │                                │                                              │
                     │                                │  Runs weekly (APScheduler) or on-demand.    │
                     │                                │  INDEX  started_at DESC, status             │
                     │                                └───────────────────────┬──────────────────────┘
                     │                                                        │ 1:N
                     │                                                        │
                     │                               ┌────────────────────────▼──────────────────────┐
                     │                               │  AgentRunServerSnapshot                       │
                     │                               │───────────────────────────────────────────────│
                     │                               │  PK  id            UUID                       │
                     │                               │  FK  agent_run_id  → AgentRun   (CASCADE)     │
                     │                               │  FK  server_id     → Server     (PROTECT)     │
                     │                               │  FK  tenant_id     → Tenant                   │
                     │                               │                                               │
                     │                               │      usu_snapshot      JSONB                  │
                     │                               │      cpu_snapshot      JSONB                  │
                     │                               │      grafana_snapshot  JSONB                  │
                     │                               │      snapshotted_at    TIMESTAMPTZ            │
                     │                               │                                               │
                     │                               │  Forensic copy of exactly what the agent     │
                     │                               │  saw per server — enables replay of any       │
                     │                               │  historical recommendation.                   │
                     │                               │  UNIQUE (agent_run, server)                   │
                     │                               └───────────────────────────────────────────────┘
                     │
                     │    ┌────────────────────────────────────────────────────────────────────────┐
                     └───▶│  OptimizationCandidate                                                 │
                          │────────────────────────────────────────────────────────────────────────│
                          │  PK  id                UUID                                            │
                          │  FK  agent_run_id      → AgentRun      (PROTECT)                      │
                          │  FK  server_id         → Server        (PROTECT)                      │
                          │  FK  rule_id           → LicenseRule   (PROTECT)                      │
                          │  FK  tenant_id         → Tenant                                        │
                          │                                                                        │
                          │      use_case          VARCHAR(10)  ← denormalised for fast filter    │
                          │      recommendation    VARCHAR(255)                                    │
                          │      rationale         TEXT         ← LLM explanation                 │
                          │      estimated_saving_eur  DECIMAL(12,2)                               │
                          │                                                                        │
                          │      status lifecycle:                                                  │
                          │        pending → in_progress → accepted                               │
                          │                             → rejected                                │
                          │                             → expired (no response before expires_at) │
                          │                                                                        │
                          │      notified_to_email  EMAIL                                          │
                          │      notified_at / expires_at / created_at / updated_at               │
                          │                                                                        │
                          │  UNIQUE (agent_run, server, rule)                                      │
                          │  INDEX  detected_on DESC, status, use_case                             │
                          │  PARTIAL INDEX  idx_open_candidates                                    │
                          │    ON (use_case, detected_on) WHERE status IN ('pending','in_progress')│
                          └──────────────────────────────────────┬───────────────────────────────┘
                                                                 │ 1:1
                                                                 ▼
                                               ┌────────────────────────────────────────────┐
                                               │  OptimizationDecision                      │
                                               │────────────────────────────────────────────│
                                               │  PK  id                UUID                │
                                               │  1:1 candidate_id      → Candidate (PROTECT│
                                               │  FK  tenant_id         → Tenant            │
                                               │                                            │
                                               │      decision          accepted / rejected  │
                                               │      decided_by        VARCHAR(120)        │
                                               │      decided_by_email  EMAIL               │
                                               │      decision_notes    TEXT                │
                                               │      decided_at        TIMESTAMPTZ         │
                                               │      snow_ticket_id    VARCHAR(80)  ← NULL │
                                               │      snow_ticket_created_at  TIMESTAMPTZ   │
                                               │                                            │
                                               │  ⚡ On save() → syncs status back to       │
                                               │     OptimizationCandidate automatically.  │
                                               │  Immutable — one decision per candidate.  │
                                               └────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 6 — COMPLETE RELATIONSHIP MAP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  auth_user                ──1:1──▶  UserProfile
  auth_user                ──1:N──▶  AnalysisSession            (nullable, CASCADE)
  auth_user                ──1:N──▶  BooneFileUpload            (nullable, SET NULL)

  Tenant                   ──1:N──▶  Server
  Tenant                   ──1:N──▶  LicenseRule
  Tenant                   ──1:N──▶  AgentRun
  Tenant                   ──1:N──▶  BooneFileUpload
  Tenant                   ──1:N──▶  USUInstallation
  Tenant                   ──1:N──▶  USUDemandDetail
  Tenant                   ──1:N──▶  CPUUtilisation
  Tenant                   ──1:N──▶  GrafanaMetricSnapshot
  Tenant                   ──1:N──▶  GrafanaMetricMonthlyRollup
  Tenant                   ──1:N──▶  AgentRunServerSnapshot
  Tenant                   ──1:N──▶  OptimizationCandidate
  Tenant                   ──1:N──▶  OptimizationDecision

  Server                   ──1:N──▶  USUInstallation
  Server                   ──1:N──▶  USUDemandDetail
  Server                   ──1:N──▶  CPUUtilisation
  Server                   ──1:N──▶  GrafanaMetricSnapshot
  Server                   ──1:N──▶  GrafanaMetricMonthlyRollup
  Server                   ──1:N──▶  AgentRunServerSnapshot
  Server                   ──1:N──▶  OptimizationCandidate

  AgentRun                 ──1:N──▶  AgentRunServerSnapshot     (CASCADE)
  AgentRun                 ──1:N──▶  OptimizationCandidate      (PROTECT)
  LicenseRule              ──1:N──▶  OptimizationCandidate      (PROTECT)
  OptimizationCandidate    ──1:1──▶  OptimizationDecision       (PROTECT)
  BooneFileUpload          ──1:N──▶  BoonesRawRow
  GrafanaMetricSnapshot    ──rollup▶  GrafanaMetricMonthlyRollup

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SECTION 7 — DESIGN NOTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌─────────────────────────┬────────────────────────────────────────────────────────────────────┐
  │  Design Decision        │  Detail                                                            │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │  Primary Keys           │  UUID everywhere except AnalysisSession (BIGINT) & auth_user (INT) │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │  Multi-tenancy          │  TenantAwareModel abstract base injects tenant_id FK on all tables  │
  │                         │  except auth_user, UserProfile, AnalysisSession, BoonesRawRow      │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │  on_delete = CASCADE    │  Source data tables — deleting a server removes its metrics        │
  │  on_delete = PROTECT    │  Decision & candidate tables — prevents accidental data loss       │
  │  on_delete = SET NULL   │  BooneFileUpload.uploaded_by — user deletion keeps file record     │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │  Flexible raw storage   │  BoonesRawRow.row_data + AgentRunServerSnapshot.*_snapshot         │
  │                         │  use JSONB — absorbs file format changes without migrations        │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │  Immutable audit trail  │  AgentRunServerSnapshot preserves exact data the agent saw         │
  │                         │  OptimizationDecision is append-only (one per candidate)           │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │  Status sync            │  OptimizationDecision.save() automatically writes status back      │
  │                         │  to OptimizationCandidate via Django signal override               │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │  Grafana retention      │  Raw snapshots purged after 90 days once rolled up to              │
  │                         │  GrafanaMetricMonthlyRollup (1st of month, 03:00 UTC)              │
  ├─────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │  Future: ServiceNow     │  OptimizationDecision.snow_ticket_id is NULL until SNOW            │
  │                         │  integration is built in a future phase                            │
  └─────────────────────────┴────────────────────────────────────────────────────────────────────┘

  Total Tables  : 15  (+ Django built-ins: auth_user, auth_group, django_session, etc.)
  All PKs       : UUID  except  AnalysisSession (BIGINT auto) and auth_user (INT auto)
  SSL           : Required for all connections to Azure PostgreSQL (sslmode=require)
  Schema owner  : Django ORM — source of truth is models.py, SQL generated via migrations
```
