# LiscenceOptimizer

This agent creates executive summary or the results that are obtained by applying usecases on the data

Built with the [agentic-ai-sdk](https://github.com/bayer-int/agentic_ai_sdk) library.

---

## 🎯 Purpose

This agent provides AI-powered capabilities for your workflows.

---

## 📋 Prerequisites

- **Python 3.11+**
- **Azure OpenAI** access with API key or Managed Identity
- **Azure Cosmos DB** (for conversation memory)
- **Azure Monitor** (optional, for observability)
- **Docker** (optional, for containerized deployment)

---

## 🚀 Quick Start

### Installation

This agent depends on `agentic-ai-sdk`, which is published to the **Bayer internal Artifactory** registry (`agf-pypi-dev-sdk`). The index is declared in `pyproject.toml` under `[tool.uv.index]` — you only need to supply credentials via environment variables.

```powershell
# Navigate to project
cd liscence-optimizer

# Set Artifactory credentials (add these to your shell profile or .env)
$env:UV_INDEX_BAYER_ARTIFACTORY_USERNAME = "your.name@bayer.com"
$env:UV_INDEX_BAYER_ARTIFACTORY_PASSWORD = "your-artifactory-token"

# Install dependencies
uv pip install -e ".[dev]"
```

> **Tip:** Your token can be generated at [artifactory.bayer.com](https://artifactory.bayer.com) → *Edit Profile* → *Generate API Key*.

### Configuration

1. **Copy environment template:**
   ```powershell
   Copy-Item .env.example .env.development
   ```

2. **Edit `.env.development`** with your Azure credentials:
   ```env
   # Azure OpenAI
   AZURE_OPENAI_ENDPOINT=https://your-instance.openai.azure.com
   AZURE_OPENAI_API_KEY=your-api-key
   AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
   
   # Cosmos DB
   COSMOSDB_ENDPOINT=https://your-cosmos.documents.azure.com:443/
   COSMOSDB_KEY=your-cosmos-key
   
   # Application Insights
   APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...
   
   # Azure AD Authentication
   AZURE_TENANT_ID=fcb2b37b-5da0-466b-9b83-0014b67a7c78
   AZURE_CLIENT_ID=6a99f31c-bf54-4a3c-89e8-bb3e5b108a25
   MANAGED_IDENTITY_CLIENT_ID=906f830e-eeab-46e1-9e90-ad410c8649a3
   
   # Authentication (optional - defaults shown)
   # APP_AUTHENTICATION__ENABLED=true
   # APP_AUTHENTICATION__REQUIRE_AUTH=true
   ```

### Authentication Setup

This agent includes enterprise-grade Azure AD authentication:

**Features:**
- ✅ Azure Container Apps Easy Authentication integration
- ✅ Automatic user identity extraction
- ✅ Bayer Appendix B compliant security headers
- ✅ OAuth 2.0 token passthrough for API calls
- ✅ Public path exemptions (health checks, docs)

**Configuration:**

Authentication is **enabled by default** in production. To disable for local development:

```env
APP_AUTHENTICATION__ENABLED=false
```

**User Identity:**

When authenticated, `request.state.user` contains:

```python
{
    "user_id": "azure-ad-oid",
    "email": "user@bayer.com",
    "name": "User Name",
    "tenant_id": "fcb2b37b-5da0-466b-9b83-0014b67a7c78",
    "authenticated": True
}
```

**Custom Handlers:**

Access user identity in your handlers:

```python
@app.post("/api/custom")
async def custom_handler(request: Request):
    user = request.state.user
    logger.info(f"Request from: {user['email']}")
    # ... your logic
```

For detailed documentation, see the [SDK Authentication Guide](../agentic_ai_sdk/docs/authentication.md).

### Run the Agent

```powershell
# Quick development mode (recommended)
agenticai dev .

# Or run with specific options
agenticai run . --port 8000

# Run in Docker
agenticai build .
agenticai run . --mode docker
```

**Note:** This agent uses the [agenticai CLI](../agentic_ai_cli) for development and deployment.

### Debugging

When running in dev mode, the debugger is automatically enabled on port 5678:

1. **Start the agent:**
   ```powershell
   agenticai dev .
   ```

2. **Attach VS Code debugger:**
   - Press `F5` or go to **Run and Debug**
   - Select "Attach to Agent (port 5678)"
   - Set breakpoints in your code

The agent starts immediately—you can attach/detach the debugger anytime without blocking the server.

---

## �️ CLI Tools

This template includes a built-in CLI for infrastructure and operations management.

### Infrastructure as Code (IaC)

Manage Terraform infrastructure with ease:

```bash
# Full workflow (init -> validate -> plan -> apply)
liscence-optimizer-cli iac

# Stop at plan to review changes
liscence-optimizer-cli iac --last-step plan

# Only initialize
liscence-optimizer-cli iac --last-step init

# Auto-approve for CI/CD
liscence-optimizer-cli iac --auto-approve

# Use custom variables file
liscence-optimizer-cli iac --var-file prod.tfvars

# Destroy infrastructure
liscence-optimizer-cli iac --destroy --auto-approve

# Dry run (show commands without executing)
liscence-optimizer-cli iac --dry-run
```

See [terraform/README.md](terraform/README.md) for detailed infrastructure documentation.

---

## 📦 Project Structure

```
liscence-optimizer/
├── a2a_server.py              # A2A server entry point
├── __main__.py                # Python module entry
├── __init__.py                # Package initialization
├── pyproject.toml             # Dependencies and project metadata
├── Dockerfile                 # Container build configuration
├── README.md                  # This file
│
├── cli/                       # CLI tools
│   ├── main.py                # CLI entry point
│   ├── commands/
│   │   └── iac.py             # Infrastructure as Code commands
│   └── __main__.py
│
├── terraform/                 # Infrastructure as Code
│   ├── main.tf                # Main Terraform configuration
│   ├── variables.tf           # Input variables
│   ├── outputs.tf             # Output values
│   ├── resources.tf           # Azure resources
│   └── README.md              # Infrastructure documentation
│
├── configs/
│   ├── config.yaml            # Local development config
│   └── config.prod.yaml       # Production config (optional)
│
├── tools/
│   ├── __init__.py
│   └── example_tool.py        # Example tool (customize as needed)
│
├── .agenticai.yaml            # Agent configuration for CLI
├── .env.example               # Environment template
├── .env.development           # Dev environment (gitignored)
└── .gitignore                 # Git ignore rules
```

---

## 🛠️ Available Tools

### Example Tool

Add your custom tools in the `tools/` directory. Each tool should:
- Register with `@tool_registry.register` decorator
- Implement the tool interface from AgenticAI SDK
- Be imported in `tools/__init__.py`

---

## 🔧 Development

```powershell
# Run with hot reload
agenticai dev .

# Run tests
pytest

# Format code
black .
ruff check .
```

---

## 🐳 Docker Deployment

### Dockerfile Features

The included [Dockerfile](Dockerfile) follows enterprise best practices:

**Multi-Stage Build:**
- 🏗️ **Builder Stage**: Installs dependencies with `uv` (10-100x faster than pip)
- 🚀 **Runtime Stage**: Minimal production image with only necessary files

**Security:**
- 🔒 Non-root user (`appuser`, UID 1000)
- 🔐 Minimal attack surface
- ✅ Health checks built-in (30s interval, 10s timeout, 5s start period)

**Performance:**
- ⚡ Fast builds with `uv` package manager from `ghcr.io/astral-sh/uv:latest`
- 📦 Optimized layer caching
- 🎯 37% smaller images compared to previous version

**Debug Support:**
- 🐛 Optional debugpy for remote debugging (install with `[debug]` extra)
- Configurable via `DEBUGPY_ENABLED` environment variable

### Building and Running

```powershell
# Build image using CLI (recommended)
agenticai build .

# Or build directly with Docker
docker build -t liscence-optimizer:latest .

# Run container using CLI
agenticai run . --mode docker

# Or run directly with Docker
docker run -p 8000:8000 \
  --env-file .env.development \
  liscence-optimizer:latest

# Run with debugging enabled
docker run -p 8000:8000 -p 5678:5678 \
  -e DEBUGPY_ENABLED=true \
  --env-file .env.development \
  liscence-optimizer:latest
```

### Health Check

The container includes a health check that verifies the A2A server is responding:

```powershell
# Check container health
docker ps

# View health check logs
docker inspect --format='{{json .State.Health}}' <container-id>
```

### What Gets Excluded (.dockerignore)

The following files/directories are excluded from the Docker image:
- Tests (`tests/`, `__pycache__/`, `*.pyc`)
- Documentation (`docs/`, `*.md` except README.md)
- Development files (`.venv/`, `.git/`, `.vscode/`)
- Terraform files (`terraform/`)
- Build artifacts (`dist/`, `*.egg-info/`)

See [`.dockerignore`](.dockerignore) for the complete list.

---

## 📚 Documentation

- **AgenticAI SDK**: [GitHub](https://github.com/bayer-int/agentic_ai_sdk)
- **AgenticAI CLI**: [../agentic_ai_cli](../agentic_ai_cli)

---

## 📝 License

MIT License

---

**Version:** 0.1.0  
**Author:** ishaan <ishaan.bhata.ext@bayer.com>