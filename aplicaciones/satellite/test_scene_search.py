from __future__ import annotations

from datetime import date
from unittest.mock import patch

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
from aplicaciones.satellite.eosda.search import (
    build_scene_search_payload,
    search_sentinel2_scenes,
)
from aplicaciones.satellite.models import SatelliteField, SatelliteScene
from aplicaciones.satellite.services.scenes import sync_sentinel2_scenes

POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [-72.992797, 5.775136],
            [-72.992397, 5.775136],
            [-72.992397, 5.774736],
            [-72.992797, 5.774736],
            [-72.992797, 5.775136],
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


class EOSDASceneSearchTests(TestCase):
    def test_search_payload_uses_bounded_sentinel_filters(self):
        payload = build_scene_search_payload(
            geometry=POLYGON,
            date_from=date(2026, 3, 10),
            date_to=date(2026, 9, 5),
            max_cloud_cover=20,
            limit=10,
        )

        self.assertEqual(payload["search"]["shape"], POLYGON)
        self.assertEqual(payload["search"]["shapeRelation"], "CONTAINS")
        self.assertEqual(payload["search"]["cloudCoverage"], {"from": 0, "to": 20})
        self.assertEqual(payload["sort"], {"date": "desc"})
        self.assertTrue(payload["intersection_validation"])

    def test_search_normalizes_scene_response(self):
        eosda = FakeEOSDAClient(
            {
                "results": [
                    {
                        "sceneID": "S2B_tile_20260903_18NXM_0",
                        "view_id": "S2/18/N/XM/2026/9/3/0",
                        "date": "2026-09-03",
                        "cloudCoverage": 7.4,
                        "dataCoveragePercentage": 100.0,
                    }
                ]
            }
        )

        scenes = search_sentinel2_scenes(
            eosda,
            geometry=POLYGON,
            date_from=date(2026, 8, 1),
            date_to=date(2026, 9, 5),
        )

        self.assertEqual(len(scenes), 1)
        self.assertEqual(scenes[0].scene_id, "S2B_tile_20260903_18NXM_0")
        self.assertEqual(scenes[0].view_id, "S2/18/N/XM/2026/9/3/0")
        self.assertEqual(scenes[0].cloud_cover, 7.4)
        self.assertEqual(eosda.calls[0][0:2], ("POST", "/api/lms/search/v2/sentinel2"))

    def test_sync_persists_scene_for_field(self):
        client = Client.objects.create(name="Cliente A", slug="cliente-a")
        field = SatelliteField.objects.create(
            client=client,
            name="Lote A",
            geometry=POLYGON,
            eosda_field_id=11082572,
        )
        eosda = FakeEOSDAClient(
            {
                "results": [
                    {
                        "sceneID": "S2A_tile_20260901_18NXM_0",
                        "view_id": "S2/18/N/XM/2026/9/1/0",
                        "date": "2026-09-01",
                        "cloudCoverage": 12.2,
                    }
                ]
            }
        )

        scenes = sync_sentinel2_scenes(field, eosda_client=eosda)

        self.assertEqual(len(scenes), 1)
        stored = SatelliteScene.objects.get(field=field)
        self.assertEqual(stored.dataset, "sentinel2")
        self.assertEqual(stored.view_id, "S2/18/N/XM/2026/9/1/0")
        self.assertEqual(stored.cloud_cover, 12.2)
        self.assertEqual(stored.metadata["sceneID"], "S2A_tile_20260901_18NXM_0")


class SceneSearchViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.client_a = Client.objects.create(name="Cliente A", slug="cliente-a")
        self.client_b = Client.objects.create(name="Cliente B", slug="cliente-b")
        self.operator = user_model.objects.create_user(
            "scene-operator",
            password="test-password-123",
        )
        self.viewer = user_model.objects.create_user(
            "scene-viewer",
            password="test-password-123",
        )
        ClientMembership.objects.create(
            user=self.operator,
            client=self.client_a,
            access_level=AccessLevel.OPERATOR,
        )
        ClientMembership.objects.create(
            user=self.viewer,
            client=self.client_a,
            access_level=AccessLevel.VIEWER,
        )
        module = PlatformModule.objects.get(code="satellite")
        ClientModule.objects.create(
            client=self.client_a,
            module=module,
            is_enabled=True,
            minimum_access_level=AccessLevel.VIEWER,
        )
        self.field_a = SatelliteField.objects.create(
            client=self.client_a,
            name="Lote A",
            geometry=POLYGON,
            eosda_field_id=1001,
        )
        self.field_b = SatelliteField.objects.create(
            client=self.client_b,
            name="Lote B",
            geometry=POLYGON,
            eosda_field_id=2001,
        )

    @patch("aplicaciones.satellite.views.sync_sentinel2_scenes", return_value=[])
    def test_operator_can_search_own_field(self, sync_scenes):
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse("satellite:search_field_scenes", args=[self.field_a.pk])
        )

        self.assertRedirects(response, reverse("satellite:dashboard"))
        sync_scenes.assert_called_once_with(self.field_a)

    @patch("aplicaciones.satellite.views.sync_sentinel2_scenes")
    def test_operator_cannot_search_another_client_field(self, sync_scenes):
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse("satellite:search_field_scenes", args=[self.field_b.pk])
        )

        self.assertEqual(response.status_code, 404)
        sync_scenes.assert_not_called()

    def test_viewer_cannot_trigger_scene_search(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            reverse("satellite:search_field_scenes", args=[self.field_a.pk])
        )

        self.assertEqual(response.status_code, 403)
