from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from aplicaciones.dashboard import views as dashboard_views

from .access import accessible_modules, can_access_module
from .db_router import ClientDatabaseRouter
from .models import (
    AccessLevel,
    Client,
    ClientDataSource,
    ClientMembership,
    ClientModule,
    ControlEvent,
    PlatformModule,
    SupportRequest,
)


class TenantAccessTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.client_a = Client.objects.create(name="Aranet", slug="aranet")
        self.client_b = Client.objects.create(name="Cliente B", slug="cliente-b")
        self.user_a = user_model.objects.create_user("user-a", password="test-password-123")
        self.user_b = user_model.objects.create_user("user-b", password="test-password-123")
        self.membership_a = ClientMembership.objects.create(
            user=self.user_a, client=self.client_a, access_level=AccessLevel.VIEWER
        )
        self.membership_b = ClientMembership.objects.create(
            user=self.user_b, client=self.client_b, access_level=AccessLevel.VIEWER
        )
        self.dashboard_module = PlatformModule.objects.get(code="dashboard")
        ClientModule.objects.create(
            client=self.client_a,
            module=self.dashboard_module,
            is_enabled=True,
            minimum_access_level=AccessLevel.VIEWER,
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("s2"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('s2')}")

    def test_enabled_module_is_visible_only_to_configured_client(self):
        self.assertTrue(can_access_module(self.user_a, "dashboard"))
        self.assertFalse(can_access_module(self.user_b, "dashboard"))
        self.assertEqual(list(accessible_modules(self.user_a)), [self.dashboard_module])
        self.assertEqual(list(accessible_modules(self.user_b)), [])

    def test_direct_url_is_forbidden_when_module_is_not_enabled(self):
        self.client.force_login(self.user_b)
        response = self.client.get(reverse("s2"))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_always_uses_client_from_authenticated_membership(self):
        self.client.force_login(self.user_a)
        with self.settings(DEBUG=False):
            from unittest.mock import patch

            with patch.object(
                dashboard_views,
                "build_dashboard",
                return_value={"sensors": [], "metrics": [], "series": []},
            ) as build:
                response = self.client.get(reverse("s2"), {"client": self.client_b.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(build.call_args.args[0], self.client_a)

    def test_user_can_have_only_one_client(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClientMembership.objects.create(user=self.user_a, client=self.client_b)

    def test_inactive_membership_revokes_access(self):
        self.membership_a.is_active = False
        self.membership_a.save(update_fields=("is_active",))
        self.assertFalse(can_access_module(self.user_a, "dashboard"))

    def test_operation_center_lists_only_enabled_modules(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("inicio"))
        self.assertContains(response, "Dashboard")
        self.assertNotContains(response, "Visión artificial")

    def test_control_event_uses_authenticated_client(self):
        control_module = PlatformModule.objects.get(code="control")
        ClientModule.objects.create(client=self.client_a, module=control_module)
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse("actualizar_control_data"),
            {"estadoBomba1": "1", "estadoBomba2": "0"},
        )
        self.assertEqual(response.status_code, 200)
        event = ControlEvent.objects.get()
        self.assertEqual(event.client, self.client_a)
        self.assertEqual(event.created_by, self.user_a)

    def test_support_ignores_spoofed_client_from_form(self):
        support_module = PlatformModule.objects.get(code="support")
        ClientModule.objects.create(client=self.client_a, module=support_module)
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse("enviar_mail"),
            {"cliente": self.client_b.name, "tipo": "Ayuda", "descripcion": "Prueba"},
        )
        self.assertEqual(response.status_code, 200)
        support_request = SupportRequest.objects.get()
        self.assertEqual(support_request.client, self.client_a)
        self.assertEqual(support_request.created_by, self.user_a)


class ClientDataSourceValidationTests(TestCase):
    def test_default_database_cannot_be_a_sensor_source(self):
        client = Client(name="Example", slug="example")
        source = ClientDataSource(client=client, database_alias="default")
        with self.assertRaises(ValidationError):
            source.full_clean(exclude=("client",))

    def test_credentials_are_not_stored_in_central_model(self):
        field_names = {field.name for field in ClientDataSource._meta.fields}
        self.assertNotIn("password", field_names)
        self.assertNotIn("host", field_names)

    def test_adapter_settings_reject_secret_keys(self):
        client = Client.objects.create(name="Secrets", slug="secrets")
        source = ClientDataSource(
            client=client,
            database_alias="secrets_db",
            settings={"password": "must-not-be-here"},
        )
        with self.assertRaises(ValidationError):
            source.full_clean()

    def test_django_migrations_are_blocked_on_client_databases(self):
        router = ClientDatabaseRouter()
        self.assertFalse(router.allow_migrate("aranet_db", "auth"))
        self.assertIsNone(router.allow_migrate("default", "auth"))
