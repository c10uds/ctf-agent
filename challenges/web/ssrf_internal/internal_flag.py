#!/usr/bin/env python3
"""ssrf_internal 的内网服务：只监听 127.0.0.1，仅 /flag 返回 flag。"""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FLAG_PATH = os.environ.get("FLAG_PATH", "/flag")
PORT = int(os.environ.get("INTERNAL_PORT", "8193"))


def flag() -> str:
    try:
        with open(FLAG_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "flag{local_ssrf_flag}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/flag":
            body = flag().encode()
            self.send_response(200)
        else:
            body = b"internal service: try /flag"
            self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
