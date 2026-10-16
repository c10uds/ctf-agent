#!/usr/bin/env python3
"""AIxCTF 容器内 LLM 请求转发器。

监听 127.0.0.1:8787，把 OpenAI 兼容请求通过反向 WS 隧道逐 chunk 转发给用户本地网关，
SSE 流式响应原路回传。对容器内程序完全无感：opencode 的 provider 指向本监听端口即可。

环境变量：
  CTF_CONFIG             配置文件路径（默认 /app/ctf.config.json），读取 gateway.server_url/token
  LLM_FORWARD_PORT       监听端口（默认 8787）
  GATEWAY_INJECT_CONFIG  若设置（如 /app/opencode.json），启动时把 gateway provider 注入该配置
"""
import json
import logging
import os
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import websocket  # websocket-client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger("llm-forwarder")

CONFIG_PATH = os.environ.get("CTF_CONFIG", "/app/ctf.config.json")
LISTEN_PORT = int(os.environ.get("LLM_FORWARD_PORT", "8787"))
INJECT_PATH = os.environ.get("GATEWAY_INJECT_CONFIG", "")

HOP_HEADERS = {"host", "content-length", "connection", "authorization", "accept-encoding"}


def load_gateway_addr():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    g = cfg.get("gateway") or {}
    url, token = g["server_url"].rstrip("/"), g.get("token", "")
    return url.replace("http", "ws", 1) + "/tunnel?token=" + token, url


def inject_opencode_config():
    """把 gateway provider 写入 opencode 配置（幂等）。"""
    if not INJECT_PATH:
        return
    try:
        with open(INJECT_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("provider", {})["gateway"] = {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Local Gateway",
            "options": {"baseURL": f"http://127.0.0.1:{LISTEN_PORT}/v1", "apiKey": "gateway"},
            "models": {"auto": {"name": "auto"}},
        }
        cfg["model"] = "gateway/auto"
        with open(INJECT_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        log.info("已注入 gateway provider → %s (model=gateway/auto)", INJECT_PATH)
    except Exception:
        log.exception("注入 opencode 配置失败")


class Tunnel:
    """反向 WS 隧道：多路复用 HTTP 请求（按 id 分发响应帧）。"""

    def __init__(self, url: str):
        self.url = url
        self.ws = None
        self.send_lock = threading.Lock()
        self.pending: dict[int, queue.Queue] = {}
        self.pending_lock = threading.Lock()
        self.connected = threading.Event()
        self._next_id = 0
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        backoff = 2
        while True:
            try:
                log.info("连接本地网关 %s", self.url.split("?")[0])
                ws = websocket.create_connection(self.url, ping_interval=25, ping_timeout=10)
                with self.send_lock:
                    self.ws = ws
                self.connected.set()
                backoff = 2
                log.info("隧道已建立")
                while True:
                    raw = ws.recv()
                    if not raw:
                        raise ConnectionError("ws closed")
                    self._on_frame(json.loads(raw))
            except Exception as e:
                log.warning("隧道断开：%s；%ds 后重连", e, backoff)
                self.connected.clear()
                with self.send_lock:
                    self.ws = None
                with self.pending_lock:
                    pending = list(self.pending.values())
                for q in pending:
                    q.put({"type": "http_resp_error", "message": f"tunnel disconnected: {e}"})
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def _on_frame(self, f: dict):
        with self.pending_lock:
            q = self.pending.get(f.get("id"))
        if q:
            q.put(f)

    def request(self, method: str, path: str, headers: dict, body: str) -> tuple[int, queue.Queue]:
        if not self.connected.is_set():
            raise RuntimeError("tunnel not connected（本地网关未连接）")
        with self.send_lock:
            self._next_id += 1
            rid = self._next_id
        q: queue.Queue = queue.Queue()
        with self.pending_lock:
            self.pending[rid] = q
        self._send({"type": "http_req", "id": rid, "method": method, "path": path, "headers": headers, "body": body})
        return rid, q

    def finish(self, rid: int):
        with self.pending_lock:
            self.pending.pop(rid, None)

    def _send(self, f: dict):
        with self.send_lock:
            if not self.ws:
                raise RuntimeError("tunnel not connected")
            self.ws.send(json.dumps(f, ensure_ascii=False))


TUNNEL: Tunnel


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        log.info("http " + fmt, *args)

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def _err(self, status: int, message: str):
        data = json.dumps({"error": message}, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def _proxy(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
            rid, q = TUNNEL.request(self.command, self.path, headers, body)
        except Exception as e:
            self._err(502, f"forwarder: {e}")
            return
        try:
            first = q.get(timeout=300)
            if first.get("type") == "http_resp_error":
                self._err(502, f"gateway: {first.get('message')}")
                return
            # http_resp_begin
            self.send_response(first.get("status", 200))
            for k, v in (first.get("headers") or {}).items():
                if k.lower() not in HOP_HEADERS and k.lower() not in ("transfer-encoding", "content-encoding"):
                    self.send_header(k, v)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            while True:
                f = q.get()
                t = f.get("type")
                if t == "http_resp_chunk":
                    data = (f.get("data") or "").encode("utf-8")
                    if data:
                        self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
                        self.wfile.flush()
                elif t == "http_resp_end":
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                    break
                elif t == "http_resp_error":
                    log.warning("请求 %d 中断：%s", rid, f.get("message"))
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                    break
        except Exception as e:
            log.warning("请求代理异常：%s", e)
        finally:
            TUNNEL.finish(rid)


def main():
    global TUNNEL
    ws_url, http_url = load_gateway_addr()
    inject_opencode_config()
    TUNNEL = Tunnel(ws_url)
    srv = ThreadingHTTPServer(("127.0.0.1", LISTEN_PORT), ProxyHandler)
    log.info("LLM 转发器监听 http://127.0.0.1:%d → %s", LISTEN_PORT, http_url)
    srv.serve_forever()


if __name__ == "__main__":
    main()
