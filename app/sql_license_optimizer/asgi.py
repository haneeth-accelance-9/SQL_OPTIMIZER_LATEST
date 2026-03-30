"""
ASGI config for SQL License Optimizer project.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sql_license_optimizer.settings")

application = get_asgi_application()
