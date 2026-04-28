"""
Management command: seed_license_rules
=======================================
Seeds the LicenseRule table with SQL Server per-core-pair pricing.

Product names must match the product_description values in USUDemandDetail
so that compute_license_metrics can calculate Current Cost.

Usage:
    python manage.py seed_license_rules
    python manage.py seed_license_rules --tenant default
    python manage.py seed_license_rules --force   # overwrite existing rows
"""
from django.core.management.base import BaseCommand
from optimizer.models import LicenseRule, Tenant


RULES = [
    {
        "rule_code":             "SQL_STD_CORE",
        "use_case":              "UC1",
        "product_family":        "Microsoft SQL Server Standard Core",
        "rule_name":             "SQL Server Standard Core",
        "description":           "SQL Server Standard Edition per-core-pair cost",
        "conditions":            {"edition": "Standard"},
        "cost_per_core_pair_eur": 3600.00,
    },
    {
        "rule_code":             "SQL_ENT_CORE",
        "use_case":              "UC1",
        "product_family":        "Microsoft SQL Server Enterprise Core",
        "rule_name":             "SQL Server Enterprise Core",
        "description":           "SQL Server Enterprise Edition per-core-pair cost",
        "conditions":            {"edition": "Enterprise"},
        "cost_per_core_pair_eur": 14256.00,
    },
    {
        "rule_code":             "SQL_DEV_CORE",
        "use_case":              "UC1",
        "product_family":        "SQL Server",
        "rule_name":             "SQL Server Developer / Other",
        "description":           "SQL Server Developer Edition and unmatched products (no license cost)",
        "conditions":            {"edition": "Developer"},
        "cost_per_core_pair_eur": 0.00,
    },
]


class Command(BaseCommand):
    help = "Seed LicenseRule table with SQL Server per-core-pair pricing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant", default="default",
            help="Tenant name. Default: 'default'",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Update cost_per_core_pair_eur on existing rows.",
        )

    def handle(self, *args, **options):
        tenant_name = options["tenant"]
        force = options["force"]

        tenant, created = Tenant.objects.get_or_create(
            name=tenant_name,
            defaults={"description": "Default tenant", "is_active": True},
        )
        if created:
            self.stdout.write(f"  Created tenant: {tenant_name}")

        created_count = 0
        updated_count = 0

        for rule_data in RULES:
            obj, is_new = LicenseRule.objects.get_or_create(
                tenant=tenant,
                rule_code=rule_data["rule_code"],
                defaults={
                    "use_case":              rule_data["use_case"],
                    "product_family":        rule_data["product_family"],
                    "rule_name":             rule_data["rule_name"],
                    "description":           rule_data["description"],
                    "conditions":            rule_data["conditions"],
                    "cost_per_core_pair_eur": rule_data["cost_per_core_pair_eur"],
                    "is_active":             True,
                },
            )
            if is_new:
                created_count += 1
                self.stdout.write(
                    f"  Created: {rule_data['rule_name']} "
                    f"(€{rule_data['cost_per_core_pair_eur']:,.2f}/core-pair)"
                )
            elif force:
                obj.cost_per_core_pair_eur = rule_data["cost_per_core_pair_eur"]
                obj.product_family = rule_data["product_family"]
                obj.is_active = True
                obj.save(update_fields=["cost_per_core_pair_eur", "product_family", "is_active", "updated_at"])
                updated_count += 1
                self.stdout.write(
                    f"  Updated: {rule_data['rule_name']} "
                    f"(€{rule_data['cost_per_core_pair_eur']:,.2f}/core-pair)"
                )
            else:
                self.stdout.write(f"  Skipped (exists): {rule_data['rule_name']}")

        self.stdout.write(self.style.SUCCESS(
            f"\n  Done. Created: {created_count}, Updated: {updated_count}. "
            f"Total active rules: {LicenseRule.objects.filter(is_active=True, cost_per_core_pair_eur__isnull=False).count()}"
        ))
        self.stdout.write(
            "\n  NOTE: Update cost_per_core_pair_eur values to match your actual "
            "negotiated SQL Server per-core-pair prices before using cost figures in reports."
        )
