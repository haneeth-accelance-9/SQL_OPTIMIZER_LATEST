from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('optimizer', '0007_seed_license_rules'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuinstallation',
            name='product_group',
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
        migrations.AddField(
            model_name='usudemanddetail',
            name='product_group',
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
    ]
