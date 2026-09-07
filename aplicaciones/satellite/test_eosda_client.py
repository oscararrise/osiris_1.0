import httpx
from django.test import SimpleTestCase, override_settings

from aplicaciones.satellite.eosda.client import (
    EOSDAClient,
    EOSDAConfigurationError,
    EOSDARequestError,
)


class EOSDAClientTests(SimpleTestCase):
    def test_sends_api_key_header_and_parses_json(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["x-api-key"], "secret-key")
            self.assertEqual(str(request.url), "https://api-connect.eos.com/ping")
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(handler)
        with EOSDAClient(api_key="secret-key", transport=transport) as client:
            payload = client.request_json("GET", "/ping")

        self.assertEqual(payload, {"ok": True})

    def test_retries_safe_get_after_transient_server_error(self):
        attempts = 0
        delays = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(503)
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(handler)
        with EOSDAClient(
            api_key="secret-key",
            transport=transport,
            sleep=delays.append,
        ) as client:
            payload = client.request_json("GET", "/status")

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(attempts, 2)
        self.assertEqual(delays, [0.25])

    def test_does_not_retry_post_after_server_error(self):
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(503)

        transport = httpx.MockTransport(handler)
        with EOSDAClient(api_key="secret-key", transport=transport) as client:
            with self.assertRaises(EOSDARequestError) as error_context:
                client.request_json("POST", "/field-management", json={"type": "Feature"})

        self.assertEqual(attempts, 1)
        self.assertEqual(error_context.exception.status_code, 503)
        self.assertFalse(error_context.exception.retryable)

    @override_settings(EOSDA_API_KEY="")
    def test_requires_api_key_when_not_explicitly_provided(self):
        with self.assertRaises(EOSDAConfigurationError):
            EOSDAClient()

    def test_rate_limit_error_is_clear_and_not_immediately_retried(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429)

        transport = httpx.MockTransport(handler)
        with EOSDAClient(api_key="secret-key", transport=transport) as client:
            with self.assertRaises(EOSDARequestError) as error_context:
                client.request_json("GET", "/statistics")

        self.assertEqual(error_context.exception.status_code, 429)
        self.assertEqual(str(error_context.exception), "EOSDA rate limit exceeded.")
        self.assertFalse(error_context.exception.retryable)
