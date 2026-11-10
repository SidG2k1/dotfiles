import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parents[1]
ROUTER_DIR = ROOT / "lib/baseten-router"
sys.path.insert(0, str(ROUTER_DIR))
SPEC = importlib.util.spec_from_file_location(
    "baseten_router", ROUTER_DIR / "router.py"
)
router = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = router
SPEC.loader.exec_module(router)
import metrics as metrics_module


def prices():
    return router.Prices(0.000001, 0.000002, 0.0000001)


def deployment(name, order):
    return router.Deployment(name, f"model-{name}", order, prices())


def config():
    return router.Config(
        "baseten-router",
        60,
        "max",
        (deployment("primary", 1), deployment("secondary", 2)),
    )


class RecordingTraffic:
    def __init__(self):
        self.records = []
        self.notes = []

    def record(self, *args, **kwargs):
        self.records.append((args, kwargs))

    def note(self, *args, **kwargs):
        self.notes.append((args, kwargs))


class ConfigTests(unittest.TestCase):
    def test_loads_and_sorts_valid_configuration(self):
        raw = {
            "model_name": "baseten-router",
            "cooldown_seconds": 60,
            "default_reasoning_effort": "max",
            "deployments": [
                {
                    "id": "second",
                    "model": "model-second",
                    "order": 2,
                    "input_cost_per_token": 0.1,
                    "output_cost_per_token": 0.2,
                    "cache_read_input_token_cost": 0.01,
                },
                {
                    "id": "first",
                    "model": "model-first",
                    "order": 1,
                    "input_cost_per_token": 0.1,
                    "output_cost_per_token": 0.2,
                    "cache_read_input_token_cost": 0.01,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            loaded = router.load_config(path)
        self.assertEqual([item.id for item in loaded.deployments], ["first", "second"])

    def test_rejects_duplicate_orders(self):
        raw = {
            "model_name": "baseten-router",
            "cooldown_seconds": 60,
            "default_reasoning_effort": "max",
            "deployments": [
                {
                    "id": "one",
                    "model": "model-one",
                    "order": 1,
                    "input_cost_per_token": 0,
                    "output_cost_per_token": 0,
                    "cache_read_input_token_cost": 0,
                },
                {
                    "id": "two",
                    "model": "model-two",
                    "order": 1,
                    "input_cost_per_token": 0,
                    "output_cost_per_token": 0,
                    "cache_read_input_token_cost": 0,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(
                router.ConfigError, "duplicate deployment order"
            ):
                router.load_config(path)


class FailoverRouterTests(unittest.TestCase):
    def test_cooldown_skips_and_then_releases_a_deployment(self):
        now = [1000.0]
        failover = router.FailoverRouter(config(), clock=lambda: now[0])
        primary, secondary = config().deployments

        failover.cool_down(primary)
        ready, wait = failover.available()
        self.assertEqual(ready, (secondary,))
        self.assertEqual(wait, 0)

        now[0] += 61
        ready, _ = failover.available()
        self.assertEqual(ready, (primary, secondary))


class UsageTests(unittest.TestCase):
    def test_stream_usage_survives_split_events(self):
        parser = router.SSEUsageParser()
        for chunk in (
            b'data: {"choices":[{"delta":{"reasoning_',
            b'content":"think"}}]}\r\n\r\ndata: {"choices":[],"usa',
            b'ge":{"prompt_tokens":10,"completion_tokens":2,',
            b'"prompt_tokens_details":{"cached_tokens":3}}}\n\n',
            b"data: [DONE]\n\n",
        ):
            parser.feed(chunk)
        parser.finish()
        self.assertEqual(
            parser.usage,
            {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "prompt_tokens_details": {"cached_tokens": 3},
            },
        )

    def test_cost_discounts_cached_input(self):
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "prompt_tokens_details": {"cached_tokens": 40},
        }
        cost = metrics_module.calculate_cost(usage, prices())
        self.assertAlmostEqual(cost, 0.000084)

    def test_redaction_removes_keys_and_bearer_tokens(self):
        redacted = metrics_module.redact_text(
            "failed with secret-key and Authorization: Bearer local-proxy",
            ("secret-key",),
        )
        self.assertNotIn("secret-key", redacted)
        self.assertNotIn("local-proxy", redacted)


class ProxyTests(unittest.IsolatedAsyncioTestCase):
    async def start_proxy(self, respond, traffic=None):
        upstream = FakeUpstream(respond)
        await upstream.start()
        self.addAsyncCleanup(upstream.close)
        proxy = TestClient(
            TestServer(
                router.create_app(
                    config(),
                    traffic or RecordingTraffic(),
                    "upstream-key",
                    chat_url=upstream.url,
                )
            )
        )
        await proxy.start_server()
        self.addAsyncCleanup(proxy.close)
        return proxy, upstream

    async def test_non_streaming_uses_primary_and_defaults_reasoning(self):
        async def respond(payload, request):
            return web.json_response(
                {
                    "id": "response",
                    "choices": [],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                }
            )

        traffic = RecordingTraffic()
        proxy, upstream = await self.start_proxy(respond, traffic)
        response = await proxy.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer local-proxy"},
            json={
                "model": "baseten-router",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(
            [item["model"] for item in upstream.requests], ["model-primary"]
        )
        self.assertEqual(upstream.requests[0]["reasoning_effort"], "max")
        self.assertTrue(traffic.records[0][1]["ok"])

    async def test_placeholder_accepts_llm_dummy_key(self):
        async def respond(payload, request):
            return web.json_response({"choices": []})

        proxy, _ = await self.start_proxy(respond)
        response = await proxy.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer DUMMY_KEY"},
            json={"model": "baseten-router", "messages": []},
        )
        self.assertEqual(response.status, 200)

    async def test_retryable_failure_cools_primary(self):
        async def respond(payload, request):
            if payload["model"] == "model-primary":
                return web.json_response({"error": {"message": "busy"}}, status=429)
            return web.json_response(
                {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            )

        traffic = RecordingTraffic()
        proxy, upstream = await self.start_proxy(respond, traffic)
        headers = {"Authorization": "Bearer local-proxy"}
        body = {"model": "baseten-router", "messages": []}

        first = await proxy.post("/v1/chat/completions", headers=headers, json=body)
        second = await proxy.post("/v1/chat/completions", headers=headers, json=body)

        self.assertEqual(first.status, 200)
        self.assertEqual(second.status, 200)
        self.assertEqual(
            [item["model"] for item in upstream.requests],
            ["model-primary", "model-secondary", "model-secondary"],
        )

    async def test_request_error_does_not_fail_over(self):
        async def respond(payload, request):
            return web.json_response({"error": {"message": "bad request"}}, status=400)

        proxy, upstream = await self.start_proxy(respond)
        response = await proxy.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer local-proxy"},
            json={"model": "baseten-router", "messages": []},
        )

        self.assertEqual(response.status, 400)
        self.assertEqual(
            [item["model"] for item in upstream.requests], ["model-primary"]
        )

    async def test_streaming_response_is_relayed_with_usage(self):
        pieces = (
            b'data: {"choices":[{"delta":{"reasoning_content":"think"}}]}\n\n',
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{}"}}]}}]}\n\n',
            b'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":2}}\n\n',
            b"data: [DONE]\n\n",
        )

        async def respond(payload, request):
            response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await response.prepare(request)
            for piece in pieces:
                await response.write(piece)
            await response.write_eof()
            return response

        traffic = RecordingTraffic()
        proxy, _ = await self.start_proxy(respond, traffic)
        response = await proxy.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer local-proxy"},
            json={"model": "baseten-router", "messages": [], "stream": True},
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(await response.read(), b"".join(pieces))
        record = traffic.records[0][1]
        self.assertTrue(record["ok"])
        self.assertTrue(record["stream"])
        self.assertEqual(record["usage"]["prompt_tokens"], 10)


class FakeUpstream:
    def __init__(self, respond):
        self.respond = respond
        self.requests = []
        app = web.Application()
        app.router.add_post("/v1/chat/completions", self.handle)
        self.server = TestServer(app)
        self.url = None

    async def start(self):
        await self.server.start_server()
        self.url = str(self.server.make_url("/v1/chat/completions"))

    async def close(self):
        await self.server.close()

    async def handle(self, request):
        payload = await request.json()
        self.requests.append(payload)
        return await self.respond(payload, request)


if __name__ == "__main__":
    unittest.main()
