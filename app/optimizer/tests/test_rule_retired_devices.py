import pandas as pd

from optimizer.rules.rule_retired_devices import find_retired_devices_with_installations_from_db


def test_find_retired_devices_with_installations_from_db_builds_from_live_db_adapter(monkeypatch):
    source_df = pd.DataFrame([
        {
            "install_status": "retired",
            "no_license_required": 0,
            "server_name": "sql-01",
        },
        {
            "install_status": "active",
            "no_license_required": 0,
            "server_name": "sql-02",
        },
    ])

    monkeypatch.setattr(
        "optimizer.services.db_analysis_service._build_installations_df",
        lambda: source_df,
    )

    result = find_retired_devices_with_installations_from_db()

    assert result["server_name"].tolist() == ["sql-01"]
