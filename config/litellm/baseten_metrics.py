"""Live traffic view for the local Baseten router.

Per-request log lines scroll past faster than they can be read, so this shows a
table per deployment that updates in place, plus a short feed of requests that
went wrong. Registered from baseten.yaml via litellm_settings.callbacks.

When stdout is not a terminal (piped or redirected), it falls back to printing
one plain line per request instead.
"""

import atexit
import copy
import logging
import os
import re
import sys
import threading
import time
from collections import Counter, deque
from datetime import datetime

from litellm._logging import redact_secrets
from litellm.integrations.custom_logger import CustomLogger

REFRESH_SECONDS = 1.0
KEEP_UNUSUAL = 5
RATE_WINDOW = 60.0

try:
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    from rich.text import Text
except ImportError:
    Console = None


def _human(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


class Bucket:
    def __init__(self):
        self.requests = 0
        self.errors = 0
        self.prompt = 0
        self.completion = 0
        self.cost = 0.0
        self.seconds = 0.0

    def add(self, prompt, completion, cost, seconds, ok):
        self.requests += 1
        self.errors += 0 if ok else 1
        self.prompt += prompt
        self.completion += completion
        self.cost += cost
        self.seconds += seconds


class WarningHandler(logging.Handler):
    """Forward litellm warnings into the unusual feed instead of the screen.

    Carries the same filters as litellm's own handler so secret redaction and
    correlation context still apply to records reaching this one.
    """

    def __init__(self, traffic, filters):
        super().__init__(level=logging.WARNING)
        self.traffic = traffic
        for f in filters:
            self.addFilter(f)

    def emit(self, record):
        try:
            message = record.getMessage()
            # LiteLLM strips custom pricing from shared backend registrations.
            if (
                record.levelno == logging.WARNING
                and record.name == "LiteLLM"
                and message.startswith("register_model: model=openai/")
                and "not in built-in cost map and no prefix/region variant matched; cache cost fields will default to 0." in message
            ):
                return
            self.traffic.note(record.name, message)
        except Exception:
            pass


class AccessFilter(logging.Filter):
    """Keep HTTP errors that may never reach a model callback."""

    def __init__(self, traffic):
        super().__init__()
        self.traffic = traffic

    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            _, method, path, _, status = record.args
            if int(status) >= 400:
                self.traffic.note("HTTP", f"{method} {path.partition('?')[0]}", str(status))
        return False


class Traffic:
    def __init__(self):
        self._lock = threading.Lock()
        self._rows = {}
        self._recent = deque()
        self._unusual = deque(maxlen=KEEP_UNUSUAL)
        self._live = None
        self._plain = True
        self._devnull = None
        self._saved_stdout = None
        self._uvicorn_streams = []
        self._start()

    # ---- output plumbing ---------------------------------------------------

    def _start(self):
        # Rich otherwise follows sys.stdout after it is redirected below.
        console = Console(file=sys.stdout) if Console is not None else None
        if console is None or not console.is_terminal or console.is_dumb_terminal:
            return

        import litellm._logging as ll

        self._saved_stdout = sys.stdout
        self._devnull = open(os.devnull, "w")
        self._log_handler = ll.handler
        self._log_stream = ll.handler.stream
        self._warning_handler = WarningHandler(self, ll.handler.filters)
        self._access_filter = AccessFilter(self)

        try:
            self._live = Live(
                console=console,
                get_renderable=self.render,
                refresh_per_second=1 / REFRESH_SECONDS,
                redirect_stdout=False,
            )
            self._live.start(refresh=True)
            for handler in logging.getLogger("uvicorn").handlers:
                if isinstance(handler, logging.StreamHandler):
                    self._uvicorn_streams.append((handler, handler.stream))
                    handler.setStream(sys.stderr)
            ll.handler.setStream(self._devnull)
            logging.getLogger("uvicorn.access").addFilter(self._access_filter)
            for name in ("LiteLLM", "LiteLLM Proxy", "LiteLLM Router"):
                logging.getLogger(name).addHandler(self._warning_handler)
            sys.stdout = self._devnull
            self._plain = False
            atexit.register(self._shutdown)
        except Exception as exc:
            self._shutdown()
            print(f"baseten-router: live display failed: {exc}", file=sys.stderr)

    def _shutdown(self):
        for handler, stream in self._uvicorn_streams:
            handler.setStream(stream)
        self._uvicorn_streams.clear()
        if self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None
        if self._saved_stdout is not None:
            sys.stdout = self._saved_stdout
            self._saved_stdout = None
        if self._devnull is not None:
            self._log_handler.setStream(self._log_stream)
            logging.getLogger("uvicorn.access").removeFilter(self._access_filter)
            for name in ("LiteLLM", "LiteLLM Proxy", "LiteLLM Router"):
                logging.getLogger(name).removeHandler(self._warning_handler)
            self._devnull.close()
            self._devnull = None
        self._plain = True

    # ---- recording ---------------------------------------------------------

    def note(self, source, message, status=""):
        message = " ".join(redact_secrets(str(message)).split())[:160]
        with self._lock:
            self._unusual.append((time.time(), source, status, message))

    def record(self, model_id, ok, status, prompt, completion, cost, seconds, stream, error=None):
        if error:
            error = " ".join(redact_secrets(str(error)).split())[:160]
        with self._lock:
            self._rows.setdefault(model_id, Bucket()).add(prompt, completion, cost, seconds, ok)
            now = time.monotonic()
            self._recent.append((now, model_id))
            while self._recent and now - self._recent[0][0] > RATE_WINDOW:
                self._recent.popleft()
            if not ok:
                self._unusual.append((time.time(), model_id, str(status), error or "request failed"))

        if self._plain:
            stamp = datetime.now().strftime("%H:%M:%S")
            detail = error if not ok else f"in={prompt} out={completion} ${cost:.6f}"
            print(f"{stamp} {model_id} stream={'yes' if stream else 'no'} {status} {seconds:.2f}s {detail}", flush=True)

    # ---- rendering ---------------------------------------------------------

    def render(self):
        with self._lock:
            rows = [(model_id, copy.copy(bucket)) for model_id, bucket in self._rows.items()]
            now = time.monotonic()
            rates = Counter(model_id for when, model_id in self._recent if now - when <= RATE_WINDOW)
            unusual = list(self._unusual)

        table = Table(box=None, pad_edge=False, show_edge=False)
        table.add_column("deployment", style="cyan", no_wrap=True)
        table.add_column("req", justify="right")
        table.add_column("err", justify="right")
        table.add_column("req/min", justify="right")
        table.add_column("tokens in/out", justify="right")
        table.add_column("avg", justify="right")
        table.add_column("cost", justify="right")

        total = Bucket()
        for model_id, b in rows:
            total.requests += b.requests
            total.errors += b.errors
            total.prompt += b.prompt
            total.completion += b.completion
            total.cost += b.cost
            total.seconds += b.seconds
            table.add_row(
                Text(model_id),
                str(b.requests) if b.requests else "[dim]0[/dim]",
                f"[red]{b.errors}[/red]" if b.errors else "[dim]0[/dim]",
                str(rates[model_id]),
                f"{_human(b.prompt)}/{_human(b.completion)}" if b.requests else "[dim]-[/dim]",
                f"{b.seconds / b.requests:.1f}s" if b.requests else "[dim]-[/dim]",
                f"${b.cost:.6f}" if b.cost else "[dim]$0[/dim]",
            )

        if rows:
            table.add_section()
            table.add_row(
                "[bold]total[/bold]",
                f"[bold]{total.requests}[/bold]",
                f"[red]{total.errors}[/red]" if total.errors else "[dim]0[/dim]",
                f"[bold]{sum(rates.values())}[/bold]",
                f"{_human(total.prompt)}/{_human(total.completion)}",
                f"{total.seconds / total.requests:.1f}s",
                f"${total.cost:.6f}",
            )

        body = Table.grid(padding=(0, 1))
        body.add_row("[bold]baseten-router[/bold]", f"[dim]{datetime.now():%H:%M:%S}[/dim]")
        body.add_row(table, "")
        if unusual:
            body.add_row("", "")
            body.add_row("[bold yellow]unusual[/bold yellow]", "")
            for when, source, status, message in unusual:
                line = Text(
                    f"{datetime.fromtimestamp(when):%H:%M:%S} {status} {source}",
                    style="yellow", no_wrap=True, overflow="ellipsis",
                )
                body.add_row(line, "")
                body.add_row(Text(f"  {message}"), "")
        return body


metrics_logger = Traffic()


class _Callback(CustomLogger):
    """Feeds request outcomes into the live view."""

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        try:
            payload = kwargs.get("standard_logging_object") or {}
            metrics_logger.record(
                model_id=payload.get("model_id") or _fallback_id(kwargs),
                ok=True,
                status=200,
                prompt=payload.get("prompt_tokens") or 0,
                completion=payload.get("completion_tokens") or 0,
                cost=payload.get("response_cost") or 0.0,
                seconds=_elapsed(start_time, end_time),
                stream=bool(payload.get("stream")),
            )
        except Exception:
            pass

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        try:
            payload = kwargs.get("standard_logging_object") or {}
            exc = kwargs.get("exception")
            metrics_logger.record(
                model_id=payload.get("model_id") or _fallback_id(kwargs),
                ok=False,
                status=getattr(exc, "status_code", None) or "ERR",
                prompt=payload.get("prompt_tokens") or 0,
                completion=payload.get("completion_tokens") or 0,
                cost=0.0,
                seconds=_elapsed(start_time, end_time),
                stream=bool(payload.get("stream")),
                error=_error_message(exc),
            )
        except Exception:
            pass


def _error_message(exc):
    if exc is None:
        return "request failed"
    body = getattr(exc, "body", None)
    response = getattr(exc, "response", None)
    if body is None and response is not None:
        try:
            body = response.json()
        except (AttributeError, ValueError):
            pass
    message = None
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            message = error["message"]
        elif isinstance(error, str):
            message = error
    message = str(message or getattr(exc, "message", None) or exc)
    return re.sub(r"^(?:(?:(?:litellm|openai)\.)?\w*(?:Error|Exception)(?::\s*|\s+-\s+))+", "", message)


def _fallback_id(kwargs):
    return (kwargs.get("litellm_params") or {}).get("model_info", {}).get("id") or "?"


def _elapsed(start_time, end_time):
    if not start_time or not end_time:
        return 0.0
    return (end_time - start_time).total_seconds()


metrics_callback = _Callback()
