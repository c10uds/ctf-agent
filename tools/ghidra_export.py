#!/usr/bin/env python3
"""AIxCTF 二进制分析归档：把 Ghidra 对某个二进制的反编译结果按函数落盘到本地。

目的：一次分析、全部落盘，后续直接 read_file / grep 本地文件，避免把大段反编译内容
经 ghidra MCP 灌进模型上下文；上下文被重置（-c 续跑 / 容器重启）也不丢分析。

本工具**自建独立 Ghidra 工程**（默认 ./ghidra-export-projects）导入并分析二进制：
ghidra MCP 的工程（./ghidra-projects）在整个会话期间被 MCP 服务器加锁，无法并发打开，
因此不能复用；二进制由 --binary-path 指定，可见 ghidra MCP 与本地归档各用各的工程。

用法：
  python3 tools/ghidra_export.py --binary main --binary-path artifacts/main \\
      --out work/42/analysis/main
  python3 tools/ghidra_export.py --binary main --out ... --lazy   # 只出清单，不逐函数反编译

输出：
  <out>/INDEX.md        索引（sha256/生成时间/文件清单/全函数表/高危导入/读取示例）
  <out>/metadata.txt    架构/位宽/endian/编译器/hash/入口点
  <out>/functions.txt   全函数清单：地址 | 名称 | 大小 | 文件
  <out>/strings.txt     地址 | 字符串 | 所在函数
  <out>/imports.txt     导入符号（库|名称）
  <out>/src/<函数名>.c   逐函数反编译（文件名=函数名，非法字符已清洗、重名加地址后缀）
"""
import argparse
import os
import re
import sys
import time
import warnings
from pathlib import Path

INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

HIGH_RISK = (
    "gets", "strcpy", "strcat", "sprintf", "vsprintf", "scanf", "system",
    "popen", "exec", "read", "write", "printf", "free", "malloc", "memcpy",
    "setvbuf", "puts", "send", "recv", "fgets", "alloca",
)


def safe_name(name: str) -> str:
    s = name.replace("::", "__")
    s = INVALID_FS.sub("_", s)
    s = re.sub(r"\s+", "_", s)
    s = s.strip("._")
    if not s:
        s = "func"
    if len(s) > 120:
        s = s[:120]
    return s


def addr_str(address) -> str:
    return "0x" + str(address).lower()


def sort_key(addr_text: str) -> int:
    try:
        return int(addr_text.replace("0x", "").replace(":", ""), 16)
    except ValueError:
        return 0


def func_signature(func) -> str:
    for getter in (
        lambda: func.getPrototypeString(False, False),
        lambda: func.getSignature().getPrototypeString(False),
        lambda: str(func.getSignature()),
    ):
        try:
            s = getter()
            if s:
                return str(s)
        except Exception:
            continue
    return str(func.getName())


def func_names(functions) -> str:
    try:
        names = sorted(str(f.getName()) for f in functions)
    except Exception:
        return ""
    return ", ".join(names)


def open_program_ctx(args):
    import pyghidra

    if not args.binary_path:
        raise SystemExit("必须提供 --binary-path（本工具自建工程、自行导入分析）")
    if not os.path.isfile(args.binary_path):
        raise SystemExit(f"找不到二进制文件：{args.binary_path}")

    # 不要复用 ghidra MCP 的工程：MCP 服务器在整个会话期间一直持有该项目（my_project.lock），
    # 并发 openProject 会直接抛 Java Exception。因此本工具使用独立工程目录，自行导入+分析。
    print(f"[ghidra_export] 导入并分析 {args.binary_path}（工程 {args.project}）", file=sys.stderr)
    # pyghidra 3.x 把 open_program 标为 deprecated（仍可用且行为稳定），这里静音避免污染 worker 输出
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    return pyghidra.open_program(
        binary_path=args.binary_path,
        project_location=args.project,
        project_name=args.project_name,
        program_name=args.binary,
        analyze=True,
        nested_project_location=False,
    )


def write_metadata(program, out: Path) -> dict:
    from ghidra.framework import Application

    lang = program.getLanguage()
    meta = {
        "program": str(program.getName()),
        "executable_path": str(program.getExecutablePath()),
        "format": str(program.getExecutableFormat()),
        "sha256": str(program.getExecutableSHA256()),
        "language": str(program.getLanguageID()),
        "compiler": str(program.getCompilerSpec().getCompilerSpecID()),
        "address_size_bits": int(program.getDefaultPointerSize()) * 8,
        "endian": "big" if lang.isBigEndian() else "little",
        "image_base": addr_str(program.getImageBase()),
        "ghidra_version": str(Application.getApplicationVersion()),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    entries = [addr_str(a) for a in program.getSymbolTable().getExternalEntryPointIterator()]
    meta["entry_points"] = ", ".join(entries) or "-"
    lines = [f"{k}: {v}" for k, v in meta.items()]
    (out / "metadata.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return meta


def write_imports(program, out: Path) -> list:
    rows = []
    try:
        for sym in program.getSymbolTable().getExternalSymbols():
            name = str(sym.getName())
            try:
                lib = str(sym.getParentNamespace().getName())
            except Exception:
                lib = "-"
            rows.append((lib, name))
    except Exception as exc:
        print(f"[ghidra_export] 读取导入符号失败：{exc}", file=sys.stderr)
    rows.sort()
    text = "\n".join(f"{lib}|{name}" for lib, name in rows)
    (out / "imports.txt").write_text((text + "\n") if text else "", encoding="utf-8")
    return rows


def write_strings(program, out: Path, with_xrefs: bool) -> int:
    listing = program.getListing()
    refman = program.getReferenceManager()
    rows = []
    for data in listing.getDefinedData(True):
        if not data.isDefined():
            continue
        dt = str(data.getDataType().getName()).lower()
        if "string" not in dt and "unicode" not in dt:
            continue
        try:
            value = data.getValue()
        except Exception:
            value = None
        if not isinstance(value, str) or not value:
            continue
        value = value.replace("\n", "\\n").replace("\r", "\\r")[:200]
        where = ""
        if with_xrefs:
            funcs = set()
            try:
                for ref in refman.getReferencesTo(data.getAddress()):
                    func = program.getFunctionManager().getFunctionContaining(ref.getFromAddress())
                    if func is not None:
                        funcs.add(str(func.getName()))
            except Exception:
                pass
            where = ", ".join(sorted(funcs))
        rows.append((addr_str(data.getAddress()), value, where))
    lines = ["# addr | string | function"] + [f"{a} | {v} | {w}" for a, v, w in rows]
    (out / "strings.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)


def export(program, out: Path, args) -> None:
    from ghidra.app.decompiler import DecompInterface, DecompileOptions
    from ghidra.util.task import ConsoleTaskMonitor

    out.mkdir(parents=True, exist_ok=True)
    src = out / "src"
    src.mkdir(exist_ok=True)
    monitor = ConsoleTaskMonitor()

    meta = write_metadata(program, out)
    imports = write_imports(program, out)
    write_strings(program, out, with_xrefs=not args.no_xrefs)

    fm = program.getFunctionManager()
    funcs = [f for f in fm.getFunctions(True)]

    decomp = None
    if not args.lazy:
        decomp = DecompInterface()
        decomp.setOptions(DecompileOptions())
        decomp.openProgram(program)

    used_paths = set()
    rows = []
    for func in funcs:
        entry = func.getEntryPoint()
        as_ = addr_str(entry)
        name = str(func.getName())
        try:
            size = int(func.getBody().getNumAddresses())
        except Exception:
            size = 0
        rel = ""
        if not args.lazy and size >= args.min_size and not func.isExternal():
            base = safe_name(name)
            fname = base + ".c"
            if fname in used_paths:
                fname = f"{base}__{safe_name(as_)}.c"
            used_paths.add(fname)
            rel = f"src/{fname}"
            body = decompile_one(decomp, func, monitor, args.timeout)
            header = [f"// addr: {as_}  size: {size}", f"// sig: {func_signature(func)}"]
            if not args.no_xrefs:
                calls = func_names(func.getCalledFunctions(monitor))
                called_by = func_names(func.getCallingFunctions(monitor))
                header.append(f"// calls: {calls or '-'}")
                header.append(f"// called_by: {called_by or '-'}")
            (out / rel).write_text("\n".join(header) + "\n" + body + "\n", encoding="utf-8")
        rows.append((as_, name, size, rel))

    rows.sort(key=lambda r: sort_key(r[0]))
    flines = ["# addr | name | size | file"]
    for as_, name, size, rel in rows:
        flines.append(f"{as_} | {name} | {size} | {rel or '-'}")
    (out / "functions.txt").write_text("\n".join(flines) + "\n", encoding="utf-8")

    write_index(out, meta, rows, imports, len(funcs))
    if decomp is not None:
        decomp.dispose()

    print(
        f"[ghidra_export] 完成：{len(funcs)} 个函数 → {out}（"
        f"{'lazy 模式未反编译' if args.lazy else 'src/ 已导出'}）"
    )


def decompile_one(decomp, func, monitor, timeout: int) -> str:
    try:
        res = decomp.decompileFunction(func, timeout, monitor)
        if res.decompileCompleted():
            code = res.getDecompiledFunction().getC()
            if code:
                return str(code)
        return f"// 反编译失败：{res.getErrorMessage()}"
    except Exception as exc:
        return f"// 反编译异常：{exc}"


def write_index(out: Path, meta: dict, rows: list, imports: list, total: int) -> None:
    libs = sorted({lib for lib, _ in imports})
    exported = sum(1 for r in rows if r[3])
    risky = sorted({f"{lib}!{n}" if lib != "-" else n for lib, n in imports
                    if n.lower() in HIGH_RISK})
    lines = [
        f"# 分析归档：{meta['program']}",
        "",
        f"- sha256: `{meta['sha256']}`",
        f"- 格式/架构: {meta['format']} / {meta['language']} ({meta['address_size_bits']} 位, {meta['endian']}-endian)",
        f"- 编译器/镜像基址/入口: {meta['compiler']} / {meta['image_base']} / {meta['entry_points']}",
        f"- Ghidra {meta['ghidra_version']}，生成于 {meta['generated_at']}",
        f"- 函数总数: {total}，已落盘: {exported} 个（src/）",
        "",
        "## 文件清单",
        "",
        "| 文件 | 说明 |",
        "| --- | --- |",
        "| `metadata.txt` | 架构/位宽/endian/编译器/hash/入口点 |",
        "| `functions.txt` | 全函数清单：地址 \\| 名称 \\| 大小 \\| 文件 |",
        "| `strings.txt` | 地址 \\| 字符串 \\| 所在函数 |",
        "| `imports.txt` | 导入符号（库\\|名称），共 %d 条，涉及库 %s |" % (len(imports), ", ".join(libs) or "-"),
        "| `src/*.c` | 逐函数反编译，文件名=函数名 |",
        "",
        "## 高危导入（优先排查）",
        "",
    ]
    lines += [f"- `{x}`" for x in risky] or ["- （无匹配）"]
    lines += [
        "",
        "## 全函数表（按地址排序）",
        "",
        "| 地址 | 名称 | 大小 | 文件 |",
        "| --- | --- | --- | --- |",
    ]
    for as_, name, size, rel in rows:
        lines.append(f"| {as_} | `{name}` | {size} | {rel or '-'} |")
    lines += [
        "",
        "## 读取示例",
        "",
        "```",
        f"read_file {out.name}/src/main.c",
        f'grep -n "strcpy" {out.name}/src/',
        f"read_file {out.name}/functions.txt",
        "```",
        "",
    ]
    (out / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args():
    ap = argparse.ArgumentParser(description="将 Ghidra 分析结果按函数归档到本地")
    ap.add_argument("--binary", required=True, help="program 名 / 输出子目录名（建议用二进制文件名）")
    ap.add_argument("--binary-path", help="二进制文件路径（工程内没有该 program 时导入用）")
    ap.add_argument("--out", required=True, help="输出目录，如 work/42/analysis/main")
    ap.add_argument("--project", default="ghidra-export-projects",
                    help="本工具自己的 Ghidra 工程目录（默认 ghidra-export-projects；"
                         "不要指向 ghidra MCP 的 ghidra-projects，那里被 MCP 长期加锁）")
    ap.add_argument("--project-name", default="my_project", help="Ghidra 工程名（默认 my_project）")
    ap.add_argument("--lazy", action="store_true", help="只出 metadata/functions/strings/imports，不逐函数反编译")
    ap.add_argument("--min-size", type=int, default=0, help="小于该字节数的函数不反编译（默认 0）")
    ap.add_argument("--timeout", type=int, default=60, help="单函数反编译超时秒数（默认 60）")
    ap.add_argument("--no-xrefs", action="store_true", help="不写调用关系（更快）")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    out = Path(args.out).resolve()
    with open_program_ctx(args) as flat_api:
        export(flat_api.getCurrentProgram(), out, args)


if __name__ == "__main__":
    main()
