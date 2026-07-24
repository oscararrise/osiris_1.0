from django.shortcuts import render, redirect
from django.contrib import messages
from .models import (
    data,
    SensorData,
    ControlData,
    Support,
    SensorReading,
)
from django.http import JsonResponse
from django.core.mail import EmailMessage
from django.http import HttpResponse
from datetime import datetime
import json 
import logging
import math

from collections import defaultdict
from statistics import mean, median
from datetime import timedelta

from django.db import DatabaseError
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_date

from .telemetry_cache import (
    build_dashboard_cache_key,
    downsample_readings,
    get_latest_device_id,
    get_telemetry_devices,
    telemetry_queryset,
)

logger = logging.getLogger(__name__)
import csv

from datetime import datetime, time, timedelta


SENSOR_DEFINITIONS = [

    # Suelo 1
    {
        "key": "sensor_1_soil_temperature_c",
        "label": "Temperatura del suelo",
        "unit": "°C",
        "group": "Sensor de suelo 1",
    },
    {
        "key": "sensor_1_soil_moisture_percent",
        "label": "Humedad del suelo",
        "unit": "%",
        "group": "Sensor de suelo 1",
    },
    {
        "key": "sensor_1_ec",
        "label": "Conductividad eléctrica",
        "unit": "µS/cm",
        "group": "Sensor de suelo 1",
    },
    {
        "key": "sensor_1_ph",
        "label": "pH",
        "unit": "pH",
        "group": "Sensor de suelo 1",
    },
    {
        "key": "sensor_1_nitrogen",
        "label": "Nitrógeno",
        "unit": "mg/kg",
        "group": "Sensor de suelo 1",
    },
    {
        "key": "sensor_1_phosphorus",
        "label": "Fósforo",
        "unit": "mg/kg",
        "group": "Sensor de suelo 1",
    },
    {
        "key": "sensor_1_potassium",
        "label": "Potasio",
        "unit": "mg/kg",
        "group": "Sensor de suelo 1",
    },
    {
        "key": "sensor_1_salinity",
        "label": "Salinidad",
        "unit": "mg/L",
        "group": "Sensor de suelo 1",
    },

    # Suelo 2
    {
        "key": "sensor_2_soil_temperature_c",
        "label": "Temperatura del suelo",
        "unit": "°C",
        "group": "Sensor de suelo 2",
    },
    {
        "key": "sensor_2_soil_moisture_percent",
        "label": "Humedad del suelo",
        "unit": "%",
        "group": "Sensor de suelo 2",
    },
    {
        "key": "sensor_2_ec",
        "label": "Conductividad eléctrica",
        "unit": "µS/cm",
        "group": "Sensor de suelo 2",
    },
    {
        "key": "sensor_2_ph",
        "label": "pH",
        "unit": "pH",
        "group": "Sensor de suelo 2",
    },
    {
        "key": "sensor_2_nitrogen",
        "label": "Nitrógeno",
        "unit": "mg/kg",
        "group": "Sensor de suelo 2",
    },
    {
        "key": "sensor_2_phosphorus",
        "label": "Fósforo",
        "unit": "mg/kg",
        "group": "Sensor de suelo 2",
    },
    {
        "key": "sensor_2_potassium",
        "label": "Potasio",
        "unit": "mg/kg",
        "group": "Sensor de suelo 2",
    },
    {
        "key": "sensor_2_salinity",
        "label": "Salinidad",
        "unit": "mg/L",
        "group": "Sensor de suelo 2",
    },

    # Estación meteorológica
    {
        "key": "air_temperature_c",
        "label": "Temperatura del aire",
        "unit": "°C",
        "group": "Estación meteorológica",
    },
    {
        "key": "air_humidity_percent",
        "label": "Humedad relativa",
        "unit": "%",
        "group": "Estación meteorológica",
    },
    {
        "key": "atmospheric_pressure_hpa",
        "label": "Presión atmosférica",
        "unit": "hPa",
        "group": "Estación meteorológica",
    },
    {
        "key": "wind_speed_ms",
        "label": "Velocidad del viento",
        "unit": "m/s",
        "group": "Estación meteorológica",
    },
    {
        "key": "wind_direction_degree",
        "label": "Dirección del viento",
        "unit": "°",
        "group": "Estación meteorológica",
    },
    {
        "key": "rain_mm",
        "label": "Precipitación",
        "unit": "mm",
        "group": "Estación meteorológica",
    },
    {
        "key": "solar_radiation_wm2",
        "label": "Radiación solar",
        "unit": "W/m²",
        "group": "Estación meteorológica",
    },
    {
        "key": "illumination_klux",
        "label": "Iluminación",
        "unit": "klux",
        "group": "Estación meteorológica",
    },
    {
        "key": "sunshine_duration_h",
        "label": "Duración de brillo solar",
        "unit": "h",
        "group": "Estación meteorológica",
    },
    {
        "key": "dew_point_temperature_c",
        "label": "Punto de rocío",
        "unit": "°C",
        "group": "Estación meteorológica",
    },
    {
        "key": "et0_mm",
        "label": "Evapotranspiración de referencia",
        "unit": "mm",
        "group": "Estación meteorológica",
    },

    # Nivel
]

SENSOR_FIELDS = [
    sensor["key"]
    for sensor in SENSOR_DEFINITIONS
]


WIND_SECTORS = [
    "N",
    "NE",
    "E",
    "SE",
    "S",
    "SO",
    "O",
    "NO",
]


def safe_number(value):
    """
    Convierte un valor a float y rechaza NaN o infinitos.
    """

    if value is None or value == "":
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number if math.isfinite(number) else None


def average(values):
    valid_values = [
        value
        for value in values
        if value is not None
    ]

    return mean(valid_values) if valid_values else None


def minimum(values):
    valid_values = [
        value
        for value in values
        if value is not None
    ]

    return min(valid_values) if valid_values else None


def maximum(values):
    valid_values = [
        value
        for value in values
        if value is not None
    ]

    return max(valid_values) if valid_values else None


def round_value(value, digits=2):
    if value is None:
        return None

    return round(value, digits)


def calculate_vpd_kpa(temperature_c, humidity_percent):
    """
    Calcula el déficit de presión de vapor en kPa.

    Usa temperatura del aire y humedad relativa.
    """

    temperature = safe_number(temperature_c)
    humidity = safe_number(humidity_percent)

    if temperature is None or humidity is None:
        return None

    if humidity < 0 or humidity > 100:
        return None

    saturation_pressure = (
        0.6108
        * math.exp(
            (17.27 * temperature)
            / (temperature + 237.3)
        )
    )

    vpd = saturation_pressure * (
        1 - humidity / 100
    )

    return max(vpd, 0)


def get_wind_sector(direction_degree):
    direction = safe_number(direction_degree)

    if direction is None:
        return None

    if direction < 0 or direction > 360:
        return None

    index = int(
        ((direction % 360) + 22.5) // 45
    ) % 8

    return WIND_SECTORS[index]


def validate_sensor_value(field, value):
    """
    Valida únicamente límites físicamente posibles.

    No evalúa si el valor es adecuado para un cultivo.
    """

    validators = {
        "sensor_1_soil_temperature_c": (
            lambda number: -30 <= number <= 80
        ),
        "sensor_1_soil_moisture_percent": (
            lambda number: 0 <= number <= 100
        ),
        "sensor_1_ec": (
            lambda number: number >= 0
        ),
        "sensor_1_ph": (
            lambda number: 0 <= number <= 14
        ),
        "sensor_1_nitrogen": (
            lambda number: number >= 0
        ),
        "sensor_1_phosphorus": (
            lambda number: number >= 0
        ),
        "sensor_1_potassium": (
            lambda number: number >= 0
        ),
        "sensor_1_salinity": (
            lambda number: number >= 0
        ),
        "sensor_2_soil_temperature_c": (
            lambda number: -30 <= number <= 80
        ),
        "sensor_2_soil_moisture_percent": (
            lambda number: 0 <= number <= 100
        ),
        "sensor_2_ec": (
            lambda number: number >= 0
        ),
        "sensor_2_ph": (
            lambda number: 0 <= number <= 14
        ),
        "sensor_2_nitrogen": (
            lambda number: number >= 0
        ),
        "sensor_2_phosphorus": (
            lambda number: number >= 0
        ),
        "sensor_2_potassium": (
            lambda number: number >= 0
        ),
        "sensor_2_salinity": (
            lambda number: number >= 0
        ),
        "air_temperature_c": (
            lambda number: -80 <= number <= 70
        ),
        "air_humidity_percent": (
            lambda number: 0 <= number <= 100
        ),
        "atmospheric_pressure_hpa": (
            lambda number: 300 <= number <= 1100
        ),
        "wind_speed_ms": (
            lambda number: number >= 0
        ),
        "wind_direction_degree": (
            lambda number: 0 <= number <= 360
        ),
        "rain_mm": (
            lambda number: number >= 0
        ),
        "solar_radiation_wm2": (
            lambda number: number >= 0
        ),
        "illumination_klux": (
            lambda number: number >= 0
        ),
        "sunshine_duration_h": (
            lambda number: 0 <= number <= 24
        ),
        "dew_point_temperature_c": (
            lambda number: -100 <= number <= 70
        ),
        "et0_mm": (
            lambda number: number >= 0
        ),
    }

    validator = validators.get(field)

    if validator is None:
        return True

    return validator(value)

def build_agro_analytics(readings):
    """
    Construye estadísticas para el dashboard agrícola.

    readings debe venir ordenado cronológicamente.
    """

    enriched_readings = []
    daily_buckets = defaultdict(
        lambda: {
            "air_temperature": [],
            "air_humidity": [],
            "soil_moisture": [],
            "soil_temperature": [],
            "vpd": [],
            "solar_radiation": [],
            "wind_speed": [],
            "rain": [],
            "et0": [],
        }
    )

    wind_data = {
        sector: {
            "count": 0,
            "speeds": [],
        }
        for sector in WIND_SECTORS
    }

    timestamps = []

    missing_values = 0
    field_present_counts = {
        field: 0
        for field in SENSOR_FIELDS
    }

    total_readings = len(readings)

    for original_reading in readings:
        reading = dict(original_reading)

        timestamp = (
            reading.get("event_timestamp")
            or reading.get("received_at")
        )

        local_timestamp = None

        if timestamp:
            if timezone.is_aware(timestamp):
                local_timestamp = timezone.localtime(
                    timestamp
                )
            else:
                local_timestamp = timestamp

            timestamps.append(timestamp)

        temperature = safe_number(
            reading.get("air_temperature_c")
        )

        humidity = safe_number(
            reading.get("air_humidity_percent")
        )

        soil_moisture = safe_number(
            reading.get(
                "sensor_2_soil_moisture_percent"
            )
        )

        soil_temperature = safe_number(
            reading.get(
                "sensor_2_soil_temperature_c"
            )
        )

        solar_radiation = safe_number(
            reading.get("solar_radiation_wm2")
        )

        wind_speed = safe_number(
            reading.get("wind_speed_ms")
        )

        rain = safe_number(
            reading.get("rain_mm")
        )

        et0 = safe_number(
            reading.get("et0_mm")
        )

        vpd = calculate_vpd_kpa(
            temperature,
            humidity,
        )

        reading["vpd_kpa"] = round_value(
            vpd,
            3,
        )

        reading["local_timestamp"] = (
            local_timestamp.isoformat()
            if local_timestamp
            else None
        )

        if local_timestamp:
            date_key = (
                local_timestamp
                .date()
                .isoformat()
            )

            bucket = daily_buckets[date_key]

            bucket["air_temperature"].append(
                temperature
            )

            bucket["air_humidity"].append(
                humidity
            )

            bucket["soil_moisture"].append(
                soil_moisture
            )

            bucket["soil_temperature"].append(
                soil_temperature
            )

            bucket["vpd"].append(vpd)

            bucket["solar_radiation"].append(
                solar_radiation
            )

            bucket["wind_speed"].append(
                wind_speed
            )

            bucket["rain"].append(rain)
            bucket["et0"].append(et0)

        wind_sector = get_wind_sector(
            reading.get(
                "wind_direction_degree"
            )
        )

        if wind_sector:
            wind_data[wind_sector]["count"] += 1

            if wind_speed is not None:
                wind_data[wind_sector][
                    "speeds"
                ].append(wind_speed)

        for field in SENSOR_FIELDS:
            value = safe_number(
                reading.get(field)
            )

            if value is None:
                continue

            field_present_counts[field] += 1

        enriched_readings.append(reading)

    daily_summary = []

    for date_key in sorted(daily_buckets):
        bucket = daily_buckets[date_key]

        # Se usa el máximo diario porque lluvia, ET0 y
        # brillo solar parecen venir como acumulados diarios.
        # Esto debe confirmarse con el fabricante.
        rain_reported = maximum(
            bucket["rain"]
        )

        et0_reported = maximum(
            bucket["et0"]
        )

        daily_summary.append(
            {
                "date": date_key,

                "air_temperature_min": round_value(
                    minimum(
                        bucket["air_temperature"]
                    )
                ),

                "air_temperature_avg": round_value(
                    average(
                        bucket["air_temperature"]
                    )
                ),

                "air_temperature_max": round_value(
                    maximum(
                        bucket["air_temperature"]
                    )
                ),

                "air_humidity_avg": round_value(
                    average(
                        bucket["air_humidity"]
                    )
                ),

                "soil_moisture_min": round_value(
                    minimum(
                        bucket["soil_moisture"]
                    )
                ),

                "soil_moisture_avg": round_value(
                    average(
                        bucket["soil_moisture"]
                    )
                ),

                "soil_moisture_max": round_value(
                    maximum(
                        bucket["soil_moisture"]
                    )
                ),

                "soil_temperature_avg": round_value(
                    average(
                        bucket["soil_temperature"]
                    )
                ),

                "vpd_avg": round_value(
                    average(bucket["vpd"]),
                    3,
                ),

                "vpd_max": round_value(
                    maximum(bucket["vpd"]),
                    3,
                ),

                "solar_radiation_avg": round_value(
                    average(
                        bucket["solar_radiation"]
                    )
                ),

                "wind_speed_avg": round_value(
                    average(
                        bucket["wind_speed"]
                    )
                ),

                "rain_reported": round_value(
                    rain_reported
                ),

                "et0_reported": round_value(
                    et0_reported
                ),

                "water_balance_proxy": (
                    round_value(
                        rain_reported
                        - et0_reported
                    )
                    if (
                        rain_reported is not None
                        and et0_reported is not None
                    )
                    else None
                ),
            }
        )

    wind_rose = []

    for sector in WIND_SECTORS:
        values = wind_data[sector]

        wind_rose.append(
            {
                "sector": sector,
                "count": values["count"],
                "average_speed": round_value(
                    average(values["speeds"])
                ),
            }
        )

    timestamps = sorted(
        set(timestamps)
    )

    median_interval_minutes = None
    completeness_percent = None
    latest_age_minutes = None
    station_status = "Sin datos"

    if timestamps:
        latest_timestamp = timestamps[-1]

        latest_age_minutes = (
            timezone.now() - latest_timestamp
        ).total_seconds() / 60

        latest_age_minutes = round(
            max(latest_age_minutes, 0),
            1,
        )

        station_status = "Actualizada"

    if len(timestamps) >= 2:
        intervals = []

        for previous, current in zip(
            timestamps,
            timestamps[1:],
        ):
            interval_minutes = (
                current - previous
            ).total_seconds() / 60

            if interval_minutes > 0:
                intervals.append(
                    interval_minutes
                )

        if intervals:
            median_interval_minutes = round(
                median(intervals),
                1,
            )

            total_period_minutes = (
                timestamps[-1]
                - timestamps[0]
            ).total_seconds() / 60

            expected_readings = (
                total_period_minutes
                / median_interval_minutes
            ) + 1

            completeness_percent = round(
                min(
                    100,
                    (
                        len(timestamps)
                        / expected_readings
                    ) * 100,
                ),
                1,
            )

            stale_limit = max(
                median_interval_minutes * 3,
                15,
            )

            if (
                latest_age_minutes is not None
                and latest_age_minutes
                > stale_limit
            ):
                station_status = (
                    "Sin actualización reciente"
                )

    # Solo se evalúan variables que tuvieron al menos
    # un valor en el período (evita penalizar sensores
    # inactivos como S1 si aún no reportan).
    active_fields = [
        field
        for field, count in field_present_counts.items()
        if count > 0
    ]

    total_expected_values = (
        total_readings * len(active_fields)
    )

    present_values = sum(
        field_present_counts[field]
        for field in active_fields
    )

    missing_values = (
        total_expected_values - present_values
    )

    data_integrity_percent = (
        round(
            (
                present_values
                / total_expected_values
            ) * 100,
            1,
        )
        if total_expected_values
        else 0
    )

    soil_moisture_values = [
        safe_number(
            reading.get(
                "sensor_2_soil_moisture_percent"
            )
        )
        for reading in enriched_readings
    ]

    soil_moisture_values = [
        value
        for value in soil_moisture_values
        if value is not None
    ]

    soil_moisture_change = None

    if len(soil_moisture_values) >= 2:
        soil_moisture_change = round(
            soil_moisture_values[-1]
            - soil_moisture_values[0],
            2,
        )

    latest_reading = (
        enriched_readings[-1]
        if enriched_readings
        else None
    )

    summary = {
        "station_status": station_status,
        "latest_age_minutes": latest_age_minutes,
        "median_interval_minutes": (
            median_interval_minutes
        ),
        "completeness_percent": (
            completeness_percent
        ),
        "data_integrity_percent": (
            data_integrity_percent
        ),
        "missing_values": missing_values,
        "total_records": total_readings,
        "soil_moisture_change": (
            soil_moisture_change
        ),
        "latest_vpd_kpa": (
            latest_reading.get("vpd_kpa")
            if latest_reading
            else None
        ),
    }

    return {
        "summary": summary,
        "daily": daily_summary,
        "wind_rose": wind_rose,
        "readings": enriched_readings,
    }

def get_history_range(request):
    """
    Obtiene el período solicitado.

    range=7       Últimos 7 días
    range=15      Últimos 15 días
    range=30      Últimos 30 días
    range=custom  Fechas personalizadas
    """

    range_key = request.GET.get("range", "7")
    today = timezone.localdate()

    if range_key == "custom":
        date_from = parse_date(request.GET.get("date_from", ""))
        date_to = parse_date(request.GET.get("date_to", ""))

        if not date_from or not date_to or date_from > date_to:
            range_key = "7"
            date_to = today
            date_from = today - timedelta(days=6)
    else:
        allowed_ranges = {
            "7": 7,
            "15": 15,
            "30": 30,
        }

        days = allowed_ranges.get(range_key, 7)
        range_key = str(days)

        date_to = today
        date_from = today - timedelta(days=days - 1)

    current_timezone = timezone.get_current_timezone()

    start_datetime = timezone.make_aware(
        datetime.combine(date_from, time.min),
        current_timezone,
    )

    # El límite superior es exclusivo.
    end_datetime = timezone.make_aware(
        datetime.combine(date_to + timedelta(days=1), time.min),
        current_timezone,
    )

    return {
        "range_key": range_key,
        "date_from": date_from,
        "date_to": date_to,
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
    }


def export_sensor_history(queryset):
    """
    Descarga el histórico filtrado en formato CSV compatible con Excel.
    """

    response = HttpResponse(
        content_type="text/csv; charset=utf-8",
    )

    filename = f"historico_sensores_{timezone.localdate()}.csv"

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    # BOM para que Excel reconozca correctamente tildes y ñ.
    response.write("\ufeff")

    writer = csv.writer(response)

    headers = [
        "Fecha del evento",
        "Fecha de recepción",
        "Estación",
    ]

    for sensor in SENSOR_DEFINITIONS:
        label = sensor["label"]
        unit = sensor["unit"]

        headers.append(
            f"{label} ({unit})" if unit else label
        )

    writer.writerow(headers)

    rows = queryset.values(
        "event_timestamp",
        "received_at",
        "device_id",
        *SENSOR_FIELDS,
    )

    for reading in rows:
        event_timestamp = reading["event_timestamp"]
        received_at = reading["received_at"]

        if event_timestamp:
            event_timestamp = timezone.localtime(
                event_timestamp
            ).strftime("%Y-%m-%d %H:%M:%S")
        else:
            event_timestamp = ""

        if received_at:
            received_at = timezone.localtime(
                received_at
            ).strftime("%Y-%m-%d %H:%M:%S")
        else:
            received_at = ""

        row = [
            event_timestamp,
            received_at,
            reading["device_id"],
        ]

        row.extend(
            reading[field]
            for field in SENSOR_FIELDS
        )

        writer.writerow(row)

    return response


def actualizar_control_data(request):
    if request.method == 'POST':
        estado_bomba1 = request.POST.get('estadoBomba1', '0')  # Obtiene el estado de la bomba1
        estado_bomba2 = request.POST.get('estadoBomba2', '0')  # Obtiene el estado de la bomba1
        print("ESTADO BOMBA 1: ", estado_bomba1)
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data_insert = {"bomba1_state": estado_bomba1,
                       "bombas2_state": estado_bomba2,}
        # Aquí insertas una nueva fila en tu tabla ControlData
        control_data_insert = ControlData.objects.create(
            cliente= 'Juan Ochoa',  # Aquí debes poner el valor que corresponda
            fecha= f'{fecha}',  # Aquí se inserta la fecha y hora actual
            control_data= f'{data_insert}' # Aquí se inserta el objeto JSON
        )
        messages.success(request, 'Control actualizado correctamente')  # Aquí creas el mensaje
        return JsonResponse({'status': 'success'})
    
def home(request):
    users = data.objects.all()
    return render(request, "home.html", {"users": users})

def enviar_mail(request):
    if request.method == 'POST':
        tipo = request.POST.get('tipo')
        cliente = request.POST.get('cliente')
        descripcion = request.POST.get('descripcion')

        fecha = str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # Persistir registro de soporte
        Support.objects.create(
            estado=(tipo or 'Solicitud'),
            cliente=(cliente or 'N/D'),
            support_information=str(descripcion or ''),
            fecha=fecha,
        )

        msg = 'Tu solicitud fue registrada correctamente.'
        return render(request, "support.html", {'messages': msg})
    # GET: mostrar formulario vacío
    return render(request, "support.html")

def get_data_sensor(request):
    if request.method == 'POST':
        print("POST request received")
        db_informations = SensorData.objects.values('DB_information')
        print("DB_information: ", db_informations)
        db_informations = [{"Luz_ultravioleta" : "20", "Presion_barometrica" : "30", "Luminosidad" : "40", "Lluvia" : "NO", "temperatura_aire" : "60", "Humedad_aire" : "70"}]
        print("DB_information: ", db_informations)
        return render(request, 's2.html', {"data": list(db_informations)})

def login(request):
    print("Función login_validate llamada")
    if request.method == 'POST':
        print("Método POST detectado")
        user_id = request.POST.get('user_id').strip()  # Elimina espacios en blanco
        password = request.POST.get('clave').strip()  # Elimina espacios en blanco
        print(f"user_id recibido: {user_id}, password recibida: {password}")
        try:
            print("=============")
            user = data.objects.get(id=user_id)
            # Convierte la clave a str antes de comparar, si es necesario
            if str(user.clave) == password:
                print("La contraseña es correcta, redirigiendo...")
                return render(request, "grid.html")
            else:
                print("La contraseña no coincide, mostrando mensaje de error")
                messages.error(request, 'Contraseña incorrecta')
        except data.DoesNotExist:
            print("El usuario no existe, mostrando mensaje de error")
            messages.error(request, 'El usuario no existe')
    
    print("Re-renderizando el formulario con la lista de usuarios")
    users = data.objects.all()
    return render(request, "home.html", {'users': users})


def s1(request):
    return render(request, "s1.html")

def s2(request):
    selected_device = request.GET.get(
        "device_id",
        "",
    ).strip()

    history_range = get_history_range(request)
    force_refresh = request.GET.get("refresh") == "1"

    dashboard_ttl = getattr(
        settings,
        "TELEMETRY_DASHBOARD_CACHE_TTL",
        120,
    )
    max_chart_points = getattr(
        settings,
        "TELEMETRY_MAX_CHART_POINTS",
        720,
    )
    max_table_rows = getattr(
        settings,
        "TELEMETRY_MAX_TABLE_ROWS",
        200,
    )

    try:
        devices = get_telemetry_devices(
            force_refresh=force_refresh
        )

        if not selected_device:
            selected_device = (
                get_latest_device_id(
                    force_refresh=force_refresh
                )
                or ""
            )

        cache_key = build_dashboard_cache_key(
            selected_device or "none",
            history_range["date_from"].isoformat(),
            history_range["date_to"].isoformat(),
            history_range["range_key"],
        )

        cached_payload = None

        if not force_refresh:
            cached_payload = cache.get(cache_key)

        if cached_payload is not None:
            context = {
                **cached_payload,
                "devices": devices,
                "selected_device": selected_device,
                "selected_range": history_range[
                    "range_key"
                ],
                "date_from": history_range[
                    "date_from"
                ].isoformat(),
                "date_to": history_range[
                    "date_to"
                ].isoformat(),
                "sensor_fields": SENSOR_FIELDS,
                "sensor_definitions": (
                    SENSOR_DEFINITIONS
                ),
                "database_error": False,
                "from_cache": True,
            }

            return render(
                request,
                "s2.html",
                context,
            )

        readings = telemetry_queryset()

        if selected_device:
            readings = readings.filter(
                device_id=selected_device
            )

        latest_reading = (
            readings
            .only(
                "device_id",
                "event_timestamp",
                "received_at",
                *SENSOR_FIELDS,
            )
            .order_by("-received_at")
            .first()
        )

        history_queryset = (
            readings
            .filter(
                received_at__gte=history_range[
                    "start_datetime"
                ],
                received_at__lt=history_range[
                    "end_datetime"
                ],
            )
            .order_by("received_at")
        )

        # Descarga exactamente los datos filtrados.
        if request.GET.get("export") == "csv":
            return export_sensor_history(
                history_queryset
            )

        history_readings = list(
            history_queryset.values(
                "id",
                "device_id",
                "event_timestamp",
                "received_at",
                *SENSOR_FIELDS,
            )
        )

        dashboard_analytics = build_agro_analytics(
            history_readings
        )

        # Analytics completo en backend; al navegador
        # solo resumen + serie reducida (sin duplicar readings).
        chart_readings = downsample_readings(
            dashboard_analytics["readings"],
            max_chart_points,
        )

        # La tabla solo necesita las lecturas más recientes.
        table_readings = list(
            reversed(chart_readings)
        )[:max_table_rows]

        public_analytics = {
            "summary": dashboard_analytics[
                "summary"
            ],
            "daily": dashboard_analytics["daily"],
            "wind_rose": dashboard_analytics[
                "wind_rose"
            ],
        }

        latest_sensor_data = {}
        latest_metadata = None

        if latest_reading:
            latest_sensor_data = {
                field: getattr(
                    latest_reading,
                    field,
                )
                for field in SENSOR_FIELDS
            }

            latest_metadata = {
                "device_id": latest_reading.device_id,
                "event_timestamp": (
                    latest_reading.event_timestamp
                ),
                "received_at": (
                    latest_reading.received_at
                ),
            }

        cache_payload = {
            "latest_metadata": latest_metadata,
            "latest_sensor_data": latest_sensor_data,
            "history_readings": chart_readings,
            "table_readings": table_readings,
            "dashboard_analytics": public_analytics,
            "total_records": (
                dashboard_analytics["summary"].get(
                    "total_records",
                    len(history_readings),
                )
            ),
        }

        cache.set(
            cache_key,
            cache_payload,
            dashboard_ttl,
        )

        context = {
            "devices": devices,
            "selected_device": selected_device,
            "selected_range": history_range[
                "range_key"
            ],
            "date_from": history_range[
                "date_from"
            ].isoformat(),
            "date_to": history_range[
                "date_to"
            ].isoformat(),
            "latest_reading": latest_reading,
            "latest_metadata": latest_metadata,
            "latest_sensor_data": latest_sensor_data,
            "history_readings": chart_readings,
            "table_readings": table_readings,
            "total_records": cache_payload[
                "total_records"
            ],
            "sensor_fields": SENSOR_FIELDS,
            "sensor_definitions": SENSOR_DEFINITIONS,
            "dashboard_analytics": public_analytics,
            "database_error": False,
            "from_cache": False,
        }

    except DatabaseError:
        logger.exception(
            "No fue posible consultar la base de datos de telemetría"
        )

        context = {
            "devices": [],
            "selected_device": selected_device,
            "selected_range": history_range[
                "range_key"
            ],
            "date_from": history_range[
                "date_from"
            ].isoformat(),
            "date_to": history_range[
                "date_to"
            ].isoformat(),
            "latest_reading": None,
            "latest_metadata": None,
            "latest_sensor_data": {},
            "history_readings": [],
            "table_readings": [],
            "total_records": 0,
            "sensor_fields": SENSOR_FIELDS,
            "sensor_definitions": SENSOR_DEFINITIONS,
            "database_error": True,
            "dashboard_analytics": {
                "summary": {},
                "daily": [],
                "wind_rose": [],
            },
            "from_cache": False,
        }

    return render(
        request,
        "s2.html",
        context,
    )

def s3(request):
    return render(request, "s3.html")

def inicio(request):
    return render(request, "grid.html")

def support(request):
    return render(request, "support.html")

def yolov5(request):
    return render(request, "yolov5.html")
def ia(request):
    return render(request, "ia.html")
def detector(request):
    return render(request, "detector.html")

def reported(request):
    # Dashboard demo de cultivo y animales
    return render(request, "reported.html")

def nvid(request):
    # Vista para análisis NVID/NDVI con imágenes de drones
    return render(request, "nvid.html")

def drones(request):
    # Módulo de planificación y supervisión de drones y tareas
    return render(request, "drones.html")


#import google.generativeai as genai
#
## Create your views here.
## add here to your generated API key
#genai.configure(api_key="AIzaSyDDURhIdmkTmkxvPKTnya0kg63hGStcSkk")
#from django.views.decorators.csrf import csrf_exempt


def _demo_response(user_text: str) -> str:
    """Genera una respuesta de demostración sobre cultivo y animales."""
    if not user_text:
        return (
            "Hola, soy tu asistente agro. Puedo hablar sobre tu cultivo, "
            "riego, clima, plagas y también sobre manejo de animales. ¿Qué te gustaría saber?"
        )

    text = user_text.lower()
    # Reglas básicas por palabras clave
    if any(k in text for k in ["riego", "regar", "humedad suelo", "goteo"]):
        return (
            "Para el riego: si la humedad del suelo está por debajo de 40%, "
            "recomiendo activar 15–20 min de goteo y reevaluar. Evita regar en horas de alta evaporación (12–15 h)."
        )
    if any(k in text for k in ["temperatura", "calor", "frío", "frio"]):
        return (
            "La temperatura óptima depende del cultivo; en general, 22–26 °C para hortalizas. "
            "Si supera 30 °C, mejora la ventilación y valora sombreo 30–40%."
        )
    if any(k in text for k in ["plaga", "plagas", "enfermedad", "trips", "pulgón", "pulgon"]):
        return (
            "Monitorea hojas jóvenes y envés 2–3 veces por semana. "
            "Implementa control integrado: trampas cromáticas, liberación de benéficos y, si es necesario, biocontrol selectivo."
        )
    if any(k in text for k in ["fertiliz", "nutriente", "nitrógeno", "nitrogeno", "npk", "abon"]):
        return (
            "Ajusta NPK según etapa: crecimiento vegetativo (más N), floración/engorde (más K). "
            "Mantén pH suelo 6.0–6.8 para disponibilidad de nutrientes."
        )
    if any(k in text for k in ["ganado", "vaca", "vacas", "bovino", "pollo", "pollos", "aves", "cerdo", "cerdos"]):
        return (
            "Para animales: revisa agua limpia y sombra. En bovinos, oferta 8–10% de MS del peso vivo en pastoreo; "
            "en aves, vigila densidad y ventilación para evitar estrés por calor."
        )
    if any(k in text for k in ["lluvia", "clima", "pronóstico", "pronostico", "uv", "radiación", "radiacion"]):
        return (
            "Considera el clima: si se esperan lluvias, reduce riego previo. "
            "Con radiación UV alta, usa sombreo parcial para evitar estrés lumínico."
        )
    if any(k in text for k in ["hola", "buenos", "buenas", "saludo"]):
        return "¡Hola! ¿En qué te ayudo con tu cultivo o animales hoy?"

    # Respuesta genérica
    return (
        "Puedo ayudarte con riego, clima, plagas, fertilización y manejo de animales. "
        "Dime el tema y doy una recomendación práctica."
    )


def chat(request):
    # GET: renderiza la página del chat (UI). POST: responde JSON para el chat.
    if request.method == 'POST':
        # Admite tanto formulario como JSON
        user_text = request.POST.get('user_text')
        body = None
        if not user_text:
            try:
                body = json.loads(request.body.decode('utf-8') or '{}')
            except Exception:
                body = None
        message = user_text or (body.get('message') if isinstance(body, dict) else None)

        # Si no hay mensaje (por ejemplo, POST desde el grid), renderiza la página
        if not message:
            return render(request, 'chat.html')

        reply = _demo_response(message)
        return JsonResponse({'ok': True, 'reply': reply})

    return render(request, 'chat.html')

def cercas(request):
    lote = request.GET.get('lote', 'A').upper()
    if lote not in ("A", "B"):
        lote = "A"
    return render(request, "fences.html", {"lote": lote})
