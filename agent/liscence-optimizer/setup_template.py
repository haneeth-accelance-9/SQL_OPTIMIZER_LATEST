#!/usr/bin/env python3
"""
Phased Orchestrator Template Setup Script

Automatically replaces placeholders in template repository after creation from GitHub.
Uses Jinja2 templating engine for consistency with AgenticAI CLI.

Usage:
    python setup_template.py
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List

try:
    from jinja2 import Template
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False
    print("⚠️  Warning: jinja2 not installed. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "jinja2"])
    from jinja2 import Template
    HAS_JINJA2 = True


def to_kebab_case(text: str) -> str:
    """Convert text to kebab-case."""
    text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1-\2', text)
    text = re.sub(r'([a-z\d])([A-Z])', r'\1-\2', text)
    text = text.replace('_', '-').replace(' ', '-')
    return text.lower()


def to_snake_case(text: str) -> str:
    """Convert text to snake_case."""
    return to_kebab_case(text).replace('-', '_')


def to_pascal_case(text: str) -> str:
    """Convert text to PascalCase."""
    words = re.split(r'[-_\s]+', text)
    return ''.join(word.capitalize() for word in words if word)


def get_user_input() -> Dict[str, str]:
    """Prompt user for template values."""
    print("\n" + "="*70)
    print("  Phased Orchestrator Template Setup")
    print("="*70 + "\n")
    
    # Get agent name
    while True:
        agent_name = input("Enter your agent name (e.g., 'finops-deferrals'): ").strip()
        if agent_name:
            break
        print("❌ Agent name cannot be empty. Please try again.")
    
    # Get description
    description = input("Enter a short description (optional): ").strip()
    if not description:
        description = f"Phased orchestration agent for {agent_name}"
    
    # Get version
    version = input("Enter initial version (default: 0.1.0): ").strip() or "0.1.0"
    
    # Get port
    port = input("Enter server port (default: 8000): ").strip() or "8000"
    
    # Get author info
    author_name = input("Enter author name (optional): ").strip() or "Your Name"
    author_email = input("Enter author email (optional): ").strip() or "your.email@example.com"
    
    # Generate all case variations
    kebab_name = to_kebab_case(agent_name)
    snake_name = to_snake_case(agent_name)
    pascal_name = to_pascal_case(agent_name)
    
    return {
        "{{ AGENT_NAME_KEBAB }}": kebab_name,
        "{{ AGENT_NAME_SNAKE }}": snake_name,
        "{{ AGENT_NAME_PASCAL }}": pascal_name,
        "{{ AGENT_DESCRIPTION }}": description,
        "{{ AGENT_VERSION }}": version,
        "{{ PORT }}": port,
        "{{ AUTHOR_NAME }}": author_name,
        "{{ AUTHOR_EMAIL }}": author_email,
        "{{ PUBLISHER_NAME }}": author_name,
        "{{ PUBLISHER_EMAIL }}": author_email,
        "{{ PRODUCT_NAME }}": kebab_name,
        "{{ PRODUCT_VERSION }}": version,
        "{{ PRODUCT_DESCRIPTION }}": description,
    }


def process_file(file_path: Path, variables: Dict[str, str]) -> bool:
    """
    Process a file by replacing placeholders with Jinja2.
    Returns True if file was modified.
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # Skip if no Jinja2 placeholders
        if '{{' not in content:
            return False
        
        # Use Jinja2 to render template
        template = Template(content)
        new_content = template.render(**variables)
        
        if new_content != content:
            file_path.write_text(new_content, encoding='utf-8')
            return True
        
        return False
    except Exception as e:
        print(f"⚠️  Warning: Could not process {file_path}: {e}")
        return False


def find_template_files(base_dir: Path) -> List[Path]:
    """Find all files that should be processed."""
    exclude_patterns = [
        '.git',
        '__pycache__',
        '.venv',
        'venv',
        'node_modules',
        '.pytest_cache',
        'dist',
        'build',
        '*.pyc',
        '.terraform',
        '*.tfstate*',
    ]
    
    include_extensions = [
        '.py', '.md', '.yaml', '.yml', '.toml', '.json',
        '.tf', '.tfvars', '.hcl', '.env', '.txt',
    ]
    
    files = []
    for file_path in base_dir.rglob('*'):
        if not file_path.is_file():
            continue
        
        # Check exclusions
        if any(pattern in str(file_path) for pattern in exclude_patterns):
            continue
        
        # Check extensions
        if file_path.suffix in include_extensions or file_path.name.startswith('.'):
            files.append(file_path)
    
    return files


def main():
    """Main setup process."""
    script_dir = Path(__file__).parent
    
    # Check if already configured
    readme_path = script_dir / "README.md"
    if readme_path.exists():
        content = readme_path.read_text(encoding='utf-8')
        if '{{' not in content:
            print("✅ This template appears to be already configured!")
            print("   (No Jinja2 placeholders found in README.md)")
            response = input("\n   Do you want to reconfigure? (y/N): ").strip().lower()
            if response != 'y':
                print("\n✋ Setup cancelled.")
                return 0
    
    # Get user input
    variables = get_user_input()
    
    # Display summary
    print("\n" + "="*70)
    print("  Configuration Summary")
    print("="*70)
    for key, value in sorted(variables.items()):
        if '{{' in key:  # Only show Jinja2 format
            print(f"  {key}: {value}")
    print("="*70 + "\n")
    
    # Confirm
    response = input("Proceed with template setup? (Y/n): ").strip().lower()
    if response == 'n':
        print("\n✋ Setup cancelled.")
        return 0
    
    # Process files
    print("\n🔄 Processing template files...")
    files = find_template_files(script_dir)
    modified_count = 0
    
    for file_path in files:
        rel_path = file_path.relative_to(script_dir)
        if process_file(file_path, variables):
            print(f"  ✓ {rel_path}")
            modified_count += 1
    
    print(f"\n✅ Setup complete! Modified {modified_count} files.")
    print("\nNext steps:")
    print(f"  1. Review the changes: git diff")
    print(f"  2. Test the agent: python -m {variables['{{ AGENT_NAME_SNAKE }}']}")
    print(f"  3. Install dependencies: pip install -e .")
    print(f"  4. Commit changes: git add . && git commit -m 'Configure {variables['{{ AGENT_NAME_KEBAB }}']}'")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
