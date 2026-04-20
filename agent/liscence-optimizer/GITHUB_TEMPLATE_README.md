# Phased Orchestrator Template

> **GitHub Template Repository** for creating phased orchestration agents with multi-phase execution.

This template provides a complete structure for building agents with phased execution, Agent-to-Agent (A2A) communication, and Azure Container Apps deployment.

## Quick Start

### Option 1: Use GitHub Template (Recommended)

1. **Click "Use this template"** button above
2. Enter your new repository name
3. Go to **Actions** → **Setup from Template**
4. Click **Run workflow** and fill in:
   - Agent name (e.g., `finops-deferrals`)
   - Description
   - Port (default: 8000)
   - Version (default: 0.1.0)
5. Wait for workflow to complete
6. Clone and start developing!

### Option 2: Manual Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd <your-repo>

# Run setup script
python setup_template.py

# Install dependencies
pip install -e .

# Start developing
<agent-name>-cli --help
```

## What's Included

### 🎯 Core Features
- **Phased Execution**: Multi-phase orchestration with configurable phases
- **A2A Communication**: Agent-to-Agent protocol support
- **Azure Integration**: Container Apps deployment ready
- **CLI Tool**: Comprehensive command-line interface
- **Docker Support**: Container build and push commands
- **Infrastructure**: Terraform configurations for Azure

### 📁 Project Structure
```
├── src/                    # Agent source code
│   ├── a2a_server.py      # A2A protocol server
│   ├── tools/             # Agent tools
│   └── __main__.py        # Entry point
├── cli/                    # CLI commands
│   ├── commands/          # Docker, infra commands
│   └── main.py            # CLI entry point
├── configs/               # Configuration files
│   └── config.yaml        # Phase configuration
├── terraform/             # Infrastructure as Code
│   └── environments/      # test, staging, prod
├── tests/                 # Test suites
└── docs/                  # Documentation
```

### 🔧 Available Commands

After setup, your agent will have a CLI with these commands:

```bash
# Docker commands
<agent-name>-cli docker build    # Build container image
<agent-name>-cli docker push     # Push to registry
<agent-name>-cli docker login    # Login to Azure ACR

# Infrastructure commands
<agent-name>-cli infra init      # Initialize Terraform
<agent-name>-cli infra plan      # Plan infrastructure
<agent-name>-cli infra apply     # Deploy infrastructure
<agent-name>-cli infra destroy   # Destroy infrastructure
```

## Placeholders

These placeholders are automatically replaced during setup:

| Placeholder | Description | Example |
|------------|-------------|---------|
| `liscence-optimizer` | Agent name in kebab-case | `finops-deferrals` |
| `liscence_optimizer` | Agent name in snake_case | `finops_deferrals` |
| `LiscenceOptimizer` | Agent name in PascalCase | `FinOpsDeferrals` |
| `This agent creates executive summary or the results that are obtained by applying usecases on the data` | Short description | `Processes financial deferrals` |
| `0.1.0` | Version number | `0.1.0` |
| `8000` | Server port | `8000` |
| `ishaan` | Author name | `Your Name` |
| `ishaan.bhata.ext@bayer.com` | Author email | `your.email@example.com` |

See [.github/PLACEHOLDERS.md](.github/PLACEHOLDERS.md) for complete reference.

## Configuration

### Phase Configuration (`configs/config.yaml`)

Define your agent's phases:

```yaml
phases:
  - name: phase1
    description: "First phase description"
    tools:
      - tool1
      - tool2
  
  - name: phase2
    description: "Second phase description"
    tools:
      - tool3
```

### Environment Variables

Required for deployment:

- `AZURE_SUBSCRIPTION_ID`: Azure subscription
- `AZURE_TENANT_ID`: Azure tenant
- `AZURE_RESOURCE_GROUP`: Resource group name
- `CONTAINER_APPS_ENVIRONMENT`: Container Apps environment

## Development

### Local Development

```bash
# Install dependencies
pip install -e .

# Run agent locally
python -m src

# Run with debugger
python -m debugpy --listen 5678 -m src
```

### Testing

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=src tests/
```

### Docker

```bash
# Build image
docker build -t <agent-name>:latest .

# Run container
docker run -p 8000:8000 <agent-name>:latest
```

## Deployment

### Azure Container Apps

1. **Configure Azure credentials**
2. **Set environment variables**
3. **Deploy using CLI**:

```bash
# Initialize Terraform
<agent-name>-cli infra init

# Plan deployment
<agent-name>-cli infra plan --env test

# Deploy
<agent-name>-cli infra apply --env test
```

### CI/CD

The template includes GitHub Actions workflows:

- `.github/workflows/setup-from-template.yml`: Initial setup
- Add your own CI/CD workflows in `.github/workflows/`

## Troubleshooting

### Setup Issues

**Placeholders not replaced?**
- Check if you used GitHub Template workflow correctly
- Or run `python setup_template.py` manually

**Jinja2 errors?**
- Install jinja2: `pip install jinja2`
- Re-run setup script

### CLI Issues

**Command not found?**
- Reinstall: `pip install -e .`
- Check PATH includes Python scripts

## Support

- **Documentation**: See `docs/` directory
- **Examples**: Check `docs/guides/`
- **Issues**: Use GitHub Issues for bugs

## License

See LICENSE file for details.