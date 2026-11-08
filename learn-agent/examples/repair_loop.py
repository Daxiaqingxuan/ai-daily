#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第 2 章配套脚本：失败闭环 + 发布闸门（只读真实项目，破坏只发生在临时沙盒）

它把教材里那段伪代码变成可运行的东西：

    for attempt in range(3):
        干活 -> 跑 validate.py -> 过了就发
        不过 -> 把「失败原文」做成工单，原样回传给 agent，只修这些
    否则 -> 写 status.json，禁止发布，等人介入

用法：
    python repair_loop.py                 # 完整演示：破坏 -> 工单 -> 修复 -> 复验通过
    python repair_loop.py --stubborn     # 演示熔断：修复器漏修一项，3 轮后停止并留状态
    python repair_loop.py --gate <root>  # 对真实项目跑一次发布闸门，只判定不改文件

注意：这里的 fix() 是「确定性规则」，用来模拟 agent 的修复动作，好让闭环
     能在没有模型的情况下跑完。真实用法是把 ticket["instruction"] 原样
     发给模型，让它自己改文件；改完仍然必须复跑同一套断言。
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate  # noqa: E402  —— 复用第 2 章的 32 条断言

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WORKSPACE = Path(__file__).resolve().parents[2]
REAL = WORKSPACE / "ai-daily"
MAX_ROUNDS = 3
PAPER = "AI晨报-2026-11-05.html"


def run_validation(root: Path):
    """跑同一套断言，拿到结构化结果 + 原始输出 + 退出码。"""
    validate.results.clear()
    old_argv = sys.argv
    sys.argv = ["validate.py", str(root)]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = validate.main()
    finally:
        sys.argv = old_argv
    return code, list(validate.results), buf.getvalue()


def make_ticket(results, rnd: int) -> dict:
    """失败信息是给 agent 的输入，不是给人看的日志：带实测数字、原样、不转述。"""
    bad = [{"group": g, "check": n,
            "detail": d or "<无实测值：这条失败信息不足以定位，应回头补 detail>"}
           for g, n, ok, d in results if not ok]
    lines = [f"  · [{x['group']}] {x['check']} {x['detail']}" for x in bad]
    return {
        "round": rnd,
        "passed": len(results) - len(bad),
        "total": len(results),
        "failed": bad,
        "instruction": (
            "自检未通过。只修下列失败项，不要改动其它内容；改完必须复跑同一套断言。\n"
            + "\n".join(lines)
        ),
    }


def sandbox() -> Path:
    """复制最小可校验集合：两期报纸 + 索引 + 入口页 + site 副本。"""
    t = Path(tempfile.mkdtemp(prefix="repair-loop-"))
    (t / "site").mkdir()
    for name in ("AI晨报-2026-11-04.html", PAPER,
                 "site/issues.js", "site/index.html",
                 "site/AI晨报-2026-11-04.html", f"site/{PAPER}"):
        shutil.copy2(REAL / name, t / name)
    return t


def break_it(root: Path) -> None:
    """模拟真实退化：模型交付的新一期少了一条锐评，且 build_index.py 还没跑。

    这两件事必须一起出现，因为「少一条锐评」改 HTML 就能补，而
    「没同步进 site/」只能靠跑构建脚本 —— 两种修复手段不同，才有教学价值。
    """
    p = root / PAPER
    t = p.read_text(encoding="utf-8")
    t = t.replace('<aside class="razor">', '<aside class="razor-gone">', 1)
    p.write_text(t, encoding="utf-8")
    (root / "site" / PAPER).unlink()  # 新一期尚未同步进发布目录


def fix(root: Path, ticket: dict, stubborn: bool) -> list[str]:
    """模拟 agent：只按工单里的失败项动手，不顺手改别处。"""
    actions = []
    names = " ".join(x["check"] for x in ticket["failed"])
    if "锐评" in names:
        p = root / PAPER
        t = p.read_text(encoding="utf-8")
        if 'class="razor-gone"' in t:
            p.write_text(t.replace('class="razor-gone"', 'class="razor"', 1), encoding="utf-8")
            actions.append("按 [A] 15 条锐评 实测 14 → 补回被改名的锐评块（改 HTML）")
    if "报纸已同步进 site/" in names:
        if stubborn:
            actions.append("（stubborn 模式故意漏跑构建脚本，用来触发熔断）")
        else:
            shutil.copy2(root / PAPER, root / "site" / PAPER)
            actions.append("按 [B] 报纸已同步进 site/ → 跑 build_index.py 等价的同步（改产物）")
    return actions


def demo(stubborn: bool) -> int:
    t = sandbox()
    print(f"沙盒：{t}")
    print("先跑一遍完整断言作为基线：", end="")
    code, results, _ = run_validation(t)
    print(f"{sum(1 for r in results if r[2])}/{len(results)}，退出码 {code}\n")

    break_it(t)
    print(">>> 故意破坏：11-05 少了一条锐评，且 site/ 里还没有这一期（模型退化 + 漏跑同步）\n")

    status = {"task": "publish", "state": "RUNNING", "rounds": []}
    first_ticket = None
    for rnd in range(1, MAX_ROUNDS + 1):
        code, results, _ = run_validation(t)
        ticket = make_ticket(results, rnd)
        if rnd == 1:
            first_ticket = ticket
        print(f"--- 第 {rnd} 轮：{ticket['passed']}/{ticket['total']} 通过，"
              f"{len(ticket['failed'])} 条失败，退出码 {code} ---")
        status["rounds"].append({"round": rnd, "passed": ticket["passed"],
                                 "total": ticket["total"], "exit": code})
        if code == 0:
            print("闸门判定：ALLOW → 允许进入发布步骤\n")
            status["state"] = "PASS"
            print("第 1 轮工单的结构化形态（真实场景把 instruction 原样发给模型）：")
            print(json.dumps(first_ticket, ensure_ascii=False, indent=2))
            print(f"\n=== 闭环完成：共 {rnd} 轮，全程复跑同一套断言 ===")
            shutil.rmtree(t, ignore_errors=True)
            return 0

        print("工单（失败原文，不做任何转述）：")
        print(ticket["instruction"])
        for a in fix(t, ticket, stubborn):
            print("  修复动作：" + a)
        print()

    status["state"] = "FAILED"
    status["reason"] = f"连续 {MAX_ROUNDS} 轮自检未通过，已熔断；保留现场，禁止发布"
    (t / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== 熔断：三轮仍不过，不发布、留状态、等人介入 ===")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print("现场保留在：", t)
    return 1


def gate(root: Path) -> int:
    print(f"=== 发布闸门：{root} ===")
    code, results, out = run_validation(root)
    if code == 0:
        print(f"ALLOW · {len(results)}/{len(results)} 条断言通过 → 允许发布")
    else:
        print(f"BLOCK · {sum(1 for r in results if r[2])}/{len(results)} 条通过 → 禁止发布")
        print(json.dumps(make_ticket(results, 1), ensure_ascii=False, indent=2))
    print("\n--- validate.py 原始输出（尾部）---")
    print("\n".join(out.strip().splitlines()[-8:]))
    return code


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--gate":
        raise SystemExit(gate(Path(args[1]).resolve() if len(args) > 1 else REAL))
    raise SystemExit(demo(stubborn="--stubborn" in args))
