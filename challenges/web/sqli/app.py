#!/usr/bin/env python3
"""Web 题 1：登录处 SQL 注入（需携带题目要求的请求头）。"""
import hashlib
import os
import sqlite3

from flask import Flask, jsonify, request

app = Flask(__name__)

TOKEN = os.environ.get("CTF_TOKEN", "local-token")
FLAG_PATH = os.environ.get("FLAG_PATH", "/flag")


def flag() -> str:
    try:
        with open(FLAG_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "flag{local_sqli_test_flag}"


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER, username TEXT, password TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'guest', 'guest')")
    conn.execute("INSERT INTO users VALUES (2, 'admin', '5f4dcc3b5aa765d61d8327deb882cf99')")
    return conn


@app.before_request
def gate():
    if request.headers.get("X-CTF-Token") != TOKEN:
        return jsonify(error="forbidden", hint="missing required header"), 403


@app.get("/")
def index():
    return (
        "<h1>Acme Internal Portal</h1>"
        "<p>POST JSON {\"username\":..., \"password\":...} to /login</p>"
    )


@app.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", ""))
    password = hashlib.md5(str(data.get("password", "")).encode()).hexdigest()

    query = f"SELECT id, username FROM users WHERE username = '{username}' AND password = '{password}'"
    try:
        row = db().execute(query).fetchone()
    except sqlite3.Error as exc:
        return jsonify(error="query failed", detail=str(exc)), 400

    if row and row[1] == "admin":
        return jsonify(msg="welcome admin", flag=flag())
    return jsonify(error="invalid credentials"), 401


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8101")))
