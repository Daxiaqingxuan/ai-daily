#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晨读卡 · 一键回归

一条命令回答三个问题：
    1. 现在的东西是对的吗？        （assertions）
    2. 重跑一次会变吗？            （idempotence）
    3. 坏了的话，断言真的会红吗？   （mutation —— 不做变异测试，你不知道断言有没有在检查）

对应教材第 7 章「评估与回归」。SKIP 会如实列出，**绝不计入通过**。

用法：
    python tools/verify.py
    python tools/verify.py --json
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
RESULTS: list[tuple[str, str, str]] = []   # (PASS|FAIL|SKIP, 名称, 说明)


def record(flag: str, name: str, detail: str) -> None:
    RESULTS.append((flag, name, detail))


def run_py(script: Path, *args: str, cwd: Path | None = None):
    return subprocess.run([PY, str(script), *args], cwd=str(cwd or ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def check_contract() -> None:
    agents = ROOT / "AGENTS.md"
    if not agents.exists():
        record("FAIL", "contract", "AGENTS.md 缺")
        return
    text = agents.read_text(encoding="utf-8")
    if "唯一真源" not in text:
        record("FAIL", "contract", "契约缺「唯一真源」一节")
        return
    offenders = []
    path_ref = re.compile(r"ai-daily[/\\]")
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.name in {"validate.py", "verify.py"}:
            continue
        if p.suffix.lower() not in {".py", ".html", ".json", ".js"}:
            continue
        if "stages" in p.parts or ".git" in p.parts:
            continue
        try:
            if path_ref.search(p.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(p.relative_to(ROOT).as_posix())
        except OSError:
            pass
    record("PASS" if not offenders else "FAIL", "contract",
           "契约有效 · 零 ai-daily 引用" if not offenders else "命中：" + "、".join(offenders[:3]))


def check_assertions() -> None:
    r = run_py(ROOT / "tools" / "validate.py", "--json")
    try:
        rows = json.loads(r.stdout)
    except json.JSONDecodeError:
        record("FAIL", "assertions", f"validate.py 输出不可解析（退出码 {r.returncode}）")
        return
    bad = [x for x in rows if not x["ok"]]
    record("PASS" if not bad else "FAIL", "assertions",
           f"{len(rows) - len(bad)}/{len(rows)} 通过" if not bad
           else f"{len(bad)} 条失败，首条：{bad[0]['check']}（{bad[0]['detail']}）")


def check_idempotence() -> None:
    r = run_py(ROOT / "tools" / "build.py", "--date", "2026-11-06", "--twice")
    ok = r.returncode == 0 and "幂等" in r.stdout and "不一致" not in r.stdout
    record("PASS" if ok else "FAIL", "idempotence",
           "连跑两次，4 份中间产物 md5 一致" if ok else "重跑产物不一致或脚本报错")


def check_mutation() -> None:
    """把整个项目复制到临时目录，故意弄坏一张卡，断言必须变红。"""
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "demo"
        shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns("stages", "__pycache__", "*.tmp"))
        cards = sorted((dst / "site" / "cards").glob("*.html"))
        if not cards:
            record("SKIP", "mutation", "没有卡片可破坏，先跑一次 build")
            return
        target = cards[0]
        target.write_text(target.read_text(encoding="utf-8").replace("<blockquote>", "<blockquote-x>", 1),
                          encoding="utf-8")
        r = run_py(dst / "tools" / "validate.py")
        caught = r.returncode == 1 and "卡片结构完整" in r.stdout
        record("PASS" if caught else "FAIL", "mutation",
               f"破坏 {target.name} 后断言返回 1（会红）" if caught
               else "破坏了却仍通过 —— 这条断言是摆设")


def check_escape() -> None:
    f = ROOT / "site" / "cards" / "2026-11-10.html"
    if not f.exists():
        record("SKIP", "escape", "11-10 的卡还没生成，用 build.py --date 2026-11-10 生成")
        return
    page = f.read_text(encoding="utf-8")
    ok = "&lt;可复现&gt;" in page and "&amp;" in page and "<可复现>" not in page
    record("PASS" if ok else "FAIL", "escape",
           "尖括号与 & 均为实体" if ok else "出现未转义字符，页面会少字")


def check_browser() -> None:
    record("SKIP", "browser", "加 --browser 启用（需本机 Edge，本次未跑）")


def main() -> int:
    only_json = "--json" in sys.argv
    check_contract()
    check_assertions()
    check_idempotence()
    check_mutation()
    check_escape()
    if "--browser" in sys.argv:
        record("SKIP", "browser", "本示例未实现，故意留白：真实视口要用 CDP，不能只看 --window-size")
    else:
        check_browser()

    passed = sum(1 for f, _, _ in RESULTS if f == "PASS")
    failed = sum(1 for f, _, _ in RESULTS if f == "FAIL")
    skipped = sum(1 for f, _, _ in RESULTS if f == "SKIP")

    if only_json:
        print(json.dumps([{"status": f, "check": n, "detail": d} for f, n, d in RESULTS],
                         ensure_ascii=False, indent=2))
        return 0 if failed == 0 else 1

    print("=== 晨读卡 · 回归报告 ===")
    for flag, name, detail in RESULTS:
        print(f"[{flag:<4}] {name:<12} {detail}")
    print(f"\n--- 结论：PASS {passed} / FAIL {failed} / SKIP {skipped} ---")
    if skipped:
        print("SKIP 不计入通过：没测就是没测，报告要敢说。")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
