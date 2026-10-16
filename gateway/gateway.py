#!/usr/bin/env python3
"""AIxCTF 本地 LLM 网关。

容器内转发器经反向 WS 隧道把 OpenAI 兼容请求送到这里，本网关按本地配置
重写 model/key 后转发到真实上游，响应流式回传。容器侧完全无感。

用法：
  python gateway.py --config gateway.config.json
  python gateway.py --upstream https://api.example.com/v1 --key sk-xxx --model gpt-4o-mini
另外监听一个本地 HTTP 端口（默认 8788），本机程序也可直接走网关（同样的重写逻辑）。
"""
import argparse
import json
import logging
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests
from websockets.sync.server import serve

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger("llm-gateway")

PREVIEW = 200
HOP_HEADERS = {"host", "content-length", "connection", "authorization", "accept-encoding", "transfer-encoding", "content-encoding"}


class Router:
    """当前路由：单一上游 + 模型重写。"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.lock = threading.Lock()

    def snapshot(self):
        with self.lock:
            return self.base_url, self.api_key, self.model

    def update(self, base_url=None, api_key=None, model=None):
        with self.lock:
            if base_url:
                self.base_url = base_url.rstrip("/")
            if api_key is not None:
                self.api_key = api_key
            if model:
                self.model = model
        log.info("路由更新：%s model=%s", self.base_url, self.model)


ROUTER: Router


def prompt_preview(body: str) -> str:
    try:
        msgs = json.loads(body).get("messages") or []
        for m in reversed(msgs):
            if m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, list):
                    c = " ".join(str(p.get("text", "")) for p in c if isinstance(p, dict))
                return str(c)[:PREVIEW].replace("\n", " ")
    except Exception:
        pass
    return ""


def proxy(method: str, path: str, headers: dict, body: str):
    """返回 (status, resp_headers, chunk_iter, log_tail)；异常抛 RuntimeError。"""
    base_url, api_key, real_model = ROUTER.snapshot()
    if not path.startswith("/v1"):
        raise RuntimeError(f"仅支持 /v1 路径: {path}")
    url = base_url + path[3:]

    out_headers = {k: v for k, v in headers.items() if k.lower() not in HOP_HEADERS}
    out_headers["Authorization"] = f"Bearer {api_key}"
    out_headers["Accept-Encoding"] = "identity"
    out_headers["Content-Type"] = "application/json"

    orig_model = None
    out_body = body
    try:
        j = json.loads(body)
        orig_model = j.get("model")
        if real_model:
            j["model"] = real_model
            out_body = json.dumps(j, ensure_ascii=False)
    except Exception:
        pass

    t0 = time.time()
    r = requests.request(method, url, headers=out_headers, data=out_body.encode("utf-8"),
                         stream=True, timeout=(15, 600))
    status = r.status_code
    if status != 200:
        content = r.content.decode("utf-8", "replace")[:500]
        r.close()
        raise RuntimeError(f"上游返回 {status}: {content}")

    preview_buf = []
    usage = {}

    def chunks():
        try:
            for data in r.iter_content(chunk_size=4096, decode_unicode=False):
                if not data:
                    continue
                text = data.decode("utf-8", "replace")
                # 收集响应预览与 token 用量（SSE data 行）
                for line in text.splitlines():
                    if not line.startswith("data:") or "[DONE]" in line:
                        continue
                    try:
                        cj = json.loads(line[5:].strip())
                        if cj.get("usage"):
                            usage.update(cj["usage"])
                        delta = (cj.get("choices") or [{}])[0].get("delta") or {}
                        piece = delta.get("content") or ""
                        if piece and sum(len(x) for x in preview_buf) < PREVIEW:
                            preview_buf.append(piece)
                    except Exception:
                        pass
                yield text
        finally:
            r.close()
            log.info("[响应] %s %s status=%d dur=%.1fs tokens=%s | %s",
                     method, path, status, time.time() - t0,
                     usage.get("total_tokens", "-"), "".join(preview_buf)[:PREVIEW].replace("\n", " "))

    log.info("[请求] %s %s model=%s→%s | %s", method, path, orig_model, real_model or orig_model, prompt_preview(body))
    return status, dict(r.headers), chunks()


# ---------- 隧道端（容器反向连接） ----------

def tunnel_handler(ws):
    try:
        path = ws.request.path
    except Exception:
        path = ""
    token = ""
    if "token=" in path:
        token = path.split("token=", 1)[1].split("&")[0]
    if token != TOKEN:
        log.warning("隧道连接 token 错误，拒绝")
        ws.close(4401)
        return
    peer = ws.remote_address
    log.info("隧道已连接：%s", peer)
    try:
        while True:
            raw = ws.recv()
            if raw is None:
                break
            try:
                f = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if f.get("type") == "http_req":
                threading.Thread(target=handle_tunnel_req, args=(ws, f), daemon=True).start()
    except Exception:
        pass
    log.info("隧道断开：%s", peer)


def ws_send(ws, frame: dict):
    ws.send(json.dumps(frame, ensure_ascii=False))


def handle_tunnel_req(ws, f: dict):
    rid = f.get("id")
    try:
        status, headers, chunks = proxy(f.get("method", "POST"), f.get("path", ""), f.get("headers") or {}, f.get("body") or "")
        ws_send(ws, {"type": "http_resp_begin", "id": rid, "status": status,
                     "headers": {k: v for k, v in headers.items() if k.lower() not in HOP_HEADERS}})
        for c in chunks:
            ws_send(ws, {"type": "http_resp_chunk", "id": rid, "data": c})
        ws_send(ws, {"type": "http_resp_end", "id": rid})
    except Exception as e:
        log.warning("隧道请求 %s 失败：%s", rid, e)
        try:
            ws_send(ws, {"type": "http_resp_error", "id": rid, "message": str(e)})
        except Exception:
            pass


# ---------- 本地直连 HTTP 端（本机程序也可走网关） ----------

class DirectHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        log.info("direct " + fmt, *args)

    def do_GET(self):
        self._p()

    def do_POST(self):
        self._p()

    def do_PUT(self):
        self._p()

    def do_DELETE(self):
        self._p()

    def _p(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
            headers = {k: v for k, v in self.headers.items()}
            status, rheaders, chunks = proxy(self.command, self.path, headers, body)
            self.send_response(status)
            for k, v in rheaders.items():
                if k.lower() not in HOP_HEADERS:
                    self.send_header(k, v)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for c in chunks:
                data = c.encode("utf-8")
                self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except Exception as e:
            data = json.dumps({"error": str(e)}, ensure_ascii=False).encode()
            try:
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                pass


def main():
    global TOKEN, ROUTER
    p = argparse.ArgumentParser(description="AIxCTF 本地 LLM 网关")
    p.add_argument("--config", help="gateway.config.json 路径")
    p.add_argument("--port", type=int, help="隧道监听端口（默认 8790）")
    p.add_argument("--http-port", type=int, help="本地直连 HTTP 端口（默认 8788，0 关闭）")
    p.add_argument("--token", help="隧道鉴权 token")
    p.add_argument("--upstream", help="上游 base_url，如 https://api.example.com/v1")
    p.add_argument("--key", help="上游 api key")
    p.add_argument("--model", help="重写为该模型名")
    args = p.parse_args()

    cfg = {}
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg = json.load(f)
    port = args.port or cfg.get("port", 8790)
    http_port = args.http_port if args.http_port is not None else cfg.get("http_port", 8788)
    TOKEN = args.token or cfg.get("token", "changeme")
    up = cfg.get("upstream") or {}
    ROUTER = Router(
        base_url=args.upstream or up.get("base_url", ""),
        api_key=args.key or up.get("api_key", ""),
        model=args.model or up.get("model", ""),
    )
    if TOKEN == "changeme":
        log.warning("使用默认 token 'changeme'，请通过 --token 或配置文件设置共享密钥")
    if not ROUTER.base_url:
        log.warning("未配置上游 base_url，转发将失败（--upstream 或配置文件 upstream.base_url）")

    if http_port:
        httpd = ThreadingHTTPServer(("0.0.0.0", http_port), DirectHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        log.info("本地直连端口：http://127.0.0.1:%d/v1", http_port)

    log.info("隧道监听 0.0.0.0:%d（容器侧连接 ws://<你的IP>:%d/tunnel?token=***）", port, port)
    with serve(tunnel_handler, "0.0.0.0", port, max_size=None) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
