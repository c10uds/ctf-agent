#!/usr/bin/env python3
"""sqli_blind：布尔盲注 + WAF（过滤空格、--、union、sleep、benchmark）。

查询：SELECT id FROM items WHERE name = '<q>'
接口：GET /search?q=...  返回 {"found": true/false}
绕过思路：用 /**/ 代替空格、用 /**/OR/**/ 代替 or、不用注释符直接闭合引号。
"""
import os
import sqlite3

from flask import Flask, jsonify, request

app = Flask(__name__)

TOKEN = os.environ.get("CTF_TOKEN", "local-token")
FLAG_PATH = os.environ.get("FLAG_PATH", "/flag")
WAF = (" ", "--", "union", "sleep", "benchmark")


def flag() -> str:
    try:
        with open(FLAG_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "flag{local_sqli_blind_flag}"


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE items (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO items VALUES (1, 'alpha'), (2, 'beta')")
    conn.execute("CREATE TABLE secrets (id INTEGER, flag TEXT)")
    conn.execute("INSERT INTO secrets VALUES (1, ?)", (flag(),))
    return conn


@app.before_request
def gate():
    if request.headers.get("X-CTF-Token") != TOKEN:
        return jsonify(error="forbidden", hint="missing required header"), 403


@app.get("/")
def index():
    return jsonify(msg="GET /search?q=...", note="only boolean result is returned")


@app.get("/search")
def search():
    q = request.args.get("q", "")
    low = q.lower()
    for w in WAF:
        if w in low:
            return jsonify(error="blocked", word=w), 400
    sql = f"SELECT id FROM items WHERE name = '{q}'"
    try:
        row = db().execute(sql).fetchone()
    except sqlite3.Error as exc:
        return jsonify(error="query error", detail=str(exc)), 400
    return jsonify(found=bool(row))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8111")))
