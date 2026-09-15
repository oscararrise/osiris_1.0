from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.db import connections

from .base import SensorDataAdapter


def _rows(cursor, rows: Iterable[tuple]) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    result = []
    for row in rows:
        values = (
            None if isinstance(value, float) and not math.isfinite(value) else value
            for value in row
        )
        result.append(dict(zip(columns, values, strict=True)))
    return result


class AranetAdapter(SensorDataAdapter):
    """Read-only adapter for the normalized schema produced by api_aranet."""

    def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with connections[self.database_alias].cursor() as cursor:
            cursor.execute(sql, params)
            return _rows(cursor, cursor.fetchall())

    def list_sensors(self) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT
                s.id,
                COALESCE(NULLIF(s.name, ''), NULLIF(s.sensor_code, ''), s.id) AS name,
                s.sensor_code AS code,
                COALESCE(st.name, s.sensor_type_id, 'Sensor') AS type_name,
                s.is_active,
                status.last_telemetry_at AS last_seen_at,
                status.rssi_dbm,
                status.battery_value,
                COALESCE(battery_unit.name, status.battery_unit_id, '') AS battery_unit
            FROM aranet.sensor AS s
            LEFT JOIN aranet.sensor_type AS st ON st.id = s.sensor_type_id
            LEFT JOIN aranet.v_sensor_status AS status ON status.sensor_id = s.id
            LEFT JOIN aranet.unit AS battery_unit ON battery_unit.id = status.battery_unit_id
            WHERE s.is_active
            ORDER BY name, s.id
            """
        )

    def list_metrics(self, sensor_id: str) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT
                capability.metric_id AS id,
                COALESCE(NULLIF(metric.name, ''), capability.metric_id) AS name,
                metric.kind,
                capability.probe_no,
                preferred_unit.id AS unit_id,
                preferred_unit.name AS unit,
                COALESCE(preferred_unit.precision_digits, 2) AS precision_digits
            FROM aranet.sensor_capability AS capability
            JOIN aranet.sensor AS sensor
              ON sensor.id = capability.sensor_id AND sensor.is_active
            LEFT JOIN aranet.metric AS metric ON metric.id = capability.metric_id
            LEFT JOIN LATERAL (
                SELECT unit.id, unit.name, unit.precision_digits
                FROM aranet.metric_unit AS metric_unit
                JOIN aranet.unit AS unit ON unit.id = metric_unit.unit_id
                WHERE metric_unit.metric_id = capability.metric_id
                ORDER BY metric_unit.is_selected DESC, metric_unit.is_default DESC, unit.id
                LIMIT 1
            ) AS preferred_unit ON TRUE
            WHERE capability.sensor_id = %s AND capability.is_active
            ORDER BY name, capability.probe_no
            """,
            (sensor_id,),
        )

    def latest_values(self, sensor_id: str) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT DISTINCT ON (latest.metric_id, latest.probe_no)
                latest.metric_id AS id,
                COALESCE(NULLIF(metric.name, ''), latest.metric_id) AS name,
                latest.probe_no,
                latest.value,
                COALESCE(unit.name, latest.unit_id, '') AS unit,
                COALESCE(unit.precision_digits, 2) AS precision_digits,
                latest.measured_at,
                latest.novelty
            FROM aranet.v_latest_measurements AS latest
            JOIN aranet.sensor AS sensor
              ON sensor.id = latest.source_sensor_id AND sensor.is_active
            LEFT JOIN aranet.metric AS metric ON metric.id = latest.metric_id
            LEFT JOIN aranet.unit AS unit ON unit.id = latest.unit_id
            WHERE latest.source_sensor_id = %s
            ORDER BY latest.metric_id, latest.probe_no, latest.measured_at DESC
            """,
            (sensor_id,),
        )

    def time_series(
        self,
        sensor_id: str,
        metric_id: str,
        probe_no: int,
        start: datetime,
        end: datetime,
        max_points: int,
    ) -> list[dict[str, Any]]:
        duration_seconds = max((end - start).total_seconds(), 1)
        bucket_seconds = max(60, math.ceil(duration_seconds / max(max_points, 1)))
        # Round up to a human-friendly granularity while keeping the result bounded.
        granularities = (60, 300, 900, 1800, 3600, 10800, 21600, 43200, 86400, 604800)
        bucket_seconds = next(
            (value for value in granularities if value >= bucket_seconds),
            math.ceil(bucket_seconds / 86400) * 86400,
        )
        interval = f"{bucket_seconds} seconds"
        return self._query(
            """
            SELECT
                date_bin(%s::interval, measurement.measured_at,
                         TIMESTAMPTZ '2001-01-01 00:00:00+00') AS measured_at,
                AVG(measurement.value) AS value,
                MIN(measurement.value) AS minimum,
                MAX(measurement.value) AS maximum,
                COUNT(*) AS sample_count,
                COALESCE(unit.name, MAX(measurement.unit_id), '') AS unit
            FROM aranet.measurement AS measurement
            JOIN aranet.sensor AS sensor
              ON sensor.id = measurement.source_sensor_id AND sensor.is_active
            JOIN aranet.sensor_capability AS capability
              ON capability.sensor_id = measurement.source_sensor_id
             AND capability.metric_id = measurement.metric_id
             AND capability.probe_no = measurement.probe_no
             AND capability.is_active
            LEFT JOIN aranet.unit AS unit ON unit.id = measurement.unit_id
            WHERE measurement.source_sensor_id = %s
              AND measurement.metric_id = %s
              AND measurement.probe_no = %s
              AND measurement.measured_at >= %s
              AND measurement.measured_at <= %s
            GROUP BY 1, unit.name
            ORDER BY 1
            LIMIT %s
            """,
            (interval, sensor_id, metric_id, probe_no, start, end, max_points),
        )

    def active_alarms(self, sensor_id: str | None = None) -> list[dict[str, Any]]:
        sensor_filter = "AND alarm.sensor_id = %s" if sensor_id else ""
        params: tuple[Any, ...] = (sensor_id,) if sensor_id else ()
        return self._query(
            f"""
            SELECT
                alarm.id,
                alarm.sensor_id,
                COALESCE(alarm.sensor_name, alarm.sensor_id, 'Sensor') AS sensor_name,
                COALESCE(alarm.rule_name, 'Alerta activa') AS rule_name,
                COALESCE(alarm.metric_name, alarm.metric_id, '') AS metric_name,
                alarm.severity,
                alarm.alarmed_at,
                alarm.threshold_direction,
                alarm.threshold_value,
                alarm.worst_value,
                COALESCE(alarm.unit_name, alarm.unit_id, '') AS unit,
                alarm.note
            FROM aranet.v_active_alarms AS alarm
            WHERE TRUE {sensor_filter}
            ORDER BY alarm.severity DESC NULLS LAST, alarm.alarmed_at DESC NULLS LAST
            LIMIT 100
            """,
            params,
        )
