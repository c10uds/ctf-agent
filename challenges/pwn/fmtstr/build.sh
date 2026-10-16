#!/usr/bin/env bash
# 编译 fmtstr：PIE + NX + Full RELRO + Canary，附 libc/ld 供算偏移
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p dist
gcc -o dist/fmtstr src/fmtstr.c \
    -O0 -fstack-protector-all -fPIE -pie \
    -Wl,-z,relro,-z,now -D_FORTIFY_SOURCE=0
cp -f /usr/lib/x86_64-linux-gnu/libc.so.6 dist/libc.so.6
cp -f /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 dist/ld-linux-x86-64.so.2 2>/dev/null || true
echo "built: $(cd dist && ls -l fmtstr | awk '{print $5}') bytes; libc $(ldd --version | head -1 | awk '{print $NF}')"
