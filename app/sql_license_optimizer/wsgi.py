"""
WSGI config for SQL License Optimizer project.
"""
import os
from pathlib import Path

# Load .env from project root (same as manage.py)
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.is_file():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        pass

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sql_license_optimizer.settings")

application = get_wsgi_application()
