#!/usr/bin/env python3
"""
LiscenceOptimizer CLI - Main Application

Command-line interface for managing infrastructure, deployments, and operations.

Usage:
    liscence-optimizer-cli docker [COMMAND]  # Docker image management
    liscence-optimizer-cli infra [COMMAND]   # Infrastructure operations
    liscence-optimizer-cli iac [OPTIONS]     # Legacy: Infrastructure operations (deprecated)
"""

import typer
from rich.console import Console

from .commands import docker, infra
from .commands.iac import iac_command

# Initialize Typer app
app = typer.Typer(
    name="liscence-optimizer-cli",
    help="🛠️  CLI tools for LiscenceOptimizer",
    add_completion=True,
    rich_markup_mode="rich",
    no_args_is_help=True,
)

console = Console()

# Register commands
app.add_typer(docker.app, name="docker", help="🐳 Docker image management")
app.add_typer(infra.app, name="infra", help="🏗️  Infrastructure operations (Terraform)")

# Keep legacy iac command for backward compatibility (deprecated)
app.command(
    name="iac",
    help="🏗️  [DEPRECATED] Use 'infra' command instead",
    hidden=True
)(iac_command)


# Version command
@app.command()
def version():
    """Show CLI version."""
    console.print("[bold cyan]LiscenceOptimizer CLI[/bold cyan] version [green]0.1.0[/green]")


def main() -> None:
    """Main entry point for the CLI."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    main()