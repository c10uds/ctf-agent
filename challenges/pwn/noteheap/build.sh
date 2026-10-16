#!/usr/bin/env bash
# 编译 noteheap：No PIE + NX + Partial RELRO（GOT 可写）+ 无 Canary，附 libc/ld 供算偏移
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p dist
gcc -o dist/noteheap src/noteheap.c \
    -O0 -fno-stack-protector -no-pie -Wl,-z,relro
cp -f /usr/lib/x86_64-linux-gnu/libc.so.6 dist/libc.so.6
cp -f /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 dist/ld-linux-x86-64.so.2 2>/dev/null || true
echo "built: $(cd dist && ls -l noteheap | awk '{print $5}') bytes; libc $(ldd --version | head -1 | awk '{print $NF}')"
