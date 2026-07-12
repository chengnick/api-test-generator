"""
mock_server.py — 極簡的本地假靶站（僅供離線驗證產生器用，不是專案的一部分）

模擬 httpbin 的幾個端點 + Basic Auth。
"""

import base64
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

USER, PWD = "demo_user", "demo_pass"

PUBLIC = {"/get", "/post", "/status/200", "/response-headers",
          "/user-agent", "/json", "/encoding/utf8"}
PROTECTED = {"/headers", "/cookies", "/ip", "/anything"}


class Handler(BaseHTTPRequestHandler):
    def _authed(self) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        decoded = base64.b64decode(header[6:]).decode()
        return decoded == f"{USER}:{PWD}"

    def _respond(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        path = self.path.split("?")[0]

        if path.startswith("/basic-auth/"):
            return self._respond(200 if self._authed() else 401,
                                 {"authenticated": self._authed()})

        if path in PROTECTED:
            if not self._authed():
                return self._respond(401, {"error": "unauthorized"})
            return self._respond(200, {"path": path, "authenticated": True})

        if path in PUBLIC:
            return self._respond(200, {"path": path})

        return self._respond(404, {"error": "not found"})

    do_GET = do_POST = _handle

    def log_message(self, *args):
        pass  # 靜音


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8888), Handler).serve_forever()
