#!/usr/bin/env bash
# 编译 5 道 pwn（需要 gcc + aarch64-linux-gnu-gcc）
set -euo pipefail
cd "$(dirname "$0")"

build() {  # name, extra flags...
  local name="$1"; shift
  mkdir -p "$name/dist"
  gcc -o "$name/dist/$name" "$name/src/$name.c" -O0 -D_FORTIFY_SOURCE=0 "$@"
  cp -f /usr/lib/x86_64-linux-gnu/libc.so.6 "$name/dist/libc.so.6"
  cp -f /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 "$name/dist/ld-linux-x86-64.so.2" 2>/dev/null || true
  echo "built $name ($(stat -c%s "$name/dist/$name") bytes)"
}

build fmt_once        -fstack-protector-all -fPIE -pie -Wl,-z,relro,-z,now
build heap_doublefree -fno-stack-protector -no-pie -Wl,-z,relro
build ret2dlresolve   -fno-stack-protector -no-pie -Wl,-z,relro,-z,lazy
build sandbox_orw     -fno-stack-protector -no-pie -static

mkdir -p arm_overflow/dist
aarch64-linux-gnu-gcc -o arm_overflow/dist/arm_overflow arm_overflow/src/arm_overflow.c \
    -O0 -fno-stack-protector -no-pie -static
echo "built arm_overflow ($(stat -c%s arm_overflow/dist/arm_overflow) bytes, aarch64 static)"
