#!/usr/bin/env python3
"""本地假平台：模拟 AIxCTF 的 aixctf-challenge MCP + 附件下载 + 动态环境。

用途：在没有真实平台的情况下，本地端到端跑通解题系统（Master/worker 的环境申请、
附件下载、远程攻击、flag 提交）。

- MCP（streamable HTTP）：<prefix>/mcp，六个工具与真实平台同名同参数
- 附件下载：GET <prefix>/challenges/<id>/attachments/<aid>（Bearer 鉴权）
- 环境：
    web → 起本地 Flask 进程，返回 url + headers
    pwn → docker run 拉起 socat，返回 tcp host/port（容器侧用 host.docker.internal 访问）

用法：
  python challenges/platform/platform.py [--port 8080] [--config challenges.json]
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
STATE: dict = {"envs": {}, "submitted": {}}
CFG: dict = {}
RUNNER_IMAGE = "ctf-pwn-runner"
WEB_RUNNER_IMAGE = "ctf-web-runner"
TOKEN = ""


def log(*a):
    print("[platform]", *a, flush=True)


def challenge(cid: int) -> dict:
    for c in CFG["challenges"]:
        if int(c["id"]) == int(cid):
            return c
    raise ValueError(f"no such challenge: {cid}")


# ----------------------------------------------------------------- 环境

def wait_port(port: int, host: str = "127.0.0.1", timeout: float = 20) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.3)
    return False


def docker_image_exists(image: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", image],
                          capture_output=True).returncode == 0


def build_image(image: str, dockerfile: str) -> bool:
    tmp = HERE / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    df = tmp / "Dockerfile"
    df.write_text(dockerfile, encoding="utf-8")
    rc = subprocess.run(["docker", "build", "-t", image, "-f", str(df), str(tmp)],
                        capture_output=True, text=True)
    if rc.returncode != 0:
        log(f"构建 {image} 失败：", rc.stderr[-500:])
    return rc.returncode == 0


def ensure_runner_image() -> bool:
    if docker_image_exists(RUNNER_IMAGE):
        return True
    log("构建 pwn 运行镜像（socat + qemu-user-static）...")
    return build_image(RUNNER_IMAGE,
                       "FROM ubuntu:24.04\n"
                       "RUN apt-get update && apt-get install -y --no-install-recommends socat qemu-user-static\n")


def ensure_web_runner() -> bool:
    if docker_image_exists(WEB_RUNNER_IMAGE):
        return True
    log("构建 web 运行镜像（python3 + flask + php）...")
    return build_image(
        WEB_RUNNER_IMAGE,
        "FROM ubuntu:24.04\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
        "      python3 python3-pip php-cli php-curl \\\n"
        "    && python3 -m pip install --break-system-packages --no-cache-dir \\\n"
        "      flask requests pyjwt\n")


def start_web(ch: dict) -> dict:
    """每个 web 题跑在一个 docker 容器里：python 或 php 运行时，可带一个内网服务。"""
    if not ensure_web_runner():
        raise RuntimeError("web 运行镜像不可用（docker 未就绪？）")
    port = int(ch["env"]["port"])
    flag_file = HERE / "tmp" / f"{ch['id']}.flag"
    flag_file.parent.mkdir(parents=True, exist_ok=True)
    flag_file.write_text(ch["flag"], encoding="utf-8")
    appdir = (REPO / ch["env"]["dir"]).resolve()
    name = f"ctf-web-{ch['id']}"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)

    internal = ch["env"].get("internal")
    cmd = []
    if internal:
        cmd.append(f"INTERNAL_PORT={int(internal['port'])} FLAG_PATH=/flag "
                   f"python3 {internal['entry']} &")
    runtime = ch["env"].get("runtime", "python")
    if runtime == "php":
        cmd.append(f"exec php -S 0.0.0.0:{port} index.php")
    else:
        cmd.append(f"exec python3 {ch['env']['entry']}")

    run = ["docker", "run", "-d", "--rm", "--name", name,
           "-p", f"{port}:{port}",
           "-v", f"{appdir}:/app:ro", "-v", f"{flag_file}:/flag:ro", "-w", "/app",
           "-e", f"PORT={port}", "-e", f"CTF_TOKEN={TOKEN}", "-e", "FLAG_PATH=/flag"]
    if internal:
        run += ["-e", f"INTERNAL_URL=http://127.0.0.1:{int(internal['port'])}"]
    run += [WEB_RUNNER_IMAGE, "bash", "-c", " ".join(cmd)]

    rc = subprocess.run(run, capture_output=True, text=True)
    if rc.returncode != 0:
        raise RuntimeError(f"docker run 失败：{rc.stderr[-300:]}")
    if not wait_port(port):
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        raise RuntimeError(f"web 环境未能在 {port} 上就绪")
    host = CFG.get("public_host", "127.0.0.1")
    return {"kind": "web", "name": name, "url": f"http://{host}:{port}",
            "headers": {"X-CTF-Token": TOKEN}}


def start_pwn(ch: dict) -> dict:
    port = int(ch["env"]["port"])
    if not ensure_runner_image():
        raise RuntimeError("pwn 运行镜像不可用（docker 未就绪？）")
    dist = (REPO / ch["env"]["dist"]).resolve()
    binary = os.path.basename(ch["env"]["binary"])
    flag_file = HERE / "tmp" / f"{ch['id']}.flag"
    flag_file.parent.mkdir(parents=True, exist_ok=True)
    flag_file.write_text(ch["flag"], encoding="utf-8")
    name = f"ctf-env-{ch['id']}"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    exe = f"/c/{binary}"
    if ch["env"].get("exec_prefix"):
        exe = f"{ch['env']['exec_prefix']} {exe}"
    cmd = ["docker", "run", "-d", "--rm", "--name", name,
           "-p", f"{port}:{port}",
           "-v", f"{dist}:/c:ro", "-v", f"{flag_file}:/flag:ro",
           RUNNER_IMAGE,
           "socat", f"TCP-LISTEN:{port},reuseaddr,fork", f"EXEC:{exe}"]
    rc = subprocess.run(cmd, capture_output=True, text=True)
    if rc.returncode != 0:
        raise RuntimeError(f"docker run 失败：{rc.stderr[-300:]}")
    if not wait_port(port):
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        raise RuntimeError(f"pwn 环境未能在 {port} 上就绪")
    host = CFG.get("public_host", "127.0.0.1")
    return {"kind": "pwn", "name": name, "tcp": {"host": host, "port": port, "handshake": ""}}


def stop_env(cid: int) -> bool:
    env = STATE["envs"].pop(int(cid), None)
    if not env:
        return False
    if env.get("kind") == "web":
        subprocess.run(["docker", "rm", "-f", env["name"]], capture_output=True)
    elif env.get("kind") == "pwn":
        subprocess.run(["docker", "rm", "-f", env["name"]], capture_output=True)
    return True


# ----------------------------------------------------------------- MCP 工具

# MCP SDK 默认开启 DNS-rebinding 防护，只认 localhost/127.0.0.1 的 Host 头；
# 容器通过 host.docker.internal 访问会被回 421，这里关掉（本地测试用）。
mcp = FastMCP("aixctf-challenge", streamable_http_path="/mcp",
              transport_security=TransportSecuritySettings(
                  enable_dns_rebinding_protection=False))


def public_challenge(ch: dict) -> dict:
    return {
        "id": int(ch["id"]),
        "name": ch["name"],
        "category": ch["category"],
        "description": ch["description"],
        "score": ch["score"],
        "current_score": ch["score"],
        "hint": None,
        "solved": STATE["submitted"].get(int(ch["id"]), {}).get("correct", False),
        "attachments": [
            {"id": i + 1, "name": Path(p).name,
             "download_url": f"/challenges/{ch['id']}/attachments/{i + 1}"}
            for i, p in enumerate(ch["attachments"])
        ],
    }


@mcp.tool()
def list_challenges() -> dict:
    """获取当前模式可见题目列表。"""
    return {"challenges": [public_challenge(c) for c in CFG["challenges"]]}


@mcp.tool()
def get_challenge(challenge_id: int) -> dict:
    """查看单题详情、附件、分值与当前队伍进度。"""
    return public_challenge(challenge(challenge_id))


@mcp.tool()
def start_challenge(challenge_id: int) -> dict:
    """启动动态题目环境，返回 Web 或 Pwn 访问入口。"""
    ch = challenge(challenge_id)
    cid = int(ch["id"])
    if cid in STATE["envs"]:
        return {"reused": True, **STATE["envs"][cid]}
    info = start_web(ch) if ch["env"]["type"] == "web" else start_pwn(ch)
    STATE["envs"][cid] = info
    log(f"start_challenge {cid} ({ch['category']}) -> {info}")
    return info


@mcp.tool()
def stop_challenge(challenge_id: int) -> dict:
    """关闭当前队伍的动态题目环境。"""
    ok = stop_env(int(challenge_id))
    log(f"stop_challenge {challenge_id} -> {ok}")
    return {"stopped": ok}


@mcp.tool()
def view_hint(challenge_id: int) -> dict:
    """查看题目提示（按规则扣分，本平台按 80% 结算）。"""
    ch = challenge(challenge_id)
    return {"challenge_id": int(ch["id"]),
            "hint": f"这是一道 {ch['category']} 题，注意输入校验。",
            "penalty": "该题后续正确提交按 80% 结算"}


@mcp.tool()
def submit_flag(challenge_id: int, flag: str) -> dict:
    """提交 Flag 并返回判定结果。"""
    ch = challenge(challenge_id)
    got = (flag or "").strip()
    correct = got == ch["flag"]
    STATE["submitted"][int(ch["id"])] = {"correct": correct, "flag": got}
    log(f"submit_flag {challenge_id} -> {'CORRECT' if correct else 'WRONG'}")
    return {"challenge_id": int(ch["id"]), "correct": correct,
            "score": ch["score"] if correct else 0}


# ----------------------------------------------------------------- ASGI 组装

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


async def download_attachment(request):
    cid = int(request.path_params["cid"])
    aid = int(request.path_params["aid"])
    ch = challenge(cid)
    if aid < 1 or aid > len(ch["attachments"]):
        return JSONResponse({"error": "no such attachment"}, status_code=404)
    path = (REPO / ch["attachments"][aid - 1]).resolve()
    if not path.is_file():
        return JSONResponse({"error": "file missing on server"}, status_code=500)
    return FileResponse(path, filename=path.name)


def build_app() -> Starlette:
    prefix = CFG.get("api_prefix", "/api/challenge/v1/agent")
    mcp_app = mcp.streamable_http_app()

    # Starlette 不会自动运行被挂载子应用的 lifespan，MCP 的 session manager 必须显式启动，
    # 否则 /mcp 上的请求会 500。
    @asynccontextmanager
    async def lifespan(app):
        async with mcp_app.router.lifespan_context(app):
            yield

    routes = [
        Route(f"{prefix}/challenges/{{cid}}/attachments/{{aid}}", download_attachment),
        Mount(prefix, app=mcp_app),
    ]
    return Starlette(routes=routes, middleware=[Middleware(AuthMiddleware)], lifespan=lifespan)


def main():
    global CFG, TOKEN
    ap = argparse.ArgumentParser(description="本地假 AIxCTF 平台")
    ap.add_argument("--config", default=str(HERE / "challenges.json"))
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()

    CFG = json.loads(Path(args.config).read_text(encoding="utf-8"))
    TOKEN = CFG.get("team_agent_key", "local-team-key")
    port = args.port or int(CFG.get("http_port", 8080))
    prefix = CFG.get("api_prefix", "/api/challenge/v1/agent")

    import uvicorn

    log(f"端点：http://<host>:{port}{prefix}")
    log(f"MCP ：http://<host>:{port}{prefix}/mcp")
    log(f"Team Agent Key：{TOKEN}")
    log(f"题目：{[c['id'] for c in CFG['challenges']]}")
    uvicorn.run(build_app(), host=args.host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
