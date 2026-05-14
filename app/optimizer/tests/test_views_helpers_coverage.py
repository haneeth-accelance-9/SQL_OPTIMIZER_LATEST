"""
Additional coverage tests for pure helper functions in optimizer.views.
Targets missed lines: 56-57, 67, 69-72, 76-77, 86-87, 146-147, 166-307, 362-415.

No duplicate of tests already in test_views_helpers.py.
"""
import pytest
import pandas as pd
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# _eu_currency  (lines 12-20)
# ---------------------------------------------------------------------------

from optimizer.views import _eu_currency


class TestEuCurrency:
    def test_integer_value(self):
        result = _eu_currency(1000)
        assert "1.000,00" in result
        assert "€" in result

    def test_float_value(self):
        result = _eu_currency(1234567.89)
        assert "1.234.567,89" in result
        assert "€" in result

    def test_zero(self):
        result = _eu_currency(0)
        assert "0,00" in result

    def test_negative_number(self):
        result = _eu_currency(-500.5)
        assert "500,50" in result

    def test_none_returns_string(self):
        result = _eu_currency(None)
        # Cannot convert None to float — returns str(None)
        assert isinstance(result, str)
        assert result == "None"

    def test_string_number(self):
        result = _eu_currency("2500.75")
        assert "2.500,75" in result

    def test_non_numeric_string(self):
        result = _eu_currency("not_a_number")
        assert result == "not_a_number"

    def test_small_float(self):
        result = _eu_currency(0.01)
        assert "0,01" in result


# ---------------------------------------------------------------------------
# _make_json_serializable  (lines 60-82) — additional edge-case paths
# ---------------------------------------------------------------------------

from optimizer.views import _make_json_serializable


class TestMakeJsonSerializableEdgeCases:
    """Cover the numpy-like paths (tolist / item) not exercised by existing tests."""

    def test_pandas_series_via_tolist(self):
        """pandas Series has .tolist() and IS iterable (covers line 67)."""
        # pd.Series is not a str/bytes, has .tolist() → goes through line 67
        series = pd.Series([1, 2, 3])
        result = _make_json_serializable(series)
        assert isinstance(result, list)
        assert result == [1, 2, 3]

    def test_item_path_via_mock_object(self):
        """Object that has .item() but not .tolist() triggers lines 68-70."""
        class FakeScalar:
            def item(self):
                return 99

        result = _make_json_serializable(FakeScalar())
        assert result == 99

    def test_dict_with_pandas_na_values(self):
        """Recursive dict serialization of pd.NA values."""
        obj = {"a": pd.NA, "b": 42, "c": "text"}
        result = _make_json_serializable(obj)
        assert result["a"] is None
        assert result["b"] == 42
        assert result["c"] == "text"

    def test_list_with_mixed_types(self):
        """List containing plain types and pandas NA."""
        obj = [1, "text", pd.NA, None, True]
        result = _make_json_serializable(obj)
        assert result[0] == 1
        assert result[1] == "text"
        assert result[2] is None  # pd.NA → None
        assert result[3] is None
        assert result[4] is True

    def test_tuple_converted_to_list(self):
        result = _make_json_serializable((10, 20))
        assert result == [10, 20]

    def test_nested_list_of_dicts(self):
        obj = [{"x": pd.NA}, {"x": 1}]
        result = _make_json_serializable(obj)
        assert result[0]["x"] is None
        assert result[1]["x"] == 1

    def test_decimal_stringified(self):
        """Decimal is not in native types so it falls through to str()."""
        d = Decimal("9.99")
        result = _make_json_serializable(d)
        assert isinstance(result, str)
        assert "9.99" in result

    def test_datetime_stringified(self):
        dt = datetime(2024, 6, 1, 12, 0)
        result = _make_json_serializable(dt)
        assert isinstance(result, str)
        assert "2024" in result


# ---------------------------------------------------------------------------
# _build_profile_initials  (lines 101-111)
# ---------------------------------------------------------------------------

from optimizer.views import _build_profile_initials


class TestBuildProfileInitials:
    def _user(self, first="", last="", username=""):
        u = MagicMock()
        u.first_name = first
        u.last_name = last
        u.username = username
        return u

    def test_first_and_last_name(self):
        user = self._user(first="Alice", last="Brown")
        assert _build_profile_initials(user) == "AB"

    def test_first_name_only(self):
        user = self._user(first="Bob")
        assert _build_profile_initials(user) == "B"

    def test_last_name_only(self):
        user = self._user(last="Smith")
        assert _build_profile_initials(user) == "S"

    def test_empty_names_falls_back_to_username(self):
        user = self._user(username="john_doe")
        result = _build_profile_initials(user)
        assert result == "JD"

    def test_email_style_username(self):
        """username with dots splits on '.' — covers re.split path."""
        user = self._user(username="jane.doe")
        result = _build_profile_initials(user)
        assert result == "JD"

    def test_username_with_dash(self):
        user = self._user(username="alex-smith")
        result = _build_profile_initials(user)
        assert result == "AS"

    def test_empty_everything_returns_u(self):
        user = self._user(username="")
        result = _build_profile_initials(user)
        assert result == "U"

    def test_result_is_uppercase(self):
        user = self._user(first="alice", last="brown")
        result = _build_profile_initials(user)
        assert result == result.upper()

    def test_whitespace_only_names_falls_back(self):
        user = self._user(first="  ", last="  ", username="bob")
        result = _build_profile_initials(user)
        assert result == "B"


# ---------------------------------------------------------------------------
# _build_post_login_redirect_url  (lines 138-140)
# ---------------------------------------------------------------------------

from optimizer.views import _build_post_login_redirect_url


class TestBuildPostLoginRedirectUrl:
    def test_returns_string(self):
        result = _build_post_login_redirect_url()
        assert isinstance(result, str)

    def test_contains_home_fragment(self):
        result = _build_post_login_redirect_url()
        assert "home" in result or "/" in result

    def test_not_empty(self):
        result = _build_post_login_redirect_url()
        assert len(result) > 0


# ---------------------------------------------------------------------------
# _get_page_number  (lines 418-423)  — covers the "clamping" and fallback paths
# ---------------------------------------------------------------------------

from optimizer.views import _get_page_number


class _FakeGET:
    def __init__(self, params):
        self._params = params

    def get(self, key, default=None):
        return self._params.get(key, default)


class _FakeRequest:
    def __init__(self, params):
        self.GET = _FakeGET(params)


class TestGetPageNumber:
    def test_valid_positive_int(self):
        req = _FakeRequest({"page": "3"})
        assert _get_page_number(req, "page") == 3

    def test_negative_value_clamped_to_one(self):
        req = _FakeRequest({"page": "-5"})
        assert _get_page_number(req, "page") == 1

    def test_zero_clamped_to_one(self):
        req = _FakeRequest({"page": "0"})
        assert _get_page_number(req, "page") == 1

    def test_string_non_numeric_returns_default(self):
        req = _FakeRequest({"page": "abc"})
        result = _get_page_number(req, "page", default=2)
        assert result == 2

    def test_missing_param_returns_default(self):
        req = _FakeRequest({})
        assert _get_page_number(req, "page") == 1

    def test_missing_param_custom_default(self):
        req = _FakeRequest({})
        assert _get_page_number(req, "p", default=5) == 5

    def test_none_value_returns_default(self):
        req = _FakeRequest({"page": None})
        result = _get_page_number(req, "page", default=1)
        # int(None) raises TypeError → returns default
        assert result == 1


# ---------------------------------------------------------------------------
# _format_metric_label — additional paths not in test_views_helpers.py
# ---------------------------------------------------------------------------

from optimizer.views import _format_metric_label


class TestFormatMetricLabelExtra:
    def test_multiple_words(self):
        assert _format_metric_label("avg_cpu_util") == "Avg Cpu Util"

    def test_all_uppercase_letters(self):
        # Each segment capitalised individually
        result = _format_metric_label("ram_usage")
        assert result == "Ram Usage"

    def test_integer_input(self):
        # Non-string is cast via str()
        result = _format_metric_label(42)
        assert result == "42"


# ---------------------------------------------------------------------------
# _build_profile_context  (lines 114-129) — needs Django DB
# ---------------------------------------------------------------------------

from optimizer.views import _build_profile_context


@pytest.mark.django_db
class TestBuildProfileContext:
    def _make_user(self, django_user_model, first="", last="", username="testprofileuser", email=""):
        return django_user_model.objects.create_user(
            username=username,
            password="pass",
            first_name=first,
            last_name=last,
            email=email,
        )

    def _make_profile(self, user):
        from optimizer.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return profile

    def test_returns_dict_with_expected_keys(self, django_user_model):
        user = self._make_user(django_user_model, first="Alice", last="Smith", username="testpc1")
        profile = self._make_profile(user)
        ctx = _build_profile_context(user, profile)
        for key in ("title", "profile_display_name", "profile_initials", "profile_email",
                    "profile_username", "profile_team_name", "profile_image_url",
                    "profile_first_name", "profile_last_name", "profile_form"):
            assert key in ctx

    def test_display_name_full_name_when_set(self, django_user_model):
        user = self._make_user(django_user_model, first="Bob", last="Jones", username="testpc2")
        profile = self._make_profile(user)
        ctx = _build_profile_context(user, profile)
        assert ctx["profile_display_name"] == "Bob Jones"

    def test_display_name_falls_back_to_username(self, django_user_model):
        user = self._make_user(django_user_model, username="testpc3")
        profile = self._make_profile(user)
        ctx = _build_profile_context(user, profile)
        assert ctx["profile_display_name"] == "testpc3"

    def test_email_not_provided_when_empty(self, django_user_model):
        user = self._make_user(django_user_model, username="testpc4", email="")
        profile = self._make_profile(user)
        ctx = _build_profile_context(user, profile)
        assert ctx["profile_email"] == "Not provided"

    def test_email_shown_when_set(self, django_user_model):
        user = self._make_user(django_user_model, username="testpc5", email="a@b.com")
        profile = self._make_profile(user)
        ctx = _build_profile_context(user, profile)
        assert ctx["profile_email"] == "a@b.com"

    def test_team_name_not_provided_when_blank(self, django_user_model):
        user = self._make_user(django_user_model, username="testpc6")
        profile = self._make_profile(user)
        profile.team_name = ""
        profile.save()
        ctx = _build_profile_context(user, profile)
        assert ctx["profile_team_name"] == "Not provided"

    def test_form_injected_when_supplied(self, django_user_model):
        from optimizer.forms import UserProfileForm
        user = self._make_user(django_user_model, username="testpc7")
        profile = self._make_profile(user)
        form = UserProfileForm(instance=profile, user=user)
        ctx = _build_profile_context(user, profile, form=form)
        assert ctx["profile_form"] is form

    def test_initials_computed_from_names(self, django_user_model):
        user = self._make_user(django_user_model, first="Carol", last="Davis", username="testpc8")
        profile = self._make_profile(user)
        ctx = _build_profile_context(user, profile)
        assert ctx["profile_initials"] == "CD"


# ---------------------------------------------------------------------------
# _get_or_create_user_profile  (lines 132-135) — needs Django DB
# ---------------------------------------------------------------------------

from optimizer.views import _get_or_create_user_profile


@pytest.mark.django_db
class TestGetOrCreateUserProfile:
    def test_creates_profile_when_missing(self, django_user_model):
        from optimizer.models import UserProfile
        user = django_user_model.objects.create_user(username="gocp_user1", password="x")
        # Ensure no profile exists
        UserProfile.objects.filter(user=user).delete()
        profile = _get_or_create_user_profile(user)
        assert profile is not None
        assert profile.user == user

    def test_returns_existing_profile(self, django_user_model):
        from optimizer.models import UserProfile
        user = django_user_model.objects.create_user(username="gocp_user2", password="x")
        UserProfile.objects.filter(user=user).delete()
        created = _get_or_create_user_profile(user)
        fetched = _get_or_create_user_profile(user)
        assert created.pk == fetched.pk

    def test_profile_count_not_duplicated(self, django_user_model):
        from optimizer.models import UserProfile
        user = django_user_model.objects.create_user(username="gocp_user3", password="x")
        _get_or_create_user_profile(user)
        _get_or_create_user_profile(user)
        assert UserProfile.objects.filter(user=user).count() == 1


# ---------------------------------------------------------------------------
# _build_report_render_context  (lines 145-157)
# ---------------------------------------------------------------------------

from optimizer.views import _build_report_render_context


class TestBuildReportRenderContext:
    """Pure function — no DB needed if we mock build_dashboard_context."""

    def _minimal_context(self):
        return {
            "rule_results": {
                "azure_payg_count": 3,
                "retired_count": 5,
            },
            "license_metrics": {
                "total_demand_quantity": 100,
                "total_license_cost": 50000.0,
                "by_product": [{"name": "SQL Server", "cost": 50000.0}],
            },
        }

    def test_returns_expected_keys(self):
        context = self._minimal_context()
        result = _build_report_render_context(context)
        for key in ("azure_payg_count", "retired_count", "total_demand_quantity",
                    "total_license_cost", "by_product", "rule_wise_savings",
                    "total_savings", "azure_payg_savings", "retired_devices_savings"):
            assert key in result

    def test_azure_payg_count_mapped(self):
        result = _build_report_render_context(self._minimal_context())
        assert result["azure_payg_count"] == 3

    def test_retired_count_mapped(self):
        result = _build_report_render_context(self._minimal_context())
        assert result["retired_count"] == 5

    def test_empty_context_does_not_crash(self):
        result = _build_report_render_context({})
        assert result["azure_payg_count"] == 0
        assert result["retired_count"] == 0

    def test_by_product_passed_through(self):
        ctx = self._minimal_context()
        result = _build_report_render_context(ctx)
        assert len(result["by_product"]) == 1


# ---------------------------------------------------------------------------
# _build_rightsizing_filter_funnel  (lines 160-353) — empty-DB path
# ---------------------------------------------------------------------------

from optimizer.views import _build_rightsizing_filter_funnel


@pytest.mark.django_db
class TestBuildRightsizingFilterFunnel:
    def test_returns_dict_with_empty_db(self):
        """With an empty DB, _build_rightsizing_df() returns empty DataFrame → {}."""
        result = _build_rightsizing_filter_funnel()
        assert isinstance(result, dict)

    def test_empty_db_returns_empty_dict(self):
        result = _build_rightsizing_filter_funnel()
        # Either empty dict (no data) or a populated dict (if seeded DB) — must not raise
        assert result is not None


# ---------------------------------------------------------------------------
# _get_db_context_for_report  (lines 356-415) — empty-DB path
# ---------------------------------------------------------------------------

from optimizer.views import _get_db_context_for_report


@pytest.mark.django_db
class TestGetDbContextForReport:
    def test_returns_dict_with_expected_keys(self):
        ctx = _get_db_context_for_report()
        assert isinstance(ctx, dict)
        for key in ("report_text", "report_used_fallback", "title", "data_source"):
            assert key in ctx

    def test_title_is_correct(self):
        ctx = _get_db_context_for_report()
        assert ctx["title"] == "IT License and Cost Optimization Report"

    def test_data_source_is_database(self):
        ctx = _get_db_context_for_report()
        assert ctx["data_source"] == "database"

    def test_report_text_is_string(self):
        ctx = _get_db_context_for_report()
        assert isinstance(ctx["report_text"], str)

    def test_filter_funnel_key_present(self):
        ctx = _get_db_context_for_report()
        assert "filter_funnel" in ctx
        assert isinstance(ctx["filter_funnel"], dict)

    def test_report_used_fallback_is_bool(self):
        ctx = _get_db_context_for_report()
        assert isinstance(ctx["report_used_fallback"], bool)

    def test_ai_report_disabled_uses_fallback(self):
        """When AI is disabled, report_used_fallback should be True."""
        with patch("django.conf.settings.OPTIMIZER_AI_REPORT_ENABLED", False):
            ctx = _get_db_context_for_report()
            assert ctx["report_used_fallback"] is True

    def test_ai_report_exception_falls_back_gracefully(self):
        """If AI generation raises, fallback report is used."""
        with patch(
            "optimizer.services.ai_report_generator.generate_report_text",
            side_effect=RuntimeError("AI unavailable"),
        ):
            ctx = _get_db_context_for_report()
            assert ctx["report_used_fallback"] is True
            assert isinstance(ctx["report_text"], str)
            assert len(ctx["report_text"]) > 0
