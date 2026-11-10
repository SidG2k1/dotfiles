# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "aiohttp==3.14.5",
#   "rich==15.0.0",
# ]
# ///
"""Local OpenAI-compatible router for Baseten deployments."""

from __future__ import annotations

import argparse
import asyncio
import codecs
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import os
from pathlib import Path
import signal
import sys
import time
from typing import Mapping

import aiohttp
from aiohttp import web

from metrics import Prices, Traffic

BASETEN_CHAT_URL = "https://inference.baseten.co/v1/chat/completions"
DEFAULT_PORT = 4000
MAX_BODY_BYTES = 64 * 1024 * 1024
CONNECT_TIMEOUT_SECONDS = 10
IDLE_TIMEOUT_SECONDS = 15 * 60
RETRYABLE_STATUSES = {404, 408, 429}
CONFIG_KEYS = {
    "model_name",
    "cooldown_seconds",
    "default_reasoning_effort",
    "deployments",
}
DEPLOYMENT_KEYS = {
    "id",
    "model",
    "order",
    "input_cost_per_token",
    "output_cost_per_token",
    "cache_read_input_token_cost",
}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Deployment:
    id: str
    model: str
    order: int
    prices: Prices


@dataclass(frozen=True)
class Config:
    model_name: str
    cooldown_seconds: float
    default_reasoning_effort: str
    deployments: tuple[Deployment, ...]


class FailoverRouter:
    def __init__(self, config: Config, *, clock=time.monotonic):
        self.config = config
        self._clock = clock
        self._cooldowns = {}

    def available(self):
        now = self._clock()
        ready = tuple(
            deployment
            for deployment in self.config.deployments
            if self._cooldowns.get(deployment.id, 0) <= now
        )
        if ready:
            return ready, 0
        wait = max(1, int(min(self._cooldowns.values()) - now + 0.999))
        return (), wait

    def cool_down(self, deployment, retry_after=None):
        delay = max(self.config.cooldown_seconds, retry_after or 0)
        self._cooldowns[deployment.id] = self._clock() + delay


CONFIG_KEY = web.AppKey("config", Config)
TRAFFIC_KEY = web.AppKey("traffic", Traffic)
API_KEY = web.AppKey("api_key", str)
CHAT_URL_KEY = web.AppKey("chat_url", str)
ROUTER_KEY = web.AppKey("router", FailoverRouter)
SESSION_KEY = web.AppKey("session", aiohttp.ClientSession)


class SSEUsageParser:
    def __init__(self):
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._buffer = ""
        self._data = []
        self.usage = None

    def feed(self, chunk):
        self._buffer += self._decoder.decode(chunk)
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._line(line.rstrip("\r"))

    def finish(self):
        self._buffer += self._decoder.decode(b"", final=True)
        if self._buffer:
            self._line(self._buffer.rstrip("\r"))
            self._buffer = ""
        self._event()

    def _line(self, line):
        if not line:
            self._event()
            return
        if line.startswith("data:"):
            self._data.append(line[5:].lstrip(" "))

    def _event(self):
        if not self._data:
            return
        data = "\n".join(self._data)
        self._data.clear()
        if data == "[DONE]":
            return
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return
        if isinstance(payload, dict) and isinstance(payload.get("usage"), dict):
            self.usage = payload["usage"]


def load_config(path: Path) -> Config:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("configuration must be a JSON object")
    _check_keys(raw, CONFIG_KEYS, "configuration")

    model_name = _required_string(raw, "model_name", "configuration")
    cooldown = _required_number(raw, "cooldown_seconds", "configuration")
    if cooldown <= 0:
        raise ConfigError("cooldown_seconds must be positive")
    reasoning = _required_string(raw, "default_reasoning_effort", "configuration")

    items = raw.get("deployments")
    if not isinstance(items, list) or not items:
        raise ConfigError("deployments must be a non-empty array")

    deployments = []
    ids = set()
    orders = set()
    for index, item in enumerate(items):
        label = f"deployments[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{label} must be an object")
        _check_keys(item, DEPLOYMENT_KEYS, label)
        deployment_id = _required_string(item, "id", label)
        model = _required_string(item, "model", label)
        order = item.get("order")
        if not isinstance(order, int) or isinstance(order, bool) or order <= 0:
            raise ConfigError(f"{label}.order must be a positive integer")
        if deployment_id in ids:
            raise ConfigError(f"duplicate deployment id: {deployment_id}")
        if order in orders:
            raise ConfigError(f"duplicate deployment order: {order}")
        prices = Prices(
            input_per_token=_required_cost(item, "input_cost_per_token", label),
            output_per_token=_required_cost(item, "output_cost_per_token", label),
            cache_read_per_token=_required_cost(
                item, "cache_read_input_token_cost", label
            ),
        )
        ids.add(deployment_id)
        orders.add(order)
        deployments.append(Deployment(deployment_id, model, order, prices))

    deployments.sort(key=lambda deployment: deployment.order)
    return Config(model_name, cooldown, reasoning, tuple(deployments))


def _check_keys(value: Mapping, allowed: set[str], label: str):
    missing = allowed - value.keys()
    unknown = value.keys() - allowed
    if missing:
        raise ConfigError(f"{label} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise ConfigError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")


def _required_string(value: Mapping, key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ConfigError(f"{label}.{key} must be a non-empty string")
    return item.strip()


def _required_number(value: Mapping, key: str, label: str) -> float:
    item = value.get(key)
    if not isinstance(item, (int, float)) or isinstance(item, bool):
        raise ConfigError(f"{label}.{key} must be a number")
    return float(item)


def _required_cost(value: Mapping, key: str, label: str) -> float:
    item = _required_number(value, key, label)
    if item < 0:
        raise ConfigError(f"{label}.{key} must not be negative")
    return item


def create_app(
    config: Config,
    traffic,
    api_key: str,
    *,
    chat_url: str = BASETEN_CHAT_URL,
) -> web.Application:
    app = web.Application(client_max_size=MAX_BODY_BYTES)
    app[CONFIG_KEY] = config
    app[TRAFFIC_KEY] = traffic
    app[API_KEY] = api_key
    app[CHAT_URL_KEY] = chat_url
    app[ROUTER_KEY] = FailoverRouter(config)
    app.on_startup.append(_open_session)
    app.on_cleanup.append(_close_session)
    app.router.add_get("/healthz", health)
    app.router.add_post("/v1/chat/completions", chat_completions)
    return app


async def _open_session(app):
    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=CONNECT_TIMEOUT_SECONDS,
        sock_connect=CONNECT_TIMEOUT_SECONDS,
        sock_read=IDLE_TIMEOUT_SECONDS,
    )
    app[SESSION_KEY] = aiohttp.ClientSession(timeout=timeout)


async def _close_session(app):
    await app[SESSION_KEY].close()


async def health(request):
    return web.json_response({"status": "ok"})


async def chat_completions(request):
    traffic = request.app[TRAFFIC_KEY]
    try:
        body = await request.read()
    except web.HTTPRequestEntityTooLarge:
        return error_response(413, "request body is too large", "invalid_request_error")

    if len(body) > MAX_BODY_BYTES:
        return error_response(413, "request body is too large", "invalid_request_error")
    if not authorized(request):
        return error_response(
            401,
            "a non-empty bearer token is required",
            "authentication_error",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return error_response(
            400, "request body is not valid JSON", "invalid_request_error"
        )
    if not isinstance(payload, dict):
        return error_response(
            400, "request body must be a JSON object", "invalid_request_error"
        )
    requested_model = payload.get("model")
    if requested_model != request.app[CONFIG_KEY].model_name:
        return error_response(
            404,
            f"unknown model: {requested_model!r}",
            "invalid_request_error",
            code="model_not_found",
        )
    if not isinstance(payload.get("messages"), list):
        return error_response(400, "messages must be an array", "invalid_request_error")

    payload.setdefault(
        "reasoning_effort", request.app[CONFIG_KEY].default_reasoning_effort
    )
    stream = payload.get("stream") is True
    if stream:
        options = payload.get("stream_options")
        if options is None:
            payload["stream_options"] = {"include_usage": True}
        elif isinstance(options, dict) and "include_usage" not in options:
            options = dict(options)
            options["include_usage"] = True
            payload["stream_options"] = options

    if stream:
        return await proxy_stream(request, payload)
    return await proxy_json(request, payload)


def authorized(request):
    scheme, separator, token = request.headers.get("Authorization", "").partition(" ")
    return bool(separator and scheme.lower() == "bearer" and token.strip())


async def proxy_json(request, payload):
    app = request.app
    ready, wait = app[ROUTER_KEY].available()
    if not ready:
        traffic.note("router", "all deployments are cooling down", "503")
        return error_response(
            503,
            "all Baseten deployments are cooling down",
            "server_error",
            headers={"Retry-After": str(wait)},
        )

    last_response = None
    for deployment in ready:
        started = time.monotonic()
        try:
            async with app[SESSION_KEY].post(
                app[CHAT_URL_KEY],
                json={**payload, "model": deployment.model},
                headers=_upstream_headers(app[API_KEY], stream=False),
            ) as upstream:
                upstream_body = await upstream.read()
                elapsed = time.monotonic() - started
                if _retryable_status(upstream.status):
                    retry_after = _retry_after_seconds(
                        upstream.headers.get("Retry-After")
                    )
                    app[ROUTER_KEY].cool_down(deployment, retry_after)
                    app[TRAFFIC_KEY].record(
                        deployment.id,
                        ok=False,
                        status=upstream.status,
                        usage=None,
                        seconds=elapsed,
                        stream=False,
                        error=_upstream_error(upstream_body),
                    )
                    last_response = _response_parts(upstream, upstream_body)
                    continue

                usage = _usage_from_json(upstream_body)
                if upstream.status >= 400:
                    app[TRAFFIC_KEY].record(
                        deployment.id,
                        ok=False,
                        status=upstream.status,
                        usage=usage,
                        seconds=elapsed,
                        stream=False,
                        error=_upstream_error(upstream_body),
                    )
                else:
                    app[TRAFFIC_KEY].record(
                        deployment.id,
                        ok=True,
                        status=upstream.status,
                        usage=usage,
                        seconds=elapsed,
                        stream=False,
                    )
                return _relay_response(upstream, upstream_body)
        except asyncio.CancelledError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            app[ROUTER_KEY].cool_down(deployment)
            app[TRAFFIC_KEY].record(
                deployment.id,
                ok=False,
                status="ERR",
                usage=None,
                seconds=time.monotonic() - started,
                stream=False,
                error=exc,
            )

    if last_response is not None:
        status, body, content_type = last_response
        return web.Response(
            status=status, body=body, headers={"Content-Type": content_type}
        )
    return error_response(502, "all Baseten deployments failed", "server_error")


async def proxy_stream(request, payload):
    app = request.app
    ready, wait = app[ROUTER_KEY].available()
    if not ready:
        app[TRAFFIC_KEY].note("router", "all deployments are cooling down", "503")
        return error_response(
            503,
            "all Baseten deployments are cooling down",
            "server_error",
            headers={"Retry-After": str(wait)},
        )

    last_response = None
    for deployment in ready:
        started = time.monotonic()
        try:
            async with app[SESSION_KEY].post(
                app[CHAT_URL_KEY],
                json={**payload, "model": deployment.model},
                headers=_upstream_headers(app[API_KEY], stream=True),
            ) as upstream:
                if upstream.status >= 400:
                    upstream_body = await upstream.read()
                    elapsed = time.monotonic() - started
                    if _retryable_status(upstream.status):
                        retry_after = _retry_after_seconds(
                            upstream.headers.get("Retry-After")
                        )
                        app[ROUTER_KEY].cool_down(deployment, retry_after)
                        last_response = _response_parts(upstream, upstream_body)
                    app[TRAFFIC_KEY].record(
                        deployment.id,
                        ok=False,
                        status=upstream.status,
                        usage=None,
                        seconds=elapsed,
                        stream=True,
                        error=_upstream_error(upstream_body),
                    )
                    if not _retryable_status(upstream.status):
                        return _relay_response(upstream, upstream_body)
                    continue

                return await _relay_stream(request, deployment, upstream, started)
        except asyncio.CancelledError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            app[ROUTER_KEY].cool_down(deployment)
            app[TRAFFIC_KEY].record(
                deployment.id,
                ok=False,
                status="ERR",
                usage=None,
                seconds=time.monotonic() - started,
                stream=True,
                error=exc,
            )

    if last_response is not None:
        status, body, content_type = last_response
        return web.Response(
            status=status, body=body, headers={"Content-Type": content_type}
        )
    return error_response(502, "all Baseten deployments failed", "server_error")


class ClientDisconnected(Exception):
    pass


async def _await_client(operation):
    try:
        return await operation
    except (ConnectionResetError, BrokenPipeError) as exc:
        raise ClientDisconnected from exc


async def _relay_stream(request, deployment, upstream, started):
    downstream = web.StreamResponse(
        status=upstream.status,
        headers={
            "Content-Type": upstream.headers.get("Content-Type", "text/event-stream"),
            "Cache-Control": "no-cache",
        },
    )
    parser = SSEUsageParser()
    try:
        await _await_client(downstream.prepare(request))
        async for chunk in upstream.content.iter_any():
            parser.feed(chunk)
            await _await_client(downstream.write(chunk))
        parser.finish()
        await _await_client(downstream.write_eof())
    except (ClientDisconnected, asyncio.CancelledError) as exc:
        request.app[TRAFFIC_KEY].record(
            deployment.id,
            ok=False,
            status="CANCEL",
            usage=parser.usage,
            seconds=time.monotonic() - started,
            stream=True,
            error="client disconnected",
            cancelled=True,
        )
        if isinstance(exc, asyncio.CancelledError):
            raise
        return downstream
    except Exception as exc:
        request.app[TRAFFIC_KEY].record(
            deployment.id,
            ok=False,
            status="ERR",
            usage=parser.usage,
            seconds=time.monotonic() - started,
            stream=True,
            error=exc,
        )
        return downstream

    request.app[TRAFFIC_KEY].record(
        deployment.id,
        ok=True,
        status=upstream.status,
        usage=parser.usage,
        seconds=time.monotonic() - started,
        stream=True,
    )
    return downstream


def _retryable_status(status):
    return status in RETRYABLE_STATUSES or 500 <= status < 600


def _retry_after_seconds(value):
    if not value:
        return None
    try:
        return max(0, int(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0, int((when - datetime.now(timezone.utc)).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


def _upstream_headers(api_key, *, stream):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
    }


def _response_parts(upstream, body):
    return (
        upstream.status,
        body,
        upstream.headers.get("Content-Type", "application/json"),
    )


def _relay_response(upstream, body):
    return web.Response(
        status=upstream.status,
        body=body,
        headers={
            "Content-Type": upstream.headers.get("Content-Type", "application/json")
        },
    )


def _usage_from_json(body):
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload.get("usage") if isinstance(payload, dict) else None


def _upstream_error(body):
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body.decode("utf-8", "replace")
    if isinstance(payload, dict):
        error = payload.get("error", payload)
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        if isinstance(error, str):
            return error
    return "request failed"


def error_response(status, message, error_type, *, code=None, headers=None):
    payload = {"error": {"message": message, "type": error_type}}
    if code:
        payload["error"]["code"] = code
    return web.json_response(payload, status=status, headers=headers)


def config_path():
    root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(root) / "baseten-router" / "config.json"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="baseten-router")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="resolve and validate the Python runtime, then exit",
    )
    return parser.parse_args(argv)


async def serve(config, api_key):
    traffic = Traffic(
        {deployment.id: deployment.prices for deployment in config.deployments},
        secrets=(api_key,),
    )
    app = create_app(config, traffic, api_key)
    runner = web.AppRunner(app, access_log=None)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)

    port = int(os.environ.get("BASETEN_ROUTER_PORT", DEFAULT_PORT))
    try:
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        print(f"baseten-router on 127.0.0.1:{port}", file=sys.stderr)
        for deployment in config.deployments:
            print(
                f"  order {deployment.order:<2} {deployment.id:<34} {deployment.model}",
                file=sys.stderr,
            )
        await stop.wait()
    finally:
        await runner.cleanup()
        traffic.close()


def main(argv=None):
    args = parse_args(argv)
    if args.setup:
        print("baseten-router runtime ready")
        return 0

    api_key = os.environ.get("BASETEN_API_KEY")
    if not api_key:
        print("baseten-router: BASETEN_API_KEY is not set", file=sys.stderr)
        return 1
    try:
        config = load_config(config_path())
    except ConfigError as exc:
        print(f"baseten-router: {exc}", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=os.environ.get("BASETEN_ROUTER_LOG", "INFO").upper(),
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(serve(config, api_key))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
