#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第 5 章配套：状态机 / 补偿 / 幂等跳过 / 熔断

把「文件存在就算成功」换成「status.json 的 state == OK 才算成功」。
全程只在临时沙盒里造文件，不碰 ai-daily。

用法：
  python status.py            # 跑四个场景的对照演示
  python status.py --json     # 额外打印最后一份状态文件的原始 JSON
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

STEPS = ["generate", "validate", "index", "publish"]
MAX_ATTEMPTS = 3


def atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class StatusBook:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.d = {"date": "", "state": "RUNNING", "steps": {}, "attempt": 0, "error": None}
        if self.path.exists():
            self.d = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self):
        atomic_json(self.path, self.d)

    def begin(self, date: str, attempt: int = 1):
        self.d = {"date": date, "state": "RUNNING",
                  "steps": {s: "PENDING" for s in STEPS},
                  "attempt": attempt, "error": None}
        self.save()

    def mark(self, step: str, ok: bool, detail: str = ""):
        self.d["steps"][step] = ("OK:" + detail if ok else "FAILED:" + detail)
        self.save()

    def finish(self):
        vals = [self.d["steps"].get(s, "PENDING") for s in STEPS]
        if all(v.startswith("OK") for v in vals):
            self.d["state"] = "OK"
        elif any(v.startswith("FAILED") for v in vals):
            # 有成功也有失败 = PARTIAL，可只补偿失败那一步
            self.d["state"] = "PARTIAL" if any(v.startswith("OK") for v in vals) else "FAILED"
        else:
            self.d["state"] = "RUNNING"
        if self.d["state"] == "FAILED" and self.d["attempt"] >= MAX_ATTEMPTS:
            self.d["error"] = "CIRCUIT_OPEN：连续 3 次失败，停止重试，等人介入"
        self.save()

    def resume_from(self):
        """补偿：返回第一个没成功的步骤，从那里续跑，不整条链路重来。"""
        for s in STEPS:
            if not self.d["steps"].get(s, "").startswith("OK"):
                return s
        return None

    def should_skip(self, date: str) -> bool:
        """补发检查的正确判据：只看状态，不看文件是否存在。"""
        return self.d.get("date") == date and self.d.get("state") == "OK"

    def summary(self) -> str:
        return (f"state={self.d['state']:<8} steps="
                + " ".join(f"{k}:{v.split(':')[0]}" for k, v in self.d["steps"].items()))


def demo(show_json: bool) -> int:
    t = Path(tempfile.mkdtemp(prefix="status-demo-"))
    p = t / "status.json"
    print(f"沙盒：{t}\n")

    print("=== 场景 1 · 全绿：补发检查应当跳过 ===")
    b = StatusBook(p)
    b.begin("2026-11-05")
    b.mark("generate", True, "15 版")
    b.mark("validate", True, "32/32")
    b.mark("index", True, "2 期")
    b.mark("publish", True, "200")
    b.finish()
    print(" ", b.summary())
    print("  should_skip(2026-11-05) =", b.should_skip("2026-11-05"),
          " resume_from =", b.resume_from())

    print("\n=== 场景 2 · 发布失败：PARTIAL 支持只补一步 ===")
    b = StatusBook(p)
    b.begin("2026-11-06")
    b.mark("generate", True, "15 版")
    b.mark("validate", True, "32/32")
    b.mark("index", True, "3 期")
    b.mark("publish", False, "deploy 超时")
    b.finish()
    print(" ", b.summary())
    print("  state =", b.d["state"], " resume_from =", b.resume_from(),
          "  → 只重跑 publish，前三步产物保留")

    print("\n=== 场景 3 · 半截文件：文件存在 ≠ 成功 ===")
    half = t / "AI晨报-2026-11-07.html"
    half.write_text("<section>只写了 6 版就崩了</section>", encoding="utf-8")
    b = StatusBook(p)
    b.begin("2026-11-07")
    b.mark("generate", False, "写到第 6 版中断")
    b.finish()
    print(f"  文件存在 = {half.exists()}（{half.stat().st_size} 字节）")
    print(" ", b.summary())
    print("  should_skip(2026-11-07) =", b.should_skip("2026-11-07"),
          "  → 补发检查会正确触发，不会被半截文件骗过")

    print("\n=== 场景 4 · 连续失败：熔断 ===")
    b = StatusBook(p)
    for i in range(1, MAX_ATTEMPTS + 1):
        b.begin("2026-11-08", attempt=i)
        b.mark("generate", False, "素材源 503")
        b.finish()
        print(f"  第 {i} 次：{b.d['state']:<8} error={b.d['error'] or '-'}")
    print("  → 第 3 次写 CIRCUIT_OPEN，停止重试；不会无限跑一整夜")

    if show_json:
        print("\n=== 最后一份状态文件原始 JSON ===")
        print(p.read_text(encoding="utf-8"))

    shutil.rmtree(t, ignore_errors=True)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    raise SystemExit(demo(a.json))
