from datetime import date
from decimal import Decimal

from django.test import TestCase

from aplicaciones.core.models import Client
from aplicaciones.satellite.eosda.fields import build_create_field_payload, create_field
from aplicaciones.satellite.models import SatelliteField
from aplicaciones.satellite.services.fields import register_field_with_eosda

POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [-74.10, 4.60],
            [-74.09, 4.60],
            [-74.09, 4.59],
            [-74.10, 4.60],
        ]
    ],
}


class FakeEOSDAClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, str, object]] = []

    def request_json(self, method: str, path: str, *, params=None, json=None):
        self.calls.append((method, path, json))
        return self.response


class EOSDAFieldManagementTests(TestCase):
    def test_build_payload_preserves_polygon_and_crop_context(self):
        payload = build_create_field_payload(
            name="Lote Norte",
            geometry=POLYGON,
            group="cliente-a",
            crop_type="Maíz",
            sowing_date=date(2026, 8, 15),
        )

        self.assertEqual(payload["type"], "Feature")
        self.assertEqual(payload["geometry"], POLYGON)
        self.assertEqual(payload["properties"]["name"], "Lote Norte")
        self.assertEqual(payload["properties"]["group"], "cliente-a")
        self.assertEqual(
            payload["properties"]["years_data"],
            [{"crop_type": "Maíz", "year": 2026, "sowing_date": "2026-08-15"}],
        )

    def test_create_field_normalizes_eosda_response(self):
        eosda = FakeEOSDAClient({"id": 12345, "area": "17.2500"})

        created = create_field(eosda, name="Lote Norte", geometry=POLYGON)

        self.assertEqual(created.field_id, 12345)
        self.assertEqual(created.area_ha, Decimal("17.2500"))
        self.assertEqual(eosda.calls[0][0:2], ("POST", "/field-management"))

    def test_registration_keeps_client_polygon_and_saves_provider_metadata(self):
        client = Client.objects.create(name="Cliente A", slug="cliente-a")
        field = SatelliteField.objects.create(
            client=client,
            name="Lote Norte",
            geometry=POLYGON,
            crop_type="Maíz",
            sowing_date=date(2026, 8, 15),
        )
        eosda = FakeEOSDAClient({"id": 98765, "area": "21.75"})

        register_field_with_eosda(field, eosda_client=eosda)
        field.refresh_from_db()

        self.assertEqual(field.client_id, client.id)
        self.assertEqual(field.geometry, POLYGON)
        self.assertEqual(field.eosda_field_id, 98765)
        self.assertEqual(field.area_ha, Decimal("21.7500"))
        self.assertIsNotNone(field.last_sync_at)
        request_payload = eosda.calls[0][2]
        self.assertEqual(request_payload["properties"]["group"], client.slug)
