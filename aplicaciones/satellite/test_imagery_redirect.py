import httpx
from django.test import SimpleTestCase

from aplicaciones.satellite.eosda.client import EOSDAClient
from aplicaciones.satellite.eosda.imagery import check_visual_task


class EOSDAImageryRedirectTests(SimpleTestCase):
    def test_finished_task_accepts_303_and_uses_location_without_following(self):
        requests: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            self.assertEqual(request.headers["x-api-key"], "secret-key")
            return httpx.Response(
                303,
                headers={
                    "Location": "https://imagery.example.test/result/scene.png?signature=abc"
                },
            )

        transport = httpx.MockTransport(handler)
        with EOSDAClient(api_key="secret-key", transport=transport) as client:
            status = check_visual_task(client, "task-123")

        self.assertEqual(requests, ["https://api-connect.eos.com/api/gdw/api/task-123"])
        self.assertTrue(status.is_finished)
        self.assertEqual(status.status, "finished")
        self.assertEqual(
            status.image_url,
            "https://imagery.example.test/result/scene.png?signature=abc",
        )
        self.assertEqual(status.payload, {"status": "finished", "redirect": True})

    def test_finished_task_resolves_relative_location_against_eosda(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(303, headers={"Location": "/downloads/scene.png"})

        transport = httpx.MockTransport(handler)
        with EOSDAClient(api_key="secret-key", transport=transport) as client:
            status = check_visual_task(client, "task-456")

        self.assertEqual(status.image_url, "https://api-connect.eos.com/downloads/scene.png")
