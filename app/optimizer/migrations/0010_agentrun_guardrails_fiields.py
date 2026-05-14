from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("optimizer", "0009_userprofile_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentrun",
            name="knowledge_sources",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="agentrun",
            name="llm_cost_eur",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=10, null=True),
        ),
    ]
