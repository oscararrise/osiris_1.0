from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from aplicaciones.core.models import Client
from aplicaciones.dashboard.adapters import get_adapter
from aplicaciones.dashboard.adapters.base import AdapterError


class Command(BaseCommand):
    help = "Comprueba en modo lectura la fuente de sensores configurada para un cliente."

    def add_arguments(self, parser):
        parser.add_argument("--client", required=True, help="Slug del cliente")

    def handle(self, *args, **options):
        try:
            client = Client.objects.select_related("data_source").get(
                slug=options["client"], is_active=True
            )
            sensors = get_adapter(client.data_source).list_sensors()
        except Client.DoesNotExist as exc:
            raise CommandError("No existe un cliente activo con ese slug.") from exc
        except (ObjectDoesNotExist, AdapterError) as exc:
            raise CommandError(str(exc)) from exc
        except DatabaseError as exc:
            raise CommandError("La base del cliente no respondió correctamente.") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Fuente de {client.name} disponible: {len(sensors)} sensor(es) activo(s)."
            )
        )
