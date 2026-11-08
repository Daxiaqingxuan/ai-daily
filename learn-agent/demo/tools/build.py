#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晨读卡 · 五阶段流水线

    select → render → index → precheck → publish

每一步只做一件事，产物落盘、可单独检查、可从任意阶段续跑。
对应教材第 3 章（任务分解 / 中间产物 / 幂等 / 原子写）与第 4 章（副作用在最后）。

用法：
    python tools/build.py                          # 出今天的卡（今天没素材会报可读错误）
    python tools/build.py --date 2026-11-06        # 指定日期
    python tools/build.py --date 2026-11-06 --from index   # 只重跑后半段
    python tools/build.py --date 2026-11-06 --twice        # 连跑两次比 md5

设计取舍（值得记住的一条）：
    索引里的 updated 取「排期时间」= <date> 08:00，而不是 datetime.now()。
    否则同一份输入连跑两次会得到不同字节，幂等永远测不过。
    真实项目若必须写当前时刻，幂等比对就要先规范化掉这个字段。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "quotes.json"
TEMPLATES = ROOT / "templates"
STAGES = ROOT / "stages"
PREVIEW = STAGES / "preview"
SITE = ROOT / "site"

STAGE_ORDER = ["select", "render", "index", "precheck", "publish"]
# 每个阶段依赖哪些前置产物：从中间阶段续跑时先检查，缺了就给人话，而不是抛 FileNotFoundError
REQUIRED = {
    "select": [],
    "render": ["selected.json"],
    "index": ["card.html"],
    "precheck": ["index.json"],
    "publish": ["precheck.ok"],
}
WEEKDAYS = "一二三四五六日"


class StageError(RuntimeError):
    """阶段失败：信息要能直接给人看，不包一层看不懂的异常。"""


def md5_bytes(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()[:10]


def md5_file(p: Path) -> str:
    return md5_bytes(p.read_bytes())


def atomic_write(path: Path, text: str) -> str:
    """先写 .tmp，再 os.replace。任何时刻观察者看到的要么是旧文件，要么是完整新文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return md5_file(path)


class Pipeline:
    def __init__(self, root: Path, date: str):
        self.root = root
        self.date = date
        self.stages = root / "stages"
        self.preview = self.stages / "preview"
        self.site = root / "site"
        self.payload: dict | None = None

    # ---------- 阶段 1：select ----------
    def select(self) -> None:
        data = json.loads((self.root / "data" / "quotes.json").read_text(encoding="utf-8"))
        quotes = data.get("quotes", [])
        if not quotes:
            raise StageError("quotes.json 里没有 quotes 数组，或数组为空")

        hit = [q for q in quotes if q.get("date") == self.date]
        if not hit:
            available = sorted(q.get("date", "?") for q in quotes)
            raise StageError(
                f"{self.date} 没有素材。可用日期：{available[0]} … {available[-1]}（共 {len(available)} 天）\n"
                f"  → 这不是 bug，是「缺素材必须显式失败」：宁可不出卡，也不要拿别的日期顶上。"
            )
        if len(hit) > 1:
            raise StageError(f"{self.date} 命中 {len(hit)} 条素材，必须唯一；请先修 data/quotes.json")

        q = hit[0]
        self.payload = {
            "date": self.date,
            "id": q["id"],
            "text": q["text"],
            "author": q["author"],
            "source": q["source"],
            "tags": list(q.get("tags") or []),
            "picked_from": len(quotes),
        }
        body = json.dumps(self.payload, ensure_ascii=False, indent=2) + "\n"
        self.stages.mkdir(parents=True, exist_ok=True)
        digest = atomic_write(self.stages / "selected.json", body)
        print(f"  [select  ] 选中 {q['id']}（{len(quotes)} 条素材中唯一匹配）{' ' * 8}md5={digest}")

    # ---------- 阶段 2：render ----------
    def render(self) -> None:
        p = self._load_selected()
        tpl = (self.root / "templates" / "card.html").read_text(encoding="utf-8")
        d = dt.date.fromisoformat(p["date"])
        esc = html.escape

        page = (tpl
                .replace("{{TITLE}}", esc(f"晨读卡 · {d.month} 月 {d.day} 日"))
                .replace("{{DATE_CN}}", f"{d.year} 年 {d.month} 月 {d.day} 日")
                .replace("{{WEEKDAY}}", "星期" + WEEKDAYS[d.weekday()])
                .replace("{{TEXT}}", esc(p["text"]))
                .replace("{{AUTHOR}}", esc(p["author"]))
                .replace("{{SOURCE}}", esc(p["source"]))
                .replace("{{ID}}", esc(p["id"]))
                .replace("{{TAGS}}", "".join(f"<span>{esc(t)}</span>" for t in p["tags"])))

        leftovers = re.findall(r"\{\{[A-Z_]+\}\}", page)
        if leftovers:
            raise StageError(f"模板还有未替换的占位符：{leftovers}")

        digest = atomic_write(self.stages / "card.html", page)
        print(f"  [render  ] 单卡已渲染 {len(page) / 1024:.1f} KB{' ' * 14}md5={digest}")

    # ---------- 阶段 3：index（全量重建，天然幂等） ----------
    def index(self) -> None:
        card = (self.stages / "card.html").read_text(encoding="utf-8")
        quotes = json.loads((self.root / "data" / "quotes.json").read_text(encoding="utf-8"))["quotes"]
        by_date = {q["date"]: q for q in quotes}

        # 待发布目录：历史卡从 site/ 复制过来，再放上这次的新卡
        (self.preview / "cards").mkdir(parents=True, exist_ok=True)
        if (self.site / "cards").exists():
            for old in sorted((self.site / "cards").glob("*.html")):
                target = self.preview / "cards" / old.name
                if not target.exists():
                    target.write_bytes(old.read_bytes())
        (self.preview / "cards" / f"{self.date}.html").write_text(card, encoding="utf-8")

        # 索引只列「磁盘上真实存在的卡」，所以条数与文件数天然一致
        items = []
        for f in sorted((self.preview / "cards").glob("*.html"), reverse=True):
            day = f.stem
            q = by_date.get(day)
            full = q["text"] if q else "（素材缺失）"
            items.append({
                "date": day,
                "title": full if len(full) <= 24 else full[:24] + "…",
                "file": f"cards/{f.name}",
                "author": q["author"] if q else "",
            })
        indexes = {
            "updated": f"{self.date} 08:00",
            "count": len(items),
            "items": items,
        }
        digest = atomic_write(self.stages / "index.json",
                              json.dumps(indexes, ensure_ascii=False, indent=2) + "\n")

        wall_tpl = (self.root / "templates" / "wall.html").read_text(encoding="utf-8")
        rows = "\n".join(
            f'      <a class="item" href="{html.escape(it["file"])}">'
            f'<span class="d">{html.escape(it["date"][5:])}</span>'
            f'<span class="t">{html.escape(it["title"])}</span></a>'
            for it in items
        )
        wall = (wall_tpl
                .replace("{{COUNT}}", str(len(items)))
                .replace("{{UPDATED}}", html.escape(indexes["updated"]))
                .replace("{{ITEMS}}", rows))
        atomic_write(self.preview / "index.html", wall)
        atomic_write(self.preview / "index.json", json.dumps(indexes, ensure_ascii=False, indent=2) + "\n")
        print(f"  [index   ] 索引 {len(items)} 张（全量重建）{' ' * 16}md5={digest}")

    # ---------- 阶段 4：precheck（对「待发布目录」跑同一套断言） ----------
    def precheck(self) -> None:
        sys.path.insert(0, str(self.root / "tools"))
        import validate as validator  # noqa: PLC0415 - 故意延迟导入，保持阶段独立

        results = validator.run(root=self.root, site_dir=self.preview)
        failed = [(n, d) for _, n, ok, d in results if not ok]
        if failed:
            detail = "\n".join(f"    · {n} —— 实测：{d}" for n, d in failed)
            raise StageError(f"发布前断言未通过（{len(failed)} 条）：\n{detail}\n"
                             f"  → 已拦在 publish 之前，site/ 一个字节都没动。")
        atomic_write(self.stages / "precheck.ok", f"{len(results)} / {len(results)}\n")
        print(f"  [precheck] 断言 {len(results)}/{len(results)} 通过（针对待发布目录）")

    # ---------- 阶段 5：publish（唯一有外部影响的阶段） ----------
    def publish(self) -> None:
        if not (self.stages / "precheck.ok").exists():
            raise StageError("没有 precheck 通过记录，拒绝发布（闸门在后，不在前）")

        written = []
        for f in sorted((self.preview / "cards").glob("*.html")):
            target = self.site / "cards" / f.name
            if target.exists() and target.read_bytes() == f.read_bytes():
                continue
            atomic_write(target, f.read_text(encoding="utf-8"))
            written.append(f"cards/{f.name}")
        for name in ("index.json", "index.html"):
            src = (self.preview / name).read_text(encoding="utf-8")
            target = self.site / name
            if target.exists() and target.read_text(encoding="utf-8") == src:
                continue
            atomic_write(target, src)
            written.append(name)

        digest = md5_file(self.site / "index.json")
        print(f"  [publish ] 写入 site/：{len(written)} 个文件{' ' * 14}md5={digest}")
        if not written:
            print("             （内容与线上一致，没有产生写入 —— 幂等的可见形式）")

    # ---------- 编排 ----------
    def _load_selected(self) -> dict:
        p = self.stages / "selected.json"
        if not p.exists():
            raise StageError(f"缺前序产物 {p.name}：请先跑 `python tools/build.py --date {self.date}`")
        return json.loads(p.read_text(encoding="utf-8"))

    def run(self, start: str = "select") -> None:
        i = STAGE_ORDER.index(start)
        if i > 0:
            missing = [r for st in STAGE_ORDER[:i] for r in REQUIRED[st]
                       if not (self.stages / r).exists()]
            if missing:
                raise StageError(
                    f"从 {start} 续跑要求前序产物存在，缺：{', '.join(sorted(set(missing)))}\n"
                    f"  → 先跑一次完整流水线，再用 --from 只重跑后半段。"
                )
            print(f"--from {start}：复用 {self.stages.name}/ 里的已有产物，只重跑 {' → '.join(STAGE_ORDER[i:])}\n")
        for stage in STAGE_ORDER[i:]:
            getattr(self, stage)()


def main() -> int:
    ap = argparse.ArgumentParser(description="晨读卡五阶段流水线")
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="出刊日期 YYYY-MM-DD")
    ap.add_argument("--from", dest="start", default="select", choices=STAGE_ORDER, help="从哪个阶段续跑")
    ap.add_argument("--twice", action="store_true", help="连跑两次并比对中间产物 md5")
    args = ap.parse_args()

    print(f"=== 晨读卡流水线 · {args.date} ===")
    try:
        pipe = Pipeline(ROOT, args.date)
        pipe.run(args.start)
    except StageError as e:
        print(f"\n已拦下：{e}")
        print("状态：未发布。site/ 保持上一版不变。")
        return 1

    if args.twice:
        print("\n--twice：连跑第二次，比对中间产物")
        before = {p.name: md5_file(p) for p in sorted(pipe.stages.glob("*")) if p.is_file()}
        pipe.run("select")
        after = {p.name: md5_file(p) for p in sorted(pipe.stages.glob("*")) if p.is_file()}
        same = before == after
        for name in sorted(before):
            flag = "一致" if before[name] == after.get(name) else "不一致"
            print(f"  {name:<16} {before[name]} vs {after.get(name, '-')}  {flag}")
        print("结论：" + ("完全一致 → 幂等" if same else "产物变化 → 不幂等，需排查时间戳/随机数"))
        return 0 if same else 1

    print(f"\n产物目录：{pipe.site}（发布） / {pipe.stages}（中间产物）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
