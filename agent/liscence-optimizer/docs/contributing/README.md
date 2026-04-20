# Contributing to Phased Orchestrator Template

Thank you for your interest in contributing to the Phased Orchestrator Agent Template! This document provides guidelines and best practices for contributing.

## 📋 Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)
- [Pull Request Process](#pull-request-process)
- [Release Process](#release-process)

---

## Getting Started

### Ways to Contribute

- **Bug Reports**: Report bugs via GitHub Issues
- **Feature Requests**: Suggest new features or improvements
- **Code Contributions**: Submit pull requests for bug fixes or features
- **Documentation**: Improve guides, examples, and API docs
- **Community**: Help others in discussions and issues

### Before You Start

1. Check existing issues to avoid duplicates
2. Discuss major changes in an issue first
3. Follow the coding standards and guidelines
4. Write tests for new features
5. Update documentation as needed

---

## Development Setup

### Prerequisites

- Python 3.11 or higher
- UV package manager
- Git
- VS Code (recommended)
- Docker (optional)

### Setup Steps

```powershell
# Clone the repository
git clone https://github.com/bayer-int/agentic_ai_template_phased_orchestrator
cd agentic_ai_template_phased_orchestrator

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
uv pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Development Dependencies

The `[dev]` extra includes:

- **pytest**: Testing framework
- **pytest-asyncio**: Async test support
- **pytest-cov**: Coverage reporting
- **black**: Code formatting
- **ruff**: Linting
- **mypy**: Type checking
- **pre-commit**: Git hooks

---

## Coding Standards

### Python Style Guide

We follow **PEP 8** with some customizations:

```python
# Line length: 100 characters (black default)
# Quotes: Double quotes for strings
# Imports: Organized by stdlib, third-party, local

# Good
from typing import Dict, Any, Optional

async def process_data(
    data: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Process input data with optional configuration.
    
    Args:
        data: Input data dictionary
        options: Optional processing options
        
    Returns:
        Processed data dictionary
        
    Raises:
        ValueError: If data is invalid
    """
    if not data:
        raise ValueError("Data cannot be empty")
    
    # Processing logic
    result = {"status": "success", "data": data}
    return result
```

### Code Formatting

```powershell
# Format code with black
black .

# Check formatting without changes
black --check .

# Lint with ruff
ruff check .

# Fix auto-fixable issues
ruff check --fix .

# Type check with mypy
mypy .
```

### Naming Conventions

- **Functions/Variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private**: `_leading_underscore`
- **Modules**: `lowercase` or `snake_case`

```python
# Good
class PhaseManager:
    """Manages phase lifecycle."""
    
    DEFAULT_TIMEOUT = 300
    
    def __init__(self):
        self._phases: Dict[str, Phase] = {}
    
    async def execute_phase(self, phase: Phase) -> PhaseResult:
        """Execute a phase."""
        pass
```

### Type Hints

Always use type hints for function signatures:

```python
from typing import Dict, Any, List, Optional

# Good
async def save_state(
    workflow_id: str,
    context: PhaseContext,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Save workflow state."""
    pass

# Bad - no type hints
async def save_state(workflow_id, context, metadata=None):
    pass
```

### Docstrings

Use Google-style docstrings:

```python
async def execute_workflow(
    workflow_id: str,
    phases: List[Phase],
    context: PhaseContext
) -> WorkflowResult:
    """
    Execute a multi-phase workflow.
    
    Args:
        workflow_id: Unique identifier for the workflow
        phases: List of phases to execute sequentially
        context: Shared context across phases
        
    Returns:
        WorkflowResult containing execution outcome
        
    Raises:
        WorkflowExecutionError: If workflow fails
        PhaseExecutionError: If a phase fails
        
    Example:
        >>> workflow_id = "wf-001"
        >>> phases = [phase1, phase2, phase3]
        >>> context = PhaseContext(...)
        >>> result = await execute_workflow(workflow_id, phases, context)
    """
    pass
```

---

## Testing Guidelines

### Test Structure

```
tests/
├── __init__.py
├── conftest.py              # Pytest fixtures
├── unit/                    # Unit tests
│   ├── test_workflow.py
│   ├── test_phases.py
│   └── test_tools.py
├── integration/             # Integration tests
│   ├── test_a2a_server.py
│   └── test_cosmos_db.py
└── e2e/                     # End-to-end tests
    └── test_complete_workflow.py
```

### Writing Tests

```python
import pytest
from agenticai.workflow import Phase, PhaseContext, PhaseResult

@pytest.mark.asyncio
async def test_phase_execution():
    """Test basic phase execution."""
    # Arrange
    async def handler(context: PhaseContext) -> PhaseResult:
        return PhaseResult(status="completed", data={"result": "success"})
    
    phase = Phase("test", "Test phase", handler)
    context = PhaseContext(
        workflow_id="test-wf",
        current_phase="test",
        state={},
        metadata={},
        previous_results=[]
    )
    
    # Act
    result = await phase.execute(context)
    
    # Assert
    assert result.status == "completed"
    assert result.data["result"] == "success"

@pytest.mark.asyncio
async def test_phase_retry_on_failure():
    """Test phase retry logic."""
    attempt_count = 0
    
    async def flaky_handler(context: PhaseContext) -> PhaseResult:
        nonlocal attempt_count
        attempt_count += 1
        
        if attempt_count < 3:
            return PhaseResult(status="retry", error="Temporary failure")
        return PhaseResult(status="completed", data={"attempts": attempt_count})
    
    phase = Phase(
        "flaky",
        "Flaky phase",
        flaky_handler,
        retry_policy=RetryPolicy(max_retries=3)
    )
    
    context = PhaseContext(...)
    result = await phase.execute(context)
    
    assert result.status == "completed"
    assert attempt_count == 3
```

### Fixtures

```python
# conftest.py
import pytest
from agenticai.workflow import PhaseContext

@pytest.fixture
def phase_context():
    """Create a test phase context."""
    return PhaseContext(
        workflow_id="test-wf-001",
        current_phase="test",
        state={"test_data": "value"},
        metadata={"user_id": "test-user"},
        previous_results=[]
    )

@pytest.fixture
async def mock_cosmos_client():
    """Create a mock Cosmos DB client."""
    # Mock implementation
    pass
```

### Running Tests

```powershell
# Run all tests
pytest

# Run with coverage
pytest --cov=agenticai --cov-report=html

# Run specific test file
pytest tests/unit/test_workflow.py

# Run tests matching pattern
pytest -k "test_phase"

# Run with verbose output
pytest -v

# Run in parallel (requires pytest-xdist)
pytest -n auto
```

### Test Coverage

Maintain **>80% code coverage** for all contributions:

```powershell
# Generate coverage report
pytest --cov=agenticai --cov-report=term --cov-report=html

# View HTML report
start htmlcov/index.html
```

---

## Documentation

### Documentation Standards

- **Guides**: Step-by-step tutorials for common tasks
- **API Reference**: Complete API documentation with examples
- **Architecture**: System design and technical details
- **Examples**: Practical code examples

### Adding Documentation

```powershell
# Documentation structure
docs/
├── README.md                 # Main documentation hub
├── guides/                   # User guides
│   ├── README.md
│   └── new-guide.md
├── architecture/             # Architecture docs
├── api-reference/            # API reference
└── examples/                 # Code examples
```

### Documentation Checklist

When adding new features:

- [ ] Update relevant guide
- [ ] Add API reference entry
- [ ] Include code example
- [ ] Update architecture docs (if applicable)
- [ ] Add docstrings to all public APIs
- [ ] Update README.md if needed

---

## Pull Request Process

### Before Submitting

1. **Create a branch** from `main`:
   ```powershell
   git checkout -b feature/my-feature
   ```

2. **Make your changes** following coding standards

3. **Write tests** for new functionality

4. **Update documentation** as needed

5. **Run checks**:
   ```powershell
   # Format code
   black .
   
   # Lint
   ruff check .
   
   # Type check
   mypy .
   
   # Run tests
   pytest
   ```

6. **Commit changes** with clear messages:
   ```powershell
   git commit -m "feat: Add conditional phase transitions"
   ```

### Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat(workflow): Add support for conditional phase transitions
fix(state): Resolve race condition in state persistence
docs(guides): Add deployment guide for Azure Container Apps
test(phases): Add integration tests for phase execution
```

### Submitting PR

1. **Push branch** to GitHub:
   ```powershell
   git push origin feature/my-feature
   ```

2. **Create Pull Request** on GitHub

3. **Fill out PR template**:
   - Description of changes
   - Related issues
   - Testing performed
   - Documentation updates
   - Breaking changes (if any)

4. **Request review** from maintainers

5. **Address feedback** and update PR

### PR Checklist

- [ ] Code follows style guidelines
- [ ] Tests added/updated
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Commit messages follow convention
- [ ] No breaking changes (or documented)
- [ ] PR description complete

---

## Release Process

### Versioning

We use [Semantic Versioning](https://semver.org/):

- **Major** (1.0.0): Breaking changes
- **Minor** (0.1.0): New features, backwards compatible
- **Patch** (0.0.1): Bug fixes

### Release Steps

1. **Update version** in `pyproject.toml`
2. **Update CHANGELOG.md** with changes
3. **Create release branch**: `release/v1.0.0`
4. **Tag release**: `git tag v1.0.0`
5. **Push tag**: `git push origin v1.0.0`
6. **Create GitHub release** with notes

---

## Code Review Guidelines

### As a Reviewer

- Be constructive and respectful
- Focus on code quality and correctness
- Check tests and documentation
- Suggest improvements, don't demand
- Approve when ready

### As an Author

- Respond to all comments
- Ask for clarification if needed
- Make requested changes
- Mark conversations as resolved
- Thank reviewers

---

## Community Guidelines

### Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Provide constructive feedback
- Focus on the code, not the person
- Report inappropriate behavior

### Getting Help

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and community help
- **Documentation**: Check guides and examples first

---

## Recognition

Contributors will be recognized in:
- CONTRIBUTORS.md file
- GitHub contributors list
- Release notes (for significant contributions)

---

## Questions?

If you have questions about contributing:

1. Check existing documentation
2. Search GitHub Issues and Discussions
3. Create a new Discussion
4. Contact maintainers

---

**Thank you for contributing!** 🎉
