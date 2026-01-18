import asyncio
import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Awaitable, Callable, Dict, Optional
from urllib.parse import urlparse


@dataclass
class Route:
    handler: Callable[[dict], Awaitable[None]]
    secret_token: Optional[str] = None


class WebhookServer:
    def __init__(
        self,
        host: str,
        port: int,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.host = host
        self.port = port
        self.loop = loop
        self.routes: Dict[str, Route] = {}
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def add_route(
        self,
        path: str,
        handler: Callable[[dict], Awaitable[None]],
        secret_token: Optional[str] = None,
    ) -> None:
        normalized = path if path.startswith("/") else f"/{path}"
        self.routes[normalized] = Route(handler=handler, secret_token=secret_token)

    def start(self) -> None:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                request_path = urlparse(self.path).path
                route = server.routes.get(request_path)
                if not route:
                    self.send_response(404)
                    self.end_headers()
                    return

                if route.secret_token:
                    header_token = self.headers.get(
                        "X-Telegram-Bot-Api-Secret-Token"
                    )
                    if header_token != route.secret_token:
                        self.send_response(401)
                        self.end_headers()
                        return

                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length) if content_length else b""

                try:
                    update = json.loads(raw_body.decode("utf-8"))
                except json.JSONDecodeError:
                    self.send_response(400)
                    self.end_headers()
                    return

                asyncio.run_coroutine_threadsafe(route.handler(update), server.loop)

                self.send_response(200)
                self.end_headers()

            def do_GET(self) -> None:
                request_path = urlparse(self.path).path
                if request_path not in server.routes:
                    self.send_response(404)
                    self.end_headers()
                    return

                self.send_response(200)
                self.end_headers()

            def log_message(self, format, *args) -> None:  # noqa: A003
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
