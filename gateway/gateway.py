#!/usr/bin/env python3
"""AIxCTF 本地网关：LLM 转发 + 观测面板后端。

一个进程干三件事：
1) 反向 WS 隧道（容器侧 llm-forwarder 连入）：LLM 请求转发、事件上行、chat 下行；
2) LLM 转发：容器内 opencode → 这里 → 真实上游（重写 model/key，流式回传）；
3) 观测面板：托管前端静态文件 + /api/snapshot + /api/stream(SSE) + /api/history + /api/chat。

事件模型：容器侧把 llm_req / llm_resp / fs / proc / metrics / env / heartbeat / chat
事件经隧道推上来，本进程维护内存快照 + 环形缓冲 + JSONL 落盘，并以 SSE 实时广播给浏览器
（推流而非轮询）。

用法：
  python gateway.py --config gateway.config.json
  python gateway.py --upstream https://api.example.com/v1 --key sk-xxx --model gpt-4o-mini
"""
import argparse
import json
import logging
import mimetypes
import os
import queue
import sys
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests
from websockets.sync.server import serve

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger("llm-gateway")

PREVIEW = 200            # 列表行里的一行摘要
DETAIL_MSG = 800         # 展开视图：单条消息正文上限（字符）
DETAIL_MSGS = 24         # 展开视图：保留的消息条数（优先首条 system + 最近若干条）
DETAIL_TEXT = 6000       # 展开视图：响应正文上限
DETAIL_REASON = 4000     # 展开视图：思考过程上限
DETAIL_ARGS = 1200       # 展开视图：单次工具调用参数上限
SNAP_LLM_DETAIL = 60     # 快照/回放里保留完整详情的最近请求数（更早的只留摘要）
HEAVY_LLM = ("messages", "text", "reasoning", "tool_calls", "tools")
RING_SIZE = 500
HOP_HEADERS = {"host", "content-length", "connection", "authorization", "accept-encoding",
               "transfer-encoding", "content-encoding"}


# ---------------------------------------------------------------- 事件总线

class Hub:
    """内存快照 + 环形缓冲 + JSONL 落盘 + SSE 订阅者广播。"""

    def __init__(self, logs_dir: Path):
        self.lock = threading.Lock()
        self.subs: list[queue.Queue] = []
        self.ring: dict[str, deque] = defaultdict(lambda: deque(maxlen=RING_SIZE))
        self.state: dict = {
            "container": None, "metrics": None, "proc": None,
            "workers": {}, "files": {}, "scoreboard": [],
            "llm": [], "chat": [], "environments": [], "requests": [],
        }
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._log_files: dict[str, object] = {}
        self._load_recent()

    # -- 启动时从 JSONL 回放最近事件（页面/网关重启都不丢历史）
    def _load_recent(self, per_topic: int = 300):
        topics = ("hello", "scoreboard", "env", "fs", "llm_req", "llm_resp", "chat")
        for topic in topics:
            path = self.logs_dir / f"{topic}.jsonl"
            if not path.is_file():
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    lines = list(deque(f, maxlen=per_topic))
            except OSError:
                continue
            events = []
            for line in lines:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(e, dict) and e.get("topic") == topic:
                    events.append(e)
            events.sort(key=lambda e: e.get("ts") or 0)
            for e in events:
                self.ring[topic].append(e)
                try:
                    d = dict(e.get("data") or {})
                    d.setdefault("ts", e.get("ts"))   # 老日志也补上时间戳
                    self._merge_state(topic, d)
                except Exception:
                    continue
        if any(self.ring.values()):
            log.info("已从日志回放事件：%s",
                     ", ".join(f"{k}={len(v)}" for k, v in self.ring.items() if v))

    # -- 落盘
    def _append_log(self, topic: str, event: dict):
        try:
            fh = self._log_files.get(topic)
            if fh is None:
                fh = open(self.logs_dir / f"{topic}.jsonl", "a", encoding="utf-8")
                self._log_files[topic] = fh
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            fh.flush()
        except Exception as exc:  # 落盘失败不影响实时观测
            log.debug("写日志失败 %s: %s", topic, exc)

    # -- 状态归并
    def _merge_state(self, topic: str, data: dict):
        s = self.state
        if topic == "hello":
            s["container"] = data
        elif topic == "metrics":
            s["metrics"] = data
        elif topic == "proc":
            s["proc"] = data
            s["workers"] = {w["id"]: w for w in data.get("workers", [])}
        elif topic == "env":
            s["environments"] = data.get("environments", [])
            s["requests"] = data.get("requests", [])
        elif topic == "scoreboard":
            s["scoreboard"] = data.get("rows", [])
        elif topic == "fs":
            path = data.get("path")
            if path:
                entry = dict(s["files"].get(path) or {})
                entry.update({k: v for k, v in data.items() if v is not None})
                if data.get("deleted"):
                    entry["tail"] = ""
                s["files"][path] = entry
        elif topic == "llm_req":
            s["llm"].append(data)
            del s["llm"][:-RING_SIZE]
        elif topic == "llm_resp":
            rid = data.get("id")
            for item in reversed(s["llm"]):
                if item.get("id") == rid:
                    item.update({k: v for k, v in data.items() if v is not None and k != "preview"})
                    if data.get("preview"):
                        item["resp_preview"] = data["preview"]
                    break
        elif topic == "chat":
            cid = data.get("id")
            for item in s["chat"]:
                if item.get("id") == cid:
                    if data.get("delta"):
                        item["text"] = (item.get("text") or "") + data["delta"]
                    for k, v in data.items():
                        if v is not None and k != "delta":
                            item[k] = v
                    break
            else:
                s["chat"].append({k: v for k, v in data.items() if k != "delta"})
            del s["chat"][:-RING_SIZE]

    def publish(self, topic: str, data: dict):
        ts = data.get("ts") or time.time()
        payload = dict(data)
        payload.setdefault("ts", ts)   # 事件时间随 data 一起下发，前端才能显示"日志时间"
        event = {"topic": topic, "ts": ts, "data": payload}
        with self.lock:
            self.ring[topic].append(event)
            self._merge_state(topic, payload)
            subs = list(self.subs)
            self._append_log(topic, event)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self.lock:
            self.subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self.lock:
            if q in self.subs:
                self.subs.remove(q)

    def snapshot(self) -> dict:
        with self.lock:
            st = dict(self.state)
            st["llm"] = self._trim_llm(list(st.get("llm") or []))
            return json.loads(json.dumps(st, ensure_ascii=False, default=str))

    def recent(self, topics: list[str] | None, limit: int) -> list[dict]:
        with self.lock:
            if topics:
                items = [e for t in topics for e in self.ring.get(t, ())]
            else:
                items = [e for dq in self.ring.values() for e in dq]
            items.sort(key=lambda e: e.get("ts") or 0)
            items = items[-limit:]
            keep_ids = self._detail_ids()
        out = []
        for e in items:
            d = e.get("data") or {}
            if e.get("topic") in ("llm_req", "llm_resp") and d.get("id") not in keep_ids:
                out.append({"topic": e.get("topic"), "ts": e.get("ts"), "data": slim_llm(d)})
            else:
                out.append(e)
        return out

    # -- 详情只保留最近若干条：快照/回放里更早的请求只留摘要，避免几 MB 的载荷
    def _trim_llm(self, items: list) -> list:
        cut = max(0, len(items) - SNAP_LLM_DETAIL)
        return [slim_llm(e) for e in items[:cut]] + items[cut:]

    def _detail_ids(self) -> set:
        return {e.get("id") for e in (self.state.get("llm") or [])[-SNAP_LLM_DETAIL:]}


# ---------------------------------------------------------------- LLM 路由

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
HUB: Hub
TOKEN = "changeme"


def text_of(content) -> str:
    """把 OpenAI 风格的 content（字符串或 parts 数组）压成纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for p in content:
            if not isinstance(p, dict):
                continue
            if p.get("text") is not None:
                out.append(str(p.get("text")))
            elif p.get("type") == "tool_use":
                out.append(f"[tool_use {p.get('name')}]")
            elif p.get("type") in ("image_url", "image", "input_image"):
                out.append("[image]")
        return "\n".join(out)
    return "" if content is None else str(content)


def clip(s: str, limit: int) -> tuple[str, bool]:
    return (s, False) if len(s) <= limit else (s[:limit], True)


def slim_llm(data: dict) -> dict:
    """只留列表行需要的摘要，去掉展开视图里的大字段（消息/正文/思考）。"""
    return {k: v for k, v in data.items() if k not in HEAVY_LLM}


def describe_request(body: str) -> dict:
    """请求体 → 展开视图所需的字段：参数、消息（截断）、工具名。"""
    try:
        j = json.loads(body)
    except Exception:
        return {"body_len": len(body), "parse_error": True}
    if not isinstance(j, dict):
        return {"body_len": len(body), "parse_error": True}
    msgs = j.get("messages") if isinstance(j.get("messages"), list) else []
    if len(msgs) > DETAIL_MSGS:
        kept = [msgs[0]] + msgs[-(DETAIL_MSGS - 1):]
    else:
        kept = msgs
    out_msgs = []
    for m in kept:
        if not isinstance(m, dict):
            continue
        t = text_of(m.get("content"))
        text, cut = clip(t, DETAIL_MSG)
        out_msgs.append({"role": str(m.get("role") or "?"), "len": len(t),
                         "text": text, "truncated": cut})
    tools = []
    raw_tools = j.get("tools")
    if isinstance(raw_tools, list):
        for t in raw_tools:
            if isinstance(t, dict):
                fn = t.get("function") if isinstance(t.get("function"), dict) else {}
                tools.append(str(fn.get("name") or t.get("name") or "?"))
    params = {k: v for k, v in j.items() if k not in ("messages", "tools")}
    return {"params": params, "message_count": len(msgs), "messages": out_msgs,
            "messages_trimmed": len(msgs) > len(kept), "tools": tools, "body_len": len(body)}


def last_message_preview(body: str) -> str:
    """列表行摘要：优先最后一条 user 消息；没有 user（如纯 tool 续跑）就退回最后一条并标角色。"""
    try:
        msgs = json.loads(body).get("messages") or []
    except Exception:
        return ""
    for m in reversed(msgs):
        if isinstance(m, dict) and m.get("role") == "user":
            return text_of(m.get("content"))[:PREVIEW].replace("\n", " ")
    for m in reversed(msgs):
        if not isinstance(m, dict):
            continue
        t = text_of(m.get("content")).replace("\n", " ").strip()
        if t:
            return f"[{m.get('role')}] {t}"[:PREVIEW]
    return ""


def proxy(method: str, path: str, headers: dict, body: str, req_meta: dict | None = None):
    """转发一次 LLM 请求；返回 (status, headers, chunk_iter)。异常抛 RuntimeError。"""
    base_url, api_key, real_model = ROUTER.snapshot()
    if not path.startswith("/v1"):
        raise RuntimeError(f"仅支持 /v1 路径: {path}")
    url = base_url + path[3:]

    out_headers = {k: v for k, v in headers.items() if k.lower() not in HOP_HEADERS}
    out_headers["Authorization"] = f"Bearer {api_key}"
    out_headers["Accept-Encoding"] = "identity"
    out_headers["Content-Type"] = "application/json"

    orig_model, stream = None, None
    out_body = body
    try:
        j = json.loads(body)
        orig_model = j.get("model")
        stream = j.get("stream")
        if real_model:
            j["model"] = real_model
            out_body = json.dumps(j, ensure_ascii=False)
    except Exception:
        pass

    meta = dict(req_meta or {})
    prefix = meta.get("prefix", "")

    if HUB is not None:
        req_event = {
            "id": meta.get("id"), "agent": meta.get("agent"), "challenge_id": meta.get("challenge_id"),
            "prefix": prefix, "model": real_model or orig_model, "orig_model": orig_model,
            "stream": stream, "preview": last_message_preview(body), "path": path,
        }
        req_event.update(describe_request(body))   # 展开视图：messages / params / tools
        HUB.publish("llm_req", req_event)

    t0 = time.time()
    r = requests.request(method, url, headers=out_headers, data=out_body.encode("utf-8"),
                         stream=True, timeout=(15, 600))
    status = r.status_code
    if status != 200:
        content = r.content.decode("utf-8", "replace")[:500]
        r.close()
        if HUB is not None:
            HUB.publish("llm_resp", {"id": meta.get("id"), "agent": meta.get("agent"),
                                     "challenge_id": meta.get("challenge_id"), "status": status,
                                     "dur": round(time.time() - t0, 2), "error": content,
                                     "preview": content[:PREVIEW]})
        raise RuntimeError(f"上游返回 {status}: {content}")

    preview_buf: list[str] = []
    reason_buf: list[str] = []
    calls: dict[int, dict] = {}
    finish: list[str] = []
    text_len = reason_len = 0
    usage: dict = {}

    def chunks():
        nonlocal text_len, reason_len
        try:
            for data in r.iter_content(chunk_size=4096, decode_unicode=False):
                if not data:
                    continue
                text = data.decode("utf-8", "replace")
                for line in text.splitlines():
                    if not line.startswith("data:") or "[DONE]" in line:
                        continue
                    try:
                        cj = json.loads(line[5:].strip())
                    except Exception:
                        continue
                    if cj.get("usage"):
                        usage.update(cj["usage"])
                    choice = (cj.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    piece = delta.get("content") or ""
                    if piece and text_len < DETAIL_TEXT:
                        preview_buf.append(piece)
                        text_len += len(piece)
                    think = delta.get("reasoning_content") or delta.get("reasoning") or ""
                    if think and reason_len < DETAIL_REASON:
                        reason_buf.append(think)
                        reason_len += len(think)
                    for tc in (delta.get("tool_calls") or []):
                        if not isinstance(tc, dict):
                            continue
                        slot = calls.setdefault(int(tc.get("index") or 0), {"name": "", "args": ""})
                        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                        if fn.get("name"):
                            slot["name"] = str(fn["name"])
                        if fn.get("arguments"):
                            slot["args"] = (slot["args"] + str(fn["arguments"]))[:DETAIL_ARGS]
                    if choice.get("finish_reason"):
                        finish.append(str(choice["finish_reason"]))
                yield text
        finally:
            r.close()
            dur = round(time.time() - t0, 2)
            text_join, reason_join = "".join(preview_buf), "".join(reason_buf)
            log.info("[响应] %s %s status=%d dur=%.1fs tokens=%s | %s",
                     method, path, status, dur, usage.get("total_tokens", "-"),
                     text_join[:PREVIEW].replace("\n", " "))
            if HUB is not None:
                HUB.publish("llm_resp", {
                    "id": meta.get("id"), "agent": meta.get("agent"),
                    "challenge_id": meta.get("challenge_id"), "status": status, "dur": dur,
                    "tokens": usage.get("total_tokens"),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "preview": text_join[:PREVIEW].replace("\n", " "),
                    "text": text_join, "text_truncated": text_len >= DETAIL_TEXT,
                    "reasoning": reason_join,
                    "reasoning_truncated": reason_len >= DETAIL_REASON,
                    "finish_reason": finish[-1] if finish else None,
                    "tool_calls": [calls[k] for k in sorted(calls)],
                })

    log.info("[请求] %s %s agent=%s challenge=%s model=%s→%s | %s",
             method, path, meta.get("agent"), meta.get("challenge_id"),
             orig_model, real_model or orig_model, last_message_preview(body))
    return status, dict(r.headers), chunks()


# ---------------------------------------------------------------- 隧道端（容器反向连接）

TUNNEL_LOCK = threading.Lock()
TUNNEL_WS = None
CHAT_SEQ = 0


def tunnel_send(frame: dict) -> bool:
    with TUNNEL_LOCK:
        ws = TUNNEL_WS
    if ws is None:
        return False
    try:
        ws.send(json.dumps(frame, ensure_ascii=False))
        return True
    except Exception as exc:
        log.warning("隧道发送失败：%s", exc)
        return False


def tunnel_handler(ws):
    global TUNNEL_WS
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
    with TUNNEL_LOCK:
        TUNNEL_WS = ws
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
            t = f.get("type")
            if t == "http_req":
                threading.Thread(target=handle_tunnel_req, args=(ws, f), daemon=True).start()
            elif t == "event":
                HUB.publish(f.get("topic", "unknown"), f.get("data") or {})
            elif t == "hello":
                HUB.publish("hello", f.get("data") or {})
            else:
                log.debug("未知隧道帧：%s", t)
    except Exception as exc:
        log.info("隧道读循环结束：%s", exc)
    finally:
        with TUNNEL_LOCK:
            if TUNNEL_WS is ws:
                TUNNEL_WS = None
        HUB.publish("hello", {"connected": False})
        log.info("隧道断开：%s", peer)


def handle_tunnel_req(ws, f: dict):
    rid = f.get("id")
    meta = {"id": rid, "agent": f.get("agent"), "challenge_id": f.get("challenge_id"),
            "prefix": f.get("prefix")}
    try:
        status, headers, chunks = proxy(f.get("method", "POST"), f.get("path", ""),
                                        f.get("headers") or {}, f.get("body") or "", meta)
        ws.send(json.dumps({"type": "http_resp_begin", "id": rid, "status": status,
                            "headers": {k: v for k, v in headers.items() if k.lower() not in HOP_HEADERS}},
                           ensure_ascii=False))
        for c in chunks:
            ws.send(json.dumps({"type": "http_resp_chunk", "id": rid, "data": c}, ensure_ascii=False))
        ws.send(json.dumps({"type": "http_resp_end", "id": rid}, ensure_ascii=False))
    except Exception as exc:
        log.warning("隧道请求 %s 失败：%s", rid, exc)
        try:
            ws.send(json.dumps({"type": "http_resp_error", "id": rid, "message": str(exc)},
                               ensure_ascii=False))
        except Exception:
            pass


# ---------------------------------------------------------------- 本地直连 LLM 端

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
            status, rheaders, chunks = proxy(self.command, self.path, headers, body,
                                             {"agent": "direct"})
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
        except Exception as exc:
            data = json.dumps({"error": str(exc)}, ensure_ascii=False).encode()
            try:
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                pass


# ---------------------------------------------------------------- 观测面板 HTTP（SSE）

STATIC_DIR: Path | None = None


class PanelHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        log.debug("panel " + fmt, *args)

    # -- 工具
    def _json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8", "replace"))
        except Exception:
            return {}

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/snapshot":
            return self._json(HUB.snapshot())
        if path == "/api/stream":
            return self._sse()
        if path == "/api/history":
            return self._history()
        return self._static(path)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/chat":
            return self._chat()
        self._json({"error": "not found"}, 404)

    # -- SSE 实时推流
    def _sse(self):
        q = HUB.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            def write_event(topic: str, data: dict):
                payload = json.dumps({"topic": topic, "data": data}, ensure_ascii=False, default=str)
                self.wfile.write(f"event: {topic}\ndata: {payload}\n\n".encode("utf-8"))

            write_event("snapshot", HUB.snapshot())
            for e in HUB.recent(["llm_req", "llm_resp", "chat", "env", "metrics", "hello",
                                 "scoreboard", "fs"], 200):
                write_event("replay", e)
            self.wfile.flush()

            while True:
                try:
                    event = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                payload = json.dumps(event, ensure_ascii=False, default=str)
                self.wfile.write(f"event: {event['topic']}\ndata: {payload}\n\n".encode("utf-8"))
                self.wfile.flush()
        except Exception as exc:
            log.debug("SSE 连接结束：%s", exc)
        finally:
            HUB.unsubscribe(q)

    def _history(self):
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        topics = qs.get("topic")
        limit = int((qs.get("limit") or ["200"])[0])
        items = HUB.recent(topics, limit)
        challenge = qs.get("challenge", [None])[0]
        if challenge:
            items = [e for e in items if str((e.get("data") or {}).get("challenge_id")) == str(challenge)]
        self._json(items)

    def _chat(self):
        body = self._read_body()
        text = (body.get("text") or "").strip()
        if not text:
            return self._json({"error": "empty text"}, 400)
        global CHAT_SEQ
        with TUNNEL_LOCK:
            CHAT_SEQ += 1
            cid = CHAT_SEQ
        if not tunnel_send({"type": "chat_req", "id": cid, "text": text}):
            return self._json({"error": "隧道未连接（容器侧未上线）"}, 503)
        HUB.publish("chat", {"id": cid, "role": "user", "text": text, "done": True})
        return self._json({"id": cid})

    # -- 静态文件（SPA）
    def _static(self, path: str):
        if STATIC_DIR is None or not STATIC_DIR.exists():
            data = ("面板静态文件未构建。请在 dashboard/ 下执行 `npm install && npm run build`，"
                    "然后用 --static dashboard/dist 启动。\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        rel = path.lstrip("/") or "index.html"
        target = (STATIC_DIR / rel).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            return self._json({"error": "forbidden"}, 403)
        if not target.is_file():
            target = STATIC_DIR / "index.html"
        if not target.is_file():
            return self._json({"error": "not found"}, 404)
        data = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if target.name == "index.html":
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


# ---------------------------------------------------------------- 启动

def main():
    global TOKEN, ROUTER, HUB, STATIC_DIR
    p = argparse.ArgumentParser(description="AIxCTF 本地网关 + 观测面板")
    p.add_argument("--config", help="gateway.config.json 路径")
    p.add_argument("--port", type=int, help="隧道监听端口（默认 8790）")
    p.add_argument("--http-port", type=int, help="本地直连 LLM 端口（默认 8788，0 关闭）")
    p.add_argument("--dashboard-port", type=int, help="观测面板端口（默认 8791，0 关闭）")
    p.add_argument("--dashboard-host", help="面板绑定地址（默认 127.0.0.1）")
    p.add_argument("--static", help="前端构建产物目录（默认 dashboard/dist）")
    p.add_argument("--logs-dir", help="事件 JSONL 落盘目录（默认 gateway/logs）")
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
    dash_port = (args.dashboard_port if args.dashboard_port is not None
                 else cfg.get("dashboard_port", 8791))
    dash_host = args.dashboard_host or cfg.get("dashboard_host", "127.0.0.1")
    static_dir = Path(args.static or cfg.get("static", "dashboard/dist"))
    logs_dir = Path(args.logs_dir or cfg.get("logs_dir", "gateway/logs"))

    TOKEN = args.token or cfg.get("token", "changeme")
    up = cfg.get("upstream") or {}
    ROUTER = Router(
        base_url=args.upstream or up.get("base_url", ""),
        api_key=args.key or up.get("api_key", ""),
        model=args.model or up.get("model", ""),
    )
    HUB = Hub(logs_dir)
    STATIC_DIR = static_dir

    if TOKEN == "changeme":
        log.warning("使用默认 token 'changeme'，请通过 --token 或配置文件设置共享密钥")
    if not ROUTER.base_url:
        log.warning("未配置上游 base_url，转发将失败（--upstream 或配置文件 upstream.base_url）")

    if http_port:
        httpd = ThreadingHTTPServer(("0.0.0.0", http_port), DirectHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        log.info("本地直连 LLM 端口：http://127.0.0.1:%d/v1", http_port)

    if dash_port:
        panel = ThreadingHTTPServer((dash_host, dash_port), PanelHandler)
        threading.Thread(target=panel.serve_forever, daemon=True).start()
        state = "已构建" if (STATIC_DIR / "index.html").is_file() else "未构建（请 npm run build）"
        log.info("观测面板：http://%s:%d  静态文件 %s [%s]", dash_host, dash_port, STATIC_DIR, state)

    log.info("隧道监听 0.0.0.0:%d（容器侧连接 ws://<你的IP>:%d/tunnel?token=***）", port, port)
    with serve(tunnel_handler, "0.0.0.0", port, max_size=None) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
