from __future__ import annotations

import math  # noqa: I001
from datetime import datetime
from typing import Any

from django.db import connections

from .base import SensorDataAdapter


METRICS: dict[str, dict[str, Any]] = {
    "sensor_1_soil_temperature_c": {
        "name": "Temperatura del suelo 1",
        "unit": "°C",
        "precision": 2,
    },
    "sensor_1_soil_moisture_percent": {"name": "Humedad del suelo 1", "unit": "%", "precision": 2},
    "sensor_1_ec": {"name": "Conductividad eléctrica suelo 1", "unit": "µS/cm", "precision": 2},
    "sensor_1_ph": {"name": "pH suelo 1", "unit": "pH", "precision": 2},
    "sensor_1_nitrogen": {"name": "Nitrógeno suelo 1", "unit": "mg/kg", "precision": 2},
    "sensor_1_phosphorus": {"name": "Fósforo suelo 1", "unit": "mg/kg", "precision": 2},
    "sensor_1_potassium": {"name": "Potasio suelo 1", "unit": "mg/kg", "precision": 2},
    "sensor_1_salinity": {"name": "Salinidad suelo 1", "unit": "mg/L", "precision": 2},
    "sensor_2_soil_temperature_c": {
        "name": "Temperatura del suelo 2",
        "unit": "°C",
        "precision": 2,
    },
    "sensor_2_soil_moisture_percent": {"name": "Humedad del suelo 2", "unit": "%", "precision": 2},
    "sensor_2_ec": {"name": "Conductividad eléctrica suelo 2", "unit": "µS/cm", "precision": 2},
    "sensor_2_ph": {"name": "pH suelo 2", "unit": "pH", "precision": 2},
    "sensor_2_nitrogen": {"name": "Nitrógeno suelo 2", "unit": "mg/kg", "precision": 2},
    "sensor_2_phosphorus": {"name": "Fósforo suelo 2", "unit": "mg/kg", "precision": 2},
    "sensor_2_potassium": {"name": "Potasio suelo 2", "unit": "mg/kg", "precision": 2},
    "sensor_2_salinity": {"name": "Salinidad suelo 2", "unit": "mg/L", "precision": 2},
    "air_temperature_c": {"name": "Temperatura del aire", "unit": "°C", "precision": 2},
    "air_humidity_percent": {"name": "Humedad relativa", "unit": "%", "precision": 2},
    "atmospheric_pressure_hpa": {"name": "Presión atmosférica", "unit": "hPa", "precision": 2},
    "wind_speed_ms": {"name": "Velocidad del viento", "unit": "m/s", "precision": 2},
    "wind_direction_degree": {"name": "Dirección del viento", "unit": "°", "precision": 1},
    "rain_mm": {"name": "Precipitación", "unit": "mm", "precision": 2},
    "solar_radiation_wm2": {"name": "Radiación solar", "unit": "W/m²", "precision": 2},
    "illumination_klux": {"name": "Iluminación", "unit": "klux", "precision": 2},
    "sunshine_duration_h": {"name": "Brillo solar", "unit": "h", "precision": 2},
    "dew_point_temperature_c": {"name": "Punto de rocío", "unit": "°C", "precision": 2},
    "et0_mm": {"name": "Evapotranspiración de referencia", "unit": "mm", "precision": 2},
    "level_temperature_c": {
        "name": "Temperatura del sensor de nivel",
        "unit": "°C",
        "precision": 2,
    },
    "level_value": {"name": "Nivel", "unit": "", "precision": 2},
}


class TelemetryAdapter(SensorDataAdapter):
    """Read-only adapter for the legacy telemetry.sensor_readings schema."""

    def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with connections[self.database_alias].cursor() as cursor:
            cursor.execute(sql, params)
            columns = [column[0] for column in cursor.description]
            rows = []
            for row in cursor.fetchall():
                clean = [
                    None if isinstance(value, float) and not math.isfinite(value) else value
                    for value in row
                ]
                rows.append(dict(zip(columns, clean, strict=True)))
            return rows

    def list_sensors(self) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT
                device_id AS id,
                device_id AS name,
                device_id AS code,
                'Estación de telemetría agrícola' AS type_name,
                TRUE AS is_active,
                MAX(COALESCE(event_timestamp, received_at)) AS last_seen_at,
                NULL::double precision AS rssi_dbm,
                NULL::double precision AS battery_value,
                ''::text AS battery_unit
            FROM telemetry.sensor_readings
            GROUP BY device_id
            ORDER BY device_id
            """
        )

    def list_metrics(self, sensor_id: str) -> list[dict[str, Any]]:
        exists = self._query(
            "SELECT 1 AS found FROM telemetry.sensor_readings WHERE device_id = %s LIMIT 1",
            (sensor_id,),
        )
        if not exists:
            return []
        return [
            {
                "id": metric_id,
                "name": definition["name"],
                "kind": "numeric",
                "probe_no": 0,
                "unit_id": None,
                "unit": definition["unit"],
                "precision_digits": definition["precision"],
            }
            for metric_id, definition in METRICS.items()
        ]

    def latest_values(self, sensor_id: str) -> list[dict[str, Any]]:
        columns = ", ".join(METRICS)
        rows = self._query(
            f"""
            SELECT
                COALESCE(event_timestamp, received_at) AS measured_at,
                {columns}
            FROM telemetry.sensor_readings
            WHERE device_id = %s
            ORDER BY COALESCE(event_timestamp, received_at) DESC
            LIMIT 1
            """,
            (sensor_id,),
        )
        if not rows:
            return []

        row = rows[0]
        measured_at = row["measured_at"]
        result = []
        for metric_id, definition in METRICS.items():
            value = row.get(metric_id)
            if value is None:
                continue
            result.append(
                {
                    "id": metric_id,
                    "name": definition["name"],
                    "probe_no": 0,
                    "value": value,
                    "unit": definition["unit"],
                    "precision_digits": definition["precision"],
                    "measured_at": measured_at,
                    "novelty": None,
                }
            )
        return result

    def time_series(
        self,
        sensor_id: str,
        metric_id: str,
        probe_no: int,
        start: datetime,
        end: datetime,
        max_points: int,
    ) -> list[dict[str, Any]]:
        definition = METRICS.get(metric_id)
        if definition is None:
            return []

        duration_seconds = max((end - start).total_seconds(), 1)
        bucket_seconds = max(60, math.ceil(duration_seconds / max(max_points, 1)))
        granularities = (60, 300, 900, 1800, 3600, 10800, 21600, 43200, 86400, 604800)
        bucket_seconds = next(
            (value for value in granularities if value >= bucket_seconds),
            math.ceil(bucket_seconds / 86400) * 86400,
        )
        interval = f"{bucket_seconds} seconds"
        column = metric_id  # metric_id is restricted to the METRICS whitelist above.

        return self._query(
            f"""
            SELECT
                date_bin(
                    %s::interval,
                    COALESCE(event_timestamp, received_at),
                    TIMESTAMPTZ '2001-01-01 00:00:00+00'
                ) AS measured_at,
                AVG({column}) AS value,
                MIN({column}) AS minimum,
                MAX({column}) AS maximum,
                COUNT(*) AS sample_count,
                %s::text AS unit
            FROM telemetry.sensor_readings
            WHERE device_id = %s
              AND {column} IS NOT NULL
              AND COALESCE(event_timestamp, received_at) >= %s
              AND COALESCE(event_timestamp, received_at) <= %s
            GROUP BY 1
            ORDER BY 1
            LIMIT %s
            """,
            (interval, definition["unit"], sensor_id, start, end, max_points),
        )

    def active_alarms(self, sensor_id: str | None = None) -> list[dict[str, Any]]:
        # El esquema legacy no tiene una tabla de alarmas normalizada todavía.
        return []
