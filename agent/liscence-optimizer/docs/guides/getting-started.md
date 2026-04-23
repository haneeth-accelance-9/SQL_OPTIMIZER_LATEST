# Getting Started with Phased Orchestrator Agent

This guide will help you create, configure, and run your first phased orchestrator agent.

## 📋 Prerequisites

Before you begin, ensure you have:

- **Python 3.11+** installed
- **UV package manager** (`pip install uv`)
- **Azure OpenAI** access with API key or Managed Identity
- **Azure Cosmos DB** instance (for conversation memory)
- **Visual Studio Code** (recommended for debugging)
- **Docker** (optional, for containerized deployment)

## 🚀 Step 1: Create Your Agent

### Option A: Using AgenticAI CLI (Recommended)

```powershell
# Install the AgenticAI CLI
pip install agenticai-cli

# Create a new agent from the phased orchestrator template
agenticai scaffold phased-orchestrator my-workflow-agent

# Navigate to your new agent
cd my-workflow-agent
```

### Option B: Clone Template Manually

```powershell
# Clone the template repository
git clone https://github.com/bayer-int/agentic_ai_template_phased_orchestrator my-workflow-agent

# Navigate to the directory
cd my-workflow-agent

# Update placeholders in template files
# Replace LiscenceOptimizer, liscence-optimizer, etc.
```

## 🔧 Step 2: Install Dependencies

```powershell
# Create and activate virtual environment (optional but recommended)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install the agent in editable mode with development dependencies
uv pip install -e ".[dev]"
```

This installs:
- **agenticai**: Core AgenticAI SDK
- **fastapi**: Web framework for A2A server
- **azure-cosmos**: Cosmos DB integration
- **azure-monitor-opentelemetry**: Observability
- Development tools: pytest, black, ruff, mypy

## ⚙️ Step 3: Configure Your Agent

### 1. Copy Environment Template

```powershell
Copy-Item .env.example .env.development
```

### 2. Edit `.env.development`

Open `.env.development` and configure your Azure services:

```env
# === Azure OpenAI Configuration ===
AZURE_OPENAI_ENDPOINT=https://your-instance.openai.azure.com
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# === Azure Cosmos DB Configuration ===
COSMOSDB_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOSDB_KEY=your-cosmos-key-here
COSMOSDB_DATABASE_NAME=agenticai
COSMOSDB_CONTAINER_NAME=conversations

# === Application Insights (Optional) ===
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=xxx;IngestionEndpoint=xxx
APPLICATIONINSIGHTS_ENABLED=true

# === Agent Configuration ===
AGENT_NAME=my-workflow-agent
AGENT_VERSION=0.1.0
LOG_LEVEL=INFO
```

### 3. Configure Agent Settings

Edit `configs/config.yaml` for agent-specific settings:

```yaml
agent:
  name: "My Workflow Agent"
  description: "Orchestrates multi-phase workflows"
  version: "0.1.0"

llm:
  config:
    deployment_name: "${AZURE_OPENAI_DEPLOYMENT_NAME:gpt-5-mini}"
    api_version: "${AZURE_OPENAI_API_VERSION:2024-12-01-preview}"
    endpoint: "${AZURE_OPENAI_ENDPOINT}"
    api_key: "${AZURE_OPENAI_API_KEY}"
    timeout: 600
```

## 🏃 Step 4: Run Your Agent

### Development Mode (Recommended)

Development mode includes:
- Auto-reload on code changes
- Debugger enabled on port 5678
- Enhanced logging

```powershell
agenticai dev .
```

Output:
```
🚀 Starting agent in development mode...
🔍 Debugger ready on port 5678
📍 A2A Server running at http://localhost:8000
🔄 Watching for changes...
```

### Production Mode

```powershell
agenticai run . --port 8000
```

### Docker Mode

```powershell
# Build the Docker image
agenticai build .

# Run in Docker
agenticai run . --mode docker
```

## 🧪 Step 5: Test Your Agent

### Send a Test Request

Create a test file `test_request.json`:

```json
{
  "task": "Process quarterly sales data",
  "phases": ["analyze", "summarize", "report"],
  "data": {
    "quarter": "Q4",
    "year": 2024
  }
}
```

Send the request:

```powershell
# Using curl
curl -X POST http://localhost:8000/a2a/execute `
  -H "Content-Type: application/json" `
  -d @test_request.json

# Using PowerShell
$body = Get-Content test_request.json -Raw
Invoke-RestMethod -Uri "http://localhost:8000/a2a/execute" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

### Expected Response

```json
{
  "status": "completed",
  "result": {
    "phases_executed": ["analyze", "summarize", "report"],
    "output": "Quarterly report generated successfully"
  },
  "execution_time_ms": 2547
}
```

## 🐛 Step 6: Debug Your Agent

### Attach VS Code Debugger

1. **Start the agent in dev mode:**
   ```powershell
   agenticai dev .
   ```

2. **Set breakpoints** in your code (e.g., in phase handlers or tools)

3. **Attach debugger:**
   - Press `F5` in VS Code
   - Select "Attach to Agent (port 5678)"
   - Or use this launch configuration:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Attach to Agent",
      "type": "debugpy",
      "request": "attach",
      "connect": {
        "host": "localhost",
        "port": 5678
      },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}",
          "remoteRoot": "."
        }
      ]
    }
  ]
}
```

4. **Send requests** - breakpoints will trigger

5. **Detach/reattach** anytime without restarting the agent

## 📊 Step 7: Monitor Your Agent

### View Logs

```powershell
# Logs are output to console in dev mode
agenticai dev .

# In production, logs go to Application Insights
```

### Check Application Insights

1. Go to Azure Portal → Your Application Insights resource
2. Navigate to "Live Metrics" for real-time monitoring
3. Check "Failures" for errors
4. Review "Performance" for execution times

### Health Check

```powershell
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "agent": "my-workflow-agent",
  "version": "0.1.0"
}
```

## 🎯 Next Steps

Now that your agent is running:

1. **Define Custom Phases**: [Defining Phases Guide](defining-phases.md)
2. **Add Custom Tools**: [Adding Tools Guide](adding-tools.md)
3. **Manage State**: [State Management Guide](state-management.md)
4. **Deploy to Azure**: [Deployment Guide](deployment.md)

## 🔍 Common Issues

### Issue: Agent won't start

**Solution**: Check that all environment variables are set correctly:
```powershell
# Verify configuration
cat .env.development
```

### Issue: Connection to Cosmos DB fails

**Solution**: Verify Cosmos DB endpoint and key:
```powershell
# Test connection
curl https://your-cosmos.documents.azure.com:443/
```

### Issue: OpenAI API errors

**Solution**: Check your API key and deployment name:
```powershell
# Verify deployment exists
az cognitiveservices account deployment list `
  --name your-openai-resource `
  --resource-group your-rg
```

### Issue: Port 8000 already in use

**Solution**: Use a different port:
```powershell
agenticai run . --port 8080
```

## 📚 Additional Resources

- [Defining Phases](defining-phases.md) - Create multi-phase workflows
- [Adding Custom Tools](adding-tools.md) - Extend functionality
- [API Reference](../api-reference/README.md) - Complete API documentation
- [Examples](../examples/README.md) - Practical code examples

## 🆘 Getting Help

- **Issues**: Report bugs on GitHub
- **Discussions**: Ask questions in GitHub Discussions
- **Documentation**: Check other guides in this section

---

**Congratulations!** 🎉 You've successfully set up your first phased orchestrator agent. Continue to [Defining Phases](defining-phases.md) to build your workflow logic.