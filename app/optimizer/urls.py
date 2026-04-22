from django.urls import path
from . import views

app_name = "optimizer"

urlpatterns = [
    path("health/", views.health, name="health"),
    path("ready/", views.ready, name="ready"),
    path("", views.home, name="home"),
    path("login/", views.OptimizerLoginView.as_view(), name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_page, name="profile"),
    path("upload/", views.upload, name="upload"),
    path("results/", views.results, name="results"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("analysis-logs/", views.analysis_logs, name="analysis_logs"),
    path("alerts/", views.alerts, name="alerts"),
    path("report/", views.report_page, name="report"),
    path("report/download/<str:format_type>/", views.report_download, name="report_download"),
    path("data/download/<str:rule_id>/", views.download_rule_data, name="download_rule_data"),
    path("rightsizing/download/<str:sheet_key>/", views.download_rightsizing_sheet, name="download_rightsizing_sheet"),
    # ── Agentic AI API endpoints ───────────────────────────────────────────────
    # GET  /api/agent-runs/                  → list recent agent runs
    # POST /api/agent-runs/trigger/          → trigger a new agent run
    # GET  /api/agent-runs/<run_id>/         → detail + candidates for one run
    # POST /api/candidates/<id>/decision/    → accept or reject a candidate
    path("api/agent-runs/", views.api_agent_runs, name="api_agent_runs"),
    path("api/agent-runs/trigger/", views.api_trigger_agent_run, name="api_trigger_agent_run"),
    path("api/agent-runs/<uuid:run_id>/", views.api_agent_run_detail, name="api_agent_run_detail"),
    path("api/candidates/<uuid:candidate_id>/decision/", views.api_candidate_decision, name="api_candidate_decision"),
]
