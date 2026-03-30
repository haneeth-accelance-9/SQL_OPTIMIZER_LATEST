"""
Views for SQL License Optimizer: upload, process, results, dashboard, report.
All optimizer views require authentication (enterprise security).
Uses AnalysisSession for persistence and TTL; session stores only analysis_id.
"""
import logging
import os
import re
import uuid
from django.conf import settings
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods
from django.contrib.auth import logout as auth_logout
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.utils import timezone

import pandas as pd
from optimizer.models import AnalysisSession, UserProfile
from optimizer.forms import SignUpForm, UserProfileForm
from optimizer.services.analysis_service import run_analysis, get_sheet_config, build_dashboard_context, _build_payg_zone_breakdown
from optimizer.services.analysis_logs import build_analysis_summary_metrics, get_user_analysis_logs
from optimizer.services.excel_processor import ExcelProcessor
from optimizer.services.report_export import (
    export_pdf,
    export_docx,
    export_xlsx,
    normalize_report_content_text,
    build_report_markdown,
)

try:
    from optimizer.services.plotly_charts import get_all_plotly_specs
except ImportError:
    get_all_plotly_specs = None


def _make_json_serializable(obj):
    """Convert numpy/pandas types to native Python so result_data passes SQLite JSON_VALID."""
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_serializable(v) for v in obj]
    if hasattr(obj, "tolist") and not isinstance(obj, (str, bytes)):  # numpy array
        return [_make_json_serializable(v) for v in obj]
    if hasattr(obj, "item"):  # numpy scalar (0-d array)
        try:
            return obj.item()
        except (ValueError, AttributeError):
            return [_make_json_serializable(v) for v in obj]
    try:
        if pd.isna(obj):
            return None
    except (ValueError, TypeError):
        pass
    if isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return str(obj)

try:
    from optimizer.services.chart_generator import generate_all_charts
except ImportError:
    generate_all_charts = None

logger = logging.getLogger(__name__)

REPORT_FORMAT_ALIASES = {
    "excel": "xlsx",
}
ALLOWED_REPORT_FORMATS = frozenset({"pdf", "docx", "xlsx", *REPORT_FORMAT_ALIASES.keys()})
ALLOWED_RULE_IDS = frozenset({"rule1", "rule2"})
PAYG_ZONE_BREAKDOWN_LABELS = ["Public Cloud", "Private Cloud AVS"]


def _build_profile_initials(user) -> str:
    """Build a short initials badge from the user's name, falling back to username."""
    first = (getattr(user, "first_name", "") or "").strip()
    last = (getattr(user, "last_name", "") or "").strip()
    if first or last:
        initials = f"{first[:1]}{last[:1]}".strip()
    else:
        username = (getattr(user, "username", "") or "").strip()
        parts = [part for part in re.split(r"[\s._-]+", username) if part]
        initials = "".join(part[:1] for part in parts[:2]) or username[:2]
    return (initials or "U").upper()


def _build_profile_context(user, profile, form=None):
    """Build the display context expected by the profile page template."""
    full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    display_name = full_name or user.username
    return {
        "title": "Profile",
        "profile_form": form or UserProfileForm(instance=profile, user=user),
        "profile_display_name": display_name,
        "profile_initials": _build_profile_initials(user),
        "profile_email": user.email or "Not provided",
        "profile_username": user.username,
        "profile_team_name": profile.team_name or "Not provided",
        "profile_image_url": profile.image_url or "",
        "profile_first_name": user.first_name or "Not provided",
        "profile_last_name": user.last_name or "Not provided",
    }


def _get_or_create_user_profile(user):
    """Return the persisted profile row for the authenticated user."""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def _get_analysis_file_path(analysis):
    """Resolve the persisted upload path for an analysis record when it still exists on disk."""
    if not analysis or not analysis.file_path:
        return None
    upload_dir = getattr(settings, "MEDIA_ROOT", None) or os.path.join(settings.BASE_DIR, "uploads")
    candidate = os.path.join(upload_dir, analysis.file_path)
    return candidate if os.path.exists(candidate) else None


def _ensure_payg_zone_breakdown(analysis, context):
    """Backfill payg zone breakdown from the stored upload when older analyses do not have it yet."""
    rule_results = context.get("rule_results") or {}
    payg_zone_breakdown = rule_results.get("payg_zone_breakdown") or {}
    existing_labels = list(payg_zone_breakdown.get("labels") or [])
    has_current = isinstance(payg_zone_breakdown.get("current"), list) and len(payg_zone_breakdown.get("current")) == len(PAYG_ZONE_BREAKDOWN_LABELS)
    has_estimated = isinstance(payg_zone_breakdown.get("estimated"), list) and len(payg_zone_breakdown.get("estimated")) == len(PAYG_ZONE_BREAKDOWN_LABELS)
    if existing_labels == PAYG_ZONE_BREAKDOWN_LABELS and has_current and has_estimated:
        return context

    file_path = _get_analysis_file_path(analysis)
    if not file_path:
        return context

    try:
        sheets = get_sheet_config()
        data = ExcelProcessor(
            sheet_installations=sheets["installations"],
            sheet_demand=sheets["demand"],
            sheet_prices=sheets["prices"],
            sheet_optimization=sheets["optimization"],
            sheet_helpful_reports=sheets.get("helpful_reports"),
        ).load_file(file_path)
        installations_df = data.get("installations")
        if isinstance(installations_df, pd.DataFrame):
            rule_results["payg_zone_breakdown"] = _build_payg_zone_breakdown(
                installations_df,
                rule_results.get("azure_payg") or [],
            )
            context["rule_results"] = rule_results
    except Exception as e:
        logger.warning("PAYG zone breakdown backfill failed for analysis_id=%s: %s", getattr(analysis, "id", None), e)
    return context


def _get_analysis_record(request):
    """Load the current persisted analysis record and enforce ownership/TTL checks."""
    analysis_id = request.session.get("optimizer_analysis_id")
    if not analysis_id:
        return None, redirect("optimizer:home")
    analysis = AnalysisSession.objects.filter(pk=analysis_id).first()
    if not analysis:
        messages.info(request, "Analysis not found. Please upload a new file.")
        return None, redirect("optimizer:home")
    if analysis.user_id and analysis.user_id != request.user.id:
        return None, redirect("optimizer:home")
    ttl = getattr(settings, "OPTIMIZER_ANALYSIS_TTL_SECONDS", 86400)
    if ttl > 0 and analysis.created_at:
        from datetime import timedelta
        if timezone.now() - analysis.created_at > timedelta(seconds=ttl):
            messages.info(request, "This analysis has expired. Please upload a new file.")
            return None, redirect("optimizer:home")
    return analysis, None


def _normalize_analysis_context(analysis):
    """Return a safe, normalized analysis context from persisted result data."""
    raw_context = analysis.result_data if isinstance(analysis.result_data, dict) else {}
    context = dict(raw_context)
    context["rule_results"] = context.get("rule_results") or {}
    context["license_metrics"] = context.get("license_metrics") or {}
    context["file_name"] = context.get("file_name") or analysis.file_name or ""
    context["sheet_names_used"] = context.get("sheet_names_used") or {}
    context["total_devices_analyzed"] = int(context.get("total_devices_analyzed", 0) or 0)
    context["report_text"] = context.get("report_text") or ""
    context["report_used_fallback"] = bool(context.get("report_used_fallback", False))
    context["cost_reduction_ai_recommendations"] = context.get("cost_reduction_ai_recommendations") or ""

    dashboard_defaults = build_dashboard_context(context)
    context["rule_wise_savings"] = context.get("rule_wise_savings") or dashboard_defaults.get("rule_wise_savings", {})
    context["scenario_wise_savings"] = context.get("scenario_wise_savings") or dashboard_defaults.get("scenario_wise_savings", {})
    context["total_savings"] = float(context.get("total_savings", dashboard_defaults.get("total_savings", 0)) or 0)
    return context


def _get_analysis_context(request):
    """
    Load analysis context from DB by session's analysis_id. Check TTL and ownership.
    Returns (context dict, None) or (None, redirect_response).
    """
    analysis, redir = _get_analysis_record(request)
    if redir is not None:
        return None, redir
    raw_context = analysis.result_data if isinstance(analysis.result_data, dict) else {}
    if not raw_context:
        return None, redirect("optimizer:home")
    return _normalize_analysis_context(analysis), None


def _build_report_render_context(context):
    dashboard_context = build_dashboard_context(context)
    return {
        "azure_payg_count": context.get("rule_results", {}).get("azure_payg_count", 0),
        "retired_count": context.get("rule_results", {}).get("retired_count", 0),
        "total_demand_quantity": context.get("license_metrics", {}).get("total_demand_quantity", 0),
        "total_license_cost": context.get("license_metrics", {}).get("total_license_cost", 0),
        "by_product": context.get("license_metrics", {}).get("by_product", []),
        "rule_wise_savings": dashboard_context.get("rule_wise_savings", {}),
        "total_savings": dashboard_context.get("total_savings", 0),
        "azure_payg_savings": dashboard_context.get("azure_payg_savings", 0),
        "retired_devices_savings": dashboard_context.get("retired_devices_savings", 0),
    }


def _get_page_number(request, param_name, default=1):
    """Parse a positive integer query param with a safe fallback."""
    try:
        return max(1, int(request.GET.get(param_name, default)))
    except (TypeError, ValueError):
        return default


def _validate_excel_upload(file_path, original_filename):
    """
    Validate saved file by magic bytes. Returns (True, None) if valid, (False, error_message) otherwise.
    - .xlsx: PK (ZIP)
    - .xls: D0 CF 11 E0 (OLE)
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(8)
        name_lower = (original_filename or "").lower()
        if name_lower.endswith(".xlsx"):
            if not header.startswith(b"PK"):
                return False, "File is not a valid .xlsx (expected ZIP format)."
        elif name_lower.endswith(".xls"):
            if not header[:8].startswith(b"\xD0\xCF\x11\xE0"):
                return False, "File is not a valid .xls (expected OLE format)."
        return True, None
    except Exception as e:
        logger.warning("Upload validation failed: %s", e)
        return False, "Could not validate file content."


def _sanitize_filename(name: str, max_len: int = 200) -> str:
    """Remove path separators and control chars; limit length for Content-Disposition."""
    if not name or not isinstance(name, str):
        return "download"
    name = os.path.basename(name)
    name = re.sub(r"[\x00-\x1f\x7f/\\]", "", name)
    return name[:max_len] if len(name) > max_len else name or "download"


def _safe_content_disposition(filename: str) -> str:
    """Build safe Content-Disposition value (ASCII filename only)."""
    safe = _sanitize_filename(filename)
    return f'attachment; filename="{safe}"'


class OptimizerLoginView(LoginView):
    """Enterprise login: unified auth page (Sign in | Create account)."""
    template_name = "optimizer/auth.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = self.request.GET.get("tab", "login")
        context["registered"] = self.request.GET.get("registered") == "1"
        context["signup_form"] = SignUpForm()
        return context


@require_http_methods(["GET", "POST"])
@csrf_protect
def signup_view(request):
    """
    Enterprise signup: POST creates user and redirects to login with success message.
    GET redirects to login with tab=signup so the unified auth page shows the signup form.
    """
    if request.user.is_authenticated:
        return redirect("optimizer:home")
    if request.method == "GET":
        login_url = reverse("optimizer:login")
        if not login_url.startswith("/"):
            login_url = "/" + login_url
        return redirect(login_url + "?tab=signup")
    form = SignUpForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "optimizer/auth.html",
            {
                "form": AuthenticationForm(),
                "signup_form": form,
                "active_tab": "signup",
                "registered": False,
            },
        )
    user = form.save(commit=True)
    logger.info("User registered id=%s username=%s", user.pk, user.username)
    messages.success(request, "Account created. Please sign in with your credentials.")
    login_url = reverse("optimizer:login")
    if not login_url.startswith("/"):
        login_url = "/" + login_url
    return redirect(login_url + "?registered=1")


@require_http_methods(["GET", "POST"])
def logout_view(request):
    """Log out and redirect to login. Accepts GET so 'Log out' link works without a form."""
    auth_logout(request)
    return redirect("optimizer:login")


@require_GET
def health(request):
    """Liveness: returns 200 if the app is running. No auth required."""
    return HttpResponse("ok", content_type="text/plain")


@require_GET
def ready(request):
    """Readiness: checks DB connectivity. No auth required. Use for load balancer probes."""
    try:
        from django.db import connection
        connection.ensure_connection()
        return HttpResponse("ready", content_type="text/plain")
    except Exception as e:
        logger.warning("Ready check failed: %s", e)
        return HttpResponse("not ready", status=503, content_type="text/plain")


@require_GET
@login_required
def home(request):
    """Landing page with upload form and instructions."""
    return render(request, "optimizer/home.html", {"title": "SQL License Optimizer"})


@require_http_methods(["GET", "POST"])
@csrf_protect
@login_required
def upload(request):
    """Handle file upload, process Excel, store results in session, redirect to results or loading."""
    if request.method != "POST":
        return redirect("optimizer:home")

    file_obj = request.FILES.get("excel_file")
    if not file_obj or not file_obj.name.lower().endswith((".xlsx", ".xls")):
        return render(
            request,
            "optimizer/home.html",
            {"error": "Please upload an Excel file (.xlsx or .xls).", "title": "SQL License Optimizer"},
        )

    upload_dir = getattr(settings, "MEDIA_ROOT", None) or os.path.join(settings.BASE_DIR, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{_sanitize_filename(file_obj.name)}"
    file_path = os.path.join(upload_dir, safe_name)
    with open(file_path, "wb") as f:
        for chunk in file_obj.chunks():
            f.write(chunk)

    allowed, error_msg = _validate_excel_upload(file_path, file_obj.name)
    if not allowed:
        try:
            os.remove(file_path)
        except OSError:
            pass
        messages.error(request, error_msg or "Invalid file.")
        return render(request, "optimizer/home.html", {"error": error_msg, "title": "SQL License Optimizer"})

    if not request.session.session_key:
        request.session.save()

    analysis_record = AnalysisSession(
        user=request.user,
        file_name=file_obj.name,
        file_path=os.path.basename(file_path),
        status="processing",
        session_key=request.session.session_key or "",
    )
    analysis_record.save()
    request_id = getattr(request, "request_id", None)
    logger.info(
        "Analysis started analysis_id=%s user_id=%s username=%s file_name=%s uploaded_at=%s request_id=%s",
        analysis_record.id,
        request.user.id,
        request.user.username,
        file_obj.name,
        timezone.localtime(analysis_record.created_at).isoformat() if analysis_record.created_at else None,
        request_id,
    )

    result = run_analysis(file_path, file_obj.name)
    if not result["success"]:
        analysis_record.status = "failed"
        analysis_record.error_message = result["error"] or ""
        analysis_record.completed_at = timezone.now()
        analysis_record.summary_metrics = {}
        analysis_record.save()
        logger.warning(
            "Analysis failed analysis_id=%s user_id=%s username=%s file_name=%s completed_at=%s error=%s request_id=%s",
            analysis_record.id,
            request.user.id,
            request.user.username,
            file_obj.name,
            timezone.localtime(analysis_record.completed_at).isoformat() if analysis_record.completed_at else None,
            analysis_record.error_message,
            request_id,
        )
        try:
            os.remove(file_path)
        except OSError:
            pass
        messages.error(request, result["error"] or "Analysis failed.")
        return render(request, "optimizer/home.html", {"error": result["error"], "title": "SQL License Optimizer"})

    context = result["context"]
    summary_metrics = build_analysis_summary_metrics(context)
    analysis_record.status = "completed"
    analysis_record.result_data = _make_json_serializable(context)
    analysis_record.summary_metrics = _make_json_serializable(summary_metrics)
    analysis_record.completed_at = timezone.now()
    analysis_record.save()

    request.session["optimizer_analysis_id"] = analysis_record.id
    request.session.pop("optimizer_results", None)
    request.session.pop("optimizer_file_path", None)
    request.session.pop("optimizer_file_name", None)
    logger.info(
        "Analysis completed analysis_id=%s user_id=%s username=%s file_name=%s completed_at=%s summary_metrics=%s request_id=%s",
        analysis_record.id,
        request.user.id,
        request.user.username,
        file_obj.name,
        timezone.localtime(analysis_record.completed_at).isoformat() if analysis_record.completed_at else None,
        summary_metrics,
        request_id,
    )
    return redirect("optimizer:results")


@require_GET
@login_required
def results(request):
    """Unified results/dashboard: tabs (Rule 1, Rule 2, Combined), single screen."""
    analysis, redir = _get_analysis_record(request)
    if redir is not None:
        return redir
    context = _normalize_analysis_context(analysis)
    context = _ensure_payg_zone_breakdown(analysis, context)

    render_context = build_dashboard_context(context, getattr(request, "request_id", None))
    render_context["rule_results"] = context["rule_results"]
    render_context["license_metrics"] = context["license_metrics"]
    render_context["file_name"] = context["file_name"]
    render_context["sheet_names_used"] = context["sheet_names_used"]
    render_context["analysis_id"] = analysis.id
    render_context["analysis_status"] = analysis.status
    render_context["analysis_source_file_name"] = context["file_name"]
    render_context["analysis_sheet_names"] = context["sheet_names_used"]
    render_context["analysis_created_at"] = timezone.localtime(analysis.created_at) if analysis.created_at else None

    # Pagination for Rule 1 and Rule 2 raw data (6 rows per page, no scrolling)
    per_page = 6
    rr = context.get("rule_results") or {}
    azure_full = rr.get("azure_payg") or []
    retired_full = rr.get("retired_devices") or []
    requested_rule1_page = _get_page_number(request, "rule1_page")
    requested_rule2_page = _get_page_number(request, "rule2_page")
    total_rule1_pages = max(1, (len(azure_full) + per_page - 1) // per_page)
    total_rule2_pages = max(1, (len(retired_full) + per_page - 1) // per_page)
    rule1_page = min(requested_rule1_page, total_rule1_pages)
    rule2_page = min(requested_rule2_page, total_rule2_pages)
    rule1_keys = list(azure_full[0].keys()) if azure_full else []
    rule2_keys = list(retired_full[0].keys()) if retired_full else []
    azure_slice = azure_full[(rule1_page - 1) * per_page : rule1_page * per_page]
    retired_slice = retired_full[(rule2_page - 1) * per_page : rule2_page * per_page]
    render_context["azure_payg_page"] = [[r.get(k) for k in rule1_keys] for r in azure_slice]
    render_context["retired_devices_page"] = [[r.get(k) for k in rule2_keys] for r in retired_slice]
    render_context["rule1_page"] = rule1_page
    render_context["rule2_page"] = rule2_page
    render_context["total_rule1_pages"] = total_rule1_pages
    render_context["total_rule2_pages"] = total_rule2_pages
    render_context["rule1_keys"] = rule1_keys
    render_context["rule2_keys"] = rule2_keys
    render_context["rule1_prev"] = max(1, rule1_page - 1)
    render_context["rule1_next"] = min(total_rule1_pages, rule1_page + 1)
    render_context["rule2_prev"] = max(1, rule2_page - 1)
    render_context["rule2_next"] = min(total_rule2_pages, rule2_page + 1)
    # Full data as JSON for client-side pagination (no full page reload)
    render_context["rule1_data_json"] = [
        [r.get(k) for k in rule1_keys] for r in azure_full
    ]
    render_context["rule2_data_json"] = [
        [r.get(k) for k in rule2_keys] for r in retired_full
    ]
    # Interactive Plotly charts (hover tooltips, responsive)
    if get_all_plotly_specs is not None:
        try:
            render_context["chart_specs"] = get_all_plotly_specs(
                context.get("rule_results", {}),
                context.get("license_metrics", {}),
            )
        except Exception as e:
            logger.exception("Plotly chart specs failed: %s", e)
            render_context["chart_specs"] = {}
    else:
        render_context["chart_specs"] = {}

    # Fallback: static matplotlib images when Plotly not used
    if getattr(settings, "OPTIMIZER_CHARTS_ENABLED", True) and generate_all_charts is not None and not render_context.get("chart_specs"):
        try:
            charts, chart_formats = generate_all_charts(
                context.get("rule_results", {}),
                context.get("license_metrics", {}),
            )
            render_context["chart_images"] = charts
            render_context["chart_formats"] = chart_formats
        except Exception as e:
            logger.exception("Chart generation failed: %s", e)
            render_context["chart_images"] = {}
            render_context["chart_formats"] = {}
    else:
        render_context.setdefault("chart_images", {})
        render_context.setdefault("chart_formats", {})
    return render(request, "optimizer/dashboard.html", render_context)


@require_GET
@login_required
def dashboard(request):
    """Same as results: unified tabbed view."""
    return results(request)


@require_http_methods(["GET", "POST"])
@csrf_protect
@login_required
def profile_page(request):
    """Display and update the logged-in user's profile details."""
    profile = _get_or_create_user_profile(request.user)
    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("optimizer:profile")
    else:
        form = UserProfileForm(instance=profile, user=request.user)
    context = _build_profile_context(request.user, profile, form=form)
    return render(request, "optimizer/profile.html", context)


@require_GET
@login_required
def report_page(request):
    """Report page with AI-generated text and download links."""
    context, redir = _get_analysis_context(request)
    if redir is not None:
        return redir
    context.setdefault("title", "IT License and Cost Optimization Report")
    if context.get("report_text"):
        context["report_text"] = build_report_markdown(
            context["report_text"],
            report_context=_build_report_render_context(context),
        )
    return render(request, "optimizer/report.html", context)


@require_GET
@login_required
def report_download(request, format_type):
    """Download report as PDF, Word, or Excel."""
    normalized_format = REPORT_FORMAT_ALIASES.get(format_type, format_type)
    if normalized_format not in ALLOWED_REPORT_FORMATS:
        return HttpResponse("Invalid format.", status=400)
    context, redir = _get_analysis_context(request)
    if redir is not None:
        return redir
    from optimizer.services.ai_report_generator import get_fallback_report
    report_text = context.get("report_text") or get_fallback_report({
        "azure_payg_count": context.get("rule_results", {}).get("azure_payg_count", 0),
        "retired_count": context.get("rule_results", {}).get("retired_count", 0),
        "total_demand_quantity": context.get("license_metrics", {}).get("total_demand_quantity", 0),
        "total_license_cost": context.get("license_metrics", {}).get("total_license_cost", 0),
        "demand_row_count": 0,
    })
    report_text = normalize_report_content_text(report_text)
    report_export_context = _build_report_render_context(context)
    generated_at = timezone.localtime()
    analysis_id = request.session.get("optimizer_analysis_id")
    base_name = f"sql_license_optimization_report_{analysis_id or 'report'}"
    if normalized_format == "pdf":
        content = export_pdf(report_text, generated_at=generated_at, report_context=report_export_context)
        if content is None:
            return HttpResponse("PDF export not available (install reportlab).", status=501)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = _safe_content_disposition(f"{base_name}.pdf")
        return response
    if normalized_format == "docx":
        content = export_docx(report_text, generated_at=generated_at, report_context=report_export_context)
        if content is None:
            return HttpResponse("Word export not available (install python-docx).", status=501)
        response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        response["Content-Disposition"] = _safe_content_disposition(f"{base_name}.docx")
        return response
    if normalized_format == "xlsx":
        content = export_xlsx(report_text, generated_at=generated_at, report_context=report_export_context)
        if content is None:
            return HttpResponse("Excel export not available (install openpyxl).", status=501)
        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = _safe_content_disposition(f"{base_name}.xlsx")
        return response
    return HttpResponse("Invalid format.", status=400)


@require_GET
@login_required
def analysis_logs(request):
    """Return all persisted analysis logs for the authenticated user."""
    return JsonResponse({"logs": get_user_analysis_logs(request.user)})


@require_GET
@login_required
def download_rule_data(request, rule_id):
    """Download Rule 1 or Rule 2 data as Excel. rule_id whitelisted to rule1, rule2."""
    if rule_id not in ALLOWED_RULE_IDS:
        return HttpResponse("Invalid rule.", status=400)
    context, redir = _get_analysis_context(request)
    if redir is not None:
        return redir
    rr = context.get("rule_results", {})
    if rule_id == "rule1":
        data = rr.get("azure_payg", [])
        filename = "azure_payg_candidates.xlsx"
    else:
        data = rr.get("retired_devices", [])
        filename = "retired_devices_with_installations.xlsx"
    if not data:
        return HttpResponse("No data to download.", status=404)
    df = pd.DataFrame(data)
    from io import BytesIO
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    aid = request.session.get("optimizer_analysis_id")
    if aid:
        base, ext = filename.rsplit(".", 1)
        filename = f"{base}_{aid}.{ext}"
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = _safe_content_disposition(filename)
    return response
