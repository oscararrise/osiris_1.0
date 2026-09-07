from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0003_controlevent_supportrequest")]

    operations = [
        migrations.AlterField(
            model_name="clientdatasource",
            name="adapter_key",
            field=models.CharField(
                choices=[
                    ("aranet", "Aranet PostgreSQL"),
                    ("telemetry", "Telemetría agrícola PostgreSQL"),
                ],
                default="aranet",
                max_length=40,
                verbose_name="adaptador",
            ),
        ),
    ]
