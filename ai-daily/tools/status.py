#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晨报状态机：把「今天这期走到哪一步」记进 status.json。

五个阶段，顺序不可换：

    parts     15 个版面片段就位
    assemble  拼版通过 8 条断言并落盘
    index     site/ 同步完成、issues.js 收录当期
    deploy    site/ 已发布到线上（发布是 agent 工具，脚本只记结果）
    verify    线上三处验证通过（同上）

为什么需要：出报是五步链，任何一步失败都可能留下「文件在、站点没跟上」这种半成品。
没有状态文件时只能靠人回忆停在哪；有状态文件，续跑、闸门、启动检查才有依据。

用法：
    python tools/status.py --status                  # 人读
    python tools/status.py --status --json           # 机读
    python tools/status.py --begin --date 2026-11-06 --issue 003
    python tools/status.py --mark assemble=OK index=OK
    python tools/status.py --mark index=FAILED:"issues.js 未收录 11-06"
    python tools/status.py --gate                    # 发布前闸门：0 允许 / 1 拒绝
    python tools/status.py --finish                  # 结算并打印
    python tools/status.py --ticket                  # 失败工单（JSON，可原样回传）

被谁调用：
    assemble_issue.py 成功后记 assemble；build_index.py 成功后记 index；
    boot_check.py 启动时读它判断「半成品」；发布前后由 agent 记 deploy / verify。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# 允许用环境变量把状态写到别处：试拼 / 演练时用临时文件，别污染当期状态
STATUS = Path(os.environ.get("AI_DAILY_STATUS") or (ROOT / "status.json"))

STEPS = ["parts", "assemble", "index", "deploy", "verify"]
STEP_CN = {
    "parts": "版面片段",
    "assemble": "拼版落盘",
    "index": "索引与站点同步",
    "deploy": "发布到线上",
    "verify": "线上验证",
}
# 发布闸门只卡前三个阶段：deploy / verify 本身是公开发布动作的结果，不能自证。
DEPLOY_REQUIRE = ("parts", "assemble", "index")
MAX_ATTEMPT = 3
HISTORY_MAX = 30


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def atomic_json(path: Path, obj: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def ok_of(value: str) -> bool:
    return bool(value) and value.startswith("OK")


def detail_of(value: str) -> str:
    return value.split(":", 1)[1] if value and ":" in value else ""


class Book:
    """status.json 的读写。每次改动都原子落盘，绝不留下半截 JSON。"""

    def __init__(self, path: Path | None = None):
        self.path = Path(path or STATUS)
        self.d: dict = {}
        if self.path.exists():
            try:
                self.d = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(self.d, dict):
                    self.d = {}
            except Exception:
                self.d = {}

    # ---------- 写 ----------

    def save(self) -> None:
        atomic_json(self.path, self.d)

    def begin(self, date: str, issue: str = "", note: str = "") -> None:
        same_day = self.d.get("date") == date
        history = list(self.d.get("history") or [])[-HISTORY_MAX:]
        history.append({"at": now(), "event": "begin", "attempt": (self.d.get("attempt", 0) if same_day else 0) + 1})
        self.d = {
            "date": date,
            "issue": issue or (self.d.get("issue", "") if same_day else ""),
            "state": "RUNNING",
            "steps": dict(self.d.get("steps") or {}) if same_day else {},
            "attempt": (self.d.get("attempt", 0) if same_day else 0) + 1,
            "error": "",
            "resume_from": None,
            "note": note,
            "updated": now(),
            "history": history[-HISTORY_MAX:],
        }
        self.save()

    def mark(self, step: str, ok: bool, detail: str = "") -> None:
        if step not in STEPS:
            raise ValueError("未知阶段：%s（可选：%s）" % (step, "/".join(STEPS)))
        self.d.setdefault("steps", {})[step] = ("OK" if ok else "FAILED") + ((":" + detail) if detail else "")
        history = list(self.d.get("history") or [])[-HISTORY_MAX:]
        history.append({"at": now(), "step": step, "value": self.d["steps"][step]})
        self.d["history"] = history[-HISTORY_MAX:]
        self.recalc()

    def recalc(self) -> None:
        steps = self.d.get("steps") or {}
        values = [steps.get(s, "") for s in STEPS]
        done = [v for v in values if ok_of(v)]
        failed = [v for v in values if v.startswith("FAILED")]
        if len(done) == len(STEPS):
            state = "OK"
        elif failed:
            state = "PARTIAL" if done else "FAILED"
        else:
            state = "RUNNING"

        self.d["state"] = state
        self.d["resume_from"] = next((s for s in STEPS if not ok_of(steps.get(s, ""))), None)
        self.d["updated"] = now()

        attempt = int(self.d.get("attempt") or 0)
        if failed and attempt >= MAX_ATTEMPT:
            self.d["error"] = "CIRCUIT_OPEN：已失败 %d 次，停止自动重试，等人介入" % attempt
        elif failed:
            first = next(s for s in STEPS if (steps.get(s, "") or "").startswith("FAILED"))
            self.d["error"] = "%s失败：%s" % (STEP_CN.get(first, first), detail_of(steps.get(first, "")) or "未记录原因")
        else:
            self.d["error"] = ""
        self.save()

    # ---------- 读 ----------

    def step_value(self, step: str) -> str:
        return (self.d.get("steps") or {}).get(step, "")

    def done(self, step: str) -> bool:
        return ok_of(self.step_value(step))

    def gate(self, date: str = "") -> tuple[bool, str]:
        """发布前闸门。返回 (是否放行, 原因)。"""
        if not self.d:
            return False, "没有 status.json：这期不是按流程跑的，先补 --begin 与 assemble/index 记录"
        if date and self.d.get("date") != date:
            return False, "status.json 记录的是 %s，不是 %s" % (self.d.get("date"), date)
        if str(self.d.get("error", "")).startswith("CIRCUIT_OPEN"):
            return False, self.d["error"]
        missing = [s for s in DEPLOY_REQUIRE if not self.done(s)]
        if missing:
            first = missing[0]
            return False, "未完成：%s；请从 %s 续跑（补偿点 resume_from=%s）" % (
                "、".join(STEP_CN.get(s, s) for s in missing), first, self.d.get("resume_from"))
        return True, "前三个阶段全部 OK，允许发布"

    def ticket(self) -> dict:
        steps = self.d.get("steps") or {}
        failed = [
            {"step": s, "cn": STEP_CN.get(s, s), "detail": detail_of(steps.get(s, "")) or "未记录原因"}
            for s in STEPS if (steps.get(s, "") or "").startswith("FAILED")
        ]
        return {
            "date": self.d.get("date", ""),
            "issue": self.d.get("issue", ""),
            "state": self.d.get("state", ""),
            "attempt": self.d.get("attempt", 0),
            "resume_from": self.d.get("resume_from"),
            "failed_count": len(failed),
            "failed": failed,
            "instruction": "只修下列失败项，不要重写已经 OK 的产物；修完重跑对应命令，再跑 status.py --finish。",
        }

    def render(self) -> str:
        if not self.d:
            return "尚无 status.json：这个工作区还没按新流程跑过一期。"
        lines = [
            "日期：    %s" % self.d.get("date", "?"),
            "期号：    %s" % (("第 %s 期" % self.d["issue"]) if self.d.get("issue") else "未记录"),
            "状态：    %s" % self.d.get("state", "?"),
            "尝试：    第 %s 次" % self.d.get("attempt", 0),
            "更新时间：%s" % self.d.get("updated", "?"),
        ]
        if self.d.get("error"):
            lines.append("错误：    %s" % self.d["error"])
        if self.d.get("resume_from"):
            lines.append("续跑点：  %s（%s）" % (self.d["resume_from"], STEP_CN.get(self.d["resume_from"], "")))
        lines.append("阶段：")
        for s in STEPS:
            v = self.step_value(s)
            mark = "·" if not v else ("✓" if ok_of(v) else "✗")
            extra = detail_of(v)
            lines.append("  %s %-9s %s%s" % (mark, s, STEP_CN.get(s, s), ("  " + extra) if extra else ""))
        return "\n".join(lines)


# ---------- 给其它脚本用的极简接口 ----------

def note(date: str, issue: str, step: str, ok: bool, detail: str = "") -> Book:
    """在流水线脚本里埋点。

    当天没有记录时自动开一期；日期不同则视为新的一期，重新计数。
    任何异常都不应向调用方抛出——状态记录是辅助，不能拖垮出报主流程。
    """
    b = Book()
    if b.d.get("date") != date:
        b.begin(date, issue)
    elif issue and not b.d.get("issue"):
        b.d["issue"] = issue
    b.mark(step, ok, detail)
    return b


def read() -> Book:
    return Book()


# ---------- CLI ----------

def parse_marks(items: list[str]) -> list[tuple[str, bool, str]]:
    out = []
    for it in items:
        if "=" not in it:
            raise SystemExit("--mark 格式应为 step=OK 或 step=FAILED:原因，收到：%s" % it)
        step, value = it.split("=", 1)
        step = step.strip()
        value = value.strip()
        ok = value.upper().startswith("OK")
        detail = value.split(":", 1)[1].strip() if ":" in value else ""
        out.append((step, ok, detail))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="晨报状态机", add_help=True)
    ap.add_argument("--status", action="store_true", help="打印当前状态")
    ap.add_argument("--json", action="store_true", help="配合 --status 输出原始 JSON")
    ap.add_argument("--begin", action="store_true", help="开一期新记录")
    ap.add_argument("--date", default="", help="YYYY-MM-DD，默认今天")
    ap.add_argument("--issue", default="", help="三位期号")
    ap.add_argument("--mark", nargs="+", default=[], metavar="STEP=OK|FAILED:原因")
    ap.add_argument("--gate", action="store_true", help="发布前闸门")
    ap.add_argument("--finish", action="store_true", help="结算并打印")
    ap.add_argument("--ticket", action="store_true", help="输出失败工单 JSON")
    ap.add_argument("--path", default="", help="指定 status.json（测试用）")
    a = ap.parse_args()

    date = a.date or dt.date.today().isoformat()
    book = Book(Path(a.path) if a.path else None)

    # --mark/--gate/--finish 作用于「当前记录」；没指定日期时沿用记录里的日期，
    # 否则稍后补记一次就会把昨天那期覆盖成今天（真实踩过的坑）。
    if not a.date and not a.begin and book.d.get("date"):
        date = book.d["date"]

    if a.status:
        if a.json:
            print(json.dumps(book.d or {}, ensure_ascii=False, indent=2))
        else:
            print(book.render())
        return 0

    if a.begin:
        book.begin(date, a.issue)
        print("已开始记录 %s%s" % (date, (" 第 %s 期" % a.issue) if a.issue else ""))
        print(book.render())
        return 0

    if a.mark:
        if book.d.get("date") != date:
            book.begin(date, a.issue)
        for step, ok, detail in parse_marks(a.mark):
            book.mark(step, ok, detail)
        print(book.render())
        # 只要有一个阶段是 FAILED 就返回非 0，避免 PARTIAL 被脚本当成成功
        failed = any((v or "").startswith("FAILED")
                     for v in (book.d.get("steps") or {}).values())
        return 1 if failed else 0

    if a.gate:
        allowed, why = book.gate(a.date)
        print(("闸门：ALLOW · " if allowed else "闸门：BLOCK · ") + why)
        return 0 if allowed else 1

    if a.ticket:
        print(json.dumps(book.ticket(), ensure_ascii=False, indent=2))
        return 0

    if a.finish:
        book.recalc()
        print(book.render())
        return 0 if book.d.get("state") == "OK" else 1

    print(book.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
