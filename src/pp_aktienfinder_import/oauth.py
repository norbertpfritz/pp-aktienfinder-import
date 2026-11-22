import asyncio
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from mcp.client.auth import TokenStorage
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthToken,
)


class MemoryTokenStorage(TokenStorage):
    def __init__(self) -> None:
        self._tokens: OAuthToken | None = None
        self._client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self._client_info

    async def set_client_info(
        self,
        client_info: OAuthClientInformationFull,
    ) -> None:
        self._client_info = client_info


async def open_browser(url: str) -> None:
    webbrowser.open(url)


async def receive_authorization_code() -> AuthorizationCodeResult:
    future: asyncio.Future[AuthorizationCodeResult] = asyncio.Future()
    loop = asyncio.get_running_loop()
    issuer = "https://dividendenfinder.de/"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            params = parse_qs(urlparse(self.path).query)
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            error = params.get("error", [None])[0]
            returned_issuer = params.get("iss", [issuer])[0]

            body = (
                "<html><body><h2>Authentifizierung abgeschlossen</h2>"
                "<p>Dieses Fenster kann geschlossen werden.</p></body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

            if error:
                loop.call_soon_threadsafe(
                    future.set_exception,
                    RuntimeError(f"OAuth authorization failed: {error}"),
                )
            elif code:
                loop.call_soon_threadsafe(
                    future.set_result,
                    AuthorizationCodeResult(
                        code=code,
                        state=state,
                        iss=returned_issuer,
                    ),
                )
            else:
                loop.call_soon_threadsafe(
                    future.set_exception,
                    RuntimeError("OAuth callback did not contain an authorization code"),
                )

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 8765), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        return await future
    finally:
        await asyncio.sleep(0)
        server.shutdown()
        thread.join(timeout=2)
