from datetime import UTC, datetime
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
from aplicaciones.satellite.eosda.imagery import (
    PRODUCT_NATURAL_COLOR,
    PRODUCT_NDVI,
    build_visual_payload,
    check_visual_task,
)
from aplicaciones.satellite.models import SatelliteField, SatelliteJob, SatelliteScene
from aplicaciones.satellite.services.imagery import (
    imagery_state,
    refresh_scene_imagery,
    request_scene_imagery,
)

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
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request_json(self, method, path, *, params=None, json=None):
        self.calls.append((method, path, json))
        return self.responses.pop(0)


class EOSDAImageryTests(TestCase):
    def setUp(self):
        self.client_model = Client.objects.create(name="Cliente A", slug="cliente-a")
        self.field = SatelliteField.objects.create(
            client=self.client_model,
            name="Lote A",
            geometry=POLYGON,
            eosda_field_id=11082572,
        )
        self.scene = SatelliteScene.objects.create(
            field=self.field,
            dataset="sentinel2",
            view_id="S2/18/N/YM/2026/6/23/0",
            captured_at=datetime(2026, 6, 23, 12, tzinfo=UTC),
            cloud_cover=8.3,
            metadata={"sceneID": "S2C_tile_20260623_18NYM_0"},
        )

    def test_visual_payload_uses_scene_polygon_and_product_bands(self):
        natural = build_visual_payload(
            view_id=self.scene.view_id,
            geometry=POLYGON,
            product=PRODUCT_NATURAL_COLOR,
            reference="ref-natural",
        )
        ndvi = build_visual_payload(
            view_id=self.scene.view_id,
            geometry=POLYGON,
            product=PRODUCT_NDVI,
            reference="ref-ndvi",
        )

        self.assertEqual(natural["type"], "jpeg")
        self.assertEqual(natural["params"]["bm_type"], "B04,B03,B02")
        self.assertEqual(natural["params"]["geometry"], POLYGON)
        self.assertEqual(natural["params"]["format"], "png")
        self.assertEqual(ndvi["params"]["bm_type"], "NDVI")

    def test_request_scene_imagery_creates_two_provider_jobs(self):
        eosda = FakeEOSDAClient(
            [
                {"status": "created", "task_id": "natural-task"},
                {"status": "created", "task_id": "ndvi-task"},
            ]
        )

        jobs = request_scene_imagery(self.scene, eosda_client=eosda)

        self.assertEqual(len(jobs), 2)
        self.assertEqual(SatelliteJob.objects.filter(scene=self.scene).count(), 2)
        self.assertEqual(
            set(
                SatelliteJob.objects.filter(scene=self.scene).values_list(
                    "provider_task_id", flat=True
                )
            ),
            {"natural-task", "ndvi-task"},
        )
        self.assertEqual(eosda.calls[0][0:2], ("POST", "/api/gdw/api"))

    def test_refresh_persists_ready_asset_urls(self):
        eosda = FakeEOSDAClient(
            [
                {"status": "created", "task_id": "natural-task"},
                {"status": "created", "task_id": "ndvi-task"},
                {
                    "status": "finished",
                    "result": {"url": "https://example.test/natural.png"},
                },
                {
                    "status": "finished",
                    "result": {"url": "https://example.test/ndvi.png"},
                },
            ]
        )
        request_scene_imagery(self.scene, eosda_client=eosda)

        refresh_scene_imagery(self.scene, eosda_client=eosda)
        self.scene.refresh_from_db()

        self.assertEqual(
            self.scene.assets[PRODUCT_NATURAL_COLOR]["url"],
            "https://example.test/natural.png",
        )
        self.assertEqual(
            self.scene.assets[PRODUCT_NDVI]["url"],
            "https://example.test/ndvi.png",
        )
        self.assertTrue(imagery_state(self.scene)[PRODUCT_NDVI]["ready"])
        self.assertEqual(
            SatelliteJob.objects.filter(
                scene=self.scene,
                status=SatelliteJob.Status.COMPLETED,
            ).count(),
            2,
        )

    def test_status_finds_nested_https_result(self):
        eosda = FakeEOSDAClient(
            [
                {
                    "status": "finished",
                    "result": [{"files": [{"download_url": "https://example.test/image.png"}]}],
                }
            ]
        )

        status = check_visual_task(eosda, "task-1")

        self.assertTrue(status.is_finished)
        self.assertEqual(status.image_url, "https://example.test/image.png")


class ImageryViewSecurityTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.client_a = Client.objects.create(name="Cliente A", slug="cliente-a")
        self.client_b = Client.objects.create(name="Cliente B", slug="cliente-b")
        self.operator = user_model.objects.create_user(
            "imagery-operator",
            password="test-password-123",
        )
        self.viewer = user_model.objects.create_user(
            "imagery-viewer",
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
        field_a = SatelliteField.objects.create(
            client=self.client_a,
            name="Lote A",
            geometry=POLYGON,
            eosda_field_id=1001,
        )
        field_b = SatelliteField.objects.create(
            client=self.client_b,
            name="Lote B",
            geometry=POLYGON,
            eosda_field_id=2001,
        )
        self.scene_a = SatelliteScene.objects.create(
            field=field_a,
            view_id="S2/A",
            captured_at=datetime(2026, 6, 23, 12, tzinfo=UTC),
        )
        self.scene_b = SatelliteScene.objects.create(
            field=field_b,
            view_id="S2/B",
            captured_at=datetime(2026, 6, 20, 12, tzinfo=UTC),
        )

    @patch("aplicaciones.satellite.views.request_scene_imagery", return_value=[])
    def test_operator_can_request_images_for_own_scene(self, request_images):
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse("satellite:request_scene_images", args=[self.scene_a.pk])
        )

        self.assertEqual(response.status_code, 302)
        request_images.assert_called_once_with(self.scene_a)

    @patch("aplicaciones.satellite.views.request_scene_imagery")
    def test_operator_cannot_request_images_for_another_client(self, request_images):
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse("satellite:request_scene_images", args=[self.scene_b.pk])
        )

        self.assertEqual(response.status_code, 404)
        request_images.assert_not_called()

    @patch("aplicaciones.satellite.views.request_scene_imagery")
    def test_viewer_cannot_consume_imagery_api(self, request_images):
        self.client.force_login(self.viewer)

        response = self.client.post(
            reverse("satellite:request_scene_images", args=[self.scene_a.pk])
        )

        self.assertEqual(response.status_code, 403)
        request_images.assert_not_called()
