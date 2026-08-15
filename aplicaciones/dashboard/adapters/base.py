from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class AdapterError(RuntimeError):
    """Base class for safe, user-facing adapter failures."""


class AdapterConfigurationError(AdapterError):
    """The central configuration does not match a runtime connection."""


class SensorDataAdapter(ABC):
    def __init__(self, database_alias: str, options: dict[str, Any] | None = None):
        self.database_alias = database_alias
        self.options = options or {}

    @abstractmethod
    def list_sensors(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_metrics(self, sensor_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def latest_values(self, sensor_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def time_series(
        self,
        sensor_id: str,
        metric_id: str,
        probe_no: int,
        start: datetime,
        end: datetime,
        max_points: int,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def active_alarms(self, sensor_id: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError
