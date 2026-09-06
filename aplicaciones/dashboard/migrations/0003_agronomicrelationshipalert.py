import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("dashboard", "0002_agronomicvariablerelationship"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgronomicRelationshipAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="nombre")),
                ("variable_a_key", models.CharField(max_length=320, verbose_name="variable A")),
                ("operator_a", models.CharField(choices=[("gt", "Mayor que"), ("gte", "Mayor o igual que"), ("lt", "Menor que"), ("lte", "Menor o igual que")], default="gt", max_length=8, verbose_name="operador A")),
                ("threshold_a", models.FloatField(verbose_name="umbral A")),
                ("variable_b_key", models.CharField(max_length=320, verbose_name="variable B")),
                ("operator_b", models.CharField(choices=[("gt", "Mayor que"), ("gte", "Mayor o igual que"), ("lt", "Menor que"), ("lte", "Menor o igual que")], default="gt", max_length=8, verbose_name="operador B")),
                ("threshold_b", models.FloatField(verbose_name="umbral B")),
                ("logic", models.CharField(choices=[("and", "Y (AND)"), ("or", "O (OR)")], default="and", max_length=8, verbose_name="lógica")),
                ("duration_minutes", models.PositiveIntegerField(default=10, verbose_name="duración mínima (min)")),
                ("cooldown_minutes", models.PositiveIntegerField(default=30, verbose_name="cooldown (min)")),
                ("severity", models.CharField(choices=[("low", "Baja"), ("medium", "Media"), ("high", "Alta"), ("critical", "Crítica")], default="medium", max_length=12, verbose_name="severidad")),
                ("email_enabled", models.BooleanField(default=False, verbose_name="notificar por email")),
                ("email_recipients", models.CharField(blank=True, max_length=500, verbose_name="destinatarios email")),
                ("whatsapp_enabled", models.BooleanField(default=False, verbose_name="notificar por WhatsApp")),
                ("whatsapp_recipients", models.CharField(blank=True, max_length=500, verbose_name="destinatarios WhatsApp")),
                ("is_enabled", models.BooleanField(default=True, verbose_name="activa")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("client", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agronomic_relationship_alerts", to="core.client", verbose_name="cliente")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_agronomic_relationship_alerts", to=settings.AUTH_USER_MODEL)),
                ("relationship", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alerts", to="dashboard.agronomicvariablerelationship", verbose_name="relación agronómica")),
            ],
            options={
                "verbose_name": "alerta de relación agronómica",
                "verbose_name_plural": "alertas de relaciones agronómicas",
                "ordering": ("relationship__name", "-is_enabled", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="agronomicrelationshipalert",
            constraint=models.UniqueConstraint(fields=("relationship", "name"), name="unique_alert_name_per_agronomic_relationship"),
        ),
    ]
