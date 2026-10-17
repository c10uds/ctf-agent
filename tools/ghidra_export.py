#!/usr/bin/env python3
"""AIxCTF 二进制分析归档（串行队列版）。

设计要点
- **串行**：所有 worker 共用一把文件锁（默认 /app/state/ghidra-export.lock），同一时刻只有一个
  导出进程（一个 JVM）。后来者排队等待，拿到锁后自动继续——worker 直接等命令返回即可。
- **做完即退**：分析完输出文件后进程退出，JVM 随之结束，内存立刻还回去。
- **缓存复用**：工程按二进制 sha256 前 12 位分目录（ghidra-export-projects/<sha12>/），
  同一个二进制（含同一 libc）只分析一次，二次导出直接复用。
- **内存**：默认**不设** -Xmx，交由 JVM 按它检测到的内存自决（容器带 `-m` 限额时约取 25% 限额，
  4G 容器 ≈ 1G 堆）；要钉死就用 `--maxmem <MB>`。注意容器**没有** `-m` 限额时 JVM 看到的是宿主机内存，
  默认堆会随之变大（此时建议显式给 `--maxmem`）。
- **全量导出**：函数（反编译 C + 逐函数汇编）、符号、导入导出、字符串、段、数据、调用边表。

用法：
  python3 tools/ghidra_export.py --binary main --binary-path artifacts/main --out analysis/main
  python3 tools/ghidra_export.py --binary main --binary-path artifacts/main --out analysis/main --lazy
  python3 tools/ghidra_export.py --binary main --binary-path artifacts/main --out analysis/main \
          --decompile check_password          # 只反编译一个函数并打印（按需交互用）
"""
import argparse
import fcntl
import hashlib
import json
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

LOCK_PATH = os.environ.get("CTF_GHIDRA_LOCK", "/app/state/ghidra-export.lock")
STATUS_PATH = os.environ.get("CTF_GHIDRA_STATUS", "/app/state/ghidra-export.json")


def default_project_base() -> str:
    """工程缓存放在容器级共享目录，跨题目按 sha256 去重（同一 libc 只分析一次）。"""
    env = os.environ.get("CTF_GHIDRA_PROJECTS")
    if env:
        return env
    return "/app/ghidra-export-projects" if os.path.isdir("/app") else "ghidra-export-projects"


def log(msg: str):
    print(f"[ghidra_export] {msg}", file=sys.stderr, flush=True)


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
        return ", ".join(sorted(str(f.getName()) for f in functions))
    except Exception:
        return ""


# ------------------------------------------------------------------ 串行队列

def read_status() -> dict:
    try:
        with open(STATUS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_status(data: dict):
    try:
        tmp = f"{STATUS_PATH}.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, STATUS_PATH)
    except Exception:
        pass


def acquire_slot(args) -> tuple:
    """拿导出锁；拿不到就排队等待（依赖内核 flock 的阻塞语义）。"""
    os.makedirs(os.path.dirname(LOCK_PATH) or ".", exist_ok=True)
    fh = open(LOCK_PATH, "a+")
    t0 = time.time()
    announced = False
    while True:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if not announced:
                st = read_status()
                who = st.get("binary") or "?"
                log(f"导出队列忙（正在导出 {who} pid={st.get('pid', '?')}），排队等待…")
                announced = True
            if args.wait_timeout and time.time() - t0 > args.wait_timeout:
                fh.close()
                raise SystemExit(f"[ghidra_export] 排队超时（>{args.wait_timeout}s），放弃")
            time.sleep(0.4)
    waited = time.time() - t0
    write_status({"pid": os.getpid(), "binary": args.binary, "started_at": time.time()})
    return fh, waited


def release_slot(fh):
    try:
        write_status({"idle": True, "ts": time.time()})
    except Exception:
        pass
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


# ------------------------------------------------------------------ Ghidra 打开

def open_program_ctx(args, project_dir: Path):
    import pyghidra
    from pyghidra.launcher import HeadlessPyGhidraLauncher

    if not pyghidra.started():
        launcher = HeadlessPyGhidraLauncher()
        if str(args.maxmem).lower() in ("none", "", "0"):
            # 默认不设上限：让 JVM 按自己检测到的内存决定（容器有 -m 限额时约 25% 限额）
            log("JVM 堆：未设 -Xmx（由 JVM 自决）")
        else:
            launcher.add_vmargs(f"-Xmx{args.maxmem}m")
            log(f"JVM 堆：-Xmx{args.maxmem}m")
        launcher.start()

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    return pyghidra.open_program(
        binary_path=args.binary_path,
        project_location=str(project_dir),
        project_name="proj",
        program_name=args.binary,
        analyze=True,
        nested_project_location=False,
    )


# ------------------------------------------------------------------ 导出

def write_metadata(program, out: Path, extra: dict) -> dict:
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
    meta.update(extra)
    (out / "metadata.txt").write_text(
        "\n".join(f"{k}: {v}" for k, v in meta.items()) + "\n", encoding="utf-8")
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
        log(f"读取导入符号失败：{exc}")
    rows.sort()
    (out / "imports.txt").write_text(
        "\n".join(f"{lib}|{name}" for lib, name in rows) + ("\n" if rows else ""),
        encoding="utf-8")
    return rows


def write_symbols(program, out: Path) -> None:
    rows = []
    try:
        for sym in program.getSymbolTable().getAllSymbols(True):
            try:
                ns = str(sym.getParentNamespace().getName())
            except Exception:
                ns = "-"
            rows.append((addr_str(sym.getAddress()), str(sym.getName()), str(sym.getSymbolType()), ns))
    except Exception as exc:
        log(f"读取符号表失败：{exc}")
    rows.sort(key=lambda r: sort_key(r[0]))
    (out / "symbols.txt").write_text(
        "\n".join(" | ".join(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8")


def write_exports(program, out: Path) -> None:
    rows = []
    try:
        for addr in program.getSymbolTable().getExternalEntryPointIterator():
            func = program.getFunctionManager().getFunctionAt(addr)
            name = str(func.getName()) if func else "-"
            rows.append(f"{addr_str(addr)} | {name}")
    except Exception as exc:
        log(f"读取导出入口失败：{exc}")
    (out / "exports.txt").write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")


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


def write_sections(program, out: Path) -> None:
    lines = ["# name | start | end | size | r/w/x"]
    try:
        for block in program.getMemory().getBlocks():
            perms = "".join([
                "r" if block.isRead() else "-",
                "w" if block.isWrite() else "-",
                "x" if block.isExecute() else "-",
            ])
            lines.append(f"{block.getName()} | {addr_str(block.getStart())} | "
                         f"{addr_str(block.getEnd())} | {block.getSize()} | {perms}")
    except Exception as exc:
        lines.append(f"# 读取段失败：{exc}")
    (out / "sections.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_data(program, out: Path, limit: int = 20000) -> int:
    rows = []
    try:
        for data in program.getListing().getDefinedData(True):
            if len(rows) >= limit:
                break
            dt = str(data.getDataType().getName())
            if "string" in dt.lower() or "unicode" in dt.lower():
                continue
            try:
                value = str(data.getValue())
            except Exception:
                value = ""
            func = program.getFunctionManager().getFunctionContaining(data.getAddress())
            rows.append(f"{addr_str(data.getAddress())} | {dt} | {value[:120]} | "
                        f"{str(func.getName()) if func else '-'}")
    except Exception as exc:
        log(f"读取数据项失败：{exc}")
    (out / "data.txt").write_text(
        "# addr | type | value | function\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return len(rows)


def write_calls(program, out: Path, monitor) -> int:
    xdir = out / "xrefs"
    xdir.mkdir(exist_ok=True)
    lines = ["# caller -> callee"]
    try:
        for func in program.getFunctionManager().getFunctions(True):
            for callee in func.getCalledFunctions(monitor):
                lines.append(f"{func.getName()} -> {callee.getName()}")
    except Exception as exc:
        lines.append(f"# 生成调用边表失败：{exc}")
    (xdir / "calls.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines) - 1


def instr_comment(ins) -> str:
    """Ghidra 的 CodeUnit.getComment 必须指定注释类型。"""
    try:
        from ghidra.program.model.listing import CommentType
        return str(ins.getComment(CommentType.EOL) or "")
    except Exception:
        pass
    for arg in (0,):
        try:
            return str(ins.getComment(arg) or "")
        except Exception:
            continue
    return ""


def disasm_function(program, func) -> str:
    listing = program.getListing()
    fm = program.getFunctionManager()
    lines = []
    failures = 0
    try:
        it = listing.getInstructions(func.getBody(), True)
    except Exception as exc:
        log(f"读取 {func.getName()} 指令失败：{exc}")
        return ""
    for ins in it:
        try:
            addr = addr_str(ins.getAddress())
            bs = "".join("%02x" % (int(b) & 0xFF) for b in ins.getBytes())
            mnem = str(ins.getMnemonicString())
            ops = ", ".join(str(ins.getDefaultOperandRepresentation(i))
                            for i in range(ins.getNumOperands()))
            line = f"{addr}  {bs:<24} {mnem:<8} {ops}".rstrip()
            cmt = instr_comment(ins)
            if cmt:
                line += f"   ; {cmt}"
            try:
                flows = list(ins.getFlows())
                if len(flows) == 1:
                    target = fm.getFunctionAt(flows[0])
                    if target is not None:
                        line += f"   ; -> {target.getName()}"
            except Exception:
                pass
            lines.append(line)
        except Exception as exc:
            failures += 1
            if failures == 1:
                log(f"指令格式化异常（{func.getName()}）：{exc}")
            continue
    return "\n".join(lines)


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


def export(program, out: Path, args) -> dict:
    from ghidra.app.decompiler import DecompInterface, DecompileOptions
    from ghidra.util.task import ConsoleTaskMonitor

    out.mkdir(parents=True, exist_ok=True)
    src = out / "src"
    asm = out / "asm"
    src.mkdir(exist_ok=True)
    asm.mkdir(exist_ok=True)
    monitor = ConsoleTaskMonitor()

    meta = write_metadata(program, out, {"queue_wait_sec": round(args.waited, 1),
                                         "cache_project": str(args.project_dir)})
    imports = write_imports(program, out)
    write_symbols(program, out)
    write_exports(program, out)
    write_sections(program, out)
    n_strings = write_strings(program, out, with_xrefs=not args.no_xrefs)
    n_data = write_data(program, out)
    n_calls = write_calls(program, out, monitor)

    fm = program.getFunctionManager()
    funcs = [f for f in fm.getFunctions(True)]

    decomp = None
    if not args.lazy and not args.no_decomp:
        decomp = DecompInterface()
        decomp.setOptions(DecompileOptions())
        decomp.openProgram(program)

    used = set()
    rows = []
    for func in funcs:
        entry = func.getEntryPoint()
        as_ = addr_str(entry)
        name = str(func.getName())
        try:
            size = int(func.getBody().getNumAddresses())
        except Exception:
            size = 0
        rel_c = rel_a = ""
        if not args.lazy and size >= args.min_size and not func.isExternal():
            base = safe_name(name)
            fname = base
            if fname in used:
                fname = f"{base}__{safe_name(as_)}"
            used.add(fname)
            if decomp is not None:
                rel_c = f"src/{fname}.c"
                header = [f"// addr: {as_}  size: {size}", f"// sig: {func_signature(func)}"]
                if not args.no_xrefs:
                    header.append(f"// calls: {func_names(func.getCalledFunctions(monitor)) or '-'}")
                    header.append(f"// called_by: {func_names(func.getCallingFunctions(monitor)) or '-'}")
                (out / rel_c).write_text(
                    "\n".join(header) + "\n" + decompile_one(decomp, func, monitor, args.timeout) + "\n",
                    encoding="utf-8")
            if not args.no_asm:
                rel_a = f"asm/{fname}.asm"
                body = disasm_function(program, func)
                head = [f"; addr: {as_}  size: {size}", f"; sig: {func_signature(func)}", ""]
                (out / rel_a).write_text("\n".join(head) + body + "\n", encoding="utf-8")
        rows.append((as_, name, size, rel_c, rel_a))

    rows.sort(key=lambda r: sort_key(r[0]))
    flines = ["# addr | name | size | src | asm"]
    for as_, name, size, rel_c, rel_a in rows:
        flines.append(f"{as_} | {name} | {size} | {rel_c or '-'} | {rel_a or '-'}")
    (out / "functions.txt").write_text("\n".join(flines) + "\n", encoding="utf-8")

    write_index(out, meta, rows, imports, len(funcs),
                {"strings": n_strings, "data": n_data, "calls": n_calls})

    if decomp is not None:
        decomp.dispose()

    return {"functions": len(funcs), "exported": sum(1 for r in rows if r[3] or r[4]),
            "strings": n_strings, "calls": n_calls}


def write_index(out: Path, meta: dict, rows: list, imports: list, total: int, stats: dict) -> None:
    libs = sorted({lib for lib, _ in imports})
    exported = sum(1 for r in rows if r[3] or r[4])
    risky = sorted({f"{lib}!{n}" if lib != "-" else n for lib, n in imports
                    if n.lower() in HIGH_RISK})
    lines = [
        f"# 分析归档：{meta['program']}",
        "",
        f"- sha256: `{meta['sha256']}`",
        f"- 格式/架构: {meta['format']} / {meta['language']} ({meta['address_size_bits']} 位, {meta['endian']}-endian)",
        f"- 编译器/镜像基址: {meta['compiler']} / {meta['image_base']}",
        f"- Ghidra {meta['ghidra_version']}，生成于 {meta['generated_at']}",
        f"- 函数 {total} 个（已落盘 {exported}），字符串 {stats['strings']}，数据项 {stats['data']}，调用边 {stats['calls']}",
        f"- 导出工程缓存: `{meta['cache_project']}`（同 sha256 复用，排队 {meta['queue_wait_sec']}s）",
        "",
        "## 文件",
        "",
        "| 文件 | 说明 |",
        "| --- | --- |",
        "| `metadata.txt` | 架构/hash/编译器等 |",
        "| `functions.txt` | 地址 \\| 名称 \\| 大小 \\| src 文件 \\| asm 文件 |",
        "| `symbols.txt` | 全符号（含命名空间与类型）|",
        "| `imports.txt` | 导入符号（库\\|名称）|",
        "| `exports.txt` | 导出入口 |",
        "| `strings.txt` | 地址 \\| 字符串 \\| 所在函数 |",
        "| `sections.txt` | 段/节与权限 |",
        "| `data.txt` | 已定义数据项 |",
        "| `xrefs/calls.txt` | 调用边表 caller -> callee |",
        "| `src/*.c` | 逐函数反编译 |",
        "| `asm/*.asm` | 逐函数汇编（地址/字节/助记符/操作数/注释）|",
        "",
        "## 高危导入（优先排查）",
        "",
    ]
    lines += [f"- `{x}`" for x in risky] or ["- （无匹配）"]
    lines += ["", "## 全函数表（按地址排序）", "",
              "| 地址 | 名称 | 大小 | src | asm |", "| --- | --- | --- | --- | --- |"]
    for as_, name, size, rel_c, rel_a in rows:
        lines.append(f"| {as_} | `{name}` | {size} | {rel_c or '-'} | {rel_a or '-'} |")
    lines += ["", "## 读取示例", "", "```",
              f"read_file {out.name}/src/main.c",
              f"read_file {out.name}/asm/main.asm",
              f"grep -n 'system' {out.name}/asm/",
              f"read_file {out.name}/functions.txt", "```", ""]
    (out / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ 单函数模式

def decompile_single(program, out: Path, args) -> int:
    from ghidra.app.decompiler import DecompInterface, DecompileOptions
    from ghidra.util.task import ConsoleTaskMonitor

    monitor = ConsoleTaskMonitor()
    target = args.decompile
    fm = program.getFunctionManager()
    func = None
    try:
        addr = program.getAddressFactory().getDefaultAddressSpace().getAddress(target)
        func = fm.getFunctionContaining(addr)
    except Exception:
        func = None
    if func is None:
        for f in fm.getFunctions(True):
            if str(f.getName()) == target:
                func = f
                break
    if func is None:
        log(f"找不到函数：{target}")
        return 2

    out.mkdir(parents=True, exist_ok=True)
    (out / "src").mkdir(exist_ok=True)
    (out / "asm").mkdir(exist_ok=True)
    base = safe_name(str(func.getName()))
    decomp = DecompInterface()
    decomp.setOptions(DecompileOptions())
    decomp.openProgram(program)
    code = decompile_one(decomp, func, monitor, args.timeout)
    decomp.dispose()
    (out / "src" / f"{base}.c").write_text(code + "\n", encoding="utf-8")
    (out / "asm" / f"{base}.asm").write_text(disasm_function(program, func) + "\n", encoding="utf-8")
    print(f"// {func.getName()} -> src/{base}.c, asm/{base}.asm", flush=True)
    print(code, flush=True)
    return 0


# ------------------------------------------------------------------ 入口

def parse_args():
    ap = argparse.ArgumentParser(description="二进制分析归档（串行队列 + C/汇编全量导出）")
    ap.add_argument("--binary", required=True, help="program 名 / 输出子目录名（建议用二进制文件名）")
    ap.add_argument("--binary-path", required=True, help="二进制文件路径")
    ap.add_argument("--out", required=True, help="输出目录，如 work/42/analysis/main")
    ap.add_argument("--project", default=default_project_base(),
                    help="导出工程根目录（默认容器内 /app/ghidra-export-projects，按 sha256 分子目录，跨题目共享）")
    ap.add_argument("--maxmem", default="none",
                    help="JVM 最大堆：'none'（默认，不传 -Xmx，交给 JVM 按检测到的内存自决）或整数 MB")
    ap.add_argument("--wait-timeout", type=int, default=1800, help="排队等待上限秒数（默认 1800）")
    ap.add_argument("--lazy", action="store_true", help="只出清单/表格，不逐函数反编译")
    ap.add_argument("--no-asm", action="store_true", help="不导出逐函数汇编")
    ap.add_argument("--no-decomp", action="store_true", help="不导出反编译 C")
    ap.add_argument("--min-size", type=int, default=0, help="小于该字节数的函数不导出（默认 0）")
    ap.add_argument("--timeout", type=int, default=60, help="单函数反编译超时秒数（默认 60）")
    ap.add_argument("--no-xrefs", action="store_true", help="不写调用关系/字符串引用（更快）")
    ap.add_argument("--decompile", help="只反编译一个函数（名字或地址）并打印，供按需查看")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    bin_path = Path(args.binary_path)
    if not bin_path.is_file():
        log(f"找不到二进制文件：{bin_path}")
        return 2

    out = Path(args.out).resolve()
    sha = hashlib.sha256(bin_path.read_bytes()).hexdigest()[:12]
    project_dir = (Path(args.project).resolve() / sha)
    args.project_dir = project_dir

    fh, waited = acquire_slot(args)
    args.waited = waited
    t0 = time.time()
    try:
        cached = (project_dir / "proj.gpr").exists()
        log(f"{'复用缓存' if cached else '新建工程'} {project_dir}（heap={args.maxmem}）")
        with open_program_ctx(args, project_dir) as flat_api:
            program = flat_api.getCurrentProgram()
            if args.decompile:
                return decompile_single(program, out, args)
            stats = export(program, out, args)
        dt = time.time() - t0
        print(json.dumps({"ok": True, "cache": cached, "wait_sec": round(waited, 1),
                          "total_sec": round(dt, 1), "out": str(out), **stats},
                         ensure_ascii=False), flush=True)
        log(f"完成：{stats['functions']} 函数 → {out}（排队 {waited:.1f}s，总 {dt:.1f}s，"
            f"{'缓存' if cached else '新分析'}）")
        return 0
    finally:
        release_slot(fh)


if __name__ == "__main__":
    sys.exit(main())
