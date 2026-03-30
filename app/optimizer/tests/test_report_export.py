import io

from openpyxl import load_workbook

from optimizer.services.report_export import _build_template_blocks, build_report_markdown, export_xlsx, format_currency


def test_build_template_blocks_uses_euro_for_cost_and_savings_values():
    euro = "\u20ac"
    _, blocks = _build_template_blocks(
        "## Executive Summary\nSummary",
        {
            "azure_payg_count": 2,
            "retired_count": 1,
            "total_demand_quantity": 20568,
            "total_license_cost": 6504721.08,
            "total_savings": 55780.96,
            "azure_payg_savings": 55433.08,
            "retired_devices_savings": 347.88,
        },
    )

    assert {"kind": "bullet", "text": f"Total annual license cost: {euro}6,504,721.08"} in blocks
    assert {"kind": "subsection", "text": "Savings"} in blocks
    assert {"kind": "bullet", "text": f"Total savings: {euro}55,780.96"} in blocks
    assert {"kind": "bullet", "text": f"BYOL to PAYG Savings: {euro}55,433.08"} in blocks
    assert {"kind": "bullet", "text": f"Retired but reporting Savings: {euro}347.88"} in blocks


def test_build_report_markdown_includes_savings_subsection():
    euro = "\u20ac"
    markdown = build_report_markdown(
        "## Executive Summary\nSummary",
        {
            "azure_payg_count": 626,
            "retired_count": 22,
            "total_demand_quantity": 20568,
            "total_license_cost": 6504721.08,
            "total_savings": 55780.96,
            "azure_payg_savings": 55433.08,
            "retired_devices_savings": 347.88,
        },
    )

    assert "### Cost" in markdown
    assert "### Savings" in markdown
    assert f"- Total savings: {euro}55,780.96" in markdown
    assert f"- BYOL to PAYG Savings: {euro}55,433.08" in markdown
    assert f"- Retired but reporting Savings: {euro}347.88" in markdown


def test_format_currency_uses_euro_symbol():
    assert format_currency(345.6) == "\u20ac345.60"


def test_export_xlsx_includes_savings_section_and_values():
    euro = "\u20ac"
    content = export_xlsx(
        "## Executive Summary\nSummary",
        report_context={
            "azure_payg_count": 626,
            "retired_count": 22,
            "total_demand_quantity": 20568,
            "total_license_cost": 6504721.08,
            "total_savings": 55780.96,
            "azure_payg_savings": 55433.08,
            "retired_devices_savings": 347.88,
        },
    )

    workbook = load_workbook(io.BytesIO(content))
    sheet = workbook["Report"]
    values = [str(row[0]) for row in sheet.iter_rows(values_only=True) if row and row[0]]

    assert "IT License and Cost Optimization Report" in values
    assert "Savings" in values
    assert f"- Total savings: {euro}55,780.96" in values
    assert f"- BYOL to PAYG Savings: {euro}55,433.08" in values
    assert f"- Retired but reporting Savings: {euro}347.88" in values
