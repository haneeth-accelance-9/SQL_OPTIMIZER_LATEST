# Phased Orchestrator API Reference

Complete API reference for the Phased Orchestrator Agent Template.

## 📋 Table of Contents

- [A2A Server API](#a2a-server-api)
- [Workflow Engine](#workflow-engine)
- [Phase System](#phase-system)
- [Tool System](#tool-system)
- [State Management](#state-management)
- [Configuration](#configuration)
- [CLI Commands](#cli-commands)

---

## A2A Server API

The Agent-to-Agent (A2A) server provides HTTP endpoints for agent communication.

### Server Initialization

```python
from agenticai.a2a import A2AServer
from agenticai.config import Settings

# Initialize server
server = A2AServer(
    agent_name="my-workflow-agent",
    settings=Settings.from_env()
)

# Register workflow handler
@server.route("/a2a/execute")
async def execute_workflow(request: A2ARequest) -> A2AResponse:
    """Handle workflow execution request."""
    workflow = WorkflowEngine(request)
    result = await workflow.execute()
    return A2AResponse(result=result)
```

### Endpoints

#### POST /a2a/execute

Execute a workflow.

**Request:**
```python
class A2ARequest(BaseModel):
    """A2A execution request."""
    request_id: str
    agent_id: str
    task: TaskDefinition
    context: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
```

**Response:**
```python
class A2AResponse(BaseModel):
    """A2A execution response."""
    request_id: str
    workflow_id: str
    status: Literal["completed", "failed", "running"]
    result: Dict[str, Any]
    execution_time_ms: int
    metadata: Dict[str, Any]
```

**Example:**
```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/a2a/execute",
        json={
            "request_id": "req-123",
            "agent_id": "caller-agent",
            "task": {
                "type": "analysis",
                "description": "Analyze Q4 data",
                "parameters": {"quarter": "Q4", "year": 2024}
            }
        }
    )
    result = response.json()
```

#### GET /health

Health check endpoint.

**Response:**
```python
class HealthResponse(BaseModel):
    """Health check response."""
    status: Literal["healthy", "unhealthy"]
    agent: str
    version: str
    timestamp: str
```

#### GET /metrics

Prometheus-compatible metrics endpoint.

**Response:** Prometheus format metrics

---

## Workflow Engine

Core workflow orchestration engine.

### WorkflowEngine Class

```python
class WorkflowEngine:
    """Orchestrates multi-phase workflow execution."""
    
    def __init__(
        self,
        workflow_id: str,
        phases: List[Phase],
        context: PhaseContext,
        settings: WorkflowSettings
    ):
        """Initialize workflow engine."""
        self.workflow_id = workflow_id
        self.phases = phases
        self.context = context
        self.settings = settings
        self.state_manager = StateManager()
        
    async def execute(self) -> WorkflowResult:
        """Execute all phases in sequence."""
        for phase in self.phases:
            result = await self.execute_phase(phase)
            if result.status == "failed":
                return self.handle_failure(phase, result)
        return WorkflowResult(status="completed")
    
    async def execute_phase(self, phase: Phase) -> PhaseResult:
        """Execute a single phase."""
        try:
            # Pre-execution
            await self.prepare_phase(phase)
            
            # Execute
            result = await phase.handler(self.context)
            
            # Post-execution
            await self.finalize_phase(phase, result)
            
            return result
        except Exception as e:
            return self.handle_phase_error(phase, e)
```

### Methods

#### execute()

```python
async def execute(self) -> WorkflowResult:
    """
    Execute the complete workflow.
    
    Returns:
        WorkflowResult: Result of workflow execution
        
    Raises:
        WorkflowExecutionError: If workflow fails
    """
```

#### execute_phase()

```python
async def execute_phase(self, phase: Phase) -> PhaseResult:
    """
    Execute a single phase.
    
    Args:
        phase: Phase to execute
        
    Returns:
        PhaseResult: Result of phase execution
    """
```

#### save_checkpoint()

```python
async def save_checkpoint(self) -> None:
    """
    Save workflow checkpoint to persistent storage.
    
    Allows resuming workflow after failure or restart.
    """
```

#### resume_from_checkpoint()

```python
async def resume_from_checkpoint(
    workflow_id: str
) -> Optional[WorkflowEngine]:
    """
    Resume workflow from saved checkpoint.
    
    Args:
        workflow_id: ID of workflow to resume
        
    Returns:
        WorkflowEngine instance or None if not found
    """
```

---

## Phase System

Phase definition and execution system.

### Phase Class

```python
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass
class Phase:
    """Represents a workflow phase."""
    
    name: str
    description: str
    handler: Callable[[PhaseContext], PhaseResult]
    retry_policy: Optional[RetryPolicy] = None
    timeout: int = 300  # seconds
    dependencies: List[str] = None
    
    async def execute(
        self,
        context: PhaseContext
    ) -> PhaseResult:
        """
        Execute the phase.
        
        Args:
            context: Shared phase context
            
        Returns:
            PhaseResult with execution outcome
        """
        return await self.handler(context)
```

### Phase Definition

```python
def create_analysis_phase() -> Phase:
    """Create the analysis phase."""
    
    async def analyze(context: PhaseContext) -> PhaseResult:
        """Analyze input data."""
        data = context.state.get("input_data")
        
        # Perform analysis
        insights = await perform_analysis(data)
        
        # Update context
        context.state["insights"] = insights
        
        return PhaseResult(
            status="completed",
            data=insights,
            next_phase="planning"
        )
    
    return Phase(
        name="analysis",
        description="Analyze input data",
        handler=analyze,
        retry_policy=RetryPolicy(max_retries=3),
        timeout=180
    )
```

### PhaseContext

```python
@dataclass
class PhaseContext:
    """Shared context across phases."""
    
    workflow_id: str
    current_phase: str
    state: Dict[str, Any]
    metadata: Dict[str, Any]
    previous_results: List[PhaseResult]
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from state."""
        return self.state.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set value in state."""
        self.state[key] = value
    
    def append_result(self, result: PhaseResult) -> None:
        """Append phase result to history."""
        self.previous_results.append(result)
```

### PhaseResult

```python
@dataclass
class PhaseResult:
    """Result of phase execution."""
    
    status: Literal["completed", "failed", "retry"]
    data: Dict[str, Any]
    next_phase: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: int = 0
    
    def is_success(self) -> bool:
        """Check if phase succeeded."""
        return self.status == "completed"
```

### RetryPolicy

```python
@dataclass
class RetryPolicy:
    """Retry policy for phase execution."""
    
    max_retries: int = 3
    backoff_multiplier: float = 2.0
    initial_delay_ms: int = 1000
    max_delay_ms: int = 30000
    
    def calculate_delay(self, attempt: int) -> int:
        """Calculate delay for retry attempt."""
        delay = self.initial_delay_ms * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_delay_ms)
```

---

## Tool System

Tool registration and execution system.

### Tool Decorator

```python
from agenticai.tools import tool_registry

@tool_registry.register
async def read_file_tool(file_path: str) -> Dict[str, Any]:
    """
    Read content from a file.
    
    Args:
        file_path: Path to file to read
        
    Returns:
        Dict with file content
    """
    with open(file_path, 'r') as f:
        content = f.read()
    
    return {
        "status": "success",
        "content": content,
        "size": len(content)
    }
```

### Tool Class Interface

```python
from agenticai.tools import Tool
from pydantic import BaseModel, Field

class FileToolInput(BaseModel):
    """Input schema for file tool."""
    file_path: str = Field(..., description="Path to file")

class FileToolOutput(BaseModel):
    """Output schema for file tool."""
    status: str
    content: str
    size: int

@tool_registry.register
class ReadFileTool(Tool):
    """Tool for reading files."""
    
    name: str = "read_file"
    description: str = "Read content from a file"
    input_schema: Type[BaseModel] = FileToolInput
    output_schema: Type[BaseModel] = FileToolOutput
    
    async def execute(self, **kwargs) -> FileToolOutput:
        """Execute the tool."""
        file_path = kwargs["file_path"]
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        return FileToolOutput(
            status="success",
            content=content,
            size=len(content)
        )
```

### Tool Registry

```python
class ToolRegistry:
    """Registry for managing tools."""
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[Tool]:
        """Get tool by name."""
        return self._tools.get(name)
    
    def list(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
    
    async def execute(
        self,
        tool_name: str,
        **kwargs
    ) -> Any:
        """Execute a tool by name."""
        tool = self.get(tool_name)
        if not tool:
            raise ToolNotFoundError(f"Tool not found: {tool_name}")
        
        return await tool.execute(**kwargs)
```

---

## State Management

State persistence and retrieval system.

### StateManager Class

```python
from azure.cosmos.aio import CosmosClient

class StateManager:
    """Manages workflow state persistence."""
    
    def __init__(self, cosmos_client: CosmosClient):
        self.client = cosmos_client
        self.container = self.client.get_container("workflows")
    
    async def save_state(
        self,
        workflow_id: str,
        context: PhaseContext
    ) -> None:
        """
        Save workflow state to Cosmos DB.
        
        Args:
            workflow_id: Unique workflow identifier
            context: Phase context to persist
        """
        document = {
            "id": workflow_id,
            "workflow_id": workflow_id,
            "current_phase": context.current_phase,
            "state": context.state,
            "metadata": context.metadata,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        await self.container.upsert_item(document)
    
    async def load_state(
        self,
        workflow_id: str
    ) -> Optional[PhaseContext]:
        """
        Load workflow state from Cosmos DB.
        
        Args:
            workflow_id: Unique workflow identifier
            
        Returns:
            PhaseContext if found, None otherwise
        """
        try:
            document = await self.container.read_item(
                item=workflow_id,
                partition_key=workflow_id
            )
            return PhaseContext.from_dict(document)
        except CosmosResourceNotFoundError:
            return None
    
    async def delete_state(self, workflow_id: str) -> None:
        """Delete workflow state."""
        await self.container.delete_item(
            item=workflow_id,
            partition_key=workflow_id
        )
```

---

## Configuration

Configuration management with Pydantic Settings.

### Settings Class

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env.development",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    # Agent Configuration
    agent_name: str = Field(default="phased-agent")
    agent_version: str = Field(default="0.1.0")
    
    # Azure OpenAI
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment_name: str
    azure_openai_api_version: str = "2024-02-15-preview"
    
    # Azure Cosmos DB
    cosmosdb_endpoint: str
    cosmosdb_key: str
    cosmosdb_database_name: str = "agenticai"
    cosmosdb_container_name: str = "workflows"
    
    # Application Insights
    applicationinsights_connection_string: str = ""
    applicationinsights_enabled: bool = True
    
    # Workflow Settings
    workflow_max_retries: int = 3
    workflow_timeout: int = 300
    phase_timeout: int = 180
    
    # Logging
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment."""
        return cls()
```

---

## CLI Commands

Built-in CLI commands for operations and infrastructure management.

### Infrastructure Commands

#### iac

Manage Terraform infrastructure.

```bash
# Full workflow (init -> validate -> plan -> apply)
{agent-name}-cli iac

# Stop at plan to review changes
{agent-name}-cli iac --last-step plan

# Auto-approve for CI/CD
{agent-name}-cli iac --auto-approve

# Use custom variables file
{agent-name}-cli iac --var-file prod.tfvars

# Destroy infrastructure
{agent-name}-cli iac --destroy --auto-approve

# Dry run (show commands without executing)
{agent-name}-cli iac --dry-run
```

**Options:**
- `--last-step`: Stop at specific step (init, validate, plan, apply)
- `--auto-approve`: Skip approval prompts
- `--var-file`: Custom Terraform variables file
- `--destroy`: Destroy infrastructure
- `--dry-run`: Show commands without execution

### Command Implementation

```python
import click
from cli.commands.iac import iac_command

@click.group()
def cli():
    """Agent CLI commands."""
    pass

cli.add_command(iac_command, name="iac")

if __name__ == "__main__":
    cli()
```

---

## Data Models

### WorkflowResult

```python
@dataclass
class WorkflowResult:
    """Result of complete workflow execution."""
    
    workflow_id: str
    status: Literal["completed", "failed"]
    phases_executed: List[str]
    total_execution_time_ms: int
    output: Dict[str, Any]
    errors: List[str] = None
```

### TaskDefinition

```python
class TaskDefinition(BaseModel):
    """Definition of a task to execute."""
    
    type: str = Field(..., description="Type of task")
    description: str = Field(..., description="Task description")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=1, ge=1, le=10)
```

---

## Error Handling

### Exception Hierarchy

```python
class WorkflowError(Exception):
    """Base exception for workflow errors."""
    pass

class PhaseExecutionError(WorkflowError):
    """Phase execution failed."""
    pass

class ToolExecutionError(WorkflowError):
    """Tool execution failed."""
    pass

class StateManagementError(WorkflowError):
    """State persistence/retrieval failed."""
    pass

class ConfigurationError(WorkflowError):
    """Invalid configuration."""
    pass
```

---

## Type Definitions

```python
from typing import TypeAlias, Literal

PhaseStatus: TypeAlias = Literal["pending", "running", "completed", "failed"]
WorkflowStatus: TypeAlias = Literal["pending", "running", "completed", "failed"]
ToolStatus: TypeAlias = Literal["success", "failure"]
```

---

## Related Documentation

- [Architecture](../architecture/README.md) - System architecture
- [Examples](../examples/README.md) - Usage examples
- [Guides](../guides/README.md) - How-to guides

---

**Last Updated**: December 2025
