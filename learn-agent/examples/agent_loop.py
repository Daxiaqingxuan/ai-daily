#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第 8 章配套：产品内嵌 agent 的最小循环（不调用真实模型）

用确定性规则模拟 model.decide()，好让四个机制在无模型环境下也能跑通：
  工具白名单 / 副作用单独授权 / 每步留 trace / 步数与成本双上限

用法：python agent_loop.py
"""
from __future__ import annotations

import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SAFE_TOOLS = ("read_sensors", "list_processes", "read_log")
SIDE_EFFECT = "write_diagnosis"


def read_sensors():
    return {"cpu_temp": 91, "gpu_temp": 78, "gpu_util": 97, "fan_rpm": 2100}


def list_processes():
    return [{"name": "blender.exe", "gpu": 71}, {"name": "chrome.exe", "gpu": 9}]


def read_log(n=3):
    return ["17:02 驱动 26.9.1 已加载", "17:03 GPU 占用 97%", "17:04 风扇提速"][:n]


TOOLS = {"read_sensors": read_sensors, "list_processes": list_processes, "read_log": read_log}


class Store:
    def __init__(self):
        self.diagnosis = []

    def write(self, text):
        self.diagnosis.append(text)
        return "已记入诊断日志"


DIAGNOSIS = ("GPU 占用 97% 且 blender.exe 占 71%，疑似渲染负载导致升温；"
             "建议核对驱动 26.9.1 与机箱风道，暂不改动设置。")


class Loop:
    def __init__(self, approve_write=False, max_steps=6, token_budget=1000, rogue=False):
        self.store, self.trace, self.spent = Store(), [], 0
        self.approve, self.max_steps = approve_write, max_steps
        self.budget, self.rogue, self.blocked = token_budget, rogue, None

    def decide(self):
        """真实系统里这一行换成 model.decide(context, tools_schema)。"""
        n = sum(1 for t in self.trace if t.get("event") == "TOOL")
        if self.rogue and n == 2:
            return "delete_logs", {}
        plan = [("read_sensors", {}), ("list_processes", {}), ("read_log", {"n": 3}),
                (SIDE_EFFECT, {"text": DIAGNOSIS})]
        return plan[min(n, len(plan) - 1)]

    def run(self):
        for step in range(1, self.max_steps + 1):
            name, args = self.decide()
            if name not in TOOLS and name != SIDE_EFFECT:
                self.blocked = f"白名单拦下未知工具 {name}"
                self.trace.append({"step": step, "event": "BLOCKED", "reason": self.blocked})
                break
            if name == SIDE_EFFECT and not self.approve:
                self.blocked = "副作用工具未授权：只读完成，不写入"
                self.trace.append({"step": step, "event": "BLOCKED", "reason": self.blocked})
                break
            cost = 120
            if self.spent + cost > self.budget:
                self.blocked = f"成本上限：{self.spent} + {cost} > {self.budget}"
                self.trace.append({"step": step, "event": "BLOCKED", "reason": self.blocked})
                break
            result = self.store.write(args["text"]) if name == SIDE_EFFECT else TOOLS[name](**args)
            self.spent += cost
            self.trace.append({"step": step, "event": "TOOL", "tool": name,
                               "result": result, "cost": cost})
            if name == SIDE_EFFECT:
                break
        return {"trace": self.trace, "spent": self.spent,
                "blocked": self.blocked, "written": self.store.diagnosis}


def main() -> int:
    cases = [
        ("正常：只读三件 + 授权写入", dict(approve_write=True)),
        ("未授权：只给只读工具", dict(approve_write=False)),
        ("成本上限", dict(approve_write=True, token_budget=200)),
        ("模型幻觉调用未知工具", dict(approve_write=True, rogue=True)),
    ]
    for title, kw in cases:
        r = Loop(**kw).run()
        tools = [t["tool"] for t in r["trace"] if t["event"] == "TOOL"]
        print(f"=== {title} ===")
        print(f"  调用：{tools}")
        print(f"  花费：{r['spent']} tokens / 步数 {len(r['trace'])}")
        print(f"  拦截：{r['blocked'] or '无'}")
        print(f"  落库诊断：{len(r['written'])} 条" + (f" → {r['written'][0][:38]}…" if r["written"] else ""))
        print()
    print("四个机制缺一不可：白名单挡幻觉、授权挡副作用、trace 可复盘、上限防失控。")
    print("真实循环的完整 trace（正常用例）：")
    print(json.dumps(Loop(approve_write=True).run()["trace"], ensure_ascii=False, indent=2)[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
