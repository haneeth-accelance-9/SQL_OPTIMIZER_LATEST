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
