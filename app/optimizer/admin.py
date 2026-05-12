"""Django admin configuration.

Role enforcement:
  - Admin role  → full access (can add/change/delete users and profiles)
  - Editor role → read-only on User model; full access on other models
  - Viewer role → read-only everywhere; no add/change/delete
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as _BaseUserAdmin
from django.contrib.auth.models import User

from optimizer.models import (
    AgentRun,
    OptimizationCandidate,
    OptimizationDecision,
    UserProfile,
)
from optimizer.permissions import ROLE_ADMIN, ROLE_EDITOR, get_user_role


def _is_admin_role(request) -> bool:
    return get_user_role(request.user) == ROLE_ADMIN


def _is_editor_or_above(request) -> bool:
    return get_user_role(request.user) in (ROLE_ADMIN, ROLE_EDITOR)


# ── User admin: only Admins can create or delete users ───────────────────────

class RoleRestrictedUserAdmin(_BaseUserAdmin):
    """Restricts user creation and deletion to Admin role users."""

    def has_add_permission(self, request):
        return super().has_add_permission(request) and _is_admin_role(request)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and _is_admin_role(request)

    def has_change_permission(self, request, obj=None):
        # Editors can view but not modify other users
        if not _is_editor_or_above(request):
            return False
        return super().has_change_permission(request, obj)

    def has_view_permission(self, request, obj=None):
        return _is_editor_or_above(request) and super().has_view_permission(request, obj)


# ── UserProfile admin ─────────────────────────────────────────────────────────

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "team_name", "updated_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email", "team_name")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return _is_admin_role(request)

    def has_delete_permission(self, request, obj=None):
        return _is_admin_role(request)

    def has_change_permission(self, request, obj=None):
        # Only admins can change role; editors can view
        return _is_editor_or_above(request)

    def has_view_permission(self, request, obj=None):
        return _is_editor_or_above(request)

    def get_readonly_fields(self, request, obj=None):
        base = list(self.readonly_fields)
        # Editors cannot change the role field
        if not _is_admin_role(request):
            base.append("role")
        return base


# Re-register User with role-restricted admin
admin.site.unregister(User)
admin.site.register(User, RoleRestrictedUserAdmin)


# ── AgentRun admin ────────────────────────────────────────────────────────────

@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display  = ("run_label", "status", "triggered_by", "servers_evaluated",
                     "candidates_found", "run_duration_sec", "started_at")
    list_filter   = ("status", "llm_used")
    search_fields = ("run_label", "triggered_by", "llm_model")
    readonly_fields = (
        "id", "started_at", "finished_at", "servers_evaluated", "candidates_found",
        "llm_tokens_used", "run_duration_sec", "input_file_versions",
        "rules_evaluation", "report_markdown", "error_detail",
    )

    def has_view_permission(self, request, obj=None):
        return _is_editor_or_above(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return _is_admin_role(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return _is_editor_or_above(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return _is_admin_role(request) and super().has_delete_permission(request, obj)


# ── OptimizationCandidate admin ───────────────────────────────────────────────

@admin.register(OptimizationCandidate)
class OptimizationCandidateAdmin(admin.ModelAdmin):
    list_display  = ("server", "use_case", "recommendation", "estimated_saving_eur",
                     "status", "detected_on", "expires_at")
    list_filter   = ("status", "use_case", "detected_on")
    search_fields = ("server__server_name", "recommendation", "rationale",
                     "notified_to_email")
    readonly_fields = (
        "id", "agent_run", "server", "rule", "detected_on",
        "created_at", "updated_at",
    )

    def has_view_permission(self, request, obj=None):
        return _is_editor_or_above(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return _is_editor_or_above(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return _is_editor_or_above(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return _is_admin_role(request) and super().has_delete_permission(request, obj)


# ── OptimizationDecision admin ────────────────────────────────────────────────

@admin.register(OptimizationDecision)
class OptimizationDecisionAdmin(admin.ModelAdmin):
    list_display  = ("candidate", "decision", "decided_by", "decided_by_email",
                     "decided_at")
    list_filter   = ("decision",)
    search_fields = ("decided_by", "decided_by_email", "decision_notes",
                     "candidate__server__server_name")
    readonly_fields = ("id", "candidate", "decided_at")

    def has_view_permission(self, request, obj=None):
        return _is_editor_or_above(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return _is_editor_or_above(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return _is_editor_or_above(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return _is_admin_role(request) and super().has_delete_permission(request, obj)
