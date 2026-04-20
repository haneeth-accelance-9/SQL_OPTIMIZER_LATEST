"""
Infrastructure as Code (IaC) command - Terraform operations.

Handles the complete Terraform workflow: init -> validate -> plan -> apply
"""

import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

console = Console()


class TerraformStep(str, Enum):
    """Terraform workflow steps."""
    INIT = "init"
    VALIDATE = "validate"
    PLAN = "plan"
    APPLY = "apply"


def _validate_environment(environment: str) -> None:
    """Validate that the environment is valid."""
    valid_environments = ["test", "staging", "prod"]
    if environment not in valid_environments:
        console.print(f"[red]✗[/red] Invalid environment: {environment}")
        console.print(f"[dim]Valid environments: {', '.join(valid_environments)}[/dim]")
        raise typer.Exit(1)


def _resolve_terraform_dir(terraform_dir: Optional[Path], environment: str) -> Path:
    """Resolve and validate the Terraform directory for the given environment."""
    valid_environments = ["test", "staging", "prod"]
    
    if terraform_dir is None:
        # Look for terraform/environments/<env> directory in project root
        project_root = Path.cwd()
        terraform_base = project_root / "terraform"
        terraform_dir = terraform_base / "environments" / environment

        if not terraform_dir.exists():
            console.print(f"[red]✗[/red] Terraform environment directory not found: {environment}")
            console.print(f"[dim]Looked in: {terraform_dir}[/dim]")
            console.print(
                f"\n[yellow]💡 Tip:[/yellow] Ensure terraform/environments/{environment}/ exists or use --dir"
            )
            raise typer.Exit(1)
    else:
        # If custom dir provided, append environment if not already there
        if terraform_dir.name not in valid_environments:
            terraform_dir = terraform_dir / "environments" / environment
            if not terraform_dir.exists():
                console.print(f"[red]✗[/red] Environment subdirectory not found: {environment}")
                console.print(f"[dim]Looked in: {terraform_dir}[/dim]")
                raise typer.Exit(1)
    
    return terraform_dir


def _resolve_var_file(var_file: Optional[Path], terraform_dir: Path) -> Optional[Path]:
    """Resolve and validate the Terraform variables file."""
    if var_file is None:
        default_tfvars = terraform_dir / "terraform.tfvars"
        if default_tfvars.exists():
            var_file = default_tfvars
    elif not var_file.is_absolute():
        # Resolve relative paths from terraform_dir
        var_file = terraform_dir / var_file

    if var_file and not var_file.exists():
        console.print(f"[yellow]⚠[/yellow] Warning: Variables file not found: {var_file}")
        var_file = None
    
    return var_file


def _setup_backend_config(
    state_storage_account: Optional[str],
    state_container: Optional[str],
    state_resource_group: Optional[str],
    resource_group_name: Optional[str],
    environment: str,
) -> dict:
    """Setup Terraform backend configuration for remote state."""
    if not state_storage_account:
        return {}
    
    # Use state_resource_group if provided, otherwise fall back to resource_group_name
    state_rg = state_resource_group or resource_group_name
    if not state_rg:
        console.print("[red]✗[/red] State storage requires --state-rg or --resource-group")
        raise typer.Exit(1)

    # Get agent name from project directory
    agent_name = Path.cwd().name

    return {
        "resource_group_name": state_rg,
        "storage_account_name": state_storage_account,
        "container_name": state_container,
        "key": f"{agent_name}-{environment}.tfstate",
    }


def _build_tf_vars(
    resource_group_name: Optional[str],
    container_env_name: Optional[str],
) -> dict:
    """Build Terraform variables dictionary from CLI inputs."""
    tf_vars = {}
    if resource_group_name:
        tf_vars["resource_group_name"] = resource_group_name
    if container_env_name:
        tf_vars["container_app_environment_name"] = container_env_name
    return tf_vars


def _display_workflow_info(
    environment: str,
    terraform_dir: Path,
    backend_config: dict,
    state_storage_account: Optional[str],
    state_container: Optional[str],
    var_file: Optional[Path],
    last_step: TerraformStep,
) -> None:
    """Display workflow configuration information."""
    backend_display = (
        "Local" if not backend_config else f"Azure Blob ({state_storage_account}/{state_container})"
    )

    console.print(
        Panel.fit(
            f"[bold cyan]Terraform Workflow[/bold cyan]\n"
            f"Environment: [magenta]{environment.upper()}[/magenta]\n"
            f"Directory: [green]{terraform_dir}[/green]\n"
            f"State Backend: [yellow]{backend_display}[/yellow]\n"
            f"Var File: [blue]{var_file or 'none'}[/blue]\n"
            f"Last Step: [yellow]{last_step.value}[/yellow]",
            border_style="cyan",
        )
    )


def _display_workflow_steps(last_step: TerraformStep, dry_run: bool) -> list[TerraformStep]:
    """Display workflow steps and return list of steps to execute."""
    workflow_steps = [
        TerraformStep.INIT,
        TerraformStep.VALIDATE,
        TerraformStep.PLAN,
        TerraformStep.APPLY,
    ]

    # Determine which steps to execute
    last_step_index = workflow_steps.index(last_step)
    steps_to_execute = workflow_steps[: last_step_index + 1]

    console.print("\n[bold]Workflow Steps:[/bold]")
    table = Table(show_header=False, box=None, padding=(0, 2))
    for step in workflow_steps:
        if step in steps_to_execute:
            table.add_row("✓", f"[green]{step.value}[/green]")
        else:
            table.add_row(" ", f"[dim]{step.value} (skipped)[/dim]")
    console.print(table)
    console.print()

    if dry_run:
        console.print("[yellow]🔍 DRY RUN MODE - No commands will be executed[/yellow]\n")
    
    return steps_to_execute


def iac_command(
    environment: str = typer.Option(
        "test",
        "--env", "-e",
        help="Environment to deploy (test, staging, prod)",
    ),
    resource_group_name: Optional[str] = typer.Option(
        None,
        "--resource-group", "-rg",
        help="Name of the existing Azure Resource Group",
    ),
    container_env_name: Optional[str] = typer.Option(
        None,
        "--container-env", "-ce",
        help="Name of the existing Container Apps Environment",
    ),
    state_storage_account: Optional[str] = typer.Option(
        None,
        "--state-storage", "-ss",
        help="Azure Storage Account name for Terraform state (enables remote backend)",
    ),
    state_container: Optional[str] = typer.Option(
        "tfstate",
        "--state-container", "-sc",
        help="Azure Storage Container name for Terraform state",
    ),
    state_resource_group: Optional[str] = typer.Option(
        None,
        "--state-rg",
        help="Resource Group for state storage (defaults to --resource-group value)",
    ),
    last_step: TerraformStep = typer.Option(
        TerraformStep.APPLY,
        "--last-step", "-l",
        help="Last step to execute in the Terraform workflow",
        case_sensitive=False,
    ),
    terraform_dir: Optional[Path] = typer.Option(
        None,
        "--dir", "-d",
        help="Path to Terraform directory (defaults to './terraform' from project root)",
        exists=False,  # Changed to False since we'll validate environment subdir
        file_okay=False,
        dir_okay=True,
    ),
    auto_approve: bool = typer.Option(
        False,
        "--auto-approve",
        help="Skip interactive approval for terraform apply",
    ),
    var_file: Optional[Path] = typer.Option(
        None,
        "--var-file",
        help="Terraform variables file (.tfvars) - defaults to terraform.tfvars in environment dir",
        exists=False,  # Changed to False for dynamic validation
    ),
    destroy: bool = typer.Option(
        False,
        "--destroy",
        help="Run terraform destroy instead of apply",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be executed without running commands",
    ),
) -> None:
    """
    Execute Terraform Infrastructure as Code workflow.
    
    This command automates the Terraform workflow from initialization through
    deployment. By default, it runs the complete workflow (init -> validate -> plan -> apply),
    but you can stop at any step using the --last-step option.
    
    Examples:
    
        # Deploy with infrastructure parameters
        liscence-optimizer-cli iac --resource-group my-rg --container-env my-env
        
        # Deploy with remote state backend
        liscence-optimizer-cli iac -rg my-rg -ce my-env \
          --state-storage mystatestorage --state-rg state-rg
        
        # Deploy to staging with state
        liscence-optimizer-cli iac --env staging -rg my-rg -ce my-env \
          -ss mystatestorage -sc tfstate
        
        # Deploy to production
        liscence-optimizer-cli iac --env prod --resource-group prod-rg --container-env prod-env \
          --state-storage prodstatestorage
        
        # Stop after plan (no apply)
        liscence-optimizer-cli iac --env prod -rg my-rg -ce my-env --last-step plan
        
        # Only initialize
        liscence-optimizer-cli iac --last-step init
        
        # Apply with auto-approval (CI/CD)
        liscence-optimizer-cli iac --env prod -rg my-rg -ce my-env --auto-approve
        
        # Use custom variables file (overrides CLI params)
        liscence-optimizer-cli iac --env prod --var-file custom.tfvars
        
        # Destroy infrastructure
        liscence-optimizer-cli iac --env test -rg my-rg -ce my-env --destroy --auto-approve
        
        # Dry run (show commands without executing)
        liscence-optimizer-cli iac --env prod -rg my-rg -ce my-env --dry-run
    """
    # Validate inputs
    _validate_environment(environment)
    
    # Resolve paths and configuration
    terraform_dir = _resolve_terraform_dir(terraform_dir, environment)
    var_file = _resolve_var_file(var_file, terraform_dir)
    backend_config = _setup_backend_config(
        state_storage_account,
        state_container,
        state_resource_group,
        resource_group_name,
        environment,
    )
    tf_vars = _build_tf_vars(resource_group_name, container_env_name)
    
    # Display workflow configuration
    _display_workflow_info(
        environment,
        terraform_dir,
        backend_config,
        state_storage_account,
        state_container,
        var_file,
        last_step,
    )
    steps_to_execute = _display_workflow_steps(last_step, dry_run)
    
    # Execute workflow
    try:
        for step in steps_to_execute:
            if step == TerraformStep.INIT:
                _terraform_init(terraform_dir, backend_config, dry_run)
            elif step == TerraformStep.VALIDATE:
                _terraform_validate(terraform_dir, dry_run)
            elif step == TerraformStep.PLAN:
                _terraform_plan(terraform_dir, var_file, tf_vars, destroy, dry_run)
            elif step == TerraformStep.APPLY:
                if destroy:
                    _terraform_destroy(terraform_dir, var_file, tf_vars, auto_approve, dry_run)
                else:
                    _terraform_apply(terraform_dir, var_file, tf_vars, auto_approve, dry_run)
        
        console.print(f"\n[bold green]✓ Terraform workflow completed successfully![/bold green]")
        console.print(f"[dim]Last step executed: {last_step.value}[/dim]")
        
    except subprocess.CalledProcessError as e:
        console.print(f"\n[bold red]✗ Terraform command failed with exit code {e.returncode}[/bold red]")
        raise typer.Exit(e.returncode)
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Workflow interrupted by user[/yellow]")
        raise typer.Exit(130)


def _terraform_init(terraform_dir: Path, backend_config: dict | None = None, dry_run: bool = False) -> None:
    """Execute terraform init."""
    console.print("[bold cyan]Step 1:[/bold cyan] Initializing Terraform...")
    
    cmd = ["terraform", "init", "-upgrade"]
    
    # Add backend configuration if provided
    if backend_config:
        console.print("[dim]Configuring remote state backend...[/dim]")
        for key, value in backend_config.items():
            cmd.extend(["-backend-config", f"{key}={value}"])
    
    if dry_run:
        console.print(f"[dim]Would run: {' '.join(cmd)}[/dim]\n")
        return
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task_msg = "Configuring remote backend..." if backend_config else "Initializing providers and modules..."
        progress.add_task(task_msg, total=None)
        
        result = subprocess.run(
            cmd,
            cwd=terraform_dir,
            capture_output=True,
            text=True,
        )
    
    if result.returncode != 0:
        console.print(f"[red]✗ Init failed[/red]")
        console.print(result.stderr)
        raise subprocess.CalledProcessError(result.returncode, cmd)
    
    console.print("[green]✓ Initialization complete[/green]\n")


def _terraform_validate(terraform_dir: Path, dry_run: bool = False) -> None:
    """Execute terraform validate."""
    console.print("[bold cyan]Step 2:[/bold cyan] Validating configuration...")
    
    cmd = ["terraform", "validate"]
    
    if dry_run:
        console.print(f"[dim]Would run: {' '.join(cmd)}[/dim]\n")
        return
    
    result = subprocess.run(
        cmd,
        cwd=terraform_dir,
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        console.print(f"[red]✗ Validation failed[/red]")
        console.print(result.stderr)
        raise subprocess.CalledProcessError(result.returncode, cmd)
    
    console.print("[green]✓ Configuration is valid[/green]\n")


def _terraform_plan(
    terraform_dir: Path,
    var_file: Optional[Path] = None,
    tf_vars: dict | None = None,
    destroy: bool = False,
    dry_run: bool = False,
) -> None:
    """Execute terraform plan."""
    console.print("[bold cyan]Step 3:[/bold cyan] Creating execution plan...")
    
    cmd = ["terraform", "plan"]
    
    if destroy:
        cmd.append("-destroy")
    
    if var_file:
        cmd.extend(["-var-file", str(var_file)])
    
    # Add CLI-provided variables
    if tf_vars:
        for key, value in tf_vars.items():
            cmd.extend(["-var", f"{key}={value}"])
    
    # Save plan to file
    plan_file = terraform_dir / "tfplan"
    cmd.extend(["-out", str(plan_file)])
    
    if dry_run:
        console.print(f"[dim]Would run: {' '.join(cmd)}[/dim]\n")
        return
    
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")
    
    result = subprocess.run(
        cmd,
        cwd=terraform_dir,
        text=True,
    )
    
    if result.returncode != 0:
        console.print(f"\n[red]✗ Plan failed[/red]")
        raise subprocess.CalledProcessError(result.returncode, cmd)
    
    console.print(f"\n[green]✓ Plan created successfully[/green]")
    console.print(f"[dim]Plan saved to: {plan_file}[/dim]\n")


def _terraform_apply(
    terraform_dir: Path,
    var_file: Optional[Path] = None,
    tf_vars: dict | None = None,
    auto_approve: bool = False,
    dry_run: bool = False,
) -> None:
    """Execute terraform apply."""
    console.print("[bold cyan]Step 4:[/bold cyan] Applying changes...")
    
    # Use saved plan file
    plan_file = terraform_dir / "tfplan"
    
    cmd = ["terraform", "apply"]
    
    if auto_approve:
        cmd.append("-auto-approve")
    
    if plan_file.exists():
        cmd.append(str(plan_file))
    else:
        if var_file:
            cmd.extend(["-var-file", str(var_file)])
        
        # Add CLI-provided variables
        if tf_vars:
            for key, value in tf_vars.items():
                cmd.extend(["-var", f"{key}={value}"])
    
    if dry_run:
        console.print(f"[dim]Would run: {' '.join(cmd)}[/dim]\n")
        return
    
    if not auto_approve and not plan_file.exists():
        console.print("[yellow]⚠ This will make real changes to your infrastructure![/yellow]")
        confirm = typer.confirm("Do you want to proceed?")
        if not confirm:
            console.print("[yellow]Apply cancelled[/yellow]")
            raise typer.Exit(0)
    
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")
    
    result = subprocess.run(
        cmd,
        cwd=terraform_dir,
        text=True,
    )
    
    if result.returncode != 0:
        console.print(f"\n[red]✗ Apply failed[/red]")
        raise subprocess.CalledProcessError(result.returncode, cmd)
    
    console.print(f"\n[green]✓ Infrastructure deployed successfully[/green]\n")
    
    # Clean up plan file
    if plan_file.exists():
        plan_file.unlink()


def _terraform_destroy(
    terraform_dir: Path,
    var_file: Optional[Path] = None,
    tf_vars: dict | None = None,
    auto_approve: bool = False,
    dry_run: bool = False,
) -> None:
    """Execute terraform destroy."""
    console.print("[bold red]Step 4:[/bold red] Destroying infrastructure...")
    
    cmd = ["terraform", "destroy"]
    
    if auto_approve:
        cmd.append("-auto-approve")
    
    if var_file:
        cmd.extend(["-var-file", str(var_file)])
    
    # Add CLI-provided variables
    if tf_vars:
        for key, value in tf_vars.items():
            cmd.extend(["-var", f"{key}={value}"])
    
    if dry_run:
        console.print(f"[dim]Would run: {' '.join(cmd)}[/dim]\n")
        return
    
    if not auto_approve:
        console.print("[bold red]⚠ WARNING: This will destroy all managed infrastructure![/bold red]")
        console.print("[yellow]This action cannot be undone.[/yellow]\n")
        confirm = typer.confirm("Are you absolutely sure you want to proceed?")
        if not confirm:
            console.print("[yellow]Destroy cancelled[/yellow]")
            raise typer.Exit(0)
    
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")
    
    result = subprocess.run(
        cmd,
        cwd=terraform_dir,
        text=True,
    )
    
    if result.returncode != 0:
        console.print(f"\n[red]✗ Destroy failed[/red]")
        raise subprocess.CalledProcessError(result.returncode, cmd)
    
    console.print(f"\n[green]✓ Infrastructure destroyed[/green]\n")