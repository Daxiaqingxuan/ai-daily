#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第 1 章配套脚本：契约漂移检查器（只读，不改任何文件）

它把「上下文工程」的三条原则变成可执行断言：
  1. 唯一真源  -> 项目根必须有 AGENTS.md，且必须真的被别的文件引用
  2. 信息分层  -> 大块参考材料放 reference/，不能混进任务目录
  3. 位置无关  -> 代码里不硬编码本机绝对路径、不硬编码别的任务目录

用法：
  python check_contract.py <项目目录>       # 扫描，FAIL 退出码 1
  python check_contract.py --self-test      # 造一个合规的临时项目，证明检查器有效

教学要点：检查器本身不神奇，神奇的是「把含糊的约定写成断言」之后，
         那些你以为已经做到的事会立刻现出原形。
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CONTRACT = "AGENTS.md"
SECTIONS = ("路径", "不变量", "常用命令", "交付流程", "验收", "本机环境事实", "明确禁止")
CODE_EXT = {".py", ".js", ".html", ".css", ".java", ".json"}
SKIP_DIRS = {".git", "node_modules", ".build", "shots", "__pycache__", ".edge-cdp", ".edge-online"}

results: list[tuple[str, str, str]] = []


def rec(level: str, name: str, detail: str) -> None:
    results.append((level, name, detail))


def walk(root: Path):
    for p in root.rglob("*"):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        yield p


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


# --- C1 / C2 / C3：契约是否存在、是否完整、是否真被加载 ---
def check_contract(root: Path) -> None:
    f = root / CONTRACT
    if not f.exists():
        rec("FAIL", "C1 契约落地", f"项目根没有 {CONTRACT}；模板还躺在 learn-agent/templates/，等于没写")
        rec("FAIL", "C2 契约结构", "无契约文件，跳过")
    else:
        rec("PASS", "C1 契约落地", f"找到 {f.relative_to(root)}")
        txt = read(f)
        missing = [s for s in SECTIONS if s not in txt]
        if missing:
            rec("WARN", "C2 契约结构", "缺节：" + "、".join(missing))
        else:
            rec("PASS", "C2 契约结构", "7 节齐全")

    readers = [p for p in walk(root)
               if p.name != CONTRACT and CONTRACT in read(p)]
    if readers:
        rec("PASS", "C3 契约被加载",
            f"{len(readers)} 个文件引用了它：" + ", ".join(str(p.relative_to(root)) for p in readers[:4]))
    else:
        rec("FAIL", "C3 契约被加载",
            "项目里没有任何脚本/文档提到 AGENTS.md —— 写了没人读，agent 下个会话照样不知道")


# --- C4：不硬编码本机绝对路径（契约外置，项目才可迁移） ---
ABS = re.compile(r"[A-Za-z]:[\\/]Users[\\/]", re.I)


def check_abs(root: Path) -> None:
    hits = []
    for p in walk(root):
        if p.suffix not in CODE_EXT or p.name == CONTRACT:
            continue
        for i, line in enumerate(read(p).splitlines(), 1):
            if ABS.search(line):
                hits.append(f"{p.relative_to(root)}:{i}")
    if hits:
        rec("WARN", "C4 无本机绝对路径",
            f"代码里硬编码了 {len(hits)} 处（换台机器/换用户就失效）：" + ", ".join(hits[:4]))
    else:
        rec("PASS", "C4 无本机绝对路径", "代码只用相对路径")


# --- C5：不硬编码别的任务目录（补丁式兜底 = 唯一真源已失守） ---
SPECIAL = re.compile(r"automation-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}")


def check_special(root: Path) -> None:
    hits = []
    for p in walk(root):
        if p.suffix not in CODE_EXT:
            continue
        for i, line in enumerate(read(p).splitlines(), 1):
            if SPECIAL.search(line):
                hits.append(f"{p.relative_to(root)}:{i}")
    if hits:
        rec("FAIL", "C5 无跨任务特例",
            f"{len(hits)} 处把「另一个自动化的工作目录」写死在工具里：" + ", ".join(hits[:3])
            + "  —— 这是契约失守后打补丁的痕迹，不是设计")
    else:
        rec("PASS", "C5 无跨任务特例", "工具只认项目内的唯一真源")


# --- C6 / C7：信息分层与上下文预算 ---
def check_layering(root: Path) -> None:
    ref = root / "reference"
    if ref.is_dir() and any(f.stat().st_size > 20_000 for f in ref.iterdir() if f.is_file()):
        big = max((f for f in ref.iterdir() if f.is_file()), key=lambda f: f.stat().st_size)
        rec("PASS", "C6 参考材料分层", f"大样板放在 reference/{big.name}（{big.stat().st_size // 1024} KB），可由脚本拼装")
    else:
        rec("WARN", "C6 参考材料分层",
            "项目内没有 reference/ 大文件；样板实际散在别的工作目录，靠绝对路径引用")

    sized = sorted(((p.stat().st_size, p.relative_to(root)) for p in walk(root)
                    if p.suffix in {".html", ".md", ".css"}), reverse=True)[:3]
    if sized:
        desc = "；".join(f"{n} {s // 1024} KB ≈ {s // 3 // 1000}k tokens" for s, n in sized)
        rec("INFO", "C7 上下文预算", "最大的三份材料：" + desc)


def scan(root: Path) -> int:
    results.clear()
    check_contract(root)
    check_abs(root)
    check_special(root)
    check_layering(root)
    print(f"\n=== 契约漂移检查：{root} ===")
    for level, name, detail in results:
        print(f"[{level:<4}] {name}  {detail}")
    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    print(f"--- 结论：FAIL {len(fails)} / WARN {len(warns)} / 共 {len(results)} 项 ---")
    if fails:
        print("    这些 FAIL 不是 bug，是「约定还只在人脑/对话里」的证据。")
    return 1 if fails else 0


GOOD_CONTRACT = """# 演示项目 · 项目契约
## 1. 路径（唯一真源）
| 报纸源文件 | `data/AI晨报-YYYY-MM-DD.html` |
## 2. 不变量
每期 15 版。
## 3. 常用命令
python tools/build.py
## 4. 交付流程
生成 → 校验 → 发布。
## 5. 验收
python tools/verify.py 退出码 0。
## 6. 本机环境事实
COM 被拦截。
## 7. 明确禁止
不要手工编辑索引。
"""

GOOD_BUILD = '''# 构建脚本：约定只从 AGENTS.md 读，不硬编码任何绝对路径
"""See AGENTS.md for the single source of truth."""
CONTRACT = Path(__file__).resolve().parent.parent / "AGENTS.md"
ROOT = Path(__file__).resolve().parent.parent
'''


def self_test() -> int:
    t = Path(tempfile.mkdtemp(prefix="contract-demo-"))
    try:
        (t / "tools").mkdir()
        (t / "reference").mkdir()
        (t / CONTRACT).write_text(GOOD_CONTRACT, encoding="utf-8")
        (t / "tools" / "build.py").write_text(GOOD_BUILD, encoding="utf-8")
        (t / "reference" / "skeleton.html").write_text("<style>" + "x" * 40_000 + "</style>", encoding="utf-8")
        print("构造了一个「合规」临时项目：有契约、脚本引用契约、样板进 reference/、无绝对路径。")
        code = scan(t)
        print(f"自检退出码 = {code}（应为 0，证明检查器能区分好项目与漂移项目）")
        return 0 if code == 0 else 1
    finally:
        shutil.rmtree(t, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        raise SystemExit(self_test())
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "ai-daily"
    raise SystemExit(scan(root))
