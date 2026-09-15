from django.db import models
class data(models.Model):
    nombre = models.CharField(max_length=100)
    clave = models.CharField(max_length=100)  # Asegura que la clave es un campo de texto

    def __str__(self):
        # Retorna una representación en cadena del objeto, combinando nombre y clave
        return f"{self.nombre} - {self.clave}"
    
class SensorData(models.Model):
    Id = models.AutoField(primary_key=True)
    Cliente = models.CharField(max_length=100)
    Fecha_carga = models.DateTimeField()
    DB_information = models.JSONField()

    class Meta:
        db_table = 'data_sensor'



# Modelo histórico conservado solo para mantener el estado de migraciones antiguas.
# Las nuevas escrituras usan core.ControlEvent, que sí tiene FK al cliente.
class control_data(models.Model):  # noqa: N801
    cliente = models.CharField(max_length=100)
    fecha = models.CharField(max_length=100)
    control_data = models.CharField(max_length=100)


class SensorReading(models.Model):
    id = models.BigIntegerField(primary_key=True)
    raw_message_id = models.BigIntegerField()
    device_id = models.CharField(max_length=255)

    event_timestamp = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField()

    # Sensor de suelo 1
    sensor_1_soil_temperature_c = models.FloatField(null=True, blank=True)
    sensor_1_soil_moisture_percent = models.FloatField(null=True, blank=True)
    sensor_1_ec = models.FloatField(null=True, blank=True)
    sensor_1_ph = models.FloatField(null=True, blank=True)
    sensor_1_nitrogen = models.FloatField(null=True, blank=True)
    sensor_1_phosphorus = models.FloatField(null=True, blank=True)
    sensor_1_potassium = models.FloatField(null=True, blank=True)
    sensor_1_salinity = models.FloatField(null=True, blank=True)

    # Sensor de suelo 2
    sensor_2_soil_temperature_c = models.FloatField(null=True, blank=True)
    sensor_2_soil_moisture_percent = models.FloatField(null=True, blank=True)
    sensor_2_ec = models.FloatField(null=True, blank=True)
    sensor_2_ph = models.FloatField(null=True, blank=True)
    sensor_2_nitrogen = models.FloatField(null=True, blank=True)
    sensor_2_phosphorus = models.FloatField(null=True, blank=True)
    sensor_2_potassium = models.FloatField(null=True, blank=True)
    sensor_2_salinity = models.FloatField(null=True, blank=True)

    # Estación meteorológica
    air_temperature_c = models.FloatField(null=True, blank=True)
    air_humidity_percent = models.FloatField(null=True, blank=True)
    atmospheric_pressure_hpa = models.FloatField(null=True, blank=True)
    wind_speed_ms = models.FloatField(null=True, blank=True)
    wind_direction_degree = models.FloatField(null=True, blank=True)
    rain_mm = models.FloatField(null=True, blank=True)
    solar_radiation_wm2 = models.FloatField(null=True, blank=True)
    illumination_klux = models.FloatField(null=True, blank=True)
    sunshine_duration_h = models.FloatField(null=True, blank=True)
    dew_point_temperature_c = models.FloatField(null=True, blank=True)
    et0_mm = models.FloatField(null=True, blank=True)

    # Sensor de nivel
    level_temperature_c = models.FloatField(null=True, blank=True)
    level_value = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = '"telemetry"."sensor_readings"'
        # Índices de rendimiento: aplicaciones/automatizacion/sql/optimize_telemetry.sql

    def __str__(self):
        return f"{self.device_id} - {self.received_at}"
