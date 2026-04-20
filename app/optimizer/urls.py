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
    path("data-quality/", views.data_quality_page, name="data_quality"),
    path("alerts/", views.alerts_page, name="alerts"),
    path("analysis-logs/", views.analysis_logs, name="analysis_logs"),
    path("report/", views.report_page, name="report"),
    path("report/download/full-report/", views.full_report_download, name="full_report_download"),
    path("report/download/full-report/<str:sheet_key>/", views.full_report_sheet_download, name="full_report_sheet_download"),
    path("report/download/<str:format_type>/", views.report_download, name="report_download"),
    path("data/download/<str:rule_id>/", views.download_rule_data, name="download_rule_data"),
]
