#!/usr/bin/env python3
"""AIxCTF 调试控制台本地服务端。

浏览器 ──WS /ui──> 本服务 <──WS /agent── 容器内 debug-agent（反向连接）

接口契约见同目录 CONTRACT.md。
"""
import argparse
import asyncio
import json
import logging
import os
import time
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger("debug-console")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

STATIC_DIR = Path(__file__).parent / "static"
MAX_ACTIVITIES_PER_SESSION = 2000

app = FastAPI(title="AIxCTF Debug Console")


class Hub:
    def __init__(self, token: str):
        self.token = token
        self.agent: WebSocket | None = None
        self.agent_hostname: str | None = None
        self.agent_last_seen: float = 0
        self.uis: set[WebSocket] = set()
        self.snapshot: dict | None = None
        self.activities: dict[str, list[dict]] = {}
        self.model_state: dict | None = None
        self.lock = asyncio.Lock()

    async def broadcast_ui(self, msg: dict):
        data = json.dumps(msg, ensure_ascii=False)
        dead = []
        for ws in list(self.uis):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.uis.discard(ws)

    async def send_agent(self, msg: dict) -> bool:
        if not self.agent:
            return False
        try:
            await self.agent.send_text(json.dumps(msg, ensure_ascii=False))
            return True
        except Exception:
            return False

    async def handle_agent_msg(self, msg: dict):
        t = msg.get("type")
        if t == "hello":
            self.agent_hostname = msg.get("hostname")
            await self.broadcast_status()
        elif t == "snapshot":
            self.snapshot = msg.get("payload")
            if self.snapshot and self.snapshot.get("model"):
                self.model_state = self.snapshot["model"]
            await self.broadcast_ui(msg)
        elif t == "activity":
            sid = msg.get("session_id")
            if sid:
                store = self.activities.setdefault(sid, [])
                seen = {e["id"] for e in store}
                for e in msg.get("entries", []):
                    if e.get("id") not in seen:
                        store.append(e)
                if len(store) > MAX_ACTIVITIES_PER_SESSION:
                    del store[: len(store) - MAX_ACTIVITIES_PER_SESSION]
            await self.broadcast_ui(msg)
        elif t in ("chat_reply", "model_state"):
            if t == "model_state":
                self.model_state = msg
            await self.broadcast_ui(msg)

    async def broadcast_status(self):
        await self.broadcast_ui({
            "type": "status",
            "agent_connected": self.agent is not None,
            "agent_hostname": self.agent_hostname,
            "last_seen": self.agent_last_seen,
        })

    async def handle_ui_msg(self, ws: WebSocket, msg: dict):
        t = msg.get("type")
        if t == "get_activities":
            sid = msg.get("session_id", "")
            entries = self.activities.get(sid, [])
            await ws.send_text(json.dumps({
                "type": "activity", "session_id": sid,
                "challenge_id": None, "entries": entries,
            }, ensure_ascii=False))
        elif t in ("chat", "set_model", "restart_master"):
            ok = await self.send_agent(msg)
            if not ok:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "message": "容器未连接，指令未送达。请确认容器已启动且网络可达本机。",
                }, ensure_ascii=False))


hub: Hub  # 在 main() 中初始化


@app.websocket("/agent")
async def agent_ws(ws: WebSocket, token: str = Query(default="")):
    if token != hub.token:
        await ws.close(code=4401)
        log.warning("agent 连接 token 错误，已拒绝")
        return
    await ws.accept()
    if hub.agent is not None:
        try:
            await hub.agent.close(code=4000)
        except Exception:
            pass
    hub.agent = ws
    hub.agent_last_seen = time.time()
    log.info("容器 debug-agent 已连接")
    await hub.broadcast_status()
    try:
        while True:
            raw = await ws.receive_text()
            hub.agent_last_seen = time.time()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await hub.handle_agent_msg(msg)
    except WebSocketDisconnect:
        pass
    finally:
        if hub.agent is ws:
            hub.agent = None
        log.info("容器 debug-agent 断开")
        await hub.broadcast_status()


@app.websocket("/ui")
async def ui_ws(ws: WebSocket):
    await ws.accept()
    hub.uis.add(ws)
    try:
        await ws.send_text(json.dumps({
            "type": "status",
            "agent_connected": hub.agent is not None,
            "agent_hostname": hub.agent_hostname,
            "last_seen": hub.agent_last_seen,
        }, ensure_ascii=False))
        if hub.snapshot:
            await ws.send_text(json.dumps({"type": "snapshot", "payload": hub.snapshot}, ensure_ascii=False))
        if hub.model_state:
            await ws.send_text(json.dumps({k: v for k, v in hub.model_state.items() if k != "type"} | {"type": "model_state"}, ensure_ascii=False))
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await hub.handle_ui_msg(ws, msg)
    except WebSocketDisconnect:
        pass
    finally:
        hub.uis.discard(ws)


@app.get("/api/models")
def api_models(base_url: str = Query(...), api_key: str = Query(default="")):
    url = base_url.rstrip("/") + "/models"
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        models = [m.get("id") for m in data.get("data", []) if m.get("id")]
        return {"models": models}
    except Exception as e:
        return JSONResponse({"models": [], "error": str(e)}, status_code=200)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


def main():
    global hub
    p = argparse.ArgumentParser(description="AIxCTF 调试控制台")
    p.add_argument("--host", default=os.environ.get("DEBUG_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("DEBUG_PORT", "8790")))
    p.add_argument("--token", default=os.environ.get("DEBUG_TOKEN", "changeme"))
    args = p.parse_args()
    if args.token == "changeme":
        log.warning("正在使用默认 token 'changeme'，请用 --token 或 DEBUG_TOKEN 设置与容器一致的共享密钥")
    hub = Hub(token=args.token)
    log.info("调试控制台启动于 http://%s:%d （容器回连地址 http://<你的IP>:%d/agent?token=***）", args.host, args.port, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
