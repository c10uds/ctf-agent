#!/usr/bin/env bash
# AIxCTF 附件解压与 ELF 候选列举（惰性辅助）。
# 只做解压和「哪些文件是 ELF」的提示，不自动跑归档——分析哪些二进制由 worker 自己决定。
# 用法: tools/archive_challenge.sh [题目目录，默认 .]
set -euo pipefail

dir="${1:-.}"
art="$dir/artifacts"
[ -d "$art" ] || { echo "未找到 $art" >&2; exit 1; }

ex="$art/extracted"
mkdir -p "$ex"
shopt -s nullglob

for f in "$art"/*.zip "$art"/*.tar "$art"/*.tar.gz "$art"/*.tgz \
         "$art"/*.tar.bz2 "$art"/*.tar.xz "$art"/*.gz "$art"/*.7z "$art"/*.rar; do
  echo "[*] 解压 $f"
  case "$f" in
    *.zip)           unzip -o -q "$f" -d "$ex" || echo "  (unzip 失败，忽略)" ;;
    *.tar.gz|*.tgz)  tar xzf "$f" -C "$ex" ;;
    *.tar.bz2)       tar xjf "$f" -C "$ex" ;;
    *.tar.xz)        tar xJf "$f" -C "$ex" ;;
    *.tar)           tar xf  "$f" -C "$ex" ;;
    *.gz)            gunzip -c "$f" > "$ex/$(basename "$f" .gz)" ;;
    *.7z)            7z x -y -o"$ex" "$f" >/dev/null || echo "  (无 7z，忽略)" ;;
    *.rar)           unrar x -o+ "$f" "$ex/" >/dev/null || echo "  (无 unrar，忽略)" ;;
  esac
done

echo
echo "== ELF 候选（供你决定归档哪些）=="
found=0
while IFS= read -r -d '' f; do
  desc="$(file -b "$f" 2>/dev/null || true)"
  case "$desc" in
    *ELF*) printf '  %s\n      %s\n' "$f" "$desc"; found=1 ;;
  esac
done < <(find "$art" -type f -print0)
[ "$found" = 1 ] || echo "  （未发现 ELF：可能是 web/脚本题，或需手动处理）"

echo
echo "== 建议（按需执行；归档哪些二进制由你决定）=="
echo "  1) 用 ghidra MCP import_binary 导入要分析的二进制（至少主程序）"
echo "  2) 归档：python3 /app/tools/ghidra_export.py --binary <名字> \\"
echo "            --binary-path <路径> --out $dir/analysis/<名字>"
echo "     需要算偏移时再对 libc/ld 单独跑一次；不分析的文件不必归档"
