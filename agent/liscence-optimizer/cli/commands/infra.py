"""
Infrastructure commands for agent deployment.

This module provides infrastructure management through Terraform with a standardized
subcommand structure: plan, apply, destroy, output, init.
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

console = Console()
app = typer.Typer(help="Infrastructure as Code operations")


# Common options that apply to multiple commands
def get_common_options():
    """Common options shared across commands."""
    return {
        "environment": typer.Option(
            "test",
            "--env", "-e",
            help="Environment to deploy (test, staging, prod)",
        ),
        "resource_group_name": typer.Option(
            None,
            "--resource-group", "-rg",
            help="Name of the existing Azure Resource Group",
        ),
        "container_env_name": typer.Option(
            None,
            "--container-env", "-ce",
            help="Name of the existing Container Apps Environment",
        ),
        "state_storage_account": typer.Option(
            None,
            "--state-storage", "-ss",
            help="Azure Storage Account name for Terraform state",
        ),
        "state_container": typer.Option(
            "tfstate",
            "--state-container", "-sc",
            help="Azure Storage Container name for Terraform state",
        ),
        "state_resource_group": typer.Option(
            None,
            "--state-rg",
            help="Resource Group for state storage",
        ),
        "terraform_dir": typer.Option(
            None,
            "--dir", "-d",
            help="Path to Terraform directory",
            exists=False,
            file_okay=False,
            dir_okay=True,
        ),
        "var_file": typer.Option(
            None,
            "--var-file",
            help="Terraform variables file (.tfvars)",
            exists=False,
        ),
        "dry_run": typer.Option(
            False,
            "--dry-run",
            help="Show commands without executing",
        ),
    }


def _get_terraform_dir(terraform_dir: Optional[Path], environment: str) -> Path:
    """Resolve terraform directory based on environment."""
    valid_environments = ["test", "staging", "prod"]
    
    if environment not in valid_environments:
        console.print(f"[red]✗[/red] Invalid environment: {environment}")
        console.print(f"[dim]Valid environments: {', '.join(valid_environments)}[/dim]")
        raise typer.Exit(1)
    
    if terraform_dir is None:
        project_root = Path.cwd()
        terraform_base = project_root / "terraform"
        terraform_dir = terraform_base / "environments" / environment
        
        if not terraform_dir.exists():
            console.print(f"[red]✗[/red] Terraform directory not found: {terraform_dir}")
            raise typer.Exit(1)
    else:
        if terraform_dir.name not in valid_environments:
            terraform_dir = terraform_dir / "environments" / environment
            if not terraform_dir.exists():
                console.print(f"[red]✗[/red] Environment subdirectory not found: {terraform_dir}")
                raise typer.Exit(1)
    
    return terraform_dir


def _get_backend_config(
    state_storage_account: Optional[str],
    state_container: str,
    state_resource_group: Optional[str],
    resource_group_name: Optional[str],
    environment: str,
) -> dict:
    """Build backend configuration for remote state."""
    if not state_storage_account:
        return {}
    
    state_rg = state_resource_group or resource_group_name
    if not state_rg:
        console.print("[red]✗[/red] State storage requires --state-rg or --resource-group")
        raise typer.Exit(1)
    
    agent_name = Path.cwd().name
    
    return {
        "resource_group_name": state_rg,
        "storage_account_name": state_storage_account,
        "container_name": state_container,
        "key": f"{agent_name}-{environment}.tfstate"
    }


def _get_terraform_vars(
    resource_group_name: Optional[str],
    container_env_name: Optional[str],
) -> dict:
    """Build Terraform variables from CLI inputs."""
    tf_vars = {}
    if resource_group_name:
        tf_vars["resource_group_name"] = resource_group_name
    if container_env_name:
        tf_vars["container_app_environment_name"] = container_env_name
    return tf_vars


def _run_terraform_command(cmd: list, cwd: Path, dry_run: bool = False) -> subprocess.CompletedProcess:
    """Execute a terraform command."""
    if dry_run:
        console.print(f"[dim]Would run: {' '.join(cmd)}[/dim]")
        return subprocess.CompletedProcess(cmd, 0)
    
    result = subprocess.run(cmd, cwd=cwd, capture_output=False)
    return result


def _terraform_init(terraform_dir: Path, backend_config: dict, dry_run: bool):
    """Initialize Terraform."""
    console.print("\n[bold cyan]→ Step 1: Initializing Terraform[/bold cyan]")
    
    cmd = ["terraform", "init"]
    
    if backend_config:
        for key, value in backend_config.items():
            cmd.extend(["-backend-config", f"{key}={value}"])
    
    result = _run_terraform_command(cmd, terraform_dir, dry_run)
    
    if result.returncode != 0:
        console.print("[red]✗[/red] Terraform init failed")
        raise typer.Exit(1)
    
    console.print("[green]✓[/green] Terraform initialized")


def _terraform_validate(terraform_dir: Path, dry_run: bool):
    """Validate Terraform configuration."""
    console.print("\n[bold cyan]→ Step 2: Validating Configuration[/bold cyan]")
    
    cmd = ["terraform", "validate"]
    result = _run_terraform_command(cmd, terraform_dir, dry_run)
    
    if result.returncode != 0:
        console.print("[red]✗[/red] Terraform validation failed")
        raise typer.Exit(1)
    
    console.print("[green]✓[/green] Configuration is valid")


def _terraform_plan(terraform_dir: Path, tf_vars: dict, var_file: Optional[Path], dry_run: bool, destroy: bool = False):
    """Generate Terraform plan."""
    console.print("\n[bold cyan]→ Step 3: Planning Changes[/bold cyan]")
    
    cmd = ["terraform", "plan"]
    
    if destroy:
        cmd.append("-destroy")
    
    for key, value in tf_vars.items():
        cmd.extend(["-var", f"{key}={value}"])
    
    if var_file:
        cmd.extend(["-var-file", str(var_file)])
    
    result = _run_terraform_command(cmd, terraform_dir, dry_run)
    
    if result.returncode != 0:
        console.print("[red]✗[/red] Terraform plan failed")
        raise typer.Exit(1)
    
    console.print("[green]✓[/green] Plan generated")


def _terraform_apply(terraform_dir: Path, tf_vars: dict, var_file: Optional[Path], auto_approve: bool, dry_run: bool):
    """Apply Terraform changes."""
    console.print("\n[bold cyan]→ Step 4: Applying Changes[/bold cyan]")
    
    cmd = ["terraform", "apply"]
    
    if auto_approve:
        cmd.append("-auto-approve")
    
    for key, value in tf_vars.items():
        cmd.extend(["-var", f"{key}={value}"])
    
    if var_file:
        cmd.extend(["-var-file", str(var_file)])
    
    result = _run_terraform_command(cmd, terraform_dir, dry_run)
    
    if result.returncode != 0:
        console.print("[red]✗[/red] Terraform apply failed")
        raise typer.Exit(1)
    
    console.print("[green]✓[/green] Infrastructure deployed successfully")


@app.command()
def init(
    environment: str = typer.Option("test", "--env", "-e", help="Environment (test/staging/prod)"),
    terraform_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Terraform directory"),
    state_storage_account: Optional[str] = typer.Option(None, "--state-storage", "-ss"),
    state_container: str = typer.Option("tfstate", "--state-container", "-sc"),
    state_resource_group: Optional[str] = typer.Option(None, "--state-rg"),
    resource_group_name: Optional[str] = typer.Option(None, "--resource-group", "-rg"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Initialize Terraform backend and download providers.
    
    Examples:
        # Initialize with local state
        liscence-optimizer-cli infra init
        
        # Initialize with remote state
        liscence-optimizer-cli infra init --state-storage mystatestorage --state-rg state-rg
    """
    terraform_dir = _get_terraform_dir(terraform_dir, environment)
    backend_config = _get_backend_config(
        state_storage_account, state_container, state_resource_group, resource_group_name, environment
    )
    
    _terraform_init(terraform_dir, backend_config, dry_run)


@app.command()
def plan(
    environment: str = typer.Option("test", "--env", "-e", help="Environment (test/staging/prod)"),
    resource_group_name: Optional[str] = typer.Option(None, "--resource-group", "-rg"),
    container_env_name: Optional[str] = typer.Option(None, "--container-env", "-ce"),
    terraform_dir: Optional[Path] = typer.Option(None, "--dir", "-d"),
    var_file: Optional[Path] = typer.Option(None, "--var-file"),
    state_storage_account: Optional[str] = typer.Option(None, "--state-storage", "-ss"),
    state_container: str = typer.Option("tfstate", "--state-container", "-sc"),
    state_resource_group: Optional[str] = typer.Option(None, "--state-rg"),
    destroy: bool = typer.Option(False, "--destroy", help="Plan for destroy"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Generate and show Terraform execution plan.
    
    Examples:
        # Plan deployment
        liscence-optimizer-cli infra plan -rg my-rg -ce my-env
        
        # Plan destruction
        liscence-optimizer-cli infra plan -rg my-rg -ce my-env --destroy
    """
    terraform_dir = _get_terraform_dir(terraform_dir, environment)
    backend_config = _get_backend_config(
        state_storage_account, state_container, state_resource_group, resource_group_name, environment
    )
    tf_vars = _get_terraform_vars(resource_group_name, container_env_name)
    
    # Ensure initialized
    _terraform_init(terraform_dir, backend_config, dry_run)
    _terraform_validate(terraform_dir, dry_run)
    _terraform_plan(terraform_dir, tf_vars, var_file, dry_run, destroy)


@app.command()
def apply(
    environment: str = typer.Option("test", "--env", "-e", help="Environment (test/staging/prod)"),
    resource_group_name: Optional[str] = typer.Option(None, "--resource-group", "-rg"),
    container_env_name: Optional[str] = typer.Option(None, "--container-env", "-ce"),
    terraform_dir: Optional[Path] = typer.Option(None, "--dir", "-d"),
    var_file: Optional[Path] = typer.Option(None, "--var-file"),
    state_storage_account: Optional[str] = typer.Option(None, "--state-storage", "-ss"),
    state_container: str = typer.Option("tfstate", "--state-container", "-sc"),
    state_resource_group: Optional[str] = typer.Option(None, "--state-rg"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Skip approval prompt"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Apply Terraform changes to deploy agent infrastructure.
    
    Examples:
        # Deploy agent
        liscence-optimizer-cli infra apply -rg my-rg -ce my-env
        
        # Deploy with remote state
        liscence-optimizer-cli infra apply -rg my-rg -ce my-env --state-storage mystatestorage
        
        # Deploy without approval (CI/CD)
        liscence-optimizer-cli infra apply -rg my-rg -ce my-env --auto-approve
    """
    terraform_dir = _get_terraform_dir(terraform_dir, environment)
    backend_config = _get_backend_config(
        state_storage_account, state_container, state_resource_group, resource_group_name, environment
    )
    tf_vars = _get_terraform_vars(resource_group_name, container_env_name)
    
    console.print(Panel.fit(
        f"[bold cyan]Infrastructure Deployment[/bold cyan]\n"
        f"Environment: [magenta]{environment.upper()}[/magenta]\n"
        f"Resource Group: [green]{resource_group_name or 'N/A'}[/green]\n"
        f"Container Env: [green]{container_env_name or 'N/A'}[/green]",
        border_style="cyan"
    ))
    
    # Full workflow: init -> validate -> plan -> apply
    _terraform_init(terraform_dir, backend_config, dry_run)
    _terraform_validate(terraform_dir, dry_run)
    _terraform_plan(terraform_dir, tf_vars, var_file, dry_run)
    _terraform_apply(terraform_dir, tf_vars, var_file, auto_approve, dry_run)


@app.command()
def destroy(
    environment: str = typer.Option("test", "--env", "-e", help="Environment (test/staging/prod)"),
    resource_group_name: Optional[str] = typer.Option(None, "--resource-group", "-rg"),
    container_env_name: Optional[str] = typer.Option(None, "--container-env", "-ce"),
    terraform_dir: Optional[Path] = typer.Option(None, "--dir", "-d"),
    var_file: Optional[Path] = typer.Option(None, "--var-file"),
    state_storage_account: Optional[str] = typer.Option(None, "--state-storage", "-ss"),
    state_container: str = typer.Option("tfstate", "--state-container", "-sc"),
    state_resource_group: Optional[str] = typer.Option(None, "--state-rg"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Skip approval prompt"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Destroy agent infrastructure.
    
    Examples:
        # Destroy infrastructure
        liscence-optimizer-cli infra destroy -rg my-rg -ce my-env
        
        # Destroy without approval
        liscence-optimizer-cli infra destroy -rg my-rg -ce my-env --auto-approve
    """
    terraform_dir = _get_terraform_dir(terraform_dir, environment)
    backend_config = _get_backend_config(
        state_storage_account, state_container, state_resource_group, resource_group_name, environment
    )
    tf_vars = _get_terraform_vars(resource_group_name, container_env_name)
    
    console.print(Panel.fit(
        f"[bold red]⚠️  DESTROY Infrastructure[/bold red]\n"
        f"Environment: [magenta]{environment.upper()}[/magenta]\n"
        f"This will delete all agent resources!",
        border_style="red"
    ))
    
    cmd = ["terraform", "destroy"]
    
    if auto_approve:
        cmd.append("-auto-approve")
    
    for key, value in tf_vars.items():
        cmd.extend(["-var", f"{key}={value}"])
    
    if var_file:
        cmd.extend(["-var-file", str(var_file)])
    
    result = _run_terraform_command(cmd, terraform_dir, dry_run)
    
    if result.returncode != 0:
        console.print("[red]✗[/red] Destroy failed")
        raise typer.Exit(1)
    
    console.print("[green]✓[/green] Infrastructure destroyed")


@app.command()
def validate(
    environment: str = typer.Option("test", "--env", "-e", help="Environment (test/staging/prod)"),
    terraform_dir: Optional[Path] = typer.Option(None, "--dir", "-d"),
):
    """Validate Terraform configuration without accessing remote state.
    
    This runs 'terraform validate' to check syntax and configuration.
    Unlike 'plan', it doesn't access remote state or check actual resources.
    
    Examples:
        # Validate test environment
        liscence-optimizer-cli infra validate
        
        # Validate production
        liscence-optimizer-cli infra validate --env prod
    """
    terraform_dir = _get_terraform_dir(terraform_dir, environment)
    
    console.print(f"[cyan]Validating Terraform configuration for {environment}...[/cyan]")
    
    cmd = ["terraform", "validate"]
    result = subprocess.run(cmd, cwd=terraform_dir, capture_output=True, text=True)
    
    if result.returncode == 0:
        console.print("[green]✓[/green] Configuration is valid")
        if result.stdout:
            console.print(result.stdout)
    else:
        console.print("[red]✗[/red] Configuration validation failed")
        if result.stderr:
            console.print(result.stderr)
        raise typer.Exit(1)


@app.command()
def output(
    environment: str = typer.Option("test", "--env", "-e", help="Environment (test/staging/prod)"),
    terraform_dir: Optional[Path] = typer.Option(None, "--dir", "-d"),
    output_name: Optional[str] = typer.Argument(None, help="Specific output to show"),
    json: bool = typer.Option(False, "--json", help="Output in JSON format"),
):
    """Show Terraform outputs from deployed infrastructure.
    
    Examples:
        # Show all outputs
        liscence-optimizer-cli infra output
        
        # Show specific output
        liscence-optimizer-cli infra output container_app_url
        
        # JSON format
        liscence-optimizer-cli infra output --json
    """
    terraform_dir = _get_terraform_dir(terraform_dir, environment)
    
    cmd = ["terraform", "output"]
    
    if json:
        cmd.append("-json")
    
    if output_name:
        cmd.append(output_name)
    
    result = subprocess.run(cmd, cwd=terraform_dir)
    
    if result.returncode != 0:
        console.print("[red]✗[/red] Failed to retrieve outputs")
        raise typer.Exit(1)