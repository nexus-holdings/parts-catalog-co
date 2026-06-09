"""HTTP server for the parts-catalog lookup service."""

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from src.lookup import load_catalog, lookup

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8400

_PART_RE = re.compile(r"^/parts/([A-Za-z0-9_-]+)$")


class CatalogHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/health":
            self._json_response(200, {"status": "ok"})
        elif path == "/parts":
            catalog = load_catalog()
            category = qs.get("category", [None])[0]
            if category is not None:
                catalog = [p for p in catalog if p.get("category") == category]
            self._json_response(200, catalog)
        elif m := _PART_RE.match(path):
            part_id = m.group(1)
            try:
                part = lookup(part_id)
                self._json_response(200, part)
            except KeyError:
                self._json_response(404, {"error": f"Part not found: {part_id}"})
        else:
            self._json_response(404, {"error": "Not found"})

    def _json_response(self, status: int, body: dict | list):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass


def main() -> int:
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--port" and i + 2 < len(sys.argv):
            port = int(sys.argv[i + 2])
        elif arg == "--host" and i + 2 < len(sys.argv):
            host = sys.argv[i + 2]

    server = HTTPServer((host, port), CatalogHandler)
    print(f"Serving parts catalog on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
