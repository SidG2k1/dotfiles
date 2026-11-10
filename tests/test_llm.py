import importlib.util
from importlib.machinery import SourceFileLoader
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOADER = SourceFileLoader("llm_cli", str(ROOT / "bin/llm"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
llm = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = llm
SPEC.loader.exec_module(llm)


class TtyInput(io.StringIO):
    def isatty(self):
        return True


class FakeRouter:
    def __init__(self, respond):
        self.respond = respond
        self.requests = []
        self.headers = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                owner.headers.append(dict(self.headers))
                owner.requests.append(json.loads(self.rfile.read(length)))
                owner.respond(self)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = (
            f"http://127.0.0.1:{self.server.server_address[1]}/v1/chat/completions"
        )

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def json_router(content):
    def respond(handler):
        body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    return respond


def stream_router(pieces):
    def respond(handler):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()
        for piece in pieces:
            handler.wfile.write(piece)
            handler.wfile.flush()

    return respond


class LLMTests(unittest.TestCase):
    def run_llm(self, router, *args, stdin=None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = llm.main(
            list(args),
            stdin=stdin or TtyInput(),
            stdout=stdout,
            stderr=stderr,
            url=router.url if router else "http://127.0.0.1:1/v1/chat/completions",
        )
        return code, stdout.getvalue(), stderr.getvalue()

    def with_router(self, respond):
        router = FakeRouter(respond)
        self.addCleanup(router.close)
        return router

    def test_prompt_system_and_request_defaults(self):
        router = self.with_router(
            stream_router(
                (
                    b'data: {"choices":[{"delta":{"content":"OK"}}]}\n\n',
                    b"data: [DONE]\n\n",
                )
            )
        )
        code, output, error = self.run_llm(
            router, "--system", "Be terse", "hello", "world"
        )

        self.assertEqual((code, output, error), (0, "OK\n", ""))
        payload = router.requests[0]
        self.assertEqual(payload["model"], "baseten-router")
        self.assertTrue(payload["stream"])
        self.assertNotIn("reasoning_effort", payload)
        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": "Be terse"},
                {"role": "user", "content": "hello world"},
            ],
        )
        self.assertEqual(router.headers[0]["Authorization"], "Bearer local-proxy")

    def test_piped_input_is_combined_with_prompt(self):
        router = self.with_router(json_router("OK"))
        code, _, _ = self.run_llm(
            router,
            "Review",
            stdin=io.StringIO("diff --git a/file b/file"),
        )

        self.assertEqual(code, 0)
        self.assertEqual(
            router.requests[0]["messages"][-1]["content"],
            "Review\n\ndiff --git a/file b/file",
        )

    def test_missing_prompt_does_not_contact_router(self):
        router = self.with_router(json_router("unused"))
        code, _, error = self.run_llm(router)

        self.assertEqual(code, 2)
        self.assertIn("prompt or piped input", error)
        self.assertEqual(router.requests, [])

    def test_non_streaming_request(self):
        router = self.with_router(json_router("complete"))
        code, output, _ = self.run_llm(router, "--no-stream", "hello")

        self.assertEqual((code, output), (0, "complete\n"))
        self.assertFalse(router.requests[0]["stream"])

    def test_streaming_prints_content_and_hides_reasoning(self):
        pieces = (
            b'data: {"choices":[{"delta":{"reasoning_content":"secret"}}]}\n\n',
            b'data: {"choices":[{"delta":{"content":"O"}}]}\n\ndata: {"choi',
            b'ces":[{"delta":{"content":"K"}}]}\n\n',
            b'data: {"choices":[],"usage":{"prompt_tokens":1}}\n\n',
            b"data: [DONE]\n\n",
        )
        router = self.with_router(stream_router(pieces))
        code, output, error = self.run_llm(router, "hello")

        self.assertEqual((code, output, error), (0, "OK\n", ""))
        self.assertNotIn("secret", output)

    def test_bad_stream_event_is_reported(self):
        router = self.with_router(stream_router((b"data: not-json\n\n",)))
        code, output, error = self.run_llm(router, "hello")

        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("invalid stream event", error)

    def test_unsupported_model_and_logs_are_rejected_locally(self):
        router = self.with_router(json_router("unused"))

        code, _, error = self.run_llm(router, "-m", "baseten", "hello")
        self.assertEqual(code, 2)
        self.assertIn("only the local", error)

        code, _, error = self.run_llm(router, "logs")
        self.assertEqual(code, 2)
        self.assertIn("history is not recorded", error)
        self.assertEqual(router.requests, [])

    def test_upstream_error_message_is_printed(self):
        def respond(handler):
            body = json.dumps({"error": {"message": "rate limited"}}).encode()
            handler.send_response(429)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)

        router = self.with_router(respond)
        code, output, error = self.run_llm(router, "hello")

        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("rate limited", error)

    def test_connection_refused_mentions_router(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        stdout = io.StringIO()
        stderr = io.StringIO()
        code = llm.main(
            ["hello"],
            stdin=TtyInput(),
            stdout=stdout,
            stderr=stderr,
            url=f"http://127.0.0.1:{port}/v1/chat/completions",
        )

        self.assertEqual(code, 1)
        self.assertIn("cannot connect to baseten-router", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
