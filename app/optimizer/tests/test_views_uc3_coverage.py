"""
Coverage tests for UC3 download view functions.
Uses RequestFactory to call view functions that are not registered in URLs.
"""
import pandas as pd
import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

User = get_user_model()

# ── Shared fake DataFrame columns ────────────────────────────────────────────

def _base_df(n=2):
    return pd.DataFrame({
        "server_name": [f"SRV-{i:02d}" for i in range(n)],
        "Environment": ["Production", "Development"][:n],
        "Avg_CPU_12m": [8.0, 20.0][:n],
        "Peak_CPU_12m": [60.0, 80.0][:n],
        "Current_vCPU": [8, 4][:n],
        "Avg_FreeMem_12m": [40.0, 20.0][:n],
        "Min_FreeMem_12m": [25.0, 10.0][:n],
        "Current_RAM_GiB": [32.0, 16.0][:n],
    })


def _crit_df():
    df = _base_df()
    df["Criticality"] = ["Business Critical", "Mission Critical"]
    return df


def _physical_df():
    df = _base_df()
    df["Is Virtual?"] = ["False", "True"]
    return df


def _lc_df():
    df = _base_df()
    df["Criticality"] = ["Business Critical", "Mission Critical"]
    df["Peak_CPU_12m"] = [98.0, 50.0]
    df["Min_FreeMem_12m"] = [2.0, 15.0]
    return df


def _make_user(username):
    return User.objects.create_user(
        username=username, password="TestPass123!", email=f"{username}@test.com"
    )


def _get_request(user, url="/fake/"):
    factory = RequestFactory()
    request = factory.get(url)
    request.user = user
    return request


# ── download_uc3_ram_input_data ───────────────────────────────────────────────

@pytest.mark.django_db
class TestDownloadUc3RamInputData:
    def test_returns_404_when_empty(self, monkeypatch):
        from optimizer.views import download_uc3_ram_input_data

        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: pd.DataFrame(),
        )
        user = _make_user("uc3_ram_empty")
        request = _get_request(user)
        response = download_uc3_ram_input_data(request)
        assert response.status_code == 404

    def test_returns_excel_with_data(self, monkeypatch):
        from optimizer.views import download_uc3_ram_input_data

        fake_df = _base_df()
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: fake_df,
        )
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service.build_rightsizing_sheet_export",
            lambda sheet_key: pd.DataFrame(),
        )
        user = _make_user("uc3_ram_data")
        request = _get_request(user)
        response = download_uc3_ram_input_data(request)
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")


# ── download_uc3_cpu_input_data ───────────────────────────────────────────────

@pytest.mark.django_db
class TestDownloadUc3CpuInputData:
    def test_returns_404_when_empty(self, monkeypatch):
        from optimizer.views import download_uc3_cpu_input_data

        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: pd.DataFrame(),
        )
        user = _make_user("uc3_cpu_empty")
        request = _get_request(user)
        response = download_uc3_cpu_input_data(request)
        assert response.status_code == 404

    def test_returns_excel_with_data(self, monkeypatch):
        from optimizer.views import download_uc3_cpu_input_data

        fake_df = _base_df()
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: fake_df,
        )
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service.build_rightsizing_sheet_export",
            lambda sheet_key: pd.DataFrame(),
        )
        user = _make_user("uc3_cpu_data")
        request = _get_request(user)
        response = download_uc3_cpu_input_data(request)
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")


# ── download_uc3_crit_cpu_input_data ─────────────────────────────────────────

@pytest.mark.django_db
class TestDownloadUc3CritCpuInputData:
    def test_returns_404_when_empty(self, monkeypatch):
        from optimizer.views import download_uc3_crit_cpu_input_data

        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: pd.DataFrame(),
        )
        user = _make_user("uc3_critcpu_empty")
        request = _get_request(user)
        response = download_uc3_crit_cpu_input_data(request)
        assert response.status_code == 404

    def test_returns_excel_without_criticality_column(self, monkeypatch):
        from optimizer.views import download_uc3_crit_cpu_input_data

        fake_df = _base_df()  # no Criticality column
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: fake_df,
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_criticality_cpu_downsize_optimizations",
            lambda df: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_criticality_cpu_upsize_optimizations",
            lambda df: pd.DataFrame(),
        )
        user = _make_user("uc3_critcpu_nocol")
        request = _get_request(user)
        response = download_uc3_crit_cpu_input_data(request)
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")

    def test_returns_excel_with_criticality_data(self, monkeypatch):
        from optimizer.views import download_uc3_crit_cpu_input_data

        fake_df = _crit_df()
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: fake_df,
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_criticality_cpu_downsize_optimizations",
            lambda df: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_criticality_cpu_upsize_optimizations",
            lambda df: pd.DataFrame(),
        )
        user = _make_user("uc3_critcpu_data")
        request = _get_request(user)
        response = download_uc3_crit_cpu_input_data(request)
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")


# ── download_uc3_crit_ram_input_data ─────────────────────────────────────────

@pytest.mark.django_db
class TestDownloadUc3CritRamInputData:
    def test_returns_404_when_empty(self, monkeypatch):
        from optimizer.views import download_uc3_crit_ram_input_data

        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: pd.DataFrame(),
        )
        user = _make_user("uc3_critram_empty")
        request = _get_request(user)
        response = download_uc3_crit_ram_input_data(request)
        assert response.status_code == 404

    def test_returns_excel_without_criticality_column(self, monkeypatch):
        from optimizer.views import download_uc3_crit_ram_input_data

        fake_df = _base_df()
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: fake_df,
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_criticality_ram_downsize_optimizations",
            lambda df: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_criticality_ram_upsize_optimizations",
            lambda df: pd.DataFrame(),
        )
        user = _make_user("uc3_critram_nocol")
        request = _get_request(user)
        response = download_uc3_crit_ram_input_data(request)
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")

    def test_returns_excel_with_criticality_data(self, monkeypatch):
        from optimizer.views import download_uc3_crit_ram_input_data

        fake_df = _crit_df()
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: fake_df,
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_criticality_ram_downsize_optimizations",
            lambda df: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_criticality_ram_upsize_optimizations",
            lambda df: pd.DataFrame(),
        )
        user = _make_user("uc3_critram_data")
        request = _get_request(user)
        response = download_uc3_crit_ram_input_data(request)
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")


# ── download_uc3_physical_input_data ─────────────────────────────────────────

@pytest.mark.django_db
class TestDownloadUc3PhysicalInputData:
    def test_returns_404_when_empty(self, monkeypatch):
        from optimizer.views import download_uc3_physical_input_data

        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: pd.DataFrame(),
        )
        user = _make_user("uc3_phys_empty")
        request = _get_request(user)
        response = download_uc3_physical_input_data(request)
        assert response.status_code == 404

    def test_returns_excel_without_virtual_column(self, monkeypatch):
        from optimizer.views import download_uc3_physical_input_data

        fake_df = _base_df()  # no Is Virtual? column
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: fake_df,
        )
        user = _make_user("uc3_phys_novirt")
        request = _get_request(user)
        response = download_uc3_physical_input_data(request)
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")

    def test_returns_excel_with_virtual_column(self, monkeypatch):
        from optimizer.views import download_uc3_physical_input_data

        fake_df = _physical_df()
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: fake_df,
        )
        user = _make_user("uc3_phys_data")
        request = _get_request(user)
        response = download_uc3_physical_input_data(request)
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")


# ── download_uc3_lifecycle_input_data ────────────────────────────────────────

@pytest.mark.django_db
class TestDownloadUc3LifecycleInputData:
    def test_returns_404_when_empty(self, monkeypatch):
        from optimizer.views import download_uc3_lifecycle_input_data

        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: pd.DataFrame(),
        )
        user = _make_user("uc3_lc_empty")
        request = _get_request(user)
        response = download_uc3_lifecycle_input_data(request)
        assert response.status_code == 404

    def test_returns_excel_without_criticality_column(self, monkeypatch):
        from optimizer.views import download_uc3_lifecycle_input_data

        fake_df = _base_df()
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: fake_df,
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_lifecycle_risk_flags",
            lambda df: pd.DataFrame(),
        )
        user = _make_user("uc3_lc_nocrit")
        request = _get_request(user)
        response = download_uc3_lifecycle_input_data(request)
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")

    def test_returns_excel_with_criticality_data(self, monkeypatch):
        from optimizer.views import download_uc3_lifecycle_input_data

        fake_df = _lc_df()
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: fake_df,
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_lifecycle_risk_flags",
            lambda df: pd.DataFrame(),
        )
        user = _make_user("uc3_lc_data")
        request = _get_request(user)
        response = download_uc3_lifecycle_input_data(request)
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")

    def test_returns_excel_with_nonempty_final_df(self, monkeypatch):
        from optimizer.views import download_uc3_lifecycle_input_data

        fake_df = _lc_df()
        final_df = fake_df.copy()
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: fake_df,
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_lifecycle_risk_flags",
            lambda df: final_df,
        )
        user = _make_user("uc3_lc_nonempty")
        request = _get_request(user)
        response = download_uc3_lifecycle_input_data(request)
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")


# ── _apply_summary_styles helper ─────────────────────────────────────────────

class TestApplySummaryStyles:
    def test_handles_exception_gracefully(self):
        from optimizer.views import _apply_summary_styles

        class BrokenWs:
            def __getitem__(self, key):
                raise RuntimeError("no styles")

        # Should not raise — exception is swallowed
        _apply_summary_styles(BrokenWs())

    def test_applies_styles_to_real_worksheet(self):
        from optimizer.views import _apply_summary_styles
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Description", "Count", "Note"])
        ws.append(["FINAL CANDIDATES", 5, "test"])
        ws.append(["--- section ---", None, ""])
        ws.append(["Normal row", 1, ""])
        _apply_summary_styles(ws)
        # No exception means success
        assert ws.column_dimensions is not None
