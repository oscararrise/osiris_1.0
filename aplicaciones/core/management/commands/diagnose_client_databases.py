from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connections

from aplicaciones.core.models import ClientDataSource


class Command(BaseCommand):
    help = "Diagnostica alias de bases de clientes cargados en el runtime de OSIRIS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--connect",
            action="store_true",
            help="Además intenta abrir cada conexión y ejecutar SELECT 1.",
        )

    def handle(self, *args, **options):
        runtime_aliases = set(settings.DATABASES) - {"default"}
        env_file = getattr(settings, "ENV_FILE", None)
        if env_file:
            state = "existe" if env_file.exists() else "no existe"
            self.stdout.write(f"Archivo de entorno: {env_file} ({state})")

        if runtime_aliases:
            self.stdout.write(
                "Alias cargados por Django: " + ", ".join(sorted(runtime_aliases))
            )
        else:
            self.stdout.write(self.style.WARNING("Alias cargados por Django: ninguno"))

        sources = list(
            ClientDataSource.objects.select_related("client")
            .filter(client__is_active=True, is_active=True)
            .order_by("client__name")
        )
        if not sources:
            self.stdout.write(self.style.WARNING("No hay fuentes de cliente activas."))
            return

        missing: list[str] = []
        failed_connections: list[str] = []
        for source in sources:
            alias = source.database_alias
            if alias not in runtime_aliases:
                missing.append(alias)
                self.stdout.write(
                    self.style.ERROR(
                        f"[FALTA] {source.client.name}: espera alias '{alias}' "
                        f"({source.get_adapter_key_display()})"
                    )
                )
                continue

            self.stdout.write(
                self.style.SUCCESS(
                    f"[OK] {source.client.name}: alias '{alias}' cargado "
                    f"({source.get_adapter_key_display()})"
                )
            )
            if not options["connect"]:
                continue

            try:
                with connections[alias].cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            except DatabaseError as exc:
                failed_connections.append(alias)
                self.stdout.write(
                    self.style.ERROR(
                        f"      conexión fallida: {exc.__class__.__name__}"
                    )
                )
            else:
                self.stdout.write(self.style.SUCCESS("      conexión PostgreSQL: OK"))

        if missing:
            missing_text = ", ".join(sorted(set(missing)))
            raise CommandError(
                "Hay fuentes activas cuyos alias no fueron cargados: " + missing_text
            )
        if failed_connections:
            failed_text = ", ".join(sorted(set(failed_connections)))
            raise CommandError("Fallaron conexiones PostgreSQL: " + failed_text)
