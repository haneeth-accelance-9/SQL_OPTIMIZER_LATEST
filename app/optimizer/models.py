"""
MVP6 License Agent — Django Models
===================================
Azure Database for PostgreSQL Flexible Server backend.

settings.py minimum config:
    DATABASES = {
        "default": {
            "ENGINE":   "django.db.backends.postgresql",
            "NAME":     env("DB_NAME"),
            "USER":     env("DB_USER"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST":     env("DB_HOST"),   # <server>.postgres.database.azure.com
            "PORT":     "5432",
            "OPTIONS":  {"sslmode": "require"},  # mandatory for Azure PostgreSQL
        }
    }
    INSTALLED_APPS += ["core"]   # or wherever this models.py lives

Run migrations:
    python manage.py makemigrations
    python manage.py migrate

Why Django models over raw SQL?
  - Migrations are versioned and reversible (manage.py migrate / migrate <app> <num>)
  - ORM queries are safer (parameterised by default, no raw string injection risk)
  - Admin UI for license_rule and optimization_candidate comes for free
  - The raw SQL file is still useful for: DBA review, Azure DB provisioning scripts,
    and as documentation for the exact schema
  - Recommendation: use Django models as the SOURCE OF TRUTH, keep the .sql file
    as a generated reference (manage.py sqlmigrate core 0001)
"""

import uuid
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models


# ─────────────────────────────────────────────────────────────────
# Shared base
# ─────────────────────────────────────────────────────────────────

class TenantAwareModel(models.Model):
    """Abstract base — every table carries tenant_id for future multi-tenancy."""
    tenant = models.ForeignKey(
        "Tenant",
        on_delete=models.PROTECT,
        db_index=True,
    )

    class Meta:
        abstract = True


# ─────────────────────────────────────────────────────────────────
# 1. Tenant
# ─────────────────────────────────────────────────────────────────

class Tenant(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenant"

    def __str__(self):
        return self.name


# ─────────────────────────────────────────────────────────────────
# 2. Server  (master registry)
# ─────────────────────────────────────────────────────────────────

class Server(TenantAwareModel):
    """
    One row per unique physical/virtual machine across all sources.

    server_key population logic (applied in ingestion layer):
      1. USU devices_device_key present  → use it
      2. Boone's Number present          → use it
      3. Neither                         → f"{server_name}|{environment}|{hosting_zone}".lower()

    beat_ids: USU can return multiple BEAT IDs newline-separated.
    Stored as TEXT[] so no data is lost and queries like
      Server.objects.filter(beat_ids__contains=["BEAT04016489"])
    work out of the box.
    """
    id                      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    server_key              = models.CharField(max_length=512)          # canonical cross-source ID
    usu_device_key          = models.CharField(max_length=512, blank=True, null=True)
    boones_number           = models.CharField(max_length=100, blank=True, null=True)
    server_name             = models.CharField(max_length=255)
    hosting_zone            = models.CharField(max_length=120, blank=True, null=True)
    environment             = models.CharField(max_length=80, blank=True, null=True)
    platform                = models.CharField(max_length=80, blank=True, null=True)
    device_type             = models.CharField(max_length=120, blank=True, null=True)
    is_virtual              = models.BooleanField(null=True)
    cluster_name            = models.CharField(max_length=255, blank=True, null=True)
    cluster_device_key      = models.CharField(max_length=512, blank=True, null=True)
    criticality             = models.CharField(max_length=80, blank=True, null=True)
    location                = models.CharField(max_length=120, blank=True, null=True)
    country                 = models.CharField(max_length=80, blank=True, null=True)
    region                  = models.CharField(max_length=80, blank=True, null=True)
    topology_type           = models.CharField(max_length=80, blank=True, null=True)
    beat_ids                = ArrayField(models.TextField(), blank=True, default=list)
    apps_id                 = models.CharField(max_length=100, blank=True, null=True)
    app_name                = models.CharField(max_length=255, blank=True, null=True)
    server_owner_email      = models.EmailField(blank=True, null=True)
    app_owner_email         = models.EmailField(blank=True, null=True)   # primary notification target
    business_owner_email    = models.EmailField(blank=True, null=True)
    business_division       = models.CharField(max_length=120, blank=True, null=True)
    installed_status_usu    = models.CharField(max_length=80, blank=True, null=True)
    installed_status_boones = models.CharField(max_length=80, blank=True, null=True)
    # NOTE: Both status columns are kept deliberately. UC2 logic checks BOTH —
    # values overlap but are not identical between USU and Boone's.
    is_cloud_device         = models.BooleanField(null=True)
    cloud_provider          = models.CharField(max_length=80, blank=True, null=True)
    source_systems          = ArrayField(models.CharField(max_length=40), blank=True, default=list)
    first_seen_at           = models.DateTimeField(auto_now_add=True)
    last_synced_at          = models.DateTimeField(auto_now=True)
    is_active               = models.BooleanField(default=True)

    class Meta:
        db_table = "server"
        unique_together = [("tenant", "server_key")]
        indexes = [
            models.Index(fields=["hosting_zone"]),
            models.Index(fields=["environment"]),
            models.Index(fields=["installed_status_usu"]),
            models.Index(fields=["installed_status_boones"]),
        ]

    def __str__(self):
        return f"{self.server_name} ({self.environment})"


# ─────────────────────────────────────────────────────────────────
# 3. USU Installation
# ─────────────────────────────────────────────────────────────────

class USUInstallation(TenantAwareModel):
    """
    Mirrors /installations API endpoint.
    Key fields for use-case logic:
      UC1: inv_status_std_name == "License included"
      UC2: device_status == "Retired"  AND  no_license_required == False
    """
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    server              = models.ForeignKey(Server, on_delete=models.CASCADE,
                                            related_name="usu_installations")
    product_family      = models.CharField(max_length=120, blank=True, null=True)
    product_group       = models.CharField(max_length=120, blank=True, null=True)
    manufacturer        = models.CharField(max_length=120, blank=True, null=True)
    product_description = models.CharField(max_length=255, blank=True, null=True)
    product_edition     = models.CharField(max_length=120, blank=True, null=True)
    license_metric      = models.CharField(max_length=120, blank=True, null=True)
    calc_license_metric = models.CharField(max_length=80, blank=True, null=True)
    inv_status_name     = models.CharField(max_length=120, blank=True, null=True)
    inv_status_std_name = models.CharField(max_length=80, blank=True, null=True)   # UC1
    ignore_usage        = models.BooleanField(null=True)
    ignore_usage_reason = models.CharField(max_length=255, blank=True, null=True)
    no_license_required = models.BooleanField(null=True)                            # UC1 + UC2
    device_status       = models.CharField(max_length=80, blank=True, null=True)   # UC2
    cpu_socket_count    = models.IntegerField(null=True)
    cpu_core_count      = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    hyper_threading_factor = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    topology_type       = models.CharField(max_length=80, blank=True, null=True)
    source_key          = models.CharField(max_length=255, blank=True, null=True)
    inventory_date      = models.DateField(null=True)
    creation_date       = models.DateField(null=True)
    fetched_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "usu_installation"
        indexes = [
            models.Index(fields=["server"]),
            models.Index(fields=["product_family"]),
            models.Index(fields=["-fetched_at"]),
        ]

    def __str__(self):
        return f"{self.product_description} on {self.server.server_name}"


# ─────────────────────────────────────────────────────────────────
# 4. USU Demand Detail
# ─────────────────────────────────────────────────────────────────

class USUDemandDetail(TenantAwareModel):
    """Mirrors /demanddetails API endpoint — licensing obligation per server."""
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    server              = models.ForeignKey(Server, on_delete=models.CASCADE,
                                            related_name="usu_demand_details")
    product_family      = models.CharField(max_length=120, blank=True, null=True)
    product_group       = models.CharField(max_length=120, blank=True, null=True)
    manufacturer        = models.CharField(max_length=120, blank=True, null=True)
    product_description = models.CharField(max_length=255, blank=True, null=True)
    product_edition     = models.CharField(max_length=120, blank=True, null=True)
    eff_quantity        = models.DecimalField(max_digits=10, decimal_places=5, null=True)
    no_license_required = models.BooleanField(null=True)
    device_purpose      = models.CharField(max_length=80, blank=True, null=True)
    topology_type       = models.CharField(max_length=80, blank=True, null=True)
    cpu_core_count      = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    virt_type           = models.CharField(max_length=80, blank=True, null=True)
    is_cloud_device     = models.BooleanField(null=True)
    cloud_provider      = models.CharField(max_length=80, blank=True, null=True)
    cpu_thread_count    = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    hyper_threading_factor = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    fetched_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "usu_demand_detail"
        indexes = [
            models.Index(fields=["server"]),
            models.Index(fields=["product_family"]),
        ]


# ─────────────────────────────────────────────────────────────────
# 5. CPU Utilisation
# ─────────────────────────────────────────────────────────────────

class CPUUtilisation(TenantAwareModel):
    """
    One row per (server, period_month, source).
    source choices:
      'boones_public'   — Boone's Public Cloud flat file
      'boones_private'  — Boone's Private Cloud flat file
      'grafana'         — future: Grafana replaces Boone's files

    Private cloud rows carry memory/storage fields.
    Public cloud rows leave those fields NULL.
    """
    SOURCE_BOONES_PUBLIC  = "boones_public"
    SOURCE_BOONES_PRIVATE = "boones_private"
    SOURCE_GRAFANA        = "grafana"
    SOURCE_CHOICES = [
        (SOURCE_BOONES_PUBLIC,  "Boone's Public Cloud"),
        (SOURCE_BOONES_PRIVATE, "Boone's Private Cloud"),
        (SOURCE_GRAFANA,        "Grafana"),
    ]

    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    server              = models.ForeignKey(Server, on_delete=models.CASCADE,
                                            related_name="cpu_utilisation")
    source              = models.CharField(max_length=40, choices=SOURCE_CHOICES)
    period_month        = models.DateField()        # always first day of month
    logical_cpu_count   = models.IntegerField(null=True)
    avg_cpu_pct         = models.DecimalField(max_digits=6, decimal_places=3, null=True)
    max_cpu_pct         = models.DecimalField(max_digits=6, decimal_places=3, null=True)
    min_cpu_pct         = models.DecimalField(max_digits=6, decimal_places=3, null=True)
    # Private cloud only
    physical_ram_gib         = models.DecimalField(max_digits=10, decimal_places=3, null=True)
    avg_free_memory_pct      = models.DecimalField(max_digits=6, decimal_places=3, null=True)
    max_free_memory_pct      = models.DecimalField(max_digits=6, decimal_places=3, null=True)
    min_free_memory_pct      = models.DecimalField(max_digits=6, decimal_places=3, null=True)
    allocated_storage_gb     = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    used_storage_gb          = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    ingested_at         = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cpu_utilisation"
        unique_together = [("server", "period_month", "source")]
        indexes = [
            models.Index(fields=["-period_month"]),
            models.Index(fields=["source"]),
            models.Index(fields=["avg_cpu_pct"]),
        ]


# ─────────────────────────────────────────────────────────────────
# 6. Boone's Raw Row  (complete flat-file snapshot, one row per server per upload)
# ─────────────────────────────────────────────────────────────────

class BoonesRawRow(models.Model):
    """
    Stores one complete row from a Boone's file upload.
    All file columns (headers as keys, cell values as values) are stored in
    row_data JSON exactly as they appear in the file — no schema change needed
    when the file format evolves.

    row_data JSON keys (xx = last two digits of year, dynamic):
    {
      # Fixed metadata (10)
      "Number": "1234",
      "Server Name": "SRV-001",
      "Is Virtual?": "Yes",
      "Cluster Name": "CLUSTER-A",
      "Criticality": "High",
      "Environment type": "Production",
      "Hosting Zone": "Zone-1",
      "Installed Status": "Active",
      "Location": "Frankfurt",
      "Platform / Class": "Physical",

      # Logical CPU — Apr-xx to Mar-xx (12 months)
      "Logical CPU Apr-xx": 8, "Logical CPU May-xx": 8, "Logical CPU June-xx": 8,
      "Logical CPU July-xx": 8, "Logical CPU Aug-xx": 8, "Logical CPU Sept-xx": 8,
      "Logical CPU Oct-xx": 8, "Logical CPU Nov-xx": 8, "Logical CPU Dec-xx": 8,
      "Logical CPU Jan -xx": 8, "Logical CPU Feb -xx": 8, "Logical CPU Mar -xx": 8,

      # Average CPU Utilisation (%) — Apr-xx to Mar-xx (12 months)
      "Average CPU Utilisation (%) - Apr-xx": 12.5, "Average CPU Utilisation (%) - May-xx": 13.0,
      "Average CPU Utilisation (%) - June-xx": 11.2, "Average CPU Utilisation (%) - July-xx": 14.1,
      "Average CPU Utilisation (%) - Aug-xx": 15.3, "Average CPU Utilisation (%) - Sept-xx": 10.8,
      "Average CPU Utilisation (%) - Oct-xx": 12.0, "Average CPU Utilisation (%) - Nov-xx": 11.5,
      "Average CPU Utilisation (%) - Dec-xx": 13.7, "Average CPU Utilisation (%) - Jan-xx": 9.9,
      "Average CPU Utilisation (%) - Feb-xx": 10.2, "Average CPU Utilisation (%) - Mar-xx": 11.0,

      # Maximum CPU Utilisation (%) — Apr-xx to Mar-xx (12 months)
      "Maximum CPU Utilisation (%) - Apr-xx": 45.2, "Maximum CPU Utilisation (%) - May-xx": 48.0,
      "Maximum CPU Utilisation (%) - June-xx": 43.1, "Maximum CPU Utilisation (%) - July-xx": 50.3,
      "Maximum CPU Utilisation (%) - Aug-xx": 55.0, "Maximum CPU Utilisation (%) - Sept-xx": 40.5,
      "Maximum CPU Utilisation (%) - Oct-xx": 44.0, "Maximum CPU Utilisation (%) - Nov-xx": 42.8,
      "Maximum CPU Utilisation (%) - Dec-xx": 47.6, "Maximum CPU Utilisation (%) -Jan-xx": 38.9,
      "Maximum CPU Utilisation (%) -Feb-xx": 39.4, "Maximum CPU Utilisation (%) -Mar-xx": 41.0,

      # Physical RAM (GiB) — Apr-xx to Mar-xx (12 months)
      "Physical RAM (GiB) - Apr-xx": 64.0, "Physical RAM (GiB) - May-xx": 64.0,
      "Physical RAM (GiB) - June-xx": 64.0, "Physical RAM (GiB) - July-xx": 64.0,
      "Physical RAM (GiB) -Aug-xx": 64.0, "Physical RAM (GiB) -Sept-xx": 64.0,
      "Physical RAM (GiB) -Oct-xx": 64.0, "Physical RAM (GiB) -Nov-xx": 64.0,
      "Physical RAM (GiB) -Dec-xx": 64.0, "Physical RAM (GiB) -Jan-xx": 64.0,
      "Physical RAM (GiB) -Feb-xx": 64.0, "Physical RAM (GiB) -Mar-xx": 64.0,

      # Average free Memory (%) — Apr-xx to Mar-xx (12 months)
      "Average free Memory (%) - Apr-xx": 78.3, "Average free Memory (%) - May-xx": 76.0,
      "Average free Memory (%) - June-xx": 79.1, "Average free Memory (%) - July-xx": 74.5,
      "Average free Memory (%) -Aug-xx": 72.0, "Average free Memory (%) -Sept-xx": 80.2,
      "Average free Memory (%) -Oct-xx": 77.5, "Average free Memory (%) -Nov-xx": 78.9,
      "Average free Memory (%) -Dec-xx": 75.3, "Average free Memory (%) -Jan-xx": 81.0,
      "Average free Memory (%) -Feb-xx": 80.5, "Average free Memory (%) -Mar-xx": 79.8,

      # Maximum free Memory (%) — Apr-xx to Mar-xx (12 months)
      "Maximum free Memory (%) - Apr-xx": 91.0, "Maximum free Memory (%) - May-xx": 89.5,
      "Maximum free Memory (%) - June-xx": 92.1, "Maximum free Memory (%) - July-xx": 88.0,
      "Maximum free Memory (%) - Aug-xx": 86.3, "Maximum free Memory (%) - Sept-xx": 93.5,
      "Maximum free Memory (%) - Oct-xx": 90.2, "Maximum free Memory (%) - Nov-xx": 91.8,
      "Maximum free Memory (%) - Dec-xx": 88.7, "Maximum free Memory (%) - Jan-xx": 94.0,
      "Maximum free Memory (%) - Feb-xx": 93.2, "Maximum free Memory (%) - Mar-xx": 92.5,

      # Minimum free Memory (%) — Apr-xx to Mar-xx (12 months)
      "Minimum free Memory (%) - Apr-xx": 55.1, "Minimum free Memory (%) - May-xx": 52.0,
      "Minimum free Memory (%) - June-xx": 57.3, "Minimum free Memory (%) - July-xx": 50.8,
      "Minimum free Memory (%) - Aug-xx": 48.5, "Minimum free Memory (%) - Sept-xx": 59.0,
      "Minimum free Memory (%) - Oct-xx": 54.2, "Minimum free Memory (%) - Nov-xx": 56.7,
      "Minimum free Memory (%) - Dec-xx": 51.3, "Minimum free Memory (%) -Jan-xx": 61.0,
      "Minimum free Memory (%) -Feb-xx": 60.2, "Minimum free Memory (%) -Mar-xx": 58.9,

      # Allocated Storage (GB) — Feb-xx, Mar-xx (2 months)
      "Allocated Storage (GB) -Feb - xx": 500.0,
      "Allocated Storage (GB) -Mar- xx": 500.0,

      # Used Storage (GB) — Feb-xx, Mar-xx (2 months)
      "Used Storage (GB) -Feb - xx": 320.0,
      "Used Storage (GB) -Mar - xx": 325.0,

      # Trailing fixed (4)
      "Comments for Allocation (GB)": "Approved by infra team",
      "Comments for Usage (GB)": "High usage in Q1",
      "Utilisation %": 42.5,
      "Decmmission Check": "No"
    }
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ingested_at = models.DateTimeField(auto_now_add=True)
    # Full Boone's file row stored as-is: all 102 named column headers as keys,
    # cell values as values. Keys follow the exact Excel header names, e.g.:
    #   "Number", "Server Name", "Is Virtual?", "Cluster Name", "Criticality",
    #   "Environment type", "Hosting Zone", "Installed Status", "Location", "Platform / Class",
    #   "Logical CPU <Month>-xx", "Average CPU Utilisation (%) - <Month>-xx",
    #   "Maximum CPU Utilisation (%) - <Month>-xx", "Physical RAM (GiB) - <Month>-xx",
    #   "Average free Memory (%) - <Month>-xx", "Maximum free Memory (%) - <Month>-xx",
    #   "Minimum free Memory (%) - <Month>-xx", "Allocated Storage (GB) -<Month>-xx",
    #   "Used Storage (GB) -<Month>-xx", "Comments for Allocation (GB)",
    #   "Comments for Usage (GB)", "Utilisation %", "Decmmission Check"
    # Empty separator columns from the Excel file are excluded.
    # xx = last two digits of the year (dynamic — no schema change needed as years roll over).
    row_data    = models.JSONField()

    class Meta:
        db_table = "boones_raw_row"
        indexes = [
            models.Index(fields=["-ingested_at"]),
        ]

    def __str__(self):
        return f"BoonesRawRow {self.id} @ {self.ingested_at:%Y-%m-%d}"


# ─────────────────────────────────────────────────────────────────
# 6b. Boone File Upload  (registry of every uploaded flat file)
# ─────────────────────────────────────────────────────────────────

class BooneFileUpload(TenantAwareModel):
    """
    Registry of every Boone flat file uploaded.
    One row per file. Status tracks the ingestion lifecycle.
    """
    SOURCE_PUBLIC  = "boones_public"
    SOURCE_PRIVATE = "boones_private"
    SOURCE_CHOICES = [
        (SOURCE_PUBLIC,  "Boone's Public Cloud"),
        (SOURCE_PRIVATE, "Boone's Private Cloud"),
    ]
    STATUS_CHOICES = [
        ("uploaded",   "Uploaded"),
        ("processing", "Processing"),
        ("completed",  "Completed"),
        ("failed",     "Failed"),
    ]

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source        = models.CharField(max_length=40, choices=SOURCE_CHOICES)
    file_name     = models.CharField(max_length=255)
    file_path     = models.CharField(max_length=500, blank=True)   # Azure Blob path
    latest_month  = models.DateField(null=True, blank=True)        # last month in file e.g. 2026-03-01
    uploaded_by   = models.ForeignKey(
                        settings.AUTH_USER_MODEL,
                        on_delete=models.SET_NULL,
                        null=True, blank=True,
                        related_name="boone_uploads",
                    )
    uploaded_at   = models.DateTimeField(auto_now_add=True)
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default="uploaded")
    rows_ingested = models.IntegerField(null=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "boone_file_upload"
        indexes = [
            models.Index(fields=["-uploaded_at"]),
            models.Index(fields=["source", "-latest_month"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.file_name} ({self.source} | {self.status})"


# ─────────────────────────────────────────────────────────────────
# 6. Grafana Metric Snapshot  (raw, 90-day retention)
# ─────────────────────────────────────────────────────────────────

class GrafanaMetricSnapshot(TenantAwareModel):
    """
    Raw Grafana metric readings.  Retained for 90 days then deleted
    after rollup job populates GrafanaMetricMonthlyRollup.

    metric_name normalised values:
      'connections', 'batch_requests', 'os_memory_available_gib',
      'memory_manager_total_gib', 'committed_memory_utilization',
      'running_queries', 'memory_utilization_pct', 'database_size_mib'
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    server       = models.ForeignKey(Server, on_delete=models.CASCADE,
                                     related_name="grafana_snapshots")
    dashboard    = models.CharField(max_length=80)   # 'primary', 'testing'
    metric_name  = models.CharField(max_length=80)
    metric_value = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    metric_unit  = models.CharField(max_length=30, blank=True)
    metric_ts    = models.DateTimeField()             # original Grafana timestamp
    fetched_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "grafana_metric_snapshot"
        indexes = [
            models.Index(fields=["server", "metric_name", "-metric_ts"]),
            models.Index(fields=["-metric_ts"]),
        ]


# ─────────────────────────────────────────────────────────────────
# 7. Grafana Monthly Rollup  (long-term aggregate)
# ─────────────────────────────────────────────────────────────────

class GrafanaMetricMonthlyRollup(TenantAwareModel):
    """Aggregated Grafana data that survives the 90-day raw retention window."""
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    server       = models.ForeignKey(Server, on_delete=models.CASCADE,
                                     related_name="grafana_rollups")
    metric_name  = models.CharField(max_length=80)
    metric_unit  = models.CharField(max_length=30, blank=True)
    period_month = models.DateField()
    avg_value    = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    max_value    = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    min_value    = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    sample_count = models.IntegerField(null=True)
    rolled_up_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "grafana_metric_monthly_rollup"
        unique_together = [("server", "metric_name", "period_month")]
        indexes = [models.Index(fields=["-period_month"])]


# ─────────────────────────────────────────────────────────────────
# 8. License Rule
# ─────────────────────────────────────────────────────────────────

class LicenseRule(TenantAwareModel):
    """
    One row per optimization rule. conditions (jsonb) stores the field
    checks the agent evaluates. Seeded via migration or Django admin.
    """
    id                      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule_code               = models.CharField(max_length=40)
    use_case                = models.CharField(max_length=10)    # 'UC1', 'UC2', 'UC3'
    product_family          = models.CharField(max_length=120, blank=True, null=True)
    rule_name               = models.CharField(max_length=120)
    description             = models.TextField(blank=True)
    conditions              = models.JSONField()
    cost_per_core_pair_eur  = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    is_active               = models.BooleanField(default=True)
    valid_from              = models.DateTimeField(null=True, blank=True)
    valid_to                = models.DateTimeField(null=True, blank=True)
    created_by              = models.CharField(max_length=80, blank=True)
    created_at              = models.DateTimeField(auto_now_add=True)
    updated_at              = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "license_rule"
        unique_together = [("tenant", "rule_code")]

    def __str__(self):
        return f"[{self.use_case}] {self.rule_name}"


# ─────────────────────────────────────────────────────────────────
# 9. Agent Run
# ─────────────────────────────────────────────────────────────────

class AgentRun(TenantAwareModel):
    """One row per weekly (or on-demand) agent execution."""
    STATUS_RUNNING   = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED    = "failed"
    STATUS_PARTIAL   = "partial"
    STATUS_CHOICES = [
        (STATUS_RUNNING,   "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED,    "Failed"),
        (STATUS_PARTIAL,   "Partial"),
    ]

    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run_label           = models.CharField(max_length=120, blank=True)
    triggered_by        = models.CharField(max_length=80, blank=True)
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                           default=STATUS_RUNNING)
    servers_evaluated   = models.IntegerField(null=True)
    candidates_found    = models.IntegerField(null=True)
    llm_model           = models.CharField(max_length=80, blank=True)
    llm_tokens_used     = models.IntegerField(null=True)
    run_duration_sec    = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    input_file_versions = models.JSONField(null=True, blank=True)
    error_detail        = models.TextField(blank=True)
    # Agent-generated executive summary report stored after each run
    report_markdown     = models.TextField(blank=True)
    agent_endpoint      = models.CharField(max_length=255, blank=True)
    llm_used            = models.BooleanField(null=True)
    rules_evaluation    = models.JSONField(null=True, blank=True)
    started_at          = models.DateTimeField(auto_now_add=True)
    finished_at         = models.DateTimeField(null=True, blank=True)
    knowledge_sources   = models.JSONField(null=True, blank=True)
    llm_cost_eur        = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

    class Meta:
        db_table = "agent_run"
        indexes = [
            models.Index(fields=["-started_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.run_label or self.id} ({self.status})"


# ─────────────────────────────────────────────────────────────────
# 10. Agent Run Server Snapshot
# ─────────────────────────────────────────────────────────────────

class AgentRunServerSnapshot(TenantAwareModel):
    """
    Forensic record: the exact data the agent saw for each server.
    Allows replaying any historical recommendation.
    At 7M servers — add DB partitioning by agent_run.started_at before scaling.
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_run       = models.ForeignKey(AgentRun, on_delete=models.CASCADE,
                                        related_name="server_snapshots")
    server          = models.ForeignKey(Server, on_delete=models.PROTECT,
                                        related_name="run_snapshots")
    usu_snapshot    = models.JSONField(null=True, blank=True)
    cpu_snapshot    = models.JSONField(null=True, blank=True)
    grafana_snapshot = models.JSONField(null=True, blank=True)
    snapshotted_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agent_run_server_snapshot"
        unique_together = [("agent_run", "server")]
        indexes = [
            models.Index(fields=["agent_run"]),
            models.Index(fields=["server"]),
        ]


# ─────────────────────────────────────────────────────────────────
# 11. Optimization Candidate
# ─────────────────────────────────────────────────────────────────

class OptimizationCandidate(TenantAwareModel):
    """
    Core output — one row per (run, server, rule).
    This is what the UI shows for human review.

    Status lifecycle:
      pending → in_progress → accepted  (human decided)
      pending → in_progress → rejected  (human decided)
      pending → expired                 (no response before expires_at)
    """
    STATUS_PENDING     = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_ACCEPTED    = "accepted"
    STATUS_REJECTED    = "rejected"
    STATUS_EXPIRED     = "expired"
    STATUS_CHOICES = [
        (STATUS_PENDING,     "Pending"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_ACCEPTED,    "Accepted"),
        (STATUS_REJECTED,    "Rejected"),
        (STATUS_EXPIRED,     "Expired"),
    ]

    id                   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_run            = models.ForeignKey(AgentRun, on_delete=models.PROTECT,
                                             related_name="candidates")
    server               = models.ForeignKey(Server, on_delete=models.PROTECT,
                                             related_name="candidates")
    rule                 = models.ForeignKey(LicenseRule, on_delete=models.PROTECT,
                                             related_name="candidates")
    detected_on          = models.DateField(auto_now_add=True)       # filter/date column
    use_case             = models.CharField(max_length=10)           # denormalised for fast filter
    recommendation       = models.CharField(max_length=255)
    rationale            = models.TextField(blank=True)              # LLM explanation
    estimated_saving_eur = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    status               = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                            default=STATUS_PENDING)
    notified_to_email    = models.EmailField(blank=True, null=True)
    notified_at          = models.DateTimeField(null=True, blank=True)
    expires_at           = models.DateTimeField(null=True, blank=True)
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "optimization_candidate"
        unique_together = [("agent_run", "server", "rule")]
        indexes = [
            models.Index(fields=["-detected_on"]),
            models.Index(fields=["status"]),
            models.Index(fields=["use_case"]),
            # open items dashboard
            models.Index(
                fields=["use_case", "-detected_on"],
                condition=models.Q(status__in=["pending", "in_progress"]),
                name="idx_open_candidates",
            ),
        ]

    def __str__(self):
        return f"{self.use_case} | {self.server.server_name} | {self.status}"


# ─────────────────────────────────────────────────────────────────
# 12. Optimization Decision
# ─────────────────────────────────────────────────────────────────

class OptimizationDecision(TenantAwareModel):
    """
    Immutable human decision on a candidate.
    OneToOne with OptimizationCandidate — one decision per candidate.
    snow_ticket_id is NULL until ServiceNow integration is built (future phase).
    """
    DECISION_ACCEPTED = "accepted"
    DECISION_REJECTED = "rejected"
    DECISION_CHOICES  = [
        (DECISION_ACCEPTED, "Accepted"),
        (DECISION_REJECTED, "Rejected"),
    ]

    id                      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate               = models.OneToOneField(
                                  OptimizationCandidate,
                                  on_delete=models.PROTECT,
                                  related_name="decision",
                              )
    decision                = models.CharField(max_length=20, choices=DECISION_CHOICES)
    decided_by              = models.CharField(max_length=120, blank=True)
    decided_by_email        = models.EmailField(blank=True, null=True)
    decision_notes          = models.TextField(blank=True)
    decided_at              = models.DateTimeField(auto_now_add=True)
    # ServiceNow — populated in future phase
    snow_ticket_id          = models.CharField(max_length=80, blank=True, null=True)
    snow_ticket_created_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "optimization_decision"
        indexes = [models.Index(fields=["-decided_at"])]

    def save(self, *args, **kwargs):
        """Sync status back to candidate on save."""
        super().save(*args, **kwargs)
        self.candidate.status = self.decision
        self.candidate.save(update_fields=["status", "updated_at"])

    def __str__(self):
        return f"{self.decision} by {self.decided_by_email} @ {self.decided_at:%Y-%m-%d}"


# ─────────────────────────────────────────────────────────────────
# 13. Analysis Session
# ─────────────────────────────────────────────────────────────────

class AnalysisSession(models.Model):
    """Tracks each Excel upload and its processing lifecycle."""
    STATUS_UPLOADED   = "uploaded"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED  = "completed"
    STATUS_FAILED     = "failed"
    STATUS_CHOICES = [
        (STATUS_UPLOADED,   "Uploaded"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED,  "Completed"),
        (STATUS_FAILED,     "Failed"),
    ]

    created_at      = models.DateTimeField(auto_now_add=True)
    completed_at    = models.DateTimeField(null=True, blank=True)
    file_name       = models.CharField(max_length=255, blank=True)
    file_path       = models.CharField(max_length=500, blank=True)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UPLOADED)
    error_message   = models.TextField(blank=True)
    session_key     = models.CharField(max_length=40, blank=True, db_index=True)
    result_data     = models.JSONField(blank=True, default=dict)
    summary_metrics = models.JSONField(blank=True, default=dict)
    user            = models.ForeignKey(
                          settings.AUTH_USER_MODEL,
                          on_delete=models.CASCADE,
                          related_name="optimizer_analyses",
                          null=True, blank=True,
                      )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Analysis session"
        verbose_name_plural = "Analysis sessions"

    def __str__(self):
        return f"{self.file_name} ({self.status})"


# ─────────────────────────────────────────────────────────────────
# 14. User Profile
# ─────────────────────────────────────────────────────────────────

class UserProfile(models.Model):
    """Extended profile attached to Django's built-in User."""

    ROLE_ADMIN = "admin"
    ROLE_EDITOR = "editor"
    ROLE_VIEWER = "viewer"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_EDITOR, "Editor"),
        (ROLE_VIEWER, "Viewer"),
    ]

    user       = models.OneToOneField(
                     settings.AUTH_USER_MODEL,
                     on_delete=models.CASCADE,
                     related_name="optimizer_profile",
                 )
    role       = models.CharField(
                     max_length=10,
                     choices=ROLE_CHOICES,
                     default=ROLE_VIEWER,
                     db_index=True,
                 )
    team_name  = models.CharField(max_length=120, blank=True)
    image_url  = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User profile"
        verbose_name_plural = "User profiles"

    def __str__(self):
        return f"Profile({self.user}, {self.role})"

    @property
    def is_admin(self) -> bool:
        return self.role == self.ROLE_ADMIN

    @property
    def is_editor(self) -> bool:
        return self.role in (self.ROLE_ADMIN, self.ROLE_EDITOR)

    @property
    def is_viewer_only(self) -> bool:
        return self.role == self.ROLE_VIEWER
