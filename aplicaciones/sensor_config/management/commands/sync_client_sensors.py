from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from aplicaciones.core.models import Client
from aplicaciones.dashboard.adapters.registry import get_adapter
from aplicaciones.sensor_config.services import sync_sensor_snapshot


class Command(BaseCommand):
    help = "Sincroniza el catálogo de sensores externos hacia la configuración central de OSIRIS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--client",
            required=True,
            help="Slug del cliente a sincronizar.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Calcula los cambios sin escribir en la base central.",
        )

    def handle(self, *args, **options):
        client_slug = options["client"].strip()
        dry_run = bool(options["dry_run"])

        try:
            client = Client.objects.select_related("data_source").get(
                slug=client_slug,
                is_active=True,
            )
        except Client.DoesNotExist as exc:
            raise CommandError(f"No existe un cliente activo con slug {client_slug!r}.") from exc

        try:
            data_source = client.data_source
        except Client.data_source.RelatedObjectDoesNotExist as exc:
            raise CommandError("El cliente no tiene una fuente de datos configurada.") from exc

        try:
            adapter = get_adapter(data_source)
            sensor_rows = adapter.list_sensors()
        except Exception as exc:
            raise CommandError(f"No fue posible leer los sensores externos: {exc}") from exc

        result = sync_sensor_snapshot(
            client=client,
            sensor_rows=sensor_rows,
            dry_run=dry_run,
        )

        mode = "DRY-RUN" if dry_run else "APLICADO"
        self.stdout.write(self.style.SUCCESS(f"[{mode}] Cliente: {client.name}"))
        self.stdout.write(f"Sensores leídos: {result.total_seen}")
        self.stdout.write(f"Creados: {result.created}")
        self.stdout.write(f"Actualizados: {result.updated}")
        self.stdout.write(f"Sin cambios: {result.unchanged}")
        self.stdout.write(f"Desactivados: {result.deactivated}")
        self.stdout.write(f"Omitidos por ID inválido: {result.skipped}")
