import sys

from django.apps import AppConfig


class OptimizerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "optimizer"
    verbose_name = "SQL License Optimizer"

    def ready(self):
        from django.db.models.signals import post_migrate, post_save
        from optimizer.groups import create_optimizer_groups, sync_user_group
        post_migrate.connect(create_optimizer_groups, sender=self)

        from optimizer.models import UserProfile
        post_save.connect(sync_user_group, sender=UserProfile)

        # Start the background scheduler unless we are running a management
        # command (migrate, collectstatic, shell, etc.) or inside the test runner.
        # The scheduler should only run in the long-lived server process.
        _management_commands = {
            "migrate", "makemigrations", "collectstatic", "shell",
            "test", "createsuperuser", "crontab",
        }
        running_command = sys.argv[1] if len(sys.argv) > 1 else ""
        is_server = running_command in ("runserver", "gunicorn", "uvicorn", "")
        is_management = running_command in _management_commands

        if not is_management and "pytest" not in sys.modules:
            from optimizer.scheduler import start
            start()
