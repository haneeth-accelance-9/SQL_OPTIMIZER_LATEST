# Architecture Diagrams

README-style architecture documentation with Mermaid diagrams. Diagrams render on GitHub, GitLab, and most Markdown viewers that support Mermaid.

---

## 1. Current Architecture (As-Built)

High-level flow and components of the SQL License Optimizer as implemented today.

### 1.1 System Context

```mermaid
flowchart LR
    subgraph User
        Browser[Browser]
    end
    subgraph App["SQL License Optimizer"]
        Django[Django App]
    end
    subgraph Data
        SQLite[(SQLite DB)]
        Media[Media / Uploads]
    end
    subgraph External
        Azure[Azure OpenAI]
    end
    Browser -->|HTTPS| Django
    Django --> SQLite
    Django --> Media
    Django -->|Optional| Azure
```

### 1.2 Request and Data Flow

```mermaid
flowchart TB
    subgraph Client
        User[User]
    end
    subgraph Web["Django (optimizer.views)"]
        Upload[upload]
        Results[results / dashboard]
        Report[report_page]
        Export[report_download / download_rule_data]
        Health[health / ready]
    end
    subgraph Services["optimizer.services"]
        Analysis[analysis_service.run_analysis]
        Excel[excel_processor]
        Rules[rule_engine]
        AI[ai_report_generator]
        Charts[chart_generator]
    end
    subgraph Storage
        DB[(AnalysisSession)]
        Files[MEDIA_ROOT]
    end
    User -->|1. Upload Excel| Upload
    Upload --> Excel
    Upload --> Analysis
    Analysis --> Excel
    Analysis --> Rules
    Analysis --> AI
    Analysis --> DB
    Upload --> Files
    User -->|2. View dashboard| Results
    Results --> DB
    Results --> Charts
    User -->|3. View report| Report
    Report --> DB
    User -->|4. Export PDF/Word/Excel| Export
    Export --> DB
```

### 1.3 Component Layering (Current)

```mermaid
flowchart TB
    subgraph Presentation["Presentation"]
        Views[optimizer.views]
        Templates[templates/]
    end
    subgraph Business["Business logic"]
        AnalysisSvc[analysis_service]
        RuleEngine[rule_engine]
        Rules[optimizer.rules]
    end
    subgraph DataAccess["Data & I/O"]
        ExcelProc[excel_processor]
        ChartGen[chart_generator]
        AIReport[ai_report_generator]
    end
    subgraph Persistence["Persistence"]
        Models[optimizer.models]
        Session[Session]
        Media[File storage]
    end
    Views --> AnalysisSvc
    Views --> ChartGen
    AnalysisSvc --> ExcelProc
    AnalysisSvc --> RuleEngine
    AnalysisSvc --> AIReport
    RuleEngine --> Rules
    AnalysisSvc --> Models
    Views --> Session
    Views --> Media
```

### 1.4 Upload-to-Results Pipeline (Current)

```mermaid
sequenceDiagram
    participant U as User
    participant V as View (upload)
    participant EP as ExcelProcessor
    participant RE as rule_engine
    participant LM as compute_license_metrics
    participant AI as ai_report_generator
    participant DB as AnalysisSession
    U->>V: POST Excel file
    V->>V: Validate (magic bytes, size)
    V->>EP: load_file(path)
    EP-->>V: installations, demand, prices
    V->>RE: run_rules(installations)
    RE-->>V: azure_payg, retired_devices
    V->>LM: compute_license_metrics(demand, prices)
    LM-->>V: total_demand_quantity, total_license_cost, by_product
    V->>AI: generate_report_text(context)
    AI-->>V: report_text or None
    V->>DB: Save result_data, analysis_id
    V->>U: Redirect to results
```

---

## 2. Target Architecture (Improvements)

What to add or change, based on [ENTERPRISE_IMPROVEMENTS.md](ENTERPRISE_IMPROVEMENTS.md).

### 2.1 Target System Context

```mermaid
flowchart LR
    subgraph User
        Browser[Browser]
    end
    subgraph App["SQL License Optimizer"]
        Django[Django App]
        Workers[Background Workers]
    end
    subgraph Data
        PG[(PostgreSQL)]
        Redis[(Redis)]
        ObjectStore[Object Storage]
    end
    subgraph External
        Azure[Azure OpenAI]
        Vault[Secrets / Key Vault]
    end
    Browser -->|HTTPS| Django
    Django --> PG
    Django --> Redis
    Django --> ObjectStore
    Django --> Workers
    Workers --> Django
    Workers --> Azure
    Django --> Vault
    Workers --> Vault
```

### 2.2 Target Layering and New Components

```mermaid
flowchart TB
    subgraph Presentation["Presentation (improved)"]
        Views[Views - HTTP only]
        API[Optional REST API]
        Templates[Templates]
    end
    subgraph Business["Business logic"]
        AnalysisSvc[analysis_service]
        RuleEngine[rule_engine]
        Serializer[Context / DTO builder]
    end
    subgraph DataAccess["Data & I/O"]
        ExcelProc[excel_processor]
        ChartGen[chart_generator + cache]
        AIReport[ai_report_generator]
    end
    subgraph New["New / improved"]
        Queue[Job queue]
        Cache[Chart/result cache]
        Secrets[Secrets manager]
    end
    subgraph Persistence["Persistence"]
        PG[(PostgreSQL)]
        Redis[(Redis)]
        ObjectStore[Uploads]
    end
    Views --> AnalysisSvc
    Views --> Cache
    API --> AnalysisSvc
    AnalysisSvc --> Queue
    AnalysisSvc --> ExcelProc
    AnalysisSvc --> RuleEngine
    AnalysisSvc --> AIReport
    Queue --> ChartGen
    AIReport --> Secrets
    AnalysisSvc --> PG
    AnalysisSvc --> Redis
    ChartGen --> Cache
```

### 2.3 Target Request Flow (Async Option)

```mermaid
sequenceDiagram
    participant U as User
    participant V as View
    participant Svc as analysis_service
    participant Q as Job queue
    participant W as Worker
    participant DB as DB / Cache
    participant Azure as Azure OpenAI
    U->>V: POST Excel
    V->>V: Validate, save file
    V->>Svc: enqueue_analysis(file_id)
    Svc->>Q: Enqueue job
    V->>U: 202 + polling URL
    W->>Q: Pick job
    W->>Svc: run_analysis(path)
    Svc->>Azure: generate_report
    Svc->>DB: Store result_data, charts
    U->>V: GET results (poll or redirect)
    V->>DB: Load by analysis_id
    V->>U: Dashboard / report
```

### 2.4 Improvement Map (Summary)

| Area | Current | Target |
|------|---------|--------|
| **Secrets** | Env vars, .env | Env + optional Key Vault; no defaults in prod |
| **Auth** | Django auth, @login_required | + RBAC, optional SSO/OIDC |
| **Session** | DB session, analysis_id only | + Redis option; strict TTL |
| **Processing** | Synchronous in request | Optional: queue (Celery/RQ), async + polling |
| **Charts** | Generated every request | Cache by analysis_id; invalidate on new analysis |
| **Database** | SQLite | PostgreSQL in production |
| **Uploads** | Local MEDIA_ROOT | Object storage (S3/Azure Blob) in prod |
| **Logging** | Console | Structured (JSON), request_id, file/rotate in prod |
| **Health** | /health, /ready | + dependency checks (DB, Redis, optional cache) |
| **Testing** | Some unit tests | Full coverage, CI, fixtures |
| **Settings** | Single settings.py | base + dev/staging/prod modules |
| **API** | HTML only | Optional versioned REST under /api/v1/ |
| **Frontend** | Tailwind CDN | Built Tailwind, pinned deps, a11y |

---

## 3. Enterprise Architecture Overview

This section describes the **SQL License Optimizer** in a single, enterprise-friendly view: what the system does, how data and control flow, and where security and operations apply. Use this when explaining the application to stakeholders, architecture boards, or compliance.

### 3.1 What the Application Does

The SQL License Optimizer is a **web application** that lets authorized users:

1. **Upload** Excel workbooks (installations, demand, prices, optimization data).
2. **Analyze** them through configurable business rules (e.g. Azure PAYG identification, retired devices) and license metrics.
3. **View** results in a tabbed dashboard with charts and an executive report (optionally AI-generated).
4. **Export** reports (PDF/Word) and rule-specific data (Excel) for traceability and audit.

All optimizer actions are **authenticated**; sessions store only an analysis reference; results are persisted with **TTL and ownership** checks. Health and readiness endpoints support **load balancers and orchestrators**.

### 3.2 Enterprise System Context

```mermaid
flowchart TB
    subgraph Users["Users"]
        Analyst[Analyst / License Manager]
    end
    subgraph App["SQL License Optimizer (Application Boundary)"]
        Web[Django Web App]
    end
    subgraph Data["Data & Storage"]
        DB[(Database\nSession + AnalysisSession)]
        Media[File Storage\nUploads]
    end
    subgraph External["External Services"]
        Azure[Azure OpenAI\nOptional AI Report]
    end
    Analyst -->|HTTPS / Login| Web
    Web -->|Read/Write| DB
    Web -->|Store/Read uploads| Media
    Web -.->|Optional| Azure
```

**Summary for enterprise:** Users interact only with the web app over HTTPS. The app owns database and file storage; the only external dependency is optional Azure OpenAI for report generation.

### 3.3 End-to-End Application Flow (All Functionalities)

This diagram shows how a request moves through the system and where each capability lives.

```mermaid
flowchart TB
    subgraph Client["Client"]
        User[User]
    end
    subgraph Gateway["Entry & Security"]
        Auth[Login / Signup / Logout]
        Health[Health / Ready]
    end
    subgraph Web["Web Layer (optimizer.views)"]
        Home[Home]
        Upload[Upload Excel]
        Results[Results]
        Dashboard[Dashboard]
        Report[Report Page]
        ReportDL[Report Download\nPDF / Word]
        RuleDL[Rule Data Download\nExcel]
    end
    subgraph Services["Business & Services"]
        Analysis[Analysis Service\nrun_analysis]
        Excel[Excel Processor]
        RuleEngine[Rule Engine]
        LicenseMetrics[License Metrics]
        AI[AI Report Generator]
        Charts[Chart Generator]
        Export[Report Export\nPDF/DOCX]
    end
    subgraph Rules["Business Rules"]
        R1[Rule 1: Azure PAYG]
        R2[Rule 2: Retired Devices]
    end
    subgraph Persistence["Persistence"]
        Session[(Session\nanalysis_id only)]
        AnalysisSession[(AnalysisSession\nresult_data, TTL, user)]
        Media[Media Root\nUploaded files]
    end
    User --> Auth
    User --> Health
    User --> Home
    User -->|1. Upload| Upload
    Upload --> Excel
    Upload --> Analysis
    Analysis --> Excel
    Analysis --> RuleEngine
    RuleEngine --> R1
    RuleEngine --> R2
    Analysis --> LicenseMetrics
    Analysis --> AI
    Analysis --> AnalysisSession
    Upload --> Media
    User -->|2. View| Results
    User -->|2. View| Dashboard
    Results --> Session
    Results --> AnalysisSession
    Results --> Charts
    Dashboard --> Session
    Dashboard --> AnalysisSession
    Dashboard --> Charts
    User -->|3. Report| Report
    Report --> Session
    Report --> AnalysisSession
    User -->|4. Export| ReportDL
    User -->|4. Export| RuleDL
    ReportDL --> AnalysisSession
    ReportDL --> Export
    RuleDL --> AnalysisSession
```

**Flow in words:**

| Step | User action | System behavior |
|------|-------------|-----------------|
| **0** | Access app | Auth (login/signup); Health/Ready for probes. |
| **1** | Upload Excel | File validated (magic bytes, size), saved to Media; Analysis Service loads sheets (Excel Processor), runs Rule Engine (Rule 1 + Rule 2), computes License Metrics, optionally calls Azure OpenAI for report text; result stored in AnalysisSession; session stores only `analysis_id`. |
| **2** | View results/dashboard | Load context by `analysis_id` from AnalysisSession (TTL + ownership checked); Chart Generator builds visuals from result_data. |
| **3** | View report | Same context load; executive summary (AI or fallback) and export options. |
| **4** | Export | Report Download (PDF/Word) or Rule Data Download (Excel); data from AnalysisSession; filenames include analysis ID for traceability. |

### 3.4 Logical Architecture (Layers)

```mermaid
flowchart TB
    subgraph Presentation["Presentation Layer"]
        Views[Views\nHTTP, validation, auth]
        Templates[Templates]
    end
    subgraph Business["Business Logic Layer"]
        AnalysisSvc[Analysis Service]
        RuleEngine[Rule Engine]
        Rules[Rules: Azure PAYG, Retired Devices]
    end
    subgraph DataAccess["Data & I/O Layer"]
        ExcelProc[Excel Processor]
        ChartGen[Chart Generator]
        AIReport[AI Report Generator]
        ReportExport[Report Export]
    end
    subgraph Persistence["Persistence Layer"]
        Models[Models\nAnalysisSession]
        Session[Session Store]
        Media[File Storage]
    end
    Views --> AnalysisSvc
    Views --> ChartGen
    Views --> ReportExport
    AnalysisSvc --> ExcelProc
    AnalysisSvc --> RuleEngine
    AnalysisSvc --> AIReport
    RuleEngine --> Rules
    AnalysisSvc --> Models
    Views --> Session
    Views --> Media
```

**Enterprise takeaway:** Clear separation: presentation handles HTTP and auth; business layer runs analysis and rules; data layer handles Excel, charts, and AI; persistence holds session, analysis results, and files.

### 3.5 Security and Operations Touchpoints

```mermaid
flowchart LR
    subgraph Security["Security"]
        A1[Authentication\nLogin / Session]
        A2[Authorization\n@login_required]
        A3[Input validation\nMagic bytes, size, whitelist]
        A4[Ownership & TTL\nAnalysisSession]
    end
    subgraph Operations["Operations"]
        O1[Health / Ready\nProbes]
        O2[Structured logging\nRequest ID]
        O3[Cleanup\ncleanup_uploads]
        O4[Config\nEnv, feature flags]
    end
    User((User)) --> A1
    A1 --> A2
    A2 --> A3
    A3 --> A4
    App((App)) --> O1
    App --> O2
    O2 --> O3
    O4 --> App
```

| Area | What the application does |
|------|----------------------------|
| **Authentication** | Login/signup/logout; session cookie (secure in production). |
| **Authorization** | All optimizer views require login; results tied to user where applicable. |
| **Input validation** | File type (magic bytes), size limit, whitelisted export formats and rule IDs. |
| **Ownership & TTL** | Analysis loaded by session `analysis_id`; ownership and TTL checked; expired analyses redirect with message. |
| **Health / Ready** | Endpoints for load balancer and orchestrator. |
| **Logging** | Request ID, structured logs; no PII in logs. |
| **Cleanup** | Management command to delete old uploads (retention policy). |
| **Configuration** | Environment-based (and optional Key Vault); feature flags for AI and charts. |

---

## How to View

- **GitHub / GitLab**: Open this file in the repo; Mermaid blocks render automatically.
- **VS Code**: Use a Markdown preview extension that supports Mermaid (e.g. Markdown Preview Mermaid Support).
- **Export**: Use [Mermaid Live Editor](https://mermaid.live) or CLI to export diagrams as PNG/SVG.
