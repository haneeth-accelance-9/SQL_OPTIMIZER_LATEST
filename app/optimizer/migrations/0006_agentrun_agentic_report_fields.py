from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("optimizer", "0005_agentrun_licenserule_optimizationcandidate_tenant_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentrun",
            name="report_markdown",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="agentrun",
            name="agent_endpoint",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="agentrun",
            name="llm_used",
            field=models.BooleanField(null=True),
        ),
        migrations.AddField(
            model_name="agentrun",
            name="rules_evaluation",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
