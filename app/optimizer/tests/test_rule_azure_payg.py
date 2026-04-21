import pandas as pd

from optimizer.rules.rule_azure_payg import find_azure_payg_candidates_from_db


def test_find_azure_payg_candidates_from_db_builds_from_live_db_adapter(monkeypatch):
    source_df = pd.DataFrame([
        {
            "u_hosting_zone": "Public Cloud",
            "inventory_status_standard": "",
            "no_license_required": 0,
            "server_name": "sql-01",
        },
        {
            "u_hosting_zone": "Private Cloud AVS",
            "inventory_status_standard": "license included",
            "no_license_required": 0,
            "server_name": "sql-02",
        },
    ])

    monkeypatch.setattr(
        "optimizer.services.db_analysis_service._build_installations_df",
        lambda: source_df,
    )

    result = find_azure_payg_candidates_from_db()

    assert result["server_name"].tolist() == ["sql-01"]
