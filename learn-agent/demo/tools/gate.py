#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晨读卡 · 发布闸门与状态机

gate.py 只做三件事：
    1. 按阶段推进，每一步都往 status.json 写真实结果；
    2. 断言不过就**不允许发布**，并把失败原文整理成工单；
    3. 失败可续跑、连续 3 次失败熔断。

对应教材第 5 章（自动化与可靠性）与第 4 章（副作用排在最后）。

用法：
    python tools/gate.py --date 2026-11-06     # 正常跑：断言全绿才发布
    python tools/gate.py --date 2026-11-06 --resume   # 从上次断点续跑
    python tools/gate.py --date 2026-11-06 --break    # 故意破坏一次，看闸门怎么拦
    python tools/gate.py --status                     # 只看当前状态
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "status.json"
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import build as builder  # noqa: E402
import validate as validator  # noqa: E402

STEPS = ["select", "render", "index", "precheck", "publish"]
MAX_ATTEMPT = 3

# A：可自动；B：做完报备；C：必须先问（写进代码，而不只是写进文档）
PERMISSION = {"read": "A", "publish": "B", "edit_source": "C", "delete": "C"}


def guard(action: str, approved: bool = False) -> None:
    level = PERMISSION[action]
    if level == "C" and not approved:
        raise PermissionError(f"{action} 属于 C 档：本合同轮未获授权，拒绝执行")


def atomic_json(path: Path, obj: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class StatusBook:
    def __init__(self, path: Path = STATUS):
        self.path = path
        self.d: dict = {}
        if path.exists():
            try:
                self.d = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.d = {}

    def begin(self, date: str) -> None:
        same_day = self.d.get("date") == date
        self.d = {
            "date": date,
            "state": "RUNNING",
            "steps": self.d.get("steps", {}) if same_day else {},
            "attempt": (self.d.get("attempt", 0) if same_day else 0) + 1,
            "error": "",
            "resume_from": None,
            "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.save()

    def mark(self, step: str, ok: bool, detail: str = "") -> None:
        self.d.setdefault("steps", {})[step] = ("OK" if ok else "FAILED") + (f":{detail}" if detail else "")
        self.d["updated"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()

    def finish(self) -> str:
        vals = [self.d.get("steps", {}).get(s, "PENDING") for s in STEPS]
        if all(v.startswith("OK") for v in vals):
            state = "OK"
        elif any(v.startswith("OK") for v in vals):
            state = "PARTIAL"
        else:
            state = "FAILED"
        self.d["state"] = state
        # 保留上游显式指定的补偿点（例如「产物坏了要回 index 重新生成」），
        # 只有在没有指定时才按「第一个未成功步骤」推算。
        self.d["resume_from"] = self.d.get("resume_from") or self.computed_resume()
        if state != "OK" and self.d.get("attempt", 0) >= MAX_ATTEMPT:
            self.d["error"] = "CIRCUIT_OPEN：连续失败达到上限，停止自动重试，等人介入"
        self.save()
        return state

    def computed_resume(self) -> str | None:
        for s in STEPS:
            if not self.d.get("steps", {}).get(s, "").startswith("OK"):
                return s
        return None

    def should_skip(self, date: str) -> bool:
        return self.d.get("date") == date and self.d.get("state") == "OK"

    def save(self) -> None:
        atomic_json(self.path, self.d)


def ticket(date: str, results: list[tuple[str, str, bool, str]]) -> dict:
    failed = [{"check": n, "detail": d} for _, n, ok, d in results if not ok]
    return {
        "date": date,
        "state": "FAILED",
        "failed_count": len(failed),
        "failed": failed,
        "instruction": "只修下列失败项，不要动其它文件；修完重跑 gate.py。",
    }


def run(date: str, do_break: bool = False, resume: bool = False) -> int:
    book = StatusBook()
    if resume and book.d.get("date") != date:
        print(f"status.json 里没有 {date} 的现场记录，无法续跑；请先正常跑一次。")
        return 1
    if book.d.get("date") == date and book.d.get("error", "").startswith("CIRCUIT_OPEN"):
        print(f"熔断中：{book.d['error']}\n→ 同一天已失败 {book.d.get('attempt')} 次，请人先看现场（stages/ 与 status.json）。")
        return 2

    # 续跑优先用状态文件里存下来的补偿点；没有时按第一个未成功的步骤推算
    start = (book.d.get("resume_from") or book.computed_resume() or "select") if resume else "select"
    book.begin(date)
    print(f"=== 闸门 · {date} · 第 {book.d['attempt']} 次尝试 · 从 {start} 开始 ===")

    pipe = builder.Pipeline(ROOT, date)
    failed_stage = None
    blocked = False

    for stage in STEPS[STEPS.index(start):]:
        try:
            getattr(pipe, stage)()
        except builder.StageError as e:
            book.mark(stage, False, str(e)[:300])
            failed_stage = stage
            print(f"\n已拦下（{stage}）：{e}")
            break
        book.mark(stage, True)

        # 故意破坏点：index 之后、precheck 之前，模拟「生成物坏了但没人发现」
        if do_break and stage == "index":
            broken = break_preview(pipe)
            print(f"  [破坏    ] 已注入 {broken} 处退化（模拟 agent 生成坏了）")
            results = validator.run(root=ROOT, site_dir=pipe.preview)
            tk = ticket(date, results)
            book.d["state"] = "FAILED"
            book.d["error"] = f"precheck 未通过：{tk['failed_count']} 条"
            # 断点指向 index 而不是 precheck：precheck 只负责判定，不负责修复产物。
            # 续跑要回到「能重新生成产物」的那一步，这是第 5 章说的「补偿点」。
            book.d["resume_from"] = "index"
            book.save()
            print("\n闸门判定：BLOCK → 禁止发布，site/ 未改动")
            print("工单（原样发给 agent）：")
            print(json.dumps(tk, ensure_ascii=False, indent=2))
            blocked = True
            failed_stage = "precheck"
            break

    if blocked:
        print(f"\n状态已写入 {STATUS.name}：state=FAILED · resume_from=index")
        print("修好后再跑 `python tools/gate.py --date " + date + " --resume`，它只会从 index 续跑。")
        return 1

    if failed_stage:
        state = book.finish()
        print(f"\n状态：{state} · resume_from={book.d.get('resume_from')}")
        return 1

    # 发布后的终检：对真实 site/ 再跑一遍同一套断言
    results = validator.run(root=ROOT)
    ok_n = sum(1 for r in results if r[2])
    print(f"\n  [终检    ] {ok_n}/{len(results)} 通过（针对 site/）")
    if ok_n != len(results):
        tk = ticket(date, results)
        book.d["state"] = "PARTIAL"
        book.d["error"] = f"已发布但终检未过：{tk['failed_count']} 条"
        book.d["resume_from"] = "precheck"
        book.save()
        print("状态：PARTIAL（产物已写入，但验收未过，需要人看一眼）")
        print(json.dumps(tk, ensure_ascii=False, indent=2))
        return 1

    # 全部通过
    for s in STEPS:
        book.d.setdefault("steps", {})[s] = "OK"
    book.d["state"] = "OK"
    book.d["resume_from"] = None
    book.d["error"] = ""
    book.save()
    print(f"\n闸门判定：ALLOW → 已发布 · state=OK")
    print(f"状态文件：{STATUS.name}（steps 全绿，attempt={book.d['attempt']}）")
    return 0


def break_preview(pipe: builder.Pipeline) -> int:
    """在「待发布目录」里制造两处真实退化，不动源素材、不动 site/。"""
    card = pipe.preview / "cards" / f"{pipe.date}.html"
    page = card.read_text(encoding="utf-8").replace("<blockquote>", "<blockquote-broken>", 1)
    card.write_text(page, encoding="utf-8")

    idx = pipe.preview / "index.json"
    data = json.loads(idx.read_text(encoding="utf-8"))
    data["items"] = data["items"][1:]          # 索引少一条，与磁盘张数对不上
    data["count"] = len(data["items"])
    atomic_json(idx, data)
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description="晨读卡发布闸门")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--break", dest="do_break", action="store_true", help="故意破坏一次，演示闸门")
    ap.add_argument("--resume", action="store_true", help="从 status.json 的断点续跑")
    ap.add_argument("--status", action="store_true", help="只打印当前状态")
    args = ap.parse_args()

    if args.status:
        book = StatusBook()
        print(json.dumps(book.d or {"状态": "尚无 status.json，还没跑过"}, ensure_ascii=False, indent=2))
        return 0

    return run(args.date, do_break=args.do_break, resume=args.resume)


if __name__ == "__main__":
    raise SystemExit(main())
