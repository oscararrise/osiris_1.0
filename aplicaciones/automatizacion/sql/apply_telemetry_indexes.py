import os

import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "osiris_dev.settings",
)
django.setup()

from django.db import connections

SQLS = [
    """
    CREATE INDEX IF NOT EXISTS idx_sensor_readings_received_at
    ON telemetry.sensor_readings (received_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sensor_readings_device_received
    ON telemetry.sensor_readings (device_id, received_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sensor_readings_device_id
    ON telemetry.sensor_readings (device_id)
    """,
]

conn = connections["telemetry"]
conn.ensure_connection()
previous = conn.get_autocommit()
conn.set_autocommit(True)

try:
    with conn.cursor() as cursor:
        for sql in SQLS:
            print("Creando índice...")
            cursor.execute(sql)
            print("OK")

        cursor.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'telemetry'
              AND tablename = 'sensor_readings'
            ORDER BY 1
            """
        )
        print("Índices actuales:")
        for row in cursor.fetchall():
            print(" -", row[0])
finally:
    conn.set_autocommit(previous)
