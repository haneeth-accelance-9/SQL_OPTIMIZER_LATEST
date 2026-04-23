"""
Docker build and push commands for agent deployment.
"""

import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Docker image management")


@app.command()
def build(
    tag: str = typer.Option(
        "latest", "--tag", "-t", help="Image tag"
    ),
    registry: Optional[str] = typer.Option(
        None, "--registry", "-r", help="Container registry URL (e.g., myacr.azurecr.io)"
    ),
    platform: str = typer.Option(
        "linux/amd64", "--platform", help="Target platform"
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Build without using cache"
    ),
    push: bool = typer.Option(
        False, "--push", help="Push image after building (requires --registry)"
    ),
):
    """Build Docker image for agent.
    
    Examples:
        # Build with default tag
        liscence-optimizer-cli docker build
        
        # Build with custom tag
        liscence-optimizer-cli docker build -t v1.0.0
        
        # Build and tag for ACR
        liscence-optimizer-cli docker build -r myacr.azurecr.io -t v1.0.0
        
        # Build and push
        liscence-optimizer-cli docker build -r myacr.azurecr.io -t v1.0.0 --push
    """
    project_root = Path(__file__).parent.parent.parent
    
    agent_name = "liscence-optimizer"
    
    # Determine full image name
    if registry:
        full_image = f"{registry}/{agent_name}:{tag}"
    else:
        full_image = f"{agent_name}:{tag}"
    
    console.print(f"[cyan]→[/cyan] Building Docker image: [bold]{full_image}[/bold]")
    
    # Build docker command
    cmd = [
        "docker", "build",
        "--platform", platform,
        "-t", full_image,
        "-f", "Dockerfile",
    ]
    
    if no_cache:
        cmd.append("--no-cache")
    
    cmd.append(".")
    
    # Execute build
    result = subprocess.run(cmd, cwd=project_root)
    
    if result.returncode != 0:
        console.print("[red]✗[/red] Build failed")
        raise typer.Exit(1)
    
    console.print(f"[green]✓[/green] Image built successfully: [bold]{full_image}[/bold]")
    
    # Push if requested
    if push:
        if not registry:
            console.print("[red]✗[/red] Cannot push: --registry is required for --push")
            raise typer.Exit(1)
        
        console.print(f"[cyan]→[/cyan] Pushing image: [bold]{full_image}[/bold]")
        push_result = subprocess.run(["docker", "push", full_image])
        
        if push_result.returncode != 0:
            console.print("[red]✗[/red] Push failed")
            raise typer.Exit(1)
        
        console.print(f"[green]✓[/green] Image pushed successfully")


@app.command()
def push(
    tag: str = typer.Option(
        "latest", "--tag", "-t", help="Image tag"
    ),
    registry: str = typer.Option(
        ..., "--registry", "-r", help="Container registry URL (e.g., myacr.azurecr.io)"
    ),
):
    """Push Docker image to container registry.
    
    Examples:
        # Push with default tag
        liscence-optimizer-cli docker push -r myacr.azurecr.io
        
        # Push specific tag
        liscence-optimizer-cli docker push -r myacr.azurecr.io -t v1.0.0
    """
    agent_name = "liscence-optimizer"
    full_image = f"{registry}/{agent_name}:{tag}"
    
    console.print(f"[cyan]→[/cyan] Pushing image: [bold]{full_image}[/bold]")
    
    cmd = ["docker", "push", full_image]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        console.print(f"[green]✓[/green] Image pushed successfully: [bold]{full_image}[/bold]")
    else:
        console.print("[red]✗[/red] Push failed")
        console.print("\n[yellow]Tip:[/yellow] Make sure you're logged in to ACR:")
        console.print(f"  {agent_name}-cli docker login -r {registry}")
        raise typer.Exit(1)


@app.command()
def login(
    registry: str = typer.Option(
        ..., "--registry", "-r", help="Container registry URL (e.g., myacr.azurecr.io)"
    ),
):
    """Login to Azure Container Registry.
    
    Examples:
        # Login to ACR
        liscence-optimizer-cli docker login -r myacr.azurecr.io
    """
    console.print(f"[cyan]→[/cyan] Logging in to: [bold]{registry}[/bold]")
    
    # Extract registry name from URL (remove .azurecr.io and https://)
    registry_name = registry.replace(".azurecr.io", "").replace("https://", "")
    
    cmd = ["az", "acr", "login", "--name", registry_name]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        console.print(f"[green]✓[/green] Successfully logged in to {registry}")
    else:
        console.print("[red]✗[/red] Login failed")
        console.print("\n[yellow]Prerequisites:[/yellow]")
        console.print("  • Azure CLI must be installed and configured")
        console.print("  • You must have access to the container registry")
        console.print("\n[yellow]Try:[/yellow]")
        console.print("  az login")
        raise typer.Exit(1)