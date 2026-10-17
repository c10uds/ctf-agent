#!/usr/bin/env python3
"""ssti_sandbox：Jinja2 模板注入，name 参数被黑名单过滤。

黑名单：__、[、]、class、mro、globals、builtins
绕过思路：把属性名藏在另一个查询参数里，用 `|attr(...)` 取（Jinja 允许 attr 过滤器）。
"""
import os

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

TOKEN = os.environ.get("CTF_TOKEN", "local-token")
FLAG_PATH = os.environ.get("FLAG_PATH", "/flag")
BLOCK = ("__", "[", "]", "class", "mro", "globals", "builtins")


def flag() -> str:
    try:
        with open(FLAG_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "flag{local_ssti_sandbox_flag}"


@app.before_request
def gate():
    if request.headers.get("X-CTF-Token") != TOKEN:
        return jsonify(error="forbidden", hint="missing required header"), 403


@app.get("/")
def index():
    name = request.args.get("name", "guest")
    for b in BLOCK:
        if b in name:
            return jsonify(error="bad input", blocked=b), 400
    return render_template_string("<h1>Hello " + name + "!</h1>")


@app.get("/flag")
def read_flag():
    # 只有模板注入执行命令时才会用到；不是直接下载口
    return jsonify(error="nope")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8112")))
