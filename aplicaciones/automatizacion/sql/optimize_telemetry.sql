-- Optimización de telemetría para el dashboard s2.
-- Ejecutar en PostgreSQL (agro_platform) con un usuario con permisos DDL.
-- CONCURRENTLY evita bloquear escrituras; no correr dentro de una transacción.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_readings_received_at
    ON telemetry.sensor_readings (received_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_readings_device_received
    ON telemetry.sensor_readings (device_id, received_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_readings_device_id
    ON telemetry.sensor_readings (device_id);

-- Acelerar listado de estaciones (DISTINCT device_id).
ANALYZE telemetry.sensor_readings;
