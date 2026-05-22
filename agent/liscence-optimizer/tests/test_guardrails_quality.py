"""
Unit tests for assess_data_quality() in guardrails.py.

Run with:
    pytest agent/liscence-optimizer/tests/test_guardrails_quality.py
"""

import sys
from pathlib import Path

# Allow direct import from the src package without installing the agent.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from guardrails import assess_data_quality, DataQualityReport  # type: ignore

# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_record(**overrides):
    """Return a record that satisfies all completeness, accuracy, and consistency checks."""
    base = {
        # licensing group fields
        "install_status": "active",
        "hosting_zone": "public_cloud",
        "no_license_required": 0,
        # compute group fields (all fractions in [0,1], consistent)
        "avg_cpu_12m": 0.10,
        "peak_cpu_12m": 0.25,
        "avg_free_mem_12m": 0.50,
        "min_free_mem_12m": 0.30,
        "current_vcpu": 4,
    }
    base.update(overrides)
    return base


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_all_clean_records():
    """Green path: all fields present and valid → all rates 1.0."""
    records = [_clean_record(), _clean_record(hostname="srv-02", current_vcpu=8)]
    report = assess_data_quality(records)

    assert isinstance(report, DataQualityReport)
    assert report.total_records == 2
    assert report.accuracy_rate == 1.0
    assert report.consistency_rate == 1.0
    for group, rate in report.completeness_by_group.items():
        assert rate == 1.0, f"Expected completeness 1.0 for group '{group}', got {rate}"
    assert report.accuracy_violations == []
    assert report.consistency_violations == []


def test_completeness_missing_install_status():
    """install_status absent → licensing group completeness drops below 1.0."""
    record = _clean_record()
    del record["install_status"]

    report = assess_data_quality([record])

    assert report.completeness_by_group["licensing"] < 1.0
    # compute group should still be complete
    assert report.completeness_by_group["compute"] == 1.0
    # no accuracy or consistency violations introduced
    assert report.accuracy_rate == 1.0
    assert report.consistency_rate == 1.0


def test_accuracy_cpu_fraction_exceeds_1():
    """avg_cpu_12m=1.5 → accuracy violation counted, rate < 1.0.

    peak_cpu_12m is set to 2.0 (> avg) to keep the avg<=peak consistency check
    passing — the test is specifically about the accuracy dimension.
    """
    records = [_clean_record(avg_cpu_12m=1.5, peak_cpu_12m=2.0)]
    report = assess_data_quality(records)

    assert report.accuracy_rate < 1.0
    assert any(v["field"] == "avg_cpu_12m" for v in report.accuracy_violations)
    assert any(v["value"] == 1.5 for v in report.accuracy_violations)
    # avg(1.5) <= peak(2.0) so no consistency violation
    assert report.consistency_rate == 1.0


def test_accuracy_vcpu_below_minimum():
    """current_vcpu=0 → accuracy violation counted, rate < 1.0."""
    records = [_clean_record(current_vcpu=0)]
    report = assess_data_quality(records)

    assert report.accuracy_rate < 1.0
    assert any(v["field"] == "current_vcpu" for v in report.accuracy_violations)
    assert any(v["value"] == 0 for v in report.accuracy_violations)


def test_consistency_avg_cpu_exceeds_peak():
    """avg_cpu_12m=0.8 > peak_cpu_12m=0.5 → consistency violation, rate < 1.0."""
    records = [_clean_record(avg_cpu_12m=0.8, peak_cpu_12m=0.5)]
    report = assess_data_quality(records)

    assert report.consistency_rate < 1.0
    checks = [v["check"] for v in report.consistency_violations]
    assert "avg_cpu_12m <= peak_cpu_12m" in checks


def test_consistency_min_free_exceeds_avg_free():
    """min_free_mem_12m=0.6 > avg_free_mem_12m=0.4 → consistency violation, rate < 1.0."""
    records = [_clean_record(min_free_mem_12m=0.6, avg_free_mem_12m=0.4)]
    report = assess_data_quality(records)

    assert report.consistency_rate < 1.0
    checks = [v["check"] for v in report.consistency_violations]
    assert "min_free_mem_12m <= avg_free_mem_12m" in checks


def test_empty_list():
    """Empty input → total_records=0, all rates 1.0, empty violation lists."""
    report = assess_data_quality([])

    assert report.total_records == 0
    assert report.accuracy_rate == 1.0
    assert report.consistency_rate == 1.0
    for rate in report.completeness_by_group.values():
        assert rate == 1.0
    assert report.accuracy_violations == []
    assert report.consistency_violations == []


def test_non_dict_records_skipped():
    """Non-dict items are skipped without raising; rates are 1.0 (no valid records to violate)."""
    report = assess_data_quality(["string", 42])

    assert report.total_records == 2
    # valid_count == 0 → all rates default to 1.0
    assert report.accuracy_rate == 1.0
    assert report.consistency_rate == 1.0
    assert report.accuracy_violations == []
    assert report.consistency_violations == []


def test_to_dict_shape():
    """to_dict() returns all expected keys with JSON-serialisable values."""
    report = assess_data_quality([_clean_record()])
    d = report.to_dict()

    assert "total_records" in d
    assert "completeness_by_group" in d
    assert "accuracy_rate" in d
    assert "accuracy_violations" in d
    assert "consistency_rate" in d
    assert "consistency_violations" in d
    assert isinstance(d["accuracy_rate"], float)
    assert isinstance(d["consistency_rate"], float)
    assert isinstance(d["completeness_by_group"], dict)
    assert isinstance(d["accuracy_violations"], list)
    assert isinstance(d["consistency_violations"], list)


def test_mixed_valid_and_invalid_records():
    """One clean + one dirty record; rates reflect only the violated fraction."""
    clean = _clean_record()
    # peak_cpu_12m=2.0 keeps avg(1.5) <= peak(2.0) so only accuracy fires, not consistency
    dirty = _clean_record(avg_cpu_12m=1.5, peak_cpu_12m=2.0)
    report = assess_data_quality([clean, dirty])

    assert report.total_records == 2
    # 1 out of 2 valid records has an accuracy violation → rate = 0.5
    assert report.accuracy_rate == 0.5
    # consistency and completeness unaffected
    assert report.consistency_rate == 1.0
