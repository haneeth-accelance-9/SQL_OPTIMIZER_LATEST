"""
Models for SQL License Optimizer.
Stores upload metadata and processing results for audit and TTL.
"""
from django.conf import settings
from django.db import models


class AnalysisSession(models.Model):
<<<<<<< HEAD
    """Tracks an analysis run (upload + processing). Persists result payload for TTL and audit."""

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_path = models.CharField(max_length=500, blank=True)  # relative to MEDIA_ROOT; avoid storing absolute path
    status = models.CharField(
        max_length=20,
        choices=[
            ("uploaded", "Uploaded"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="uploaded",
    )
    error_message = models.TextField(blank=True)
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="optimizer_analyses",
    )
    # Persist full result payload (rule_results, license_metrics, report_text) for TTL and loading by analysis_id
    result_data = models.JSONField(default=dict, blank=True)
    summary_metrics = models.JSONField(default=dict, blank=True)

=======
    """Tracks an analysis run (upload + processing). Persists result payload for TTL and audit."""

    created_at = models.DateTimeField(auto_now_add=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_path = models.CharField(max_length=500, blank=True)  # relative to MEDIA_ROOT; avoid storing absolute path
    status = models.CharField(
        max_length=20,
        choices=[
            ("uploaded", "Uploaded"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="uploaded",
    )
    error_message = models.TextField(blank=True)
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="optimizer_analyses",
    )
    # Persist full result payload (rule_results, license_metrics, report_text) for TTL and loading by analysis_id
    result_data = models.JSONField(default=dict, blank=True)

>>>>>>> 0b2248414cebac88ae5b45c7b2fdc4ce7c96eba3
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Analysis session"
        verbose_name_plural = "Analysis sessions"


class UserProfile(models.Model):
    """Stores optional user profile details shown on the profile page."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="optimizer_profile",
    )
    team_name = models.CharField(max_length=120, blank=True)
    image_url = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User profile"
        verbose_name_plural = "User profiles"

    def __str__(self):
        return f"Profile for {self.user.username}"
