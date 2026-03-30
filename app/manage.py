#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# Load .env from project root so AZURE_OPENAI_* and other vars are available
def _load_env():
    from pathlib import Path
    base = Path(__file__).resolve().parent
    env_path = base / ".env"
    if env_path.is_file():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            pass


def main():
    """Run administrative tasks."""
    _load_env()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sql_license_optimizer.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
