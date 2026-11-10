"""Live traffic accounting for the local Baseten router."""

from __future__ import annotations

import atexit
import copy
import re
import sys
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

try:
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    from rich.text import Text
except ImportError:
    Console = None

KEEP_UNUSUAL = 5
RATE_WINDOW = 60.0


@dataclass(frozen=True)
class Prices:
    input_per_token: float
    output_per_token: float
    cache_read_per_token: float


@dataclass
class Bucket:
    requests: int = 0
    errors: int = 0
    prompt: int = 0
    completion: int = 0
    cost: float = 0.0
    seconds: float = 0.0
    usage_requests: int = 0


def usage_tokens(usage):
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if not _non_negative_int(prompt) or not _non_negative_int(completion):
        return None
    details = usage.get("prompt_tokens_details")
    cached = details.get("cached_tokens") if isinstance(details, dict) else 0
    if not _non_negative_int(cached):
        cached = 0
    return prompt, completion, min(cached, prompt)


def calculate_cost(usage, prices):
    tokens = usage_tokens(usage)
    if tokens is None:
        return None
    prompt, completion, cached = tokens
    return (
        (prompt - cached) * prices.input_per_token
        + cached * prices.cache_read_per_token
        + completion * prices.output_per_token
    )


def redact_text(value, secrets=()):
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    text = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [redacted]", text)
    return " ".join(text.split())[:160]


def _non_negative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _human(number):
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}k"
    return str(number)


class Traffic:
    def __init__(self, prices: Mapping[str, Prices], secrets=(), *, interactive=None):
        self._lock = threading.Lock()
        self._prices = dict(prices)
        self._secrets = tuple(secret for secret in secrets if secret)
        self._rows = {}
        self._recent = deque()
        self._unusual = deque(maxlen=KEEP_UNUSUAL)
        self._live = None
        self._plain = True

        console = Console(file=sys.stdout) if Console is not None else None
        if (
            interactive is False
            or console is None
            or not console.is_terminal
            or console.is_dumb_terminal
        ):
            return
        try:
            self._live = Live(
                console=console,
                get_renderable=self.render,
                refresh_per_second=1,
                redirect_stdout=False,
            )
            self._live.start(refresh=True)
            self._plain = False
            atexit.register(self.close)
        except Exception as exc:
            self.close()
            print(f"baseten-router: live display failed: {exc}", file=sys.stderr)

    def close(self):
        live = self._live
        self._live = None
        if live is not None:
            try:
                live.stop()
            except Exception:
                pass
        self._plain = True

    def note(self, source, message, status=""):
        item = (time.time(), source, str(status), redact_text(message, self._secrets))
        with self._lock:
            self._unusual.append(item)

    def record(
        self,
        deployment_id,
        *,
        ok,
        status,
        usage,
        seconds,
        stream,
        error=None,
        cancelled=False,
    ):
        message = redact_text(error, self._secrets) if error else ""
        tokens = usage_tokens(usage)
        cost = calculate_cost(usage, self._prices[deployment_id]) if tokens else None
        now = time.monotonic()

        with self._lock:
            bucket = self._rows.setdefault(deployment_id, Bucket())
            bucket.requests += 1
            bucket.errors += 0 if ok or cancelled else 1
            bucket.seconds += seconds
            if tokens is not None:
                bucket.prompt += tokens[0]
                bucket.completion += tokens[1]
                bucket.usage_requests += 1
            if cost is not None:
                bucket.cost += cost
            self._recent.append((now, deployment_id))
            while self._recent and now - self._recent[0][0] > RATE_WINDOW:
                self._recent.popleft()
            if not ok and not cancelled:
                self._unusual.append(
                    (
                        time.time(),
                        deployment_id,
                        str(status),
                        message or "request failed",
                    )
                )

        if self._plain:
            stamp = datetime.now().strftime("%H:%M:%S")
            detail = (
                error
                if not ok
                else (
                    f"in={tokens[0]} out={tokens[1]} ${cost:.6f}"
                    if tokens is not None
                    else "usage=unknown"
                )
            )
            print(
                f"{stamp} {deployment_id} stream={'yes' if stream else 'no'} "
                f"{status} {seconds:.2f}s {detail}",
                flush=True,
            )

    def render(self):
        with self._lock:
            rows = [
                (deployment_id, copy.copy(bucket))
                for deployment_id, bucket in self._rows.items()
            ]
            now = time.monotonic()
            rates = Counter(
                deployment_id
                for when, deployment_id in self._recent
                if now - when <= RATE_WINDOW
            )
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
        for deployment_id, bucket in rows:
            total.requests += bucket.requests
            total.errors += bucket.errors
            total.prompt += bucket.prompt
            total.completion += bucket.completion
            total.cost += bucket.cost
            total.seconds += bucket.seconds
            total.usage_requests += bucket.usage_requests
            table.add_row(
                Text(deployment_id),
                str(bucket.requests),
                f"[red]{bucket.errors}[/red]" if bucket.errors else "[dim]0[/dim]",
                str(rates[deployment_id]),
                _token_text(bucket),
                f"{bucket.seconds / bucket.requests:.1f}s"
                if bucket.requests
                else "[dim]-[/dim]",
                f"${bucket.cost:.6f}" if bucket.usage_requests else "[dim]-[/dim]",
            )

        if rows:
            table.add_section()
            table.add_row(
                "[bold]total[/bold]",
                f"[bold]{total.requests}[/bold]",
                f"[red]{total.errors}[/red]" if total.errors else "[dim]0[/dim]",
                f"[bold]{sum(rates.values())}[/bold]",
                _token_text(total),
                f"{total.seconds / total.requests:.1f}s",
                f"${total.cost:.6f}" if total.usage_requests else "[dim]-[/dim]",
            )

        body = Table.grid(padding=(0, 1))
        body.add_row(
            "[bold]baseten-router[/bold]", f"[dim]{datetime.now():%H:%M:%S}[/dim]"
        )
        body.add_row(table, "")
        if unusual:
            body.add_row("", "")
            body.add_row("[bold yellow]unusual[/bold yellow]", "")
            for when, source, status, message in unusual:
                line = Text(
                    f"{datetime.fromtimestamp(when):%H:%M:%S} {status} {source}",
                    style="yellow",
                    no_wrap=True,
                    overflow="ellipsis",
                )
                body.add_row(line, "")
                body.add_row(Text(f"  {message}"), "")
        return body


def _token_text(bucket):
    if not bucket.usage_requests:
        return "[dim]-[/dim]"
    return f"{_human(bucket.prompt)}/{_human(bucket.completion)}"
