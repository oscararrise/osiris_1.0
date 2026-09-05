from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from aplicaciones.core.models import (
    AccessLevel,
    Client,
    ClientMembership,
    ClientModule,
    PlatformModule,
)

from .models import ClientSensor, Zone
from .services import sync_sensor_snapshot


class ProductiveContextModelTests(TestCase):
    def setUp(self):
        self.client_org = Client.objects.create(name="Productive Client", slug="productive-client")
        self.sensor = ClientSensor.objects.create(
            client=self.client_org,
            external_sensor_id="sensor-berry",
            sensor_name="Sensor berries",
            activity_type=ClientSensor.ActivityType.CROP,
            product_name="Arándano",
        )

    def test_productive_context_label_combines_activity_and_product(self):
        self.assertEqual(self.sensor.productive_context, "Cultivo · Arándano")

    def test_aranet_sync_preserves_local_productive_context(self):
        sync_sensor_snapshot(
            client=self.client_org,
            sensor_rows=[
                {
                    "id": "sensor-berry",
                    "name": "Sensor berries actualizado",
                    "type_name": "Aranet4",
                    "is_active": True,
                }
            ],
        )

        self.sensor.refresh_from_db()
        self.assertEqual(self.sensor.activity_type, ClientSensor.ActivityType.CROP)
        self.assertEqual(self.sensor.product_name, "Arándano")


class ProductiveContextViewTests(TestCase):
    def setUp(self):
        self.client_org = Client.objects.create(name="Farm Client", slug="farm-client")
        self.user = get_user_model().objects.create_user(username="farm-admin")
        ClientMembership.objects.create(
            user=self.user,
            client=self.client_org,
            access_level=AccessLevel.CLIENT_ADMIN,
        )
        module, _ = PlatformModule.objects.update_or_create(
            code="sensor_configuration",
            defaults={
                "name": "Configuración de sensores",
                "description": "Contexto operativo de sensores",
                "route_name": "sensor_configuration",
                "category": "Configuración",
                "sort_order": 15,
                "is_active": True,
            },
        )
        ClientModule.objects.create(
            client=self.client_org,
            module=module,
            minimum_access_level=AccessLevel.CLIENT_ADMIN,
        )
        self.sensor = ClientSensor.objects.create(
            client=self.client_org,
            external_sensor_id="sensor-23",
            sensor_name="Aranet 23",
        )
        self.client.force_login(self.user)

    def test_detail_post_saves_activity_and_product(self):
        response = self.client.post(
            reverse("sensor_configuration_detail", args=(self.sensor.pk,)),
            {
                "activity_type": ClientSensor.ActivityType.CROP,
                "product_name": "Fresa",
                "facility_type": Zone.ZoneType.GREENHOUSE,
                "facility_name": "Invernadero Principal",
                "zone_name": "Sector Fresas",
                "city": "Bogotá",
                "department": "Cundinamarca",
                "latitude": "4.6872531",
                "longitude": "-74.0628734",
                "altitude_m": "2630",
                "notes": "Monitoreo productivo.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.sensor.refresh_from_db()
        self.assertEqual(self.sensor.activity_type, ClientSensor.ActivityType.CROP)
        self.assertEqual(self.sensor.product_name, "Fresa")
        self.assertEqual(self.sensor.productive_context, "Cultivo · Fresa")

    def test_inventory_can_search_by_product(self):
        self.sensor.activity_type = ClientSensor.ActivityType.POULTRY
        self.sensor.product_name = "Gallinas"
        self.sensor.save(update_fields=("activity_type", "product_name", "updated_at"))

        response = self.client.get(reverse("sensor_configuration"), {"q": "Gallinas"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gallinas")
        self.assertContains(response, "Avicultura")
