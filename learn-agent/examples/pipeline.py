#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第 3–4 章配套：分阶段流水线

演示四件事：中间产物落盘、可单独重跑、幂等、原子写（含事实核查独立一步）。
全程只在临时沙盒里造文件，不碰 ai-daily。

用法：
  python pipeline.py                   # 完整跑一遍 6 个阶段
  python pipeline.py --from write      # 只重跑 write 及之后，复用前面的产物
  python pipeline.py --twice           # 连跑两次，比对全部中间产物 md5（幂等）
  python pipeline.py --bad-material    # 注入跨来源数字冲突，验证坏素材停在 verify
  python pipeline.py --keep            # 保留沙盒目录供检查
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

STAGES = ["collect", "verify", "write", "assemble", "validate", "publish"]

MATERIAL = [
    {"id": "repo-a", "name": "项目 A", "source": "github", "date": "2026-11-05", "number": "12.4k"},
    {"id": "repo-b", "name": "项目 B", "source": "github", "date": "2026-11-05", "number": "8.1k"},
    {"id": "model-c", "name": "模型 C", "source": "价目表", "date": "2026-11-05", "number": "$2/M"},
]
PUBLISHED_FACTS = {"repo-a": "12.4k", "repo-b": "8.1k", "model-c": "$2/M"}

CSS = "body{font-family:serif;color:#1b1a17;background:#fbf8f0}"
SKELETON = ("<html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<style>{css}</style></head><body>{body}</body></html>")


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()[:10]


def atomic_write(path: Path, text: str, validator=None) -> str:
    """临时文件 → 校验 → os.replace 原子改名；观察者只会看到旧文件或完整新文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    if validator:
        code, why = validator(tmp)
        if code != 0:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"原子写被拦下：{why}（临时文件已删，目标文件未被触碰）")
    os.replace(tmp, path)
    return md5(path)


class Pipeline:
    def __init__(self, root: Path, bad_material: bool = False):
        self.out = root / "stages"
        self.out.mkdir(parents=True, exist_ok=True)
        self.bad = bad_material

    def _say(self, stage: str, msg: str, h: str = "") -> None:
        print(f"  [{stage:<9}] {msg}" + (f"   md5={h}" if h else ""))

    def collect(self):
        items = [dict(x) for x in MATERIAL]
        if self.bad:
            items[0]["number"] = "99.9k"  # 与已发布口径冲突
        h = atomic_write(self.out / "material.json",
                         json.dumps({"items": items}, ensure_ascii=False, indent=2))
        self._say("collect", f"素材落盘（{len(items)} 条，字段 source/date/number 齐全）", h)

    def verify(self):
        items = json.loads((self.out / "material.json").read_text(encoding="utf-8"))["items"]
        problems = []
        for it in items:
            for k in ("source", "date", "number"):
                if not it.get(k):
                    problems.append(f"{it['id']} 缺字段 {k}")
            expect = PUBLISHED_FACTS.get(it["id"], it["number"])
            if expect != it["number"]:
                problems.append(f"{it['id']} 数字冲突：素材 {it['number']} ≠ 口径表 {expect}")
        if problems:
            raise RuntimeError("事实核查未过：" + "；".join(problems))
        h = atomic_write(self.out / "material.checked.json",
                         json.dumps({"items": items, "checked": True, "problems": []},
                                    ensure_ascii=False, indent=2))
        self._say("verify", "独立核对通过（字段齐全 + 跨来源数字一致）", h)

    def write(self):
        items = json.loads((self.out / "material.checked.json").read_text(encoding="utf-8"))["items"]
        body = "\n".join(
            f"<p>{it['name']}：{it['number']}（{it['source']}，{it['date']}）</p>" for it in items)
        h = atomic_write(self.out / "body.md", "# 本期正文片段\n\n" + body)
        self._say("write", "只写正文片段，模型看不到 CSS", h)

    def assemble(self):
        body = (self.out / "body.md").read_text(encoding="utf-8").split("\n", 2)[-1]
        def v(tmp):
            t = tmp.read_text(encoding="utf-8")
            return (0, "") if "<style>" in t and "viewport" in t else (1, "骨架缺 style 或 viewport")
        h = atomic_write(self.out / "paper.html", SKELETON.format(css=CSS, body=body), validator=v)
        self._say("assemble", "脚本拼装整页（CSS 由代码注入，模型不参与）", h)

    def validate(self):
        text = (self.out / "paper.html").read_text(encoding="utf-8")
        n = text.count("<p>")
        if n != len(MATERIAL):
            raise RuntimeError(f"断言失败：期望 {len(MATERIAL)} 段，实测 {n}")
        self._say("validate", f"断言通过（{n} 段正文、viewport、style 齐全）")

    def publish(self):
        h = atomic_write(self.out / "status.json",
                         json.dumps({"state": "OK", "stages": STAGES, "published": True},
                                    ensure_ascii=False, indent=2))
        self._say("publish", "（模拟）发布 + 写状态文件", h)

    REQUIRED = {
        "collect": [], "verify": ["material.json"],
        "write": ["material.checked.json"], "assemble": ["body.md"],
        "validate": ["paper.html"], "publish": ["paper.html"],
    }

    def run(self, start: str = "collect"):
        i = STAGES.index(start)
        if i > 0:
            missing = [f for f in self.REQUIRED[start]
                       if not (self.out / f).exists()]
            if missing:
                raise RuntimeError(
                    f"无法从 {start} 续跑：缺少前序产物 {missing}，请先跑完整流水线")
            have = sorted(p.name for p in self.out.iterdir())
            print(f"--from {start}：复用已有中间产物 {have}")
            print(f"  只重跑 {STAGES[i:]}\n")
        for st in STAGES[i:]:
            getattr(self, st)()
        return self


def snapshot(root: Path) -> dict:
    return {p.name: md5(p) for p in sorted((root / "stages").iterdir())
            if p.is_file() and p.name != "status.json"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", choices=STAGES, default="collect")
    ap.add_argument("--twice", action="store_true")
    ap.add_argument("--bad-material", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    t = Path(tempfile.mkdtemp(prefix="pipeline-demo-"))
    print(f"沙盒：{t}\n")
    code = 0
    try:
        if a.bad_material:
            print("=== 注入跨来源数字冲突，验证坏素材停在 verify ===\n")
            try:
                Pipeline(t, bad_material=True).run()
                print("!! 错误：冲突竟然流到了发布")
                code = 1
            except RuntimeError as e:
                print(f"已拦下：{e}")
                left = sorted(p.name for p in (t / "stages").iterdir())
                print(f"现场产物：{left}")
                print("→ 没有 body.md / paper.html / status.json：坏素材没有流到下游")
        elif a.twice:
            print("=== 幂等测试：连跑两次，比对全部中间产物 md5 ===\n")
            print("--- 第 1 次 ---")
            Pipeline(t).run()
            s1 = snapshot(t)
            print("\n--- 第 2 次 ---")
            Pipeline(t).run()
            s2 = snapshot(t)
            print("\n逐项比对：")
            for k in sorted(set(s1) | set(s2)):
                print(f"  {k:<26} {s1.get(k, '-')}  {s2.get(k, '-')}")
            print("结论：", "完全一致 → 幂等" if s1 == s2 else "不一致 → 不幂等")
            code = 0 if s1 == s2 else 1
        else:
            print(f"=== 完整流水线（{len(STAGES)} 个阶段，每步产物落盘）===\n")
            if a.start != "collect":
                print("--- 先建立现场：完整跑一遍 ---")
                Pipeline(t).run()
                print("\n--- 再演示「只重跑后半段」---\n")
            Pipeline(t).run(a.start)
            print(f"\n最终产物：{sorted(x.name for x in (t / 'stages').iterdir())}")
            print("每份中间产物都能单独抽查；任一步失败可从那一步续跑，不必整期重来。")
            code = 0
    finally:
        if a.keep:
            print("\n现场保留：", t)
        else:
            shutil.rmtree(t, ignore_errors=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
