"""
Data migration: seed default SQL Server per-core-pair pricing into LicenseRule.

The LicenseRule model docstring says "Seeded via migration or Django admin".
This migration fulfils that contract so the dashboard shows correct Current Cost
values as soon as the application is deployed.

Per-core-pair costs below are placeholder estimates. Update them to match your
actual negotiated SQL Server prices using the Django admin or by running:

    python manage.py seed_license_rules --force

after editing RULES in seed_license_rules.py.
"""
import uuid
from django.db import migrations


RULES = [
    {
        "rule_code":              "SQL_STD_CORE",
        "use_case":               "UC1",
        "product_family":         "Microsoft SQL Server Standard Core",
        "rule_name":              "SQL Server Standard Core",
        "description":            "SQL Server Standard Edition per-core-pair cost",
        "conditions":             {"edition": "Standard"},
        "cost_per_core_pair_eur": 3600.00,
    },
    {
        "rule_code":              "SQL_ENT_CORE",
        "use_case":               "UC1",
        "product_family":         "Microsoft SQL Server Enterprise Core",
        "rule_name":              "SQL Server Enterprise Core",
        "description":            "SQL Server Enterprise Edition per-core-pair cost",
        "conditions":             {"edition": "Enterprise"},
        "cost_per_core_pair_eur": 14256.00,
    },
    {
        "rule_code":              "SQL_DEV_CORE",
        "use_case":               "UC1",
        "product_family":         "SQL Server",
        "rule_name":              "SQL Server Developer / Other",
        "description":            "SQL Server Developer Edition and unmatched products (no license cost)",
        "conditions":             {"edition": "Developer"},
        "cost_per_core_pair_eur": 0.00,
    },
]


def seed_license_rules(apps, schema_editor):
    Tenant = apps.get_model("optimizer", "Tenant")
    LicenseRule = apps.get_model("optimizer", "LicenseRule")

    tenant, _ = Tenant.objects.get_or_create(
        name="default",
        defaults={"description": "Default tenant", "is_active": True},
    )

    for rule in RULES:
        LicenseRule.objects.get_or_create(
            tenant=tenant,
            rule_code=rule["rule_code"],
            defaults={
                "id":                    uuid.uuid4(),
                "use_case":              rule["use_case"],
                "product_family":        rule["product_family"],
                "rule_name":             rule["rule_name"],
                "description":           rule["description"],
                "conditions":            rule["conditions"],
                "cost_per_core_pair_eur": rule["cost_per_core_pair_eur"],
                "is_active":             True,
                "created_by":            "migration:0007_seed_license_rules",
            },
        )


def unseed_license_rules(apps, schema_editor):
    LicenseRule = apps.get_model("optimizer", "LicenseRule")
    rule_codes = [r["rule_code"] for r in RULES]
    LicenseRule.objects.filter(rule_code__in=rule_codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("optimizer", "0006_agentrun_agentic_report_fields"),
    ]

    operations = [
        migrations.RunPython(seed_license_rules, reverse_code=unseed_license_rules),
    ]
