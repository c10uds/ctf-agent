#!/usr/bin/env python3
"""ssrf_internal：/fetch?url= 会代为请求；内网服务只监听 127.0.0.1 的另一个端口。

过滤：url 里出现 "127.0.0.1" 或 "localhost" 就拒绝。
绕过思路：127.1 / [::1] / 十进制 IP 等等价写法。
"""
import os

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

TOKEN = os.environ.get("CTF_TOKEN", "local-token")
INTERNAL = os.environ.get("INTERNAL_URL", "http://127.0.0.1:8193")


@app.before_request
def gate():
    if request.headers.get("X-CTF-Token") != TOKEN:
        return jsonify(error="forbidden", hint="missing required header"), 403


@app.get("/")
def index():
    return jsonify(msg="GET /fetch?url=http://...", internal_hint="there is an internal service")


@app.get("/fetch")
def fetch():
    url = request.args.get("url", "")
    if not url.startswith("http://") and not url.startswith("https://"):
        return jsonify(error="bad url"), 400
    if "127.0.0.1" in url or "localhost" in url:
        return jsonify(error="blocked"), 400
    try:
        r = requests.get(url, timeout=4)
    except Exception as exc:
        return jsonify(error="fetch failed", detail=str(exc)), 502
    return r.text, r.status_code, {"Content-Type": r.headers.get("Content-Type", "text/plain")}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8113")))
