#!/usr/bin/env python3
"""测试用 mock OpenAI 兼容上游：固定返回一段 SSE 流式回复。仅用于链路联调。"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9001
REPLY = "你好，我是 mock 上游。链路工作正常。Hello from mock upstream, streaming works."


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("[mock]", fmt % args, flush=True)

    def do_GET(self):
        if self.path.endswith("/models"):
            data = json.dumps({"object": "list", "data": [{"id": "mock-model", "object": "model"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        try:
            j = json.loads(body)
            print(f"[mock] POST {self.path} model={j.get('model')} stream={j.get('stream')}", flush=True)
        except Exception:
            pass
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def chunk(obj):
            return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()

        def raw(s: bytes):
            self.wfile.write(f"{len(s):X}\r\n".encode() + s + b"\r\n")
            self.wfile.flush()

        raw(chunk({"id": "chatcmpl-mock", "object": "chat.completion.chunk", "created": int(time.time()),
                   "model": "mock-model", "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}))
        for word in REPLY:
            raw(chunk({"id": "chatcmpl-mock", "object": "chat.completion.chunk", "created": int(time.time()),
                       "model": "mock-model", "choices": [{"index": 0, "delta": {"content": word}, "finish_reason": None}]}))
            time.sleep(0.01)
        raw(chunk({"id": "chatcmpl-mock", "object": "chat.completion.chunk", "created": int(time.time()),
                   "model": "mock-model", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 42, "completion_tokens": len(REPLY), "total_tokens": 42 + len(REPLY)}}))
        raw(b"data: [DONE]\n\n")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()


print(f"mock upstream on 127.0.0.1:{PORT}", flush=True)
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
