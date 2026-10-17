#!/usr/bin/env python3
"""jwt_admin：HS256 的密钥很弱；/admin 需要 role=admin。
思路：登录取 token，离线爆破常见弱密钥，再伪造 admin token。"""
import os

import jwt
from flask import Flask, jsonify, request

app = Flask(__name__)

TOKEN = os.environ.get("CTF_TOKEN", "local-token")
FLAG_PATH = os.environ.get("FLAG_PATH", "/flag")
JWT_SECRET = os.environ.get("JWT_SECRET", "secret")


def flag() -> str:
    try:
        with open(FLAG_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "flag{local_jwt_flag}"


@app.before_request
def gate():
    if request.headers.get("X-CTF-Token") != TOKEN:
        return jsonify(error="forbidden", hint="missing required header"), 403


@app.get("/")
def index():
    return jsonify(msg="POST /login then GET /admin with Bearer token",
                   note="only admins may read the flag")


@app.post("/login")
def login():
    user = (request.get_json(silent=True) or {}).get("user", "guest")
    token = jwt.encode({"user": str(user), "role": "guest"}, JWT_SECRET, algorithm="HS256")
    return jsonify(token=token)


@app.get("/admin")
def admin():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify(error="missing token"), 401
    try:
        payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
    except Exception as exc:
        return jsonify(error="invalid token", detail=str(exc)), 401
    if payload.get("role") != "admin":
        return jsonify(error="not admin", role=payload.get("role")), 403
    return jsonify(msg="welcome admin", flag=flag())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8115")))
