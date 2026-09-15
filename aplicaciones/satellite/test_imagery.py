from datetime import UTC, datetime
from unittest.mock import patch

import httpx
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
    VIEW_CONTEXT,
    VIEW_DETAIL,
    build_context_geometry,
    build_detail_geometry,
    build_overlay_points,
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

    def request(
        self,
        method,
        path,
        *,
        params=None,
        json=None,
        accepted_status_codes=None,
    ):
        self.calls.append((method, path, json))
        payload = self.responses.pop(0)
        request = httpx.Request(method, f"https://api-connect.eos.com{path}")
        return httpx.Response(200, json=payload, request=request)


def _lon_span(geometry):
    ring = geometry["coordinates"][0]
    return max(point[0] for point in ring) - min(point[0] for point in ring)


def _lat_span(geometry):
    ring = geometry["coordinates"][0]
    return max(point[1] for point in ring) - min(point[1] for point in ring)


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

    def test_context_geometry_is_larger_than_tiny_field(self):
        context = build_context_geometry(POLYGON)

        self.assertGreater(_lon_span(context), _lon_span(POLYGON) * 5)
        self.assertGreater(_lat_span(context), _lat_span(POLYGON) * 5)
        self.assertTrue(build_overlay_points(POLYGON, context))

    def test_detail_geometry_is_closer_than_context_but_keeps_margin(self):
        context = build_context_geometry(POLYGON)
        detail = build_detail_geometry(POLYGON)

        self.assertGreater(_lon_span(detail), _lon_span(POLYGON))
        self.assertGreater(_lat_span(detail), _lat_span(POLYGON))
        self.assertLess(_lon_span(detail), _lon_span(context))
        self.assertLess(_lat_span(detail), _lat_span(context))
        self.assertTrue(build_overlay_points(POLYGON, detail))

    def test_request_scene_imagery_uses_context_window_by_default(self):
        eosda = FakeEOSDAClient(
            [
                {"status": "created", "task_id": "natural-task"},
                {"status": "created", "task_id": "ndvi-task"},
            ]
        )

        jobs = request_scene_imagery(self.scene, eosda_client=eosda)

        self.assertEqual(len(jobs), 2)
        self.assertEqual(SatelliteJob.objects.filter(scene=self.scene).count(), 2)
        self.assertEqual(eosda.calls[0][0:2], ("POST", "/api/gdw/api"))
        sent_geometry = eosda.calls[0][2]["params"]["geometry"]
        self.assertEqual(jobs[0].request_payload["view_mode"], VIEW_CONTEXT)
        self.assertEqual(jobs[0].request_payload["view_geometry"], sent_geometry)
        self.assertTrue(jobs[0].request_payload["overlay_points"])

    def test_request_detail_uses_closer_window_and_finer_output(self):
        eosda = FakeEOSDAClient(
            [
                {"status": "created", "task_id": "detail-natural-task"},
                {"status": "created", "task_id": "detail-ndvi-task"},
            ]
        )

        jobs = request_scene_imagery(
            self.scene,
            eosda_client=eosda,
            view_mode=VIEW_DETAIL,
        )
        sent_payload = eosda.calls[0][2]["params"]

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].request_payload["view_mode"], VIEW_DETAIL)
        self.assertEqual(sent_payload["geometry"], build_detail_geometry(POLYGON))
        self.assertEqual(sent_payload["px_size"], 1)
        self.assertLess(
            _lon_span(sent_payload["geometry"]),
            _lon_span(build_context_geometry(POLYGON)),
        )

    def test_legacy_single_assets_are_exposed_as_context(self):
        self.scene.assets = {
            PRODUCT_NATURAL_COLOR: {"url": "https://example.test/legacy-natural.png"},
            PRODUCT_NDVI: {"url": "https://example.test/legacy-ndvi.png"},
        }
        self.scene.save(update_fields=("assets", "updated_at"))

        state = imagery_state(self.scene)

        self.assertTrue(state[PRODUCT_NATURAL_COLOR][VIEW_CONTEXT]["ready"])
        self.assertFalse(state[PRODUCT_NATURAL_COLOR][VIEW_DETAIL]["has_asset"])

    def test_force_detail_regeneration_keeps_old_detail_asset_while_job_runs(self):
        self.scene.assets = {
            PRODUCT_NATURAL_COLOR: {
                VIEW_CONTEXT: {"url": "https://example.test/context-natural.png"},
                VIEW_DETAIL: {"url": "https://example.test/detail-natural.png"},
            },
            PRODUCT_NDVI: {
                VIEW_CONTEXT: {"url": "https://example.test/context-ndvi.png"},
                VIEW_DETAIL: {"url": "https://example.test/detail-ndvi.png"},
            },
        }
        self.scene.save(update_fields=("assets", "updated_at"))
        eosda = FakeEOSDAClient(
            [
                {"status": "created", "task_id": "new-detail-natural-task"},
                {"status": "created", "task_id": "new-detail-ndvi-task"},
            ]
        )

        jobs = request_scene_imagery(
            self.scene,
            eosda_client=eosda,
            view_mode=VIEW_DETAIL,
            force=True,
        )
        state = imagery_state(self.scene)

        self.assertEqual(len(jobs), 2)
        self.assertTrue(state[PRODUCT_NATURAL_COLOR][VIEW_CONTEXT]["ready"])
        self.assertTrue(state[PRODUCT_NATURAL_COLOR][VIEW_DETAIL]["has_asset"])
        self.assertTrue(state[PRODUCT_NATURAL_COLOR][VIEW_DETAIL]["waiting"])
        self.assertFalse(state[PRODUCT_NATURAL_COLOR][VIEW_DETAIL]["ready"])

    def test_refresh_persists_context_assets_in_variant_structure(self):
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

        natural = self.scene.assets[PRODUCT_NATURAL_COLOR][VIEW_CONTEXT]
        ndvi = self.scene.assets[PRODUCT_NDVI][VIEW_CONTEXT]
        self.assertEqual(natural["url"], "https://example.test/natural.png")
        self.assertEqual(ndvi["url"], "https://example.test/ndvi.png")
        self.assertTrue(natural["overlay_points"])
        self.assertTrue(ndvi["view_geometry"])
        self.assertTrue(imagery_state(self.scene)[PRODUCT_NDVI][VIEW_CONTEXT]["ready"])
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
    def test_operator_can_request_context_for_own_scene(self, request_images):
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse("satellite:request_scene_images", args=[self.scene_a.pk])
        )

        self.assertEqual(response.status_code, 302)
        request_images.assert_called_once_with(
            self.scene_a,
            view_mode=VIEW_CONTEXT,
            force=False,
        )

    @patch("aplicaciones.satellite.views.request_scene_imagery", return_value=[])
    def test_operator_can_request_detail_for_own_scene(self, request_images):
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse("satellite:request_scene_images", args=[self.scene_a.pk]),
            {"view_mode": VIEW_DETAIL},
        )

        self.assertEqual(response.status_code, 302)
        request_images.assert_called_once_with(
            self.scene_a,
            view_mode=VIEW_DETAIL,
            force=False,
        )

    @patch("aplicaciones.satellite.views.request_scene_imagery", return_value=[])
    def test_operator_can_regenerate_detail_for_own_scene(self, request_images):
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse("satellite:request_scene_images", args=[self.scene_a.pk]),
            {"view_mode": VIEW_DETAIL, "regenerate": "1"},
        )

        self.assertEqual(response.status_code, 302)
        request_images.assert_called_once_with(
            self.scene_a,
            view_mode=VIEW_DETAIL,
            force=True,
        )

    @patch("aplicaciones.satellite.views.request_scene_imagery")
    def test_invalid_view_mode_does_not_call_provider(self, request_images):
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse("satellite:request_scene_images", args=[self.scene_a.pk]),
            {"view_mode": "invalid"},
        )

        self.assertEqual(response.status_code, 302)
        request_images.assert_not_called()

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
