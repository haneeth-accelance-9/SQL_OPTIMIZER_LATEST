import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("optimizer", "0010_agentrun_guardrails_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="BoonesRawRow",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("ingested_at", models.DateTimeField(auto_now_add=True)),
                ("row_data", models.JSONField()),
            ],
            options={
                "db_table": "boones_raw_row",
            },
        ),
        migrations.AddIndex(
            model_name="boonesrawrow",
            index=models.Index(fields=["-ingested_at"], name="boones_raw_ingested_at_idx"),
        ),
    ]
