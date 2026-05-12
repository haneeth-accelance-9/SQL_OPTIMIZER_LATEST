"""
Django Group bootstrap for the optimizer app.

Called via ``post_migrate`` signal from ``OptimizerConfig.ready()``.
Runs after every ``manage.py migrate`` — safe to re-run; groups and their
permission sets are always brought to the declared state without touching
any other groups or permissions on the site.

Groups created:
  optimizer_viewer  – view only on the three core models
  optimizer_editor  – view + change + add (same as admin except user management)
  optimizer_admin   – view + change + add
"""
import logging

logger = logging.getLogger(__name__)

# Models covered by these groups
_MODEL_NAMES = ["agentrun", "optimizationcandidate", "optimizationdecision"]

# Actions granted per group (delete is intentionally excluded)
_GROUP_PERMISSIONS: dict[str, list[str]] = {
    "optimizer_viewer": ["view"],
    "optimizer_editor": ["view", "change", "add"],
    "optimizer_admin":  ["view", "change", "add"],
}

# Maps UserProfile.role values to Django group names
ROLE_TO_GROUP: dict[str, str] = {
    "admin":  "optimizer_admin",
    "editor": "optimizer_editor",
    "viewer": "optimizer_viewer",
}

_OPTIMIZER_GROUPS = set(ROLE_TO_GROUP.values())


def create_optimizer_groups(sender, **kwargs) -> None:
    """
    Idempotent bootstrap: create / sync the three optimizer permission groups.

    Signature matches Django's ``post_migrate`` signal.
    """
    try:
        from django.contrib.auth.models import Group, Permission
        from django.contrib.contenttypes.models import ContentType
        from optimizer.models import AgentRun, OptimizationCandidate, OptimizationDecision
    except Exception as exc:
        # App registry not ready (e.g. called too early in startup)
        logger.debug("create_optimizer_groups skipped: %s", exc)
        return

    _models = [AgentRun, OptimizationCandidate, OptimizationDecision]

    for group_name, actions in _GROUP_PERMISSIONS.items():
        group, created = Group.objects.get_or_create(name=group_name)
        perms: list[Permission] = []
        for model in _models:
            ct = ContentType.objects.get_for_model(model)
            for action in actions:
                codename = f"{action}_{model._meta.model_name}"
                try:
                    perms.append(Permission.objects.get(content_type=ct, codename=codename))
                except Permission.DoesNotExist:
                    logger.warning(
                        "Permission %s does not exist yet — run migrate first", codename
                    )
        group.permissions.set(perms)
        verb = "created" if created else "updated"
        logger.info(
            "Group %s %s with %d permission(s): %s",
            group_name,
            verb,
            len(perms),
            [f"{a}_{m._meta.model_name}" for a in actions for m in _models],
        )


def sync_user_group(sender, instance, **kwargs) -> None:
    """
    Keeps a user's Django Group in sync with their UserProfile.role.

    Connected to UserProfile post_save in OptimizerConfig.ready().
    Removes the user from all optimizer groups then adds the one matching
    their current role, so the mapping is always authoritative.
    """
    try:
        from django.contrib.auth.models import Group
        user = instance.user
        target_group_name = ROLE_TO_GROUP.get(instance.role)
        if target_group_name is None:
            return
        optimizer_groups = Group.objects.filter(name__in=_OPTIMIZER_GROUPS)
        user.groups.remove(*optimizer_groups)
        target_group, _ = Group.objects.get_or_create(name=target_group_name)
        user.groups.add(target_group)
        logger.debug(
            "sync_user_group: user=%s role=%s → group=%s",
            user.get_username(), instance.role, target_group_name,
        )
    except Exception as exc:
        logger.warning("sync_user_group failed for profile %s: %s", instance.pk, exc)
