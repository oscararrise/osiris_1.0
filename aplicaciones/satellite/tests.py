from django.core.exceptions import ValidationError
from django.test import TestCase

from aplicaciones.core.models import Client
from aplicaciones.satellite.models import (
    SatelliteField,
    SatelliteJob,
    SatelliteScene,
)


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
        field = SatelliteField(client=self.client_obj, name="Lote Norte", geometry=VALID_POLYGON)
        field.full_clean()

    def test_invalid_geometry_is_rejected(self):
        field = SatelliteField(
            client=self.client_obj,
            name="Lote Norte",
            geometry={"type": "Point", "coordinates": [-74.10, 4.60]},
        )
        with self.assertRaises(ValidationError):
            field.full_clean()

    def test_job_rejects_scene_from_another_field(self):
        field_a = SatelliteField.objects.create(
            client=self.client_obj,
            name="Lote A",
            geometry=VALID_POLYGON,
        )
        field_b = SatelliteField.objects.create(
            client=self.client_obj,
            name="Lote B",
            geometry=VALID_POLYGON,
        )
        scene = SatelliteScene.objects.create(
            field=field_b,
            view_id="scene-1",
            captured_at="2026-09-05T12:00:00Z",
        )
        job = SatelliteJob(
            field=field_a,
            scene=scene,
            job_type=SatelliteJob.JobType.IMAGERY,
        )

        with self.assertRaises(ValidationError):
            job.full_clean()
