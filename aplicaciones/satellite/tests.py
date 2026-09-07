from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from aplicaciones.core.models import Client
from aplicaciones.satellite import models as satellite_models

VALID_POLYGON = {
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


class SatelliteFieldTests(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(name="Cliente Satélite", slug="cliente-satelite")

    def test_valid_polygon_passes_model_validation(self):
        field = satellite_models.SatelliteField(
            client=self.client_obj,
            name="Lote Norte",
            geometry=VALID_POLYGON,
        )
        field.full_clean()

    def test_invalid_geometry_is_rejected(self):
        field = satellite_models.SatelliteField(
            client=self.client_obj,
            name="Lote Norte",
            geometry={"type": "Point", "coordinates": [-74.10, 4.60]},
        )
        with self.assertRaises(ValidationError):
            field.full_clean()

    def test_job_rejects_scene_from_another_field(self):
        field_a = satellite_models.SatelliteField.objects.create(
            client=self.client_obj,
            name="Lote A",
            geometry=VALID_POLYGON,
        )
        field_b = satellite_models.SatelliteField.objects.create(
            client=self.client_obj,
            name="Lote B",
            geometry=VALID_POLYGON,
        )
        scene = satellite_models.SatelliteScene.objects.create(
            field=field_b,
            view_id="scene-1",
            captured_at=timezone.now(),
        )
        job = satellite_models.SatelliteJob(
            field=field_a,
            scene=scene,
            job_type=satellite_models.SatelliteJob.JobType.IMAGERY,
        )

        with self.assertRaises(ValidationError):
            job.full_clean()
