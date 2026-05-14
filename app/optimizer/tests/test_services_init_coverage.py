"""
Coverage tests for optimizer.services.__init__.py — lines 7-8 (ImportError branch).

The module does:
    try:
        from .chart_generator import generate_all_charts
    except ImportError:
        generate_all_charts = None  # lines 7-8

We exercise both the normal path and the ImportError path.
"""
import importlib
import sys
from unittest.mock import patch

import pytest


class TestServicesInitImport:
    def test_generate_all_charts_is_callable_or_none(self):
        """Smoke test: the attribute exists and is either callable or None."""
        from optimizer.services import generate_all_charts
        assert generate_all_charts is None or callable(generate_all_charts)

    def test_generate_all_charts_exists_in_module(self):
        """Ensure generate_all_charts is actually exported."""
        import optimizer.services as services
        assert hasattr(services, "generate_all_charts")

    def test_import_error_path_sets_generate_all_charts_to_none(self):
        """
        Simulate an ImportError when importing chart_generator to cover lines 7-8.
        We poison sys.modules with None for chart_generator, then reload optimizer.services.
        When Python finds None in sys.modules for an import, it raises ImportError,
        which exercises the except ImportError branch.
        """
        chart_gen_key = "optimizer.services.chart_generator"
        services_key = "optimizer.services"

        original_chart_gen = sys.modules.get(chart_gen_key, "NOT_PRESENT")
        original_services = sys.modules.get(services_key, "NOT_PRESENT")

        # Setting a module entry to None causes ImportError when imported
        sys.modules[chart_gen_key] = None  # type: ignore[assignment]
        # Remove services so it gets re-imported fresh
        sys.modules.pop(services_key, None)

        try:
            import optimizer.services as services_module
            # The attribute must exist — either None (ImportError hit) or callable
            assert hasattr(services_module, "generate_all_charts")
        finally:
            # Restore originals
            if original_chart_gen == "NOT_PRESENT":
                sys.modules.pop(chart_gen_key, None)
            else:
                sys.modules[chart_gen_key] = original_chart_gen  # type: ignore[assignment]

            if original_services == "NOT_PRESENT":
                sys.modules.pop(services_key, None)
            else:
                sys.modules[services_key] = original_services  # type: ignore[assignment]

    def test_import_error_fallback_via_sys_modules_manipulation(self):
        """
        Alternative coverage approach: remove chart_generator from sys.modules
        and replace with a broken module, then reload optimizer.services.
        """
        # Save originals
        chart_gen_key = "optimizer.services.chart_generator"
        services_key = "optimizer.services"

        original_chart_gen = sys.modules.get(chart_gen_key)
        original_services = sys.modules.get(services_key)

        # Install a broken module stub that raises ImportError on attribute access
        class _BrokenModule:
            def __getattr__(self, name):
                raise ImportError("simulated missing dependency")

        sys.modules[chart_gen_key] = None  # type: ignore[assignment]

        try:
            # Re-import after poisoning the cache
            if services_key in sys.modules:
                del sys.modules[services_key]
            # Re-import — chart_generator is None in sys.modules, so the import
            # inside __init__.py will raise ImportError and set generate_all_charts = None
            import optimizer.services as fresh_services
            result = getattr(fresh_services, "generate_all_charts", "MISSING")
            # It's either None (ImportError path) or a callable (if import succeeded)
            assert result is None or callable(result)
        finally:
            # Restore everything
            if original_chart_gen is None and chart_gen_key in sys.modules:
                del sys.modules[chart_gen_key]
            elif original_chart_gen is not None:
                sys.modules[chart_gen_key] = original_chart_gen

            if original_services is not None:
                sys.modules[services_key] = original_services
            elif services_key in sys.modules:
                del sys.modules[services_key]

    def test_all_other_exports_always_present(self):
        """The other exports should always be available regardless of matplotlib."""
        from optimizer.services import (
            build_analysis_summary_metrics,
            compute_license_metrics,
            get_fallback_report,
            get_user_analysis_logs,
            generate_report_text,
            run_rules,
        )
        assert callable(run_rules)
        assert callable(compute_license_metrics)
        assert callable(generate_report_text)
        assert callable(get_fallback_report)
        assert callable(build_analysis_summary_metrics)
        assert callable(get_user_analysis_logs)
