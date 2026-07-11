import os
import django
from django.db import connections

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "osiris_dev.settings")
django.setup()

try:
    with connections["telemetry"].cursor() as cursor:
        cursor.execute("""
            SELECT
                current_database(),
                current_user,
                version();
        """)

        database_name, database_user, version = cursor.fetchone()

        print("Conexión exitosa")
        print(f"Base de datos: {database_name}")
        print(f"Usuario: {database_user}")
        print(f"Versión: {version}")

        cursor.execute("""
            SELECT COUNT(*)
            FROM telemetry.sensor_readings;
        """)

        total = cursor.fetchone()[0]

        print(f"Registros en telemetry.sensor_readings: {total}")

except Exception as error:
    print("Error de conexión")
    print(error)