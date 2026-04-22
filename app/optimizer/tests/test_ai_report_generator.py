from urllib.error import HTTPError

from optimizer.services import ai_report_generator


def _fallback_result() -> dict:
    return {
        "success": True,
        "usecase_id": "uc_1_2_3",
        "rules_evaluation": {
            "success": True,
            "evaluation": {"matched_counts": {}, "per_rule": {}},
            "summary": {"rules": []},
        },
        "report_markdown": "# Fallback report",
        "llm_used": False,
        "llm_error": None,
        "llm_meta": None,
        "deterministic_report_markdown": "# Fallback report",
        "agent_endpoint_used": "django-native-fallback",
    }


def test_call_agent_generate_report_skips_default_local_endpoint(monkeypatch, settings):
    settings.AGENT_A2A_ENDPOINT = "http://localhost:8000"
    monkeypatch.delenv("AGENT_A2A_ENDPOINT", raising=False)

    fallback_result = _fallback_result()
    called = {"urlopen": False}

    def _unexpected(*args, **kwargs):
        called["urlopen"] = True
        raise AssertionError("urlopen should not be called for the default local Django endpoint")

    monkeypatch.setattr("urllib.request.urlopen", _unexpected)
    monkeypatch.setattr(
        ai_report_generator,
        "_build_local_agent_report_response",
        lambda **kwargs: fallback_result,
    )

    result = ai_report_generator.call_agent_generate_report(
        records=[{"server_name": "sql-01"}],
        usecase_id="uc_1_2_3",
    )

    assert result == fallback_result
    assert called["urlopen"] is False


def test_call_agent_generate_report_falls_back_after_http_error(monkeypatch, settings):
    settings.AGENT_A2A_ENDPOINT = "http://agent.example:8000"
    monkeypatch.setenv("AGENT_A2A_ENDPOINT", "http://agent.example:8000")

    fallback_result = _fallback_result()

    def _raise_http_error(*args, **kwargs):
        raise HTTPError(
            url="http://agent.example:8000/generate-report",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("urllib.request.urlopen", _raise_http_error)
    monkeypatch.setattr(
        ai_report_generator,
        "_build_local_agent_report_response",
        lambda **kwargs: fallback_result,
    )

    result = ai_report_generator.call_agent_generate_report(
        records=[{"server_name": "sql-01"}],
        usecase_id="uc_1_2_3",
    )

    assert result == fallback_result


def test_build_local_rules_evaluation_includes_counts_and_hostnames():
    result = ai_report_generator._build_local_rules_evaluation(
        rule_results={
            "azure_payg": [{"server_name": "sql-01"}],
            "retired_devices": [{"hostname": "sql-02"}],
        },
        rightsizing={
            "cpu_candidates": [{"server_name": "sql-03", "CPU_Recommendation": "Reduce vCPU by ~50% -> 4"}],
            "ram_candidates": [{"server_name": "sql-04", "RAM_Recommendation": "Reduce RAM by ~25% -> 32"}],
            "crit_cpu_optimizations": [],
            "crit_ram_optimizations": [],
        },
    )

    evaluation = result["evaluation"]

    assert evaluation["matched_counts"]["uc_1_1"] == 1
    assert evaluation["matched_counts"]["uc_1_2"] == 1
    assert evaluation["matched_counts"]["uc_3_1"] == 1
    assert evaluation["matched_counts"]["uc_3_2"] == 1
    assert evaluation["per_rule"]["uc_1_1"][0]["record"]["hostname"] == "sql-01"
    assert evaluation["per_rule"]["uc_1_2"][0]["record"]["server_name"] == "sql-02"
