import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("optimizer", "0011_boonesrawrow"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BooneFileUpload",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="optimizer.tenant")),
                ("source", models.CharField(choices=[("boones_public", "Boone's Public Cloud"), ("boones_private", "Boone's Private Cloud")], max_length=40)),
                ("file_name", models.CharField(max_length=255)),
                ("file_path", models.CharField(blank=True, max_length=500)),
                ("latest_month", models.DateField(blank=True, null=True)),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="boone_uploads", to=settings.AUTH_USER_MODEL)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("status", models.CharField(choices=[("uploaded", "Uploaded"), ("processing", "Processing"), ("completed", "Completed"), ("failed", "Failed")], default="uploaded", max_length=20)),
                ("rows_ingested", models.IntegerField(null=True)),
                ("error_message", models.TextField(blank=True)),
            ],
            options={
                "db_table": "boone_file_upload",
            },
        ),
        migrations.AddIndex(
            model_name="boonefileupload",
            index=models.Index(fields=["-uploaded_at"], name="boone_upload_uploaded_at_idx"),
        ),
        migrations.AddIndex(
            model_name="boonefileupload",
            index=models.Index(fields=["source", "-latest_month"], name="boone_upload_source_month_idx"),
        ),
        migrations.AddIndex(
            model_name="boonefileupload",
            index=models.Index(fields=["status"], name="boone_upload_status_idx"),
        ),
    ]
