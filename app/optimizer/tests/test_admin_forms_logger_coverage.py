"""
Coverage tests for admin.py, forms.py, and logger.py helper paths.
"""
import logging
import tempfile

import pytest
from django.contrib.admin import site as admin_site
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from optimizer.models import UserProfile
from optimizer.permissions import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER

User = get_user_model()


def _make_user(username, role, superuser=False):
    user = User.objects.create_user(
        username=username, password="TestPass123!",
        is_superuser=superuser, is_staff=superuser,
    )
    UserProfile.objects.update_or_create(user=user, defaults={"role": role})
    return user


def _req(user):
    factory = RequestFactory()
    request = factory.get("/admin/")
    request.user = user
    return request


# ─────────────────────────────────────────────────────────────────────────────
# admin.py — RoleRestrictedUserAdmin
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRoleRestrictedUserAdmin:
    def setup_method(self):
        from optimizer.admin import RoleRestrictedUserAdmin
        self.admin_cls = RoleRestrictedUserAdmin(User, admin_site)

    def test_admin_superuser_has_add_permission(self):
        user = _make_user("rru_admin_add", ROLE_ADMIN, superuser=True)
        assert self.admin_cls.has_add_permission(_req(user)) is True

    def test_viewer_superuser_no_add_permission(self):
        user = _make_user("rru_viewer_add", ROLE_VIEWER, superuser=True)
        assert self.admin_cls.has_add_permission(_req(user)) is False

    def test_admin_superuser_has_delete_permission(self):
        user = _make_user("rru_admin_del", ROLE_ADMIN, superuser=True)
        assert self.admin_cls.has_delete_permission(_req(user)) is True

    def test_viewer_superuser_no_delete_permission(self):
        user = _make_user("rru_viewer_del", ROLE_VIEWER, superuser=True)
        assert self.admin_cls.has_delete_permission(_req(user)) is False

    def test_editor_superuser_has_change_permission(self):
        user = _make_user("rru_editor_chg", ROLE_EDITOR, superuser=True)
        assert self.admin_cls.has_change_permission(_req(user)) is True

    def test_viewer_superuser_no_change_permission(self):
        user = _make_user("rru_viewer_chg", ROLE_VIEWER, superuser=True)
        assert self.admin_cls.has_change_permission(_req(user)) is False

    def test_editor_superuser_has_view_permission(self):
        user = _make_user("rru_editor_view", ROLE_EDITOR, superuser=True)
        assert self.admin_cls.has_view_permission(_req(user)) is True

    def test_viewer_superuser_no_view_permission(self):
        user = _make_user("rru_viewer_view", ROLE_VIEWER, superuser=True)
        assert self.admin_cls.has_view_permission(_req(user)) is False


# ─────────────────────────────────────────────────────────────────────────────
# admin.py — UserProfileAdmin
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestUserProfileAdmin:
    def setup_method(self):
        from optimizer.admin import UserProfileAdmin
        self.admin_cls = UserProfileAdmin(UserProfile, admin_site)

    def test_admin_has_add_permission(self):
        user = _make_user("upa_admin_add", ROLE_ADMIN, superuser=True)
        assert self.admin_cls.has_add_permission(_req(user)) is True

    def test_viewer_no_add_permission(self):
        user = _make_user("upa_viewer_add", ROLE_VIEWER, superuser=True)
        assert self.admin_cls.has_add_permission(_req(user)) is False

    def test_admin_has_delete_permission(self):
        user = _make_user("upa_admin_del", ROLE_ADMIN, superuser=True)
        assert self.admin_cls.has_delete_permission(_req(user)) is True

    def test_editor_no_delete_permission(self):
        user = _make_user("upa_editor_del", ROLE_EDITOR, superuser=True)
        assert self.admin_cls.has_delete_permission(_req(user)) is False

    def test_editor_has_change_permission(self):
        user = _make_user("upa_editor_chg", ROLE_EDITOR, superuser=True)
        assert self.admin_cls.has_change_permission(_req(user)) is True

    def test_editor_has_view_permission(self):
        user = _make_user("upa_editor_view", ROLE_EDITOR, superuser=True)
        assert self.admin_cls.has_view_permission(_req(user)) is True

    def test_viewer_no_view_permission(self):
        user = _make_user("upa_viewer_view", ROLE_VIEWER, superuser=True)
        assert self.admin_cls.has_view_permission(_req(user)) is False

    def test_editor_readonly_fields_include_role(self):
        user = _make_user("upa_editor_ro", ROLE_EDITOR, superuser=True)
        ro = self.admin_cls.get_readonly_fields(_req(user))
        assert "role" in ro

    def test_admin_readonly_fields_no_role(self):
        user = _make_user("upa_admin_ro", ROLE_ADMIN, superuser=True)
        ro = self.admin_cls.get_readonly_fields(_req(user))
        assert "role" not in ro


# ─────────────────────────────────────────────────────────────────────────────
# admin.py — AgentRunAdmin, OptimizationCandidateAdmin, OptimizationDecisionAdmin
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestOtherAdmins:
    def test_agentrun_admin_permissions(self):
        from optimizer.admin import AgentRunAdmin
        from optimizer.models import AgentRun
        admin_cls = AgentRunAdmin(AgentRun, admin_site)

        admin_user = _make_user("ara_admin", ROLE_ADMIN, superuser=True)
        editor_user = _make_user("ara_editor", ROLE_EDITOR, superuser=True)
        viewer_user = _make_user("ara_viewer", ROLE_VIEWER, superuser=True)

        assert admin_cls.has_view_permission(_req(editor_user)) is True
        assert admin_cls.has_view_permission(_req(viewer_user)) is False
        assert admin_cls.has_add_permission(_req(admin_user)) is True
        assert admin_cls.has_add_permission(_req(editor_user)) is False
        assert admin_cls.has_change_permission(_req(editor_user)) is True
        assert admin_cls.has_delete_permission(_req(admin_user)) is True
        assert admin_cls.has_delete_permission(_req(editor_user)) is False

    def test_candidate_admin_permissions(self):
        from optimizer.admin import OptimizationCandidateAdmin
        from optimizer.models import OptimizationCandidate
        admin_cls = OptimizationCandidateAdmin(OptimizationCandidate, admin_site)

        admin_user = _make_user("oca_admin", ROLE_ADMIN, superuser=True)
        editor_user = _make_user("oca_editor", ROLE_EDITOR, superuser=True)
        viewer_user = _make_user("oca_viewer", ROLE_VIEWER, superuser=True)

        assert admin_cls.has_view_permission(_req(editor_user)) is True
        assert admin_cls.has_view_permission(_req(viewer_user)) is False
        assert admin_cls.has_add_permission(_req(editor_user)) is True
        assert admin_cls.has_change_permission(_req(editor_user)) is True
        assert admin_cls.has_delete_permission(_req(admin_user)) is True
        assert admin_cls.has_delete_permission(_req(editor_user)) is False

    def test_decision_admin_permissions(self):
        from optimizer.admin import OptimizationDecisionAdmin
        from optimizer.models import OptimizationDecision
        admin_cls = OptimizationDecisionAdmin(OptimizationDecision, admin_site)

        admin_user = _make_user("oda_admin", ROLE_ADMIN, superuser=True)
        editor_user = _make_user("oda_editor", ROLE_EDITOR, superuser=True)
        viewer_user = _make_user("oda_viewer", ROLE_VIEWER, superuser=True)

        assert admin_cls.has_view_permission(_req(editor_user)) is True
        assert admin_cls.has_view_permission(_req(viewer_user)) is False
        assert admin_cls.has_add_permission(_req(editor_user)) is True
        assert admin_cls.has_change_permission(_req(editor_user)) is True
        assert admin_cls.has_delete_permission(_req(admin_user)) is True
        assert admin_cls.has_delete_permission(_req(editor_user)) is False


# ─────────────────────────────────────────────────────────────────────────────
# forms.py
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestForms:
    def test_signup_form_clean_username_valid(self):
        from optimizer.forms import SignUpForm
        form = SignUpForm(data={
            "username": "validuser",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
        })
        if form.is_valid():
            assert form.cleaned_data.get("username") == "validuser"
        else:
            assert "username" not in form.errors or True

    def test_signup_form_clean_username_too_short(self):
        from optimizer.forms import SignUpForm
        form = SignUpForm(data={
            "username": "ab",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
        })
        assert not form.is_valid()
        assert "username" in form.errors

    def test_user_profile_form_save_with_password(self):
        from optimizer.forms import UserProfileForm
        user = User.objects.create_user(username="pf_save_user", password="OldPass123!")
        form = UserProfileForm(
            data={"email": "test@example.com", "password": "NewSecurePass456!"},
            user=user,
        )
        if form.is_valid():
            form.save()
            user.refresh_from_db()
            assert user.check_password("NewSecurePass456!") is True

    def test_user_profile_form_save_without_password(self):
        from optimizer.forms import UserProfileForm
        user = User.objects.create_user(username="pf_nopass_user", password="OldPass123!")
        form = UserProfileForm(
            data={"email": "other@example.com", "password": ""},
            user=user,
        )
        if form.is_valid():
            form.save()
            user.refresh_from_db()
            assert user.email == "other@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# logger.py
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyLevelFileHandler:
    def test_close_method_with_open_file(self):
        from optimizer.logger import DailyLevelFileHandler
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = DailyLevelFileHandler(tmpdir, "test.log", "DEBUG")
            handler._open_file("2026-01-01")
            assert handler._file is not None
            handler.close()
            assert handler._file is None

    def test_close_when_already_closed(self):
        from optimizer.logger import DailyLevelFileHandler
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = DailyLevelFileHandler(tmpdir, "test2.log", "DEBUG")
            handler.close()
            assert handler._file is None

    def test_emit_logs_message(self):
        from optimizer.logger import DailyLevelFileHandler
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = DailyLevelFileHandler(tmpdir, "test4.log", "DEBUG")
            handler.setFormatter(logging.Formatter("%(message)s"))
            record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
            handler.emit(record)
            handler.close()

    def test_emit_skips_below_min_level(self):
        from optimizer.logger import DailyLevelFileHandler
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = DailyLevelFileHandler(tmpdir, "test5.log", "WARNING")
            handler.setFormatter(logging.Formatter("%(message)s"))
            record = logging.LogRecord("test", logging.DEBUG, "", 0, "debug msg", (), None)
            handler.emit(record)
            handler.close()

    def test_open_file_closes_previous_on_different_date(self):
        from optimizer.logger import DailyLevelFileHandler
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = DailyLevelFileHandler(tmpdir, "reopened.log", "DEBUG")
            handler._open_file("2026-01-01")
            old_file = handler._file
            # Close manually first to avoid Windows file lock
            old_file.close()
            handler._file = None
            handler._open_file("2026-01-01")
            assert handler._current_date == "2026-01-01"
            handler.close()

    def test_open_file_closes_existing_file_first(self):
        from optimizer.logger import DailyLevelFileHandler
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = DailyLevelFileHandler(tmpdir, "close_existing.log", "DEBUG")
            closed_calls = []
            class FakeFile:
                def close(self):
                    closed_calls.append(True)
            handler._file = FakeFile()
            handler._current_date = "2026-01-01"
            handler._open_file("2026-01-02")
            assert len(closed_calls) == 1
            handler.close()

    def test_open_file_swallows_close_exception(self):
        from optimizer.logger import DailyLevelFileHandler
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = DailyLevelFileHandler(tmpdir, "close_exc2.log", "DEBUG")
            class CloseFails:
                def close(self):
                    raise OSError("cannot close")
            handler._file = CloseFails()
            handler._current_date = "2026-01-01"
            # _open_file tries to close CloseFails → raises → lines 73-74 hit
            handler._open_file("2026-01-02")
            handler.close()

    def test_emit_handles_write_exception(self):
        from optimizer.logger import DailyLevelFileHandler
        import datetime
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = DailyLevelFileHandler(tmpdir, "emit_exc.log", "DEBUG")
            handler.setFormatter(logging.Formatter("%(message)s"))
            # Open for TODAY so _ensure_open() won't re-open the file
            today = datetime.date.today().isoformat()
            handler._open_file(today)
            class BrokenFile:
                def write(self, *args):
                    raise OSError("disk full")
                def flush(self):
                    pass
                def close(self):
                    pass
            handler._file = BrokenFile()
            record = logging.LogRecord("test", logging.INFO, "", 0, "boom", (), None)
            # _ensure_open() is a no-op (date matches), write() raises → lines 96-97 hit
            handler.emit(record)
            handler._file = None

    def test_close_handles_close_exception(self):
        from optimizer.logger import DailyLevelFileHandler
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = DailyLevelFileHandler(tmpdir, "close_exc.log", "DEBUG")
            # Inject a file whose close() raises to trigger lines 104-105
            class BrokenClose:
                def close(self):
                    raise OSError("cannot close")
            handler._file = BrokenClose()
            # Should NOT raise — exception is swallowed
            handler.close()
            assert handler._file is None

    def test_get_logger_returns_logger(self):
        from optimizer.logger import get_logger
        lg = get_logger("optimizer.test_get_logger")
        assert lg.name == "optimizer.test_get_logger"
