"""Small, defensive HTTP client for EOSDA API Connect."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx
from django.conf import settings

_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_AUTO_RETRY_STATUS_CODES = frozenset({502, 503, 504})
_RETRY_DELAYS_SECONDS = (0.25, 0.75)


class EOSDAError(Exception):
    """Base exception for EOSDA integration failures."""


class EOSDAConfigurationError(EOSDAError):
    """Raised when required EOSDA configuration is missing or invalid."""


class EOSDARequestError(EOSDAError):
    """Raised when EOSDA rejects a request or cannot be reached."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class EOSDAClient:
    """Synchronous EOSDA API client with safe retries for idempotent requests."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        resolved_api_key = api_key if api_key is not None else settings.EOSDA_API_KEY
        resolved_api_key = resolved_api_key.strip()
        if not resolved_api_key:
            raise EOSDAConfigurationError(
                "EOSDA_API_KEY is not configured. Set it in the server environment."
            )

        resolved_base_url = base_url if base_url is not None else settings.EOSDA_BASE_URL
        resolved_base_url = resolved_base_url.strip().rstrip("/")
        if not resolved_base_url:
            raise EOSDAConfigurationError("EOSDA_BASE_URL cannot be empty.")

        resolved_timeout = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else float(settings.EOSDA_TIMEOUT_SECONDS)
        )
        if resolved_timeout <= 0:
            raise EOSDAConfigurationError("EOSDA timeout must be greater than zero.")

        self._sleep = sleep
        self._client = httpx.Client(
            base_url=resolved_base_url,
            timeout=resolved_timeout,
            transport=transport,
            headers={
                "Accept": "application/json",
                "User-Agent": "osiris-satellite/1.0",
                "x-api-key": resolved_api_key,
            },
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""

        self._client.close()

    def __enter__(self) -> EOSDAClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
    ) -> httpx.Response:
        """Execute an EOSDA request and raise sanitized integration errors."""

        normalized_method = method.upper()
        can_auto_retry = normalized_method in _IDEMPOTENT_METHODS
        max_attempts = 1 + len(_RETRY_DELAYS_SECONDS) if can_auto_retry else 1

        for attempt in range(max_attempts):
            try:
                response = self._client.request(
                    normalized_method,
                    path,
                    params=params,
                    json=json,
                )
            except httpx.RequestError as exc:
                if can_auto_retry and attempt < max_attempts - 1:
                    self._sleep(_RETRY_DELAYS_SECONDS[attempt])
                    continue
                raise EOSDARequestError(
                    "EOSDA could not be reached.",
                    retryable=can_auto_retry,
                ) from exc

            if 200 <= response.status_code < 300:
                return response

            should_retry_status = response.status_code in _AUTO_RETRY_STATUS_CODES
            if can_auto_retry and should_retry_status and attempt < max_attempts - 1:
                self._sleep(_RETRY_DELAYS_SECONDS[attempt])
                continue

            raise self._request_error(
                response.status_code,
                retryable=can_auto_retry and should_retry_status,
            )

        raise EOSDARequestError("EOSDA request failed unexpectedly.")

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        """Execute a request expected to return JSON."""

        response = self.request(method, path, params=params, json=json)
        try:
            return response.json()
        except ValueError as exc:
            raise EOSDARequestError(
                "EOSDA returned an invalid JSON response.",
                status_code=response.status_code,
            ) from exc

    @staticmethod
    def _request_error(status_code: int, *, retryable: bool) -> EOSDARequestError:
        if status_code == 401:
            message = "EOSDA rejected the API key."
        elif status_code == 403:
            message = "EOSDA denied access to this resource."
        elif status_code == 429:
            message = "EOSDA rate limit exceeded."
        else:
            message = f"EOSDA request failed with HTTP {status_code}."
        return EOSDARequestError(
            message,
            status_code=status_code,
            retryable=retryable,
        )
