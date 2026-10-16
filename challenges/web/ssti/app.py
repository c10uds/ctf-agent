#!/usr/bin/env python3
"""Web 题 2：Jinja2 模板注入（SSTI）RCE。name 参数过滤了 `__`，需要用 request.args 绕。"""
import os

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

TOKEN = os.environ.get("CTF_TOKEN", "local-token")
FLAG_PATH = os.environ.get("FLAG_PATH", "/flag")


def flag() -> str:
    try:
        with open(FLAG_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "flag{local_ssti_test_flag}"


@app.before_request
def gate():
    if request.headers.get("X-CTF-Token") != TOKEN:
        return jsonify(error="forbidden", hint="missing required header"), 403


@app.get("/")
def index():
    name = request.args.get("name", "guest")
    if "__" in name:
        return jsonify(error="bad input", detail="illegal sequence"), 400
    return render_template_string("<h1>Hello " + name + "!</h1>")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8102")))
