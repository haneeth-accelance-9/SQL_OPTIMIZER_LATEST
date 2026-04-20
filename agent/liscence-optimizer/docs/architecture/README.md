# Phased Orchestrator Architecture

This document describes the architecture, design patterns, and technical implementation of the Phased Orchestrator Agent Template.

## 📋 Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Workflow Engine](#workflow-engine)
- [State Management](#state-management)
- [A2A Protocol](#a2a-protocol)
- [Tool System](#tool-system)
- [LLM Integration](#llm-integration)
- [Security](#security)
- [Deployment Architecture](#deployment-architecture)

---

## Overview

The Phased Orchestrator template implements a **multi-phase workflow execution engine** that orchestrates complex tasks through sequential phases, each with its own logic, tools, and state management.

### Design Principles

1. **Phase Isolation**: Each phase is independent and testable
2. **State Persistence**: Workflow state is preserved across phases
3. **Error Recovery**: Automatic retry and error handling
4. **Observability**: Comprehensive logging and telemetry
5. **Scalability**: Horizontal scaling with stateless design
6. **Extensibility**: Easy to add new phases and tools

---

## System Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        Client[Client/Other Agent]
    end
    
    subgraph "API Layer"
        A2A[A2A Server<br/>FastAPI]
    end
    
    subgraph "Orchestration Layer"
        WE[Workflow Engine]
        PM[Phase Manager]
        TM[Transition Manager]
    end
    
    subgraph "Execution Layer"
        P1[Phase 1<br/>Analysis]
        P2[Phase 2<br/>Planning]
        P3[Phase 3<br/>Execution]
        P4[Phase 4<br/>Validation]
    end
    
    subgraph "Tool Layer"
        TR[Tool Registry]
        T1[Custom Tool 1]
        T2[Custom Tool 2]
        T3[Custom Tool 3]
    end
    
    subgraph "LLM Layer"
        LLM[Azure OpenAI]
        Gateway[LLM Gateway]
    end
    
    subgraph "Storage Layer"
        Cosmos[(Azure Cosmos DB<br/>State Store)]
        Memory[Conversation Memory]
    end
    
    subgraph "Observability Layer"
        AppInsights[Application Insights]
        Metrics[Metrics]
        Traces[Distributed Traces]
    end
    
    Client -->|A2A Request| A2A
    A2A -->|Initiate Workflow| WE
    WE -->|Manage Phases| PM
    PM -->|Execute| P1
    P1 -->|Transition| P2
    P2 -->|Transition| P3
    P3 -->|Transition| P4
    
    P1 -.->|Use Tools| TR
    P2 -.->|Use Tools| TR
    P3 -.->|Use Tools| TR
    P4 -.->|Use Tools| TR
    
    TR --> T1
    TR --> T2
    TR --> T3
    
    WE -->|LLM Calls| Gateway
    Gateway -->|API| LLM
    
    WE -->|Save State| Cosmos
    WE -->|Load State| Cosmos
    Cosmos --> Memory
    
    WE -.->|Telemetry| AppInsights
    PM -.->|Metrics| Metrics
    TM -.->|Traces| Traces
    
    A2A -->|Response| Client
```

### Component Overview

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| **A2A Server** | API endpoint for agent communication | FastAPI |
| **Workflow Engine** | Orchestrates phase execution | Custom Python |
| **Phase Manager** | Manages phase lifecycle | AgenticAI SDK |
| **Tool Registry** | Manages and executes tools | AgenticAI SDK |
| **LLM Gateway** | Routes LLM requests | Azure OpenAI |
| **State Store** | Persists workflow state | Azure Cosmos DB |
| **Observability** | Monitoring and tracing | Application Insights |

---

## Workflow Engine

The workflow engine orchestrates the execution of multiple phases in sequence.

### Phase Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Pending: Workflow Created
    Pending --> Running: Phase Started
    Running --> Executing: Processing
    Executing --> Completed: Success
    Executing --> Failed: Error
    Completed --> Running: Next Phase
    Failed --> Retrying: Retry Available
    Retrying --> Running: Retry Attempt
    Failed --> Terminated: Max Retries
    Completed --> [*]: All Phases Done
    Terminated --> [*]: Workflow Failed
```

### Key Concepts

#### Phase Definition

Each phase represents a discrete step in the workflow:

```python
class Phase:
    """Represents a workflow phase."""
    
    def __init__(
        self,
        name: str,
        handler: Callable,
        retry_policy: RetryPolicy,
        timeout: int = 300
    ):
        self.name = name
        self.handler = handler
        self.retry_policy = retry_policy
        self.timeout = timeout
        
    async def execute(self, context: PhaseContext) -> PhaseResult:
        """Execute the phase with context."""
        pass
```

#### Phase Context

Shared state passed between phases:

```python
@dataclass
class PhaseContext:
    """Context shared across phases."""
    workflow_id: str
    current_phase: str
    state: Dict[str, Any]
    metadata: Dict[str, Any]
    previous_results: List[PhaseResult]
```

#### Phase Transitions

Control flow between phases:

```python
class TransitionManager:
    """Manages phase transitions."""
    
    def determine_next_phase(
        self,
        current: Phase,
        result: PhaseResult,
        context: PhaseContext
    ) -> Optional[Phase]:
        """Determine the next phase based on result."""
        # Conditional logic
        if result.status == "completed":
            return self.get_next_sequential_phase(current)
        elif result.status == "retry":
            return current  # Retry same phase
        else:
            return None  # Terminate workflow
```

### Execution Flow

1. **Initialization**: Create workflow context
2. **Phase Selection**: Select first phase
3. **Pre-Execution**: Load phase dependencies
4. **Execution**: Run phase handler
5. **Post-Execution**: Save phase result
6. **Transition**: Determine next phase
7. **Repeat**: Continue until complete or failed

---

## State Management

State management ensures workflow continuity across phases and system restarts.

### State Architecture

```mermaid
graph LR
    subgraph "In-Memory State"
        Context[Phase Context]
        Cache[Result Cache]
    end
    
    subgraph "Persistent State"
        Cosmos[(Cosmos DB)]
        Container[Workflow Container]
    end
    
    subgraph "State Operations"
        Save[Save State]
        Load[Load State]
        Query[Query State]
    end
    
    Context -->|Write| Save
    Save -->|Store| Container
    Container -->|Retrieve| Load
    Load -->|Read| Context
    Container -->|Search| Query
    Cache -.->|Evict| Container
```

### State Schema

```json
{
  "id": "workflow-uuid",
  "workflow_id": "wf-12345",
  "agent_id": "my-agent",
  "status": "running",
  "current_phase": "execution",
  "phases": [
    {
      "name": "analysis",
      "status": "completed",
      "started_at": "2024-01-15T10:00:00Z",
      "completed_at": "2024-01-15T10:02:30Z",
      "result": { }
    }
  ],
  "context": {
    "user_input": "...",
    "accumulated_data": { }
  },
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:05:00Z",
  "ttl": 86400
}
```

### State Operations

#### Save State

```python
async def save_workflow_state(
    workflow_id: str,
    context: PhaseContext,
    cosmos_client: CosmosClient
) -> None:
    """Persist workflow state to Cosmos DB."""
    container = cosmos_client.get_container("workflows")
    
    state_document = {
        "id": workflow_id,
        "workflow_id": workflow_id,
        "status": context.status,
        "current_phase": context.current_phase,
        "context": context.state,
        "updated_at": datetime.utcnow().isoformat()
    }
    
    await container.upsert_item(state_document)
```

#### Load State

```python
async def load_workflow_state(
    workflow_id: str,
    cosmos_client: CosmosClient
) -> Optional[PhaseContext]:
    """Retrieve workflow state from Cosmos DB."""
    container = cosmos_client.get_container("workflows")
    
    try:
        document = await container.read_item(
            item=workflow_id,
            partition_key=workflow_id
        )
        return PhaseContext.from_dict(document)
    except CosmosResourceNotFoundError:
        return None
```

---

## A2A Protocol

Agent-to-Agent protocol implementation for standardized communication.

### Protocol Architecture

```mermaid
sequenceDiagram
    participant Client as Client Agent
    participant Server as This Agent
    participant WE as Workflow Engine
    participant LLM as Azure OpenAI
    
    Client->>Server: POST /a2a/execute
    Note over Client,Server: A2A Request
    
    Server->>Server: Validate Request
    Server->>WE: Initialize Workflow
    
    loop For Each Phase
        WE->>WE: Execute Phase
        WE->>LLM: LLM Call (if needed)
        LLM-->>WE: Response
        WE->>WE: Save State
    end
    
    WE-->>Server: Workflow Complete
    Server-->>Client: A2A Response
    Note over Client,Server: Result + Metadata
```

### A2A Request Schema

```json
{
  "request_id": "req-uuid",
  "agent_id": "requesting-agent",
  "task": {
    "type": "workflow",
    "description": "Process quarterly data",
    "parameters": {
      "quarter": "Q4",
      "year": 2024
    }
  },
  "context": {
    "conversation_id": "conv-123",
    "user_id": "user-456"
  },
  "metadata": {
    "priority": "high",
    "deadline": "2024-01-20T18:00:00Z"
  }
}
```

### A2A Response Schema

```json
{
  "request_id": "req-uuid",
  "workflow_id": "wf-12345",
  "status": "completed",
  "result": {
    "summary": "Quarterly analysis complete",
    "phases_executed": ["analysis", "planning", "execution", "validation"],
    "output": { }
  },
  "execution_time_ms": 2547,
  "metadata": {
    "agent_version": "1.0.0",
    "timestamp": "2024-01-15T10:05:47Z"
  }
}
```

---

## Tool System

Extensible tool system for adding custom capabilities.

### Tool Architecture

```mermaid
graph TB
    subgraph "Tool Registry"
        Registry[Tool Registry]
        Loader[Tool Loader]
    end
    
    subgraph "Tool Definitions"
        T1[Read File Tool]
        T2[Export Report Tool]
        T3[Custom Tool]
    end
    
    subgraph "Tool Execution"
        Executor[Tool Executor]
        Validator[Input Validator]
        Monitor[Performance Monitor]
    end
    
    subgraph "Phase Handlers"
        Phase[Phase Handler]
    end
    
    Loader -->|Discover| T1
    Loader -->|Discover| T2
    Loader -->|Discover| T3
    
    T1 -->|Register| Registry
    T2 -->|Register| Registry
    T3 -->|Register| Registry
    
    Phase -->|Request Tool| Registry
    Registry -->|Invoke| Executor
    Executor -->|Validate| Validator
    Executor -->|Execute| T1
    Executor -.->|Track| Monitor
```

### Tool Interface

```python
from agenticai.tools import tool_registry, Tool

@tool_registry.register
class CustomTool(Tool):
    """Custom tool for domain-specific operations."""
    
    name: str = "custom_tool"
    description: str = "Performs custom operation"
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool with given parameters."""
        # Tool logic here
        return {"status": "success", "data": result}
    
    def validate_input(self, **kwargs) -> bool:
        """Validate input parameters."""
        required_params = ["param1", "param2"]
        return all(p in kwargs for p in required_params)
```

---

## LLM Integration

Azure OpenAI integration for intelligent processing.

### LLM Gateway Pattern

```mermaid
graph LR
    Phase[Phase Handler] -->|Request| Gateway[LLM Gateway]
    Gateway -->|Route| Cache{Response Cache}
    Cache -->|Hit| Return[Return Cached]
    Cache -->|Miss| OpenAI[Azure OpenAI]
    OpenAI -->|Response| Store[Store in Cache]
    Store --> Return
    Return -->|Response| Phase
```

### Prompt Engineering

Templates for consistent LLM interactions:

```python
PHASE_ANALYSIS_PROMPT = """
You are analyzing {task_description}.

Context:
{context}

Previous Results:
{previous_results}

Perform a thorough analysis and provide:
1. Key findings
2. Identified patterns
3. Recommendations for next phase

Output as JSON.
"""
```

---

## Security

Security considerations and best practices.

### Authentication & Authorization

- **Azure Managed Identity**: For Azure service authentication
- **API Keys**: Secured in Azure Key Vault
- **RBAC**: Role-based access control for API endpoints

### Data Protection

- **Encryption at Rest**: Cosmos DB encryption
- **Encryption in Transit**: TLS 1.2+ for all connections
- **Secrets Management**: Azure Key Vault integration
- **PII Handling**: Automatic redaction in logs

### Network Security

- **Virtual Network**: Deploy within VNet
- **Private Endpoints**: Private connectivity to Azure services
- **NSG Rules**: Restrict inbound/outbound traffic

---

## Deployment Architecture

Azure deployment architecture for production.

```mermaid
graph TB
    subgraph "Azure Cloud"
        subgraph "Container Apps Environment"
            CA1[Container App<br/>Instance 1]
            CA2[Container App<br/>Instance 2]
            CA3[Container App<br/>Instance 3]
        end
        
        subgraph "Data Layer"
            Cosmos[(Cosmos DB)]
            KeyVault[Key Vault]
        end
        
        subgraph "AI Services"
            OpenAI[Azure OpenAI]
        end
        
        subgraph "Monitoring"
            AppInsights[Application Insights]
            LogAnalytics[Log Analytics]
        end
        
        LB[Load Balancer] --> CA1
        LB --> CA2
        LB --> CA3
        
        CA1 --> Cosmos
        CA2 --> Cosmos
        CA3 --> Cosmos
        
        CA1 --> OpenAI
        CA2 --> OpenAI
        CA3 --> OpenAI
        
        CA1 -.-> AppInsights
        CA2 -.-> AppInsights
        CA3 -.-> AppInsights
        
        CA1 -.-> KeyVault
        CA2 -.-> KeyVault
        CA3 -.-> KeyVault
        
        AppInsights --> LogAnalytics
    end
    
    Internet[Internet] --> LB
```

### Key Components

- **Azure Container Apps**: Serverless container hosting
- **Azure Cosmos DB**: NoSQL database for state
- **Azure OpenAI**: LLM processing
- **Application Insights**: Monitoring and diagnostics
- **Key Vault**: Secrets management
- **Virtual Network**: Network isolation

---

## Performance Considerations

### Optimization Strategies

1. **Phase Parallelization**: Execute independent phases concurrently
2. **Response Caching**: Cache LLM responses for common queries
3. **Connection Pooling**: Reuse database connections
4. **Lazy Loading**: Load tools only when needed
5. **Batch Processing**: Group multiple operations

### Scaling Patterns

- **Horizontal Scaling**: Add more container instances
- **Partitioning**: Partition workflows by ID
- **Read Replicas**: Use Cosmos DB read replicas
- **CDN**: Cache static responses

---

## Monitoring & Observability

### Metrics

- Phase execution time
- Workflow success/failure rate
- LLM token usage
- Database query performance

### Distributed Tracing

OpenTelemetry integration for end-to-end tracing across phases.

### Alerting

- Phase failures exceed threshold
- LLM rate limiting
- Database connection failures
- High latency alerts

---

## Related Documentation

- [API Reference](../api-reference/README.md) - Detailed API documentation
- [Deployment Guide](../guides/deployment.md) - Production deployment
- [Examples](../examples/README.md) - Architecture patterns in action

---

**Last Updated**: December 2025
