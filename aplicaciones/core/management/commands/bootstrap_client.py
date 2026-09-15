from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.utils.text import slugify

from aplicaciones.core.models import (
    AccessLevel,
    Client,
    ClientDataSource,
    ClientMembership,
    ClientModule,
    PlatformModule,
)


class Command(BaseCommand):
    help = "Crea o actualiza un cliente, su fuente de datos y su usuario inicial."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Nombre comercial del cliente")
        parser.add_argument("--slug", help="Identificador; por defecto se deriva del nombre")
        parser.add_argument("--db-alias", required=True, help="Alias declarado en CLIENT_DATABASES")
        parser.add_argument(
            "--adapter",
            default=ClientDataSource.Adapter.ARANET,
            choices=tuple(ClientDataSource.Adapter.values),
        )
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", default="")
        parser.add_argument(
            "--password",
            help="Solo para desarrollo; en producción evite guardar claves en el historial",
        )
        parser.add_argument(
            "--modules",
            default="dashboard",
            help="Códigos separados por coma o 'all'",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["db_alias"] not in connections.databases:
            raise CommandError("El alias no está declarado en OSIRIS_CLIENT_DATABASES_FILE/JSON.")
        slug = options["slug"] or slugify(options["name"])
        if not slug:
            raise CommandError("No fue posible crear un slug válido.")

        client, _ = Client.objects.update_or_create(
            slug=slug, defaults={"name": options["name"], "is_active": True}
        )
        ClientDataSource.objects.update_or_create(
            client=client,
            defaults={
                "database_alias": options["db_alias"],
                "adapter_key": options["adapter"],
                "is_active": True,
            },
        )

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=options["username"], defaults={"email": options["email"]}
        )
        if created:
            if options["password"]:
                user.set_password(options["password"])
            else:
                user.set_unusable_password()
            user.save(update_fields=("password",))

        ClientMembership.objects.update_or_create(
            user=user,
            defaults={
                "client": client,
                "access_level": AccessLevel.CLIENT_ADMIN,
                "is_active": True,
            },
        )

        requested = options["modules"].split(",")
        modules = PlatformModule.objects.filter(is_active=True)
        if requested != ["all"]:
            modules = modules.filter(code__in=[code.strip() for code in requested])
        if not modules.exists():
            raise CommandError("No se encontraron módulos con esos códigos.")
        for module in modules:
            ClientModule.objects.update_or_create(
                client=client,
                module=module,
                defaults={
                    "is_enabled": True,
                    "minimum_access_level": AccessLevel.VIEWER,
                },
            )

        self.stdout.write(self.style.SUCCESS(f"Cliente {client.name} configurado para {user}."))
        if created and not options["password"]:
            self.stdout.write(
                self.style.WARNING(
                    "El usuario quedó sin clave utilizable. Asígnela con el admin o changepassword."
                )
            )
