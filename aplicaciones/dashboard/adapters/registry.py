from __future__ import annotations

from django.db import connections

from aplicaciones.core.models import ClientDataSource

from .aranet import AranetAdapter
from .base import AdapterConfigurationError, SensorDataAdapter

ADAPTERS: dict[str, type[SensorDataAdapter]] = {
    ClientDataSource.Adapter.ARANET: AranetAdapter,
}


def get_adapter(data_source: ClientDataSource) -> SensorDataAdapter:
    if not data_source.is_active:
        raise AdapterConfigurationError("La fuente de datos está desactivada.")
    if data_source.database_alias not in connections.databases:
        raise AdapterConfigurationError(
            "La conexión del cliente no está declarada en el entorno de ejecución."
        )
    adapter_class = ADAPTERS.get(data_source.adapter_key)
    if adapter_class is None:
        raise AdapterConfigurationError("No existe un adaptador para esta fuente de datos.")
    return adapter_class(data_source.database_alias, data_source.settings)
