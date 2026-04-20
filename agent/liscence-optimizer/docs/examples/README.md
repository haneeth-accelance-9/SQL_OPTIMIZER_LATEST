# Phased Orchestrator Examples

Practical examples demonstrating common patterns and use cases with the Phased Orchestrator Agent Template.

## 📋 Table of Contents

- [Quick Examples](#quick-examples)
- [Sequential Workflow](#sequential-workflow)
- [Conditional Phase Execution](#conditional-phase-execution)
- [Custom Tool Integration](#custom-tool-integration)
- [State Management](#state-management)
- [A2A Communication](#a2a-communication)
- [Error Handling](#error-handling)
- [Complete Workflow Example](#complete-workflow-example)

---

## Quick Examples

### 1. Simple Three-Phase Workflow

```python
from agenticai.workflow import WorkflowEngine, Phase, PhaseContext, PhaseResult

# Define phases
async def analysis_phase(context: PhaseContext) -> PhaseResult:
    """Analyze input data."""
    data = context.get("input_data")
    insights = {"key_findings": ["finding1", "finding2"]}
    context.set("insights", insights)
    return PhaseResult(status="completed", data=insights)

async def planning_phase(context: PhaseContext) -> PhaseResult:
    """Create execution plan."""
    insights = context.get("insights")
    plan = {"steps": ["step1", "step2", "step3"]}
    context.set("plan", plan)
    return PhaseResult(status="completed", data=plan)

async def execution_phase(context: PhaseContext) -> PhaseResult:
    """Execute the plan."""
    plan = context.get("plan")
    result = {"status": "executed", "steps_completed": len(plan["steps"])}
    return PhaseResult(status="completed", data=result)

# Create workflow
workflow = WorkflowEngine(
    workflow_id="wf-001",
    phases=[
        Phase("analysis", "Analyze data", analysis_phase),
        Phase("planning", "Create plan", planning_phase),
        Phase("execution", "Execute plan", execution_phase)
    ],
    context=PhaseContext(
        workflow_id="wf-001",
        current_phase="analysis",
        state={"input_data": {"quarter": "Q4"}},
        metadata={},
        previous_results=[]
    )
)

# Execute
result = await workflow.execute()
print(f"Workflow {result.status}: {result.output}")
```

### 2. Phase with Retry Policy

```python
from agenticai.workflow import Phase, RetryPolicy

phase = Phase(
    name="api_call",
    description="Call external API",
    handler=call_api_handler,
    retry_policy=RetryPolicy(
        max_retries=3,
        backoff_multiplier=2.0,
        initial_delay_ms=1000
    ),
    timeout=60
)
```

### 3. Register a Custom Tool

```python
from agenticai.tools import tool_registry

@tool_registry.register
async def calculate_metrics(data: dict) -> dict:
    """Calculate business metrics from data."""
    total = sum(data.values())
    average = total / len(data)
    return {
        "total": total,
        "average": average,
        "count": len(data)
    }
```

---

## Sequential Workflow

Complete example of a multi-phase data processing workflow.

```python
from typing import Dict, Any
from agenticai.workflow import WorkflowEngine, Phase, PhaseContext, PhaseResult
from agenticai.tools import tool_registry

# Phase 1: Data Collection
async def collect_data(context: PhaseContext) -> PhaseResult:
    """Collect data from various sources."""
    query = context.get("query")
    
    # Simulate data collection
    raw_data = {
        "source_a": [1, 2, 3, 4, 5],
        "source_b": [10, 20, 30, 40, 50],
        "source_c": [100, 200, 300, 400, 500]
    }
    
    context.set("raw_data", raw_data)
    
    return PhaseResult(
        status="completed",
        data={"records_collected": sum(len(v) for v in raw_data.values())},
        next_phase="validation"
    )

# Phase 2: Data Validation
async def validate_data(context: PhaseContext) -> PhaseResult:
    """Validate collected data."""
    raw_data = context.get("raw_data")
    
    # Validation logic
    validation_results = {
        "total_records": sum(len(v) for v in raw_data.values()),
        "sources_validated": len(raw_data),
        "errors": []
    }
    
    # Check for issues
    for source, data in raw_data.items():
        if not data:
            validation_results["errors"].append(f"Empty data from {source}")
    
    if validation_results["errors"]:
        return PhaseResult(
            status="failed",
            data=validation_results,
            error="Validation failed"
        )
    
    context.set("validated_data", raw_data)
    
    return PhaseResult(
        status="completed",
        data=validation_results,
        next_phase="processing"
    )

# Phase 3: Data Processing
async def process_data(context: PhaseContext) -> PhaseResult:
    """Process and transform data."""
    validated_data = context.get("validated_data")
    
    # Processing logic
    processed = {
        source: sum(values) 
        for source, values in validated_data.items()
    }
    
    context.set("processed_data", processed)
    
    return PhaseResult(
        status="completed",
        data=processed,
        next_phase="reporting"
    )

# Phase 4: Report Generation
async def generate_report(context: PhaseContext) -> PhaseResult:
    """Generate final report."""
    processed_data = context.get("processed_data")
    
    report = {
        "summary": {
            "total": sum(processed_data.values()),
            "by_source": processed_data
        },
        "metadata": {
            "workflow_id": context.workflow_id,
            "timestamp": "2024-01-15T10:00:00Z"
        }
    }
    
    context.set("final_report", report)
    
    return PhaseResult(
        status="completed",
        data=report
    )

# Create and execute workflow
async def run_data_workflow():
    """Run the complete data workflow."""
    workflow = WorkflowEngine(
        workflow_id="data-wf-001",
        phases=[
            Phase("collection", "Collect data", collect_data),
            Phase("validation", "Validate data", validate_data),
            Phase("processing", "Process data", process_data),
            Phase("reporting", "Generate report", generate_report)
        ],
        context=PhaseContext(
            workflow_id="data-wf-001",
            current_phase="collection",
            state={"query": "Q4 2024 data"},
            metadata={"user_id": "user-123"},
            previous_results=[]
        )
    )
    
    result = await workflow.execute()
    return result

# Run it
if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_data_workflow())
    print(f"Workflow completed: {result.output}")
```

---

## Conditional Phase Execution

Example showing conditional logic for phase transitions.

```python
async def analysis_phase(context: PhaseContext) -> PhaseResult:
    """Analyze data and determine next steps."""
    data = context.get("input_data")
    
    # Perform analysis
    analysis = {"complexity": "high" if len(data) > 100 else "low"}
    context.set("analysis", analysis)
    
    # Conditional transition
    if analysis["complexity"] == "high":
        next_phase = "detailed_planning"
    else:
        next_phase = "simple_execution"
    
    return PhaseResult(
        status="completed",
        data=analysis,
        next_phase=next_phase
    )

# Alternative approach: Transition Manager
class CustomTransitionManager:
    """Manages conditional phase transitions."""
    
    def determine_next_phase(
        self,
        current_phase: str,
        result: PhaseResult,
        context: PhaseContext
    ) -> Optional[str]:
        """Determine next phase based on results."""
        
        if current_phase == "analysis":
            complexity = context.get("analysis", {}).get("complexity")
            if complexity == "high":
                return "detailed_planning"
            else:
                return "simple_execution"
        
        elif current_phase in ["detailed_planning", "simple_execution"]:
            return "validation"
        
        elif current_phase == "validation":
            if result.is_success():
                return "completion"
            else:
                return "error_handling"
        
        return None  # End workflow
```

---

## Custom Tool Integration

Examples of creating and using custom tools.

### File Operation Tool

```python
from agenticai.tools import Tool, tool_registry
from pydantic import BaseModel, Field
from pathlib import Path

class FileReadInput(BaseModel):
    """Input for file read tool."""
    file_path: str = Field(..., description="Path to file")
    encoding: str = Field(default="utf-8", description="File encoding")

class FileReadOutput(BaseModel):
    """Output from file read tool."""
    status: str
    content: str
    size: int
    lines: int

@tool_registry.register
class ReadFileTool(Tool):
    """Tool for reading files."""
    
    name = "read_file"
    description = "Read content from a file"
    input_schema = FileReadInput
    output_schema = FileReadOutput
    
    async def execute(self, **kwargs) -> FileReadOutput:
        """Execute file read."""
        file_path = kwargs["file_path"]
        encoding = kwargs.get("encoding", "utf-8")
        
        path = Path(file_path)
        if not path.exists():
            return FileReadOutput(
                status="error",
                content="",
                size=0,
                lines=0
            )
        
        content = path.read_text(encoding=encoding)
        lines = content.count('\n') + 1
        
        return FileReadOutput(
            status="success",
            content=content,
            size=len(content),
            lines=lines
        )

# Use in phase
async def read_config_phase(context: PhaseContext) -> PhaseResult:
    """Read configuration file."""
    config_path = context.get("config_path")
    
    # Execute tool
    result = await tool_registry.execute(
        "read_file",
        file_path=config_path
    )
    
    if result.status == "success":
        context.set("config_content", result.content)
        return PhaseResult(status="completed", data=result.dict())
    else:
        return PhaseResult(status="failed", error="Config read failed")
```

### API Integration Tool

```python
import httpx
from agenticai.tools import tool_registry

@tool_registry.register
async def call_external_api(
    endpoint: str,
    method: str = "GET",
    data: dict = None
) -> dict:
    """Call an external REST API."""
    
    async with httpx.AsyncClient() as client:
        if method == "GET":
            response = await client.get(endpoint)
        elif method == "POST":
            response = await client.post(endpoint, json=data)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        return {
            "status_code": response.status_code,
            "data": response.json() if response.status_code == 200 else None,
            "error": None if response.status_code == 200 else response.text
        }

# Use in workflow
async def fetch_data_phase(context: PhaseContext) -> PhaseResult:
    """Fetch data from external API."""
    api_url = context.get("api_url")
    
    result = await tool_registry.execute(
        "call_external_api",
        endpoint=api_url,
        method="GET"
    )
    
    if result["status_code"] == 200:
        context.set("api_data", result["data"])
        return PhaseResult(status="completed", data=result["data"])
    else:
        return PhaseResult(
            status="failed",
            error=f"API call failed: {result['error']}"
        )
```

---

## State Management

Examples of working with workflow state.

```python
from agenticai.state import StateManager
from azure.cosmos.aio import CosmosClient

# Initialize state manager
cosmos_client = CosmosClient(endpoint, credential)
state_manager = StateManager(cosmos_client)

# Save state during workflow
async def processing_phase(context: PhaseContext) -> PhaseResult:
    """Process data and save intermediate state."""
    
    # Process data
    results = await process_data(context.get("input"))
    context.set("intermediate_results", results)
    
    # Save checkpoint
    await state_manager.save_state(context.workflow_id, context)
    
    return PhaseResult(status="completed", data=results)

# Resume workflow from saved state
async def resume_workflow(workflow_id: str):
    """Resume a workflow from saved state."""
    
    # Load state
    context = await state_manager.load_state(workflow_id)
    
    if not context:
        raise ValueError(f"No state found for workflow {workflow_id}")
    
    # Determine which phase to resume from
    resume_phase = context.current_phase
    
    # Create workflow with resumed context
    workflow = WorkflowEngine(
        workflow_id=workflow_id,
        phases=get_all_phases(),
        context=context
    )
    
    # Execute from current phase
    result = await workflow.execute_from_phase(resume_phase)
    return result

# Query workflow state
async def get_workflow_status(workflow_id: str) -> dict:
    """Get current status of a workflow."""
    context = await state_manager.load_state(workflow_id)
    
    if not context:
        return {"status": "not_found"}
    
    return {
        "workflow_id": workflow_id,
        "current_phase": context.current_phase,
        "completed_phases": [r.phase for r in context.previous_results],
        "state_keys": list(context.state.keys())
    }
```

---

## A2A Communication

Example of calling another agent via A2A protocol.

```python
import httpx
from agenticai.a2a import A2ARequest, A2AResponse

async def call_analysis_agent_phase(context: PhaseContext) -> PhaseResult:
    """Call specialized analysis agent."""
    
    # Prepare A2A request
    request = A2ARequest(
        request_id="req-123",
        agent_id="my-workflow-agent",
        task={
            "type": "analysis",
            "description": "Analyze sales data",
            "parameters": {
                "data": context.get("sales_data"),
                "period": "Q4-2024"
            }
        },
        context={
            "conversation_id": context.get("conversation_id")
        }
    )
    
    # Call analysis agent
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://analysis-agent:8000/a2a/execute",
            json=request.dict(),
            timeout=300.0
        )
        
        if response.status_code != 200:
            return PhaseResult(
                status="failed",
                error=f"Agent call failed: {response.status_code}"
            )
        
        a2a_response = A2AResponse(**response.json())
        
        # Store analysis results
        context.set("analysis_results", a2a_response.result)
        
        return PhaseResult(
            status="completed",
            data=a2a_response.result,
            next_phase="reporting"
        )

# Parallel agent calls
async def orchestrate_multiple_agents(context: PhaseContext) -> PhaseResult:
    """Call multiple agents in parallel."""
    import asyncio
    
    async def call_agent(agent_url: str, task: dict) -> dict:
        """Helper to call an agent."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{agent_url}/a2a/execute",
                json={"task": task},
                timeout=300.0
            )
            return response.json()
    
    # Define parallel tasks
    tasks = [
        call_agent("http://agent-a:8000", {"type": "analyze_a"}),
        call_agent("http://agent-b:8000", {"type": "analyze_b"}),
        call_agent("http://agent-c:8000", {"type": "analyze_c"})
    ]
    
    # Execute in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Aggregate results
    aggregated = {
        "results": [r for r in results if not isinstance(r, Exception)],
        "errors": [str(r) for r in results if isinstance(r, Exception)]
    }
    
    context.set("agent_results", aggregated)
    
    return PhaseResult(
        status="completed" if not aggregated["errors"] else "partial",
        data=aggregated
    )
```

---

## Error Handling

Examples of robust error handling patterns.

```python
from agenticai.workflow import PhaseExecutionError

# Graceful error handling in phase
async def resilient_phase(context: PhaseContext) -> PhaseResult:
    """Phase with comprehensive error handling."""
    
    try:
        # Attempt main operation
        result = await risky_operation(context.get("input"))
        context.set("result", result)
        return PhaseResult(status="completed", data=result)
        
    except ConnectionError as e:
        # Retryable error
        return PhaseResult(
            status="retry",
            error=f"Connection failed: {e}",
            data={"retry_reason": "connection_error"}
        )
        
    except ValueError as e:
        # Non-retryable error
        return PhaseResult(
            status="failed",
            error=f"Invalid input: {e}",
            data={"error_type": "validation"}
        )
        
    except Exception as e:
        # Unexpected error - log and fail
        logger.exception(f"Unexpected error in phase: {e}")
        return PhaseResult(
            status="failed",
            error=f"Unexpected error: {type(e).__name__}",
            data={"error_type": "unexpected"}
        )

# Workflow-level error handler
class ErrorRecoveryWorkflow(WorkflowEngine):
    """Workflow with error recovery."""
    
    async def handle_phase_error(
        self,
        phase: Phase,
        error: Exception
    ) -> PhaseResult:
        """Handle phase execution error."""
        
        # Log error
        logger.error(f"Phase {phase.name} failed: {error}")
        
        # Attempt recovery
        if isinstance(error, ConnectionError):
            # Wait and retry
            await asyncio.sleep(5)
            return PhaseResult(status="retry")
        
        elif isinstance(error, ValidationError):
            # Try fallback data
            fallback_data = await self.get_fallback_data()
            self.context.set("fallback_used", True)
            self.context.set("data", fallback_data)
            return PhaseResult(status="completed", data=fallback_data)
        
        else:
            # Fatal error
            return PhaseResult(
                status="failed",
                error=str(error)
            )
```

---

## Complete Workflow Example

Full end-to-end example of a report generation workflow.

```python
# See guides/getting-started.md for the complete example
```

For complete, production-ready workflow examples, see:
- [Getting Started Guide](../guides/getting-started.md)
- [Defining Phases Guide](../guides/defining-phases.md)
- [Architecture Documentation](../architecture/README.md)

---

**Explore more examples in the guides!**
