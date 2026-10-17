#!/usr/bin/env python3
"""AIxCTF 容器侧「转发 + 观察 + 桥接」进程。

一个进程干三件事（共用同一条反向 WS 隧道）：
1) LLM 转发：127.0.0.1:8787 ← 容器内 opencode，逐 chunk 经隧道送到本地网关；
2) 事件采集：把 LLM 请求/响应、状态文件、进程、资源指标、环境队列实时上报（topic=event）；
3) chat 桥：收到 chat_req 时在 /app/customer 下跑 ctf-customer，把回复流式回传。

归属（哪个 agent / 哪道题）：按请求来源进程的 cwd 精确判定（/proc），
worker → /app/work/<id>、customer → /app/customer、其余 → master。失败则回退正则。

环境变量：
  CTF_CONFIG             配置文件路径（默认 /app/ctf.config.json）
  LLM_FORWARD_PORT       监听端口（默认 8787）
  GATEWAY_INJECT_CONFIG  若设置（如 /app/opencode.json），启动时把 gateway provider 注入该配置
  CTF_APP_DIR            应用根目录（默认 /app）
  CTF_CUSTOMER_DIR       customer 会话目录（默认 /app/customer）
"""
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import websocket  # websocket-client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger("llm-forwarder")

CONFIG_PATH = os.environ.get("CTF_CONFIG", "/app/ctf.config.json")
LISTEN_PORT = int(os.environ.get("LLM_FORWARD_PORT", "8787"))
INJECT_PATH = os.environ.get("GATEWAY_INJECT_CONFIG", "")
APP_DIR = os.environ.get("CTF_APP_DIR", "/app")
CUSTOMER_DIR = os.environ.get("CTF_CUSTOMER_DIR", os.path.join(APP_DIR, "customer"))
WATCH_INTERVAL = float(os.environ.get("CTF_WATCH_INTERVAL", "1.0"))

HOP_HEADERS = {"host", "content-length", "connection", "authorization", "accept-encoding"}
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
WORK_RE = re.compile(r"/work/(\d+)")


def load_gateway_addr():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    g = cfg.get("gateway") or {}
    url, token = g["server_url"].rstrip("/"), g.get("token", "")
    return url.replace("http", "ws", 1) + "/tunnel?token=" + token, url


def inject_opencode_config():
    """把 gateway provider 写入 opencode 配置（幂等）。"""
    if not INJECT_PATH:
        return
    try:
        with open(INJECT_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("provider", {})["gateway"] = {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Local Gateway",
            "options": {"baseURL": f"http://127.0.0.1:{LISTEN_PORT}/v1", "apiKey": "gateway"},
            "models": {"auto": {"name": "auto"}},
        }
        cfg["model"] = "gateway/auto"
        with open(INJECT_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        log.info("已注入 gateway provider → %s (model=gateway/auto)", INJECT_PATH)
    except Exception:
        log.exception("注入 opencode 配置失败")


# ------------------------------------------------------------------ 归属判定

class Identifier:
    """按「发起请求的进程 cwd」判定 agent 与题目，精确且零配置。"""

    def __init__(self, listen_port: int):
        self.listen_port = listen_port
        self.cache: dict[int, tuple] = {}
        self.lock = threading.Lock()

    def identify(self, client_port: int, body: str) -> tuple[str, int | None]:
        now = time.time()
        with self.lock:
            hit = self.cache.get(client_port)
            if hit and now - hit[0] < 10:
                return hit[1], hit[2]
        agent, cid = None, None
        cwd = self._cwd_for_port(client_port)
        if cwd:
            agent, cid = self._classify(cwd)
        if agent is None:
            agent, cid = self._guess_from_body(body)
        with self.lock:
            self.cache[client_port] = (now, agent, cid)
        return agent, cid

    @staticmethod
    def _classify(cwd: str):
        cwd = cwd.rstrip("/")
        m = WORK_RE.search(cwd)
        if m:
            return "worker", int(m.group(1))
        if cwd == CUSTOMER_DIR:
            return "customer", None
        if cwd == APP_DIR:
            return "master", None
        return None, None

    @staticmethod
    def _guess_from_body(body: str) -> tuple[str, int | None]:
        cid = None
        m = WORK_RE.search(body)
        if m:
            cid = int(m.group(1))
        agent = "unknown"
        if "CTF-Master" in body:
            agent = "master"
        elif "CTF-Worker" in body:
            agent = "worker"
        elif "CTF-Customer" in body:
            agent = "customer"
        return agent, cid

    def _cwd_for_port(self, client_port: int) -> str | None:
        inode = self._find_client_inode(client_port)
        if inode is None:
            return None
        pid = self._pid_for_inode(inode)
        if pid is None:
            return None
        try:
            return os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            return None

    def _find_client_inode(self, client_port: int) -> str | None:
        hex_port = f"{client_port:04X}"
        for path in ("/proc/net/tcp", "/proc/net/tcp6"):
            try:
                with open(path, encoding="utf-8") as f:
                    next(f, None)
                    for line in f:
                        parts = line.split()
                        if len(parts) < 10:
                            continue
                        local, rem, inode = parts[1], parts[2], parts[9]
                        if local.endswith(":" + hex_port) and rem.endswith(f":{self.listen_port:04X}"):
                            return inode
            except OSError:
                continue
        return None

    @staticmethod
    def _pid_for_inode(inode: str) -> int | None:
        target = f"socket:[{inode}]"
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            fd_dir = f"/proc/{entry}/fd"
            try:
                for fd in os.listdir(fd_dir):
                    try:
                        if os.readlink(os.path.join(fd_dir, fd)) == target:
                            return int(entry)
                    except OSError:
                        continue
            except OSError:
                continue
        return None


# ------------------------------------------------------------------ 隧道

class Tunnel:
    """反向 WS 隧道：多路复用 HTTP 请求 + 事件上行 + chat 下行。"""

    def __init__(self, url: str):
        self.url = url
        self.ws = None
        self.send_lock = threading.Lock()
        self.pending: dict[int, queue.Queue] = {}
        self.pending_lock = threading.Lock()
        self.connected = threading.Event()
        self._next_id = 0
        self.on_control = None  # 由 ChatBridge 注入
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        backoff = 2
        while True:
            try:
                log.info("连接本地网关 %s", self.url.split("?")[0])
                ws = websocket.create_connection(self.url, ping_interval=25, ping_timeout=10)
                with self.send_lock:
                    self.ws = ws
                self.connected.set()
                backoff = 2
                log.info("隧道已建立")
                self.send_event("hello", container_info())
                while True:
                    raw = ws.recv()
                    if not raw:
                        raise ConnectionError("ws closed")
                    self._on_frame(json.loads(raw))
            except Exception as e:
                log.warning("隧道断开：%s；%ds 后重连", e, backoff)
                self.connected.clear()
                with self.send_lock:
                    self.ws = None
                with self.pending_lock:
                    pending = list(self.pending.values())
                for q in pending:
                    q.put({"type": "http_resp_error", "message": f"tunnel disconnected: {e}"})
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def _on_frame(self, f: dict):
        t = f.get("type")
        if t == "chat_req":
            if self.on_control:
                self.on_control(f)
            return
        with self.pending_lock:
            q = self.pending.get(f.get("id"))
        if q:
            q.put(f)

    def request(self, method: str, path: str, headers: dict, body: str,
                agent: str | None = None, challenge_id: int | None = None):
        if not self.connected.is_set():
            raise RuntimeError("tunnel not connected（本地网关未连接）")
        with self.send_lock:
            self._next_id += 1
            rid = self._next_id
        q: queue.Queue = queue.Queue()
        with self.pending_lock:
            self.pending[rid] = q
        frame = {"type": "http_req", "id": rid, "method": method, "path": path,
                 "headers": headers, "body": body, "agent": agent, "challenge_id": challenge_id}
        self._send(frame)
        return rid, q

    def finish(self, rid: int):
        with self.pending_lock:
            self.pending.pop(rid, None)

    def send_event(self, topic: str, data: dict):
        self._send({"type": "event", "topic": topic, "data": data})

    def _send(self, f: dict):
        with self.send_lock:
            if not self.ws:
                return
            try:
                self.ws.send(json.dumps(f, ensure_ascii=False))
            except Exception as exc:
                log.debug("发送失败：%s", exc)


TUNNEL: Tunnel
IDENT: Identifier


def container_info() -> dict:
    try:
        uptime = float(open("/proc/uptime").read().split()[0])
    except Exception:
        uptime = 0
    return {"host": os.uname().nodename, "pid": os.getpid(), "app_dir": APP_DIR,
            "customer_dir": CUSTOMER_DIR, "uptime": uptime,
            "connected": True, "started_at": time.time()}


# ------------------------------------------------------------------ HTTP 代理端

class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        log.debug("http " + fmt, *args)

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def _err(self, status: int, message: str):
        data = json.dumps({"error": message}, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def _proxy(self):
        body = ""
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
            agent, cid = IDENT.identify(self.client_address[1], body)
            rid, q = TUNNEL.request(self.command, self.path, headers, body, agent, cid)
        except Exception as e:
            self._err(502, f"forwarder: {e}")
            return
        try:
            first = q.get(timeout=300)
            if first.get("type") == "http_resp_error":
                self._err(502, f"gateway: {first.get('message')}")
                return
            self.send_response(first.get("status", 200))
            for k, v in (first.get("headers") or {}).items():
                if k.lower() not in HOP_HEADERS and k.lower() not in ("transfer-encoding", "content-encoding"):
                    self.send_header(k, v)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            while True:
                f = q.get()
                t = f.get("type")
                if t == "http_resp_chunk":
                    data = (f.get("data") or "").encode("utf-8")
                    if data:
                        self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
                        self.wfile.flush()
                elif t == "http_resp_end":
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                    break
                elif t == "http_resp_error":
                    log.warning("请求 %d 中断：%s", rid, f.get("message"))
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                    break
        except Exception as e:
            log.warning("请求代理异常：%s", e)
        finally:
            TUNNEL.finish(rid)


# ------------------------------------------------------------------ 采集

class Watcher(threading.Thread):
    """周期采集状态文件 / 进程 / 指标 / 环境队列并上报。"""

    def __init__(self):
        super().__init__(daemon=True, name="watcher")
        self.seen: dict[str, tuple] = {}

    def run(self):
        while True:
            try:
                self.tick()
            except Exception:
                log.exception("采集异常")
            time.sleep(WATCH_INTERVAL)

    def tick(self):
        TUNNEL.send_event("metrics", self.metrics())
        TUNNEL.send_event("proc", self.procs())
        self.files_and_env()

    # -- 资源指标
    @staticmethod
    def metrics() -> dict:
        try:
            load = open("/proc/loadavg").read().split()[:3]
        except Exception:
            load = ["0", "0", "0"]
        mem_total = mem_avail = 0
        try:
            for line in open("/proc/meminfo"):
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    mem_avail = int(line.split()[1]) * 1024
        except Exception:
            pass
        try:
            du = shutil.disk_usage(APP_DIR)
            disk = {"total": du.total, "used": du.used, "free": du.free}
        except Exception:
            disk = {}
        try:
            uptime = float(open("/proc/uptime").read().split()[0])
        except Exception:
            uptime = 0
        opencode = 0
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                cmd = open(f"/proc/{entry}/cmdline", "rb").read().decode("utf-8", "replace")
            except OSError:
                continue
            if "opencode" in cmd:
                opencode += 1
        return {"load": [float(x) for x in load], "mem_total": mem_total,
                "mem_used": max(mem_total - mem_avail, 0), "disk": disk,
                "uptime": uptime, "opencode_procs": opencode, "ts": time.time()}

    # -- worker / master 进程
    @staticmethod
    def procs() -> dict:
        # 真实在跑的 ctf-worker 进程：按 cwd 映射到题号（worker.pid 可能是 setsid/包装 shell 的 pid）
        real: dict[int, int] = {}
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                comm = open(f"/proc/{entry}/comm").read().strip().lower()
                cmd = open(f"/proc/{entry}/cmdline", "rb").read().decode("utf-8", "replace")
            except OSError:
                continue
            # 只认真正的 opencode 进程；包装它的 bash -c 里同样含 "ctf-worker" 字样，要排除
            if "opencode" not in comm or "ctf-worker" not in cmd:
                continue
            try:
                cwd = os.readlink(f"/proc/{entry}/cwd")
            except OSError:
                continue
            m = WORK_RE.search(cwd)
            if m:
                real[int(m.group(1))] = int(entry)

        workers = []
        work_root = os.path.join(APP_DIR, "work")
        if os.path.isdir(work_root):
            for cid in sorted(os.listdir(work_root)):
                if not cid.isdigit():
                    continue
                pid_file = os.path.join(work_root, cid, "worker.pid")
                pid = None
                try:
                    pid = int(open(pid_file).read().strip())
                except Exception:
                    pass
                info = {"id": int(cid), "pid": real.get(int(cid)) or pid, "alive": False}
                if info["pid"]:
                    info.update(proc_stat(info["pid"]))
                if not info.get("alive") and pid and pid != info["pid"]:
                    info["pid"] = pid
                    info.update(proc_stat(pid))
                workers.append(info)
        master = {"pid": os.getpid(), "alive": True}
        return {"workers": workers, "master": master, "ts": time.time()}

    # -- 状态文件 + 环境队列
    def files_and_env(self):
        targets = []
        state_dir = os.path.join(APP_DIR, "state")
        for name in ("SCOREBOARD.md", "ENVIRONMENTS.md", "REQUESTS.md"):
            targets.append((os.path.join(state_dir, name), "state", None))
        req_dir = os.path.join(state_dir, "env-requests")
        if os.path.isdir(req_dir):
            for name in sorted(os.listdir(req_dir)):
                if name.endswith(".req"):
                    targets.append((os.path.join(req_dir, name), "req",
                                    int(name[:-4]) if name[:-4].isdigit() else None))
        work_root = os.path.join(APP_DIR, "work")
        if os.path.isdir(work_root):
            for cid in sorted(os.listdir(work_root)):
                if not cid.isdigit():
                    continue
                for name, kind in (("notes.md", "notes"), ("run.log", "log")):
                    targets.append((os.path.join(work_root, cid, name), kind, int(cid)))

        changed_env = False
        changed_score = False
        for path, kind, cid in targets:
            try:
                st = os.stat(path)
            except OSError:
                if self.seen.pop(path, None) is not None:
                    TUNNEL.send_event("fs", {"path": path, "rel": self.rel(path), "kind": kind,
                                             "challenge_id": cid, "deleted": True})
                    changed_env = True
                continue
            sig = (st.st_mtime, st.st_size)
            if self.seen.get(path) == sig:
                continue
            self.seen[path] = sig
            data = {"path": path, "rel": self.rel(path), "kind": kind, "challenge_id": cid,
                    "mtime": st.st_mtime, "size": st.st_size}
            if kind in ("notes", "log", "state", "req"):
                data["tail"] = tail_text(path, 4000)
            TUNNEL.send_event("fs", data)
            if kind in ("state", "req") and path.endswith(("ENVIRONMENTS.md", ".req")):
                changed_env = True
            if path.endswith("SCOREBOARD.md"):
                changed_score = True
        if changed_env:
            TUNNEL.send_event("env", self.env_state())
        if changed_score:
            TUNNEL.send_event("scoreboard", {"rows": parse_scoreboard(), "ts": time.time()})

    @staticmethod
    def rel(path: str) -> str:
        return os.path.relpath(path, APP_DIR).replace(os.sep, "/")

    @staticmethod
    def env_state() -> dict:
        environments = []
        env_md = os.path.join(APP_DIR, "state", "ENVIRONMENTS.md")
        header_words = {"challenge id", "题目id", "题目 id", "id"}
        aliases = {
            "id": ("challenge id", "id", "题目id", "题目 id"),
            "entry": ("name", "entry", "url", "题目", "入口", "入口（url / host:port）"),
            "since": ("since", "started", "启动时间", "时间"),
            "usage": ("holder", "usage", "用途", "用途（worker pid）", "worker"),
        }
        header = None
        pending = None
        try:
            for line in open(env_md, encoding="utf-8"):
                line = line.strip()
                if not line.startswith("|"):
                    continue
                cols = [c.strip() for c in line.strip("|").split("|")]
                if cols and all(set(c) <= set("-: ") for c in cols):
                    low = [c.lower() for c in (pending or [])]
                    if any(x in low for x in ("challenge id", "id", "题目id", "题目 id")) and any(
                            x in low for x in ("holder", "usage", "name", "entry", "url",
                                               "用途", "题目", "入口", "worker")):
                        header = pending
                    else:
                        header = None
                    pending = None
                    continue
                if header is None:
                    pending = cols
                    continue
                first = cols[0] if cols else ""
                if not first or first.lower() in header_words or set(first) <= set("-"):
                    continue
                if first in ("(none)", "（无）"):
                    continue
                row = {}
                for key, names in aliases.items():
                    idx = next((i for i, c in enumerate(header)
                                if c in names or any(c.startswith(n) for n in names)), None)
                    row[key] = cols[idx] if idx is not None and idx < len(cols) else ""
                if not row.get("id"):
                    row["id"] = first
                environments.append(row)
        except OSError:
            pass
        requests = []
        req_dir = os.path.join(APP_DIR, "state", "env-requests")
        if os.path.isdir(req_dir):
            for name in sorted(os.listdir(req_dir)):
                if not name.endswith(".req"):
                    continue
                item = {"file": name, "challenge_id": name[:-4], "preempted": False}
                try:
                    for line in open(os.path.join(req_dir, name), encoding="utf-8"):
                        if ":" in line:
                            k, v = line.split(":", 1)
                            item[k.strip()] = v.strip()
                            if k.strip() == "preempted_at":
                                item["preempted"] = True
                except OSError:
                    pass
                requests.append(item)
        return {"environments": environments, "requests": requests, "ts": time.time()}


def proc_stat(pid: int) -> dict:
    out = {"alive": False}
    try:
        fields = open(f"/proc/{pid}/stat").read().rsplit(") ", 1)[1].split()
        out["cpu_ticks"] = int(fields[11]) + int(fields[12])
    except Exception:
        return out
    try:
        for line in open(f"/proc/{pid}/status"):
            if line.startswith("VmRSS:"):
                out["rss"] = int(line.split()[1]) * 1024
    except Exception:
        pass
    try:
        out["started_at"] = os.path.getmtime(f"/proc/{pid}")
    except Exception:
        pass
    out["alive"] = True
    return out


def tail_text(path: str, limit: int) -> str:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > limit:
                f.seek(size - limit)
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def parse_scoreboard() -> list:
    """解析 state/SCOREBOARD.md 的表格为题目行（按表头列名映射，列序/中英文可变）。"""
    path = os.path.join(APP_DIR, "state", "SCOREBOARD.md")
    rows = []
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return rows

    aliases = {
        "id": ("id", "题目id", "题目 id", "#"),
        "title": ("name", "题目", "名称", "标题"),
        "category": ("category", "分类", "类型"),
        "score": ("score", "分值", "points"),
        "current_score": ("current_score", "current score", "当前分值"),
        "status": ("status", "状态"),
        "flag": ("flag",),
    }
    header = None
    pending = None
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if cols and all(set(c) <= set("-: ") for c in cols):
            # 分隔行：上一行才是表头；只认「id + status」这类计分板表头，忽略其它说明表格
            low = [c.lower() for c in (pending or [])]
            if ("status" in low or "状态" in low) and any(
                    x in low for x in ("id", "题目id", "题目 id")):
                header = pending
            else:
                header = None
            pending = None
            continue
        if header is None:
            pending = cols
            continue
        row = {}
        for key, names in aliases.items():
            idx = next((i for i, c in enumerate(header) if c.lower() in names), None)
            row[key] = cols[idx] if idx is not None and idx < len(cols) else ""
        if row.get("id", "").lower() in ("id", "题目id", "题目 id") or not row.get("id"):
            continue
        rows.append(row)
    return rows


# ------------------------------------------------------------------ chat 桥

class ChatBridge:
    """在 /app/customer 下驱动 ctf-customer 会话，回复流式回传。"""

    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.marker = os.path.join(CUSTOMER_DIR, ".session_started")
        threading.Thread(target=self._loop, daemon=True, name="chat-bridge").start()

    def submit(self, frame: dict):
        self.q.put(frame)

    def _loop(self):
        while True:
            frame = self.q.get()
            try:
                self._run(frame)
            except Exception as exc:
                log.exception("chat 失败")
                TUNNEL.send_event("chat", {"id": frame.get("id"), "role": "assistant",
                                           "error": str(exc), "done": True})

    def _run(self, frame: dict):
        cid = frame.get("id")
        text = frame.get("text") or ""
        TUNNEL.send_event("chat", {"id": cid, "role": "assistant", "delta": "", "done": False})
        os.makedirs(CUSTOMER_DIR, exist_ok=True)
        base = ["opencode", "run", "--agent", "ctf-customer", "--auto"]
        cmd = base + (["-c", text] if os.path.exists(self.marker) else [text])
        proc = subprocess.Popen(cmd, cwd=CUSTOMER_DIR, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1,
                                encoding="utf-8", errors="replace")
        try:
            open(self.marker, "w").close()
        except OSError:
            pass
        buf = []
        for line in proc.stdout:
            clean = ANSI_RE.sub("", line).rstrip("\n")
            if not clean.strip():
                continue
            buf.append(clean)
            TUNNEL.send_event("chat", {"id": cid, "role": "assistant", "delta": clean + "\n"})
        rc = proc.wait()
        TUNNEL.send_event("chat", {"id": cid, "role": "assistant", "done": True,
                                   "exit_code": rc, "text": "\n".join(buf)})


# ------------------------------------------------------------------ 启动

def main():
    global TUNNEL, IDENT
    ws_url, http_url = load_gateway_addr()
    inject_opencode_config()
    IDENT = Identifier(LISTEN_PORT)
    TUNNEL = Tunnel(ws_url)
    bridge = ChatBridge()
    TUNNEL.on_control = bridge.submit
    Watcher().start()
    srv = ThreadingHTTPServer(("127.0.0.1", LISTEN_PORT), ProxyHandler)
    log.info("LLM 转发器监听 http://127.0.0.1:%d → %s（含事件采集与 chat 桥）", LISTEN_PORT, http_url)
    srv.serve_forever()


if __name__ == "__main__":
    main()
