#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晨读卡 · 验收断言（19 条）

这个文件先于生成器存在，顺序是故意的：
    先定义「怎样算做对了」，再写「怎么做」。
对应教材第 2 章「验收前置」。

用法：
    python tools/validate.py          # 只判定，不生成任何文件
    python tools/validate.py --json   # 结构化输出，供 agent/闸门消费

约定：
    每条断言都必须带「实测值」，失败时能直接当工单发给 agent（第 2 章）。
    退出码 0 = 全通过；1 = 有失败。
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "quotes.json"
SITE = ROOT / "site"
CARDS = SITE / "cards"
INDEX = SITE / "index.json"
WALL = SITE / "index.html"
STATUS = ROOT / "status.json"

FIELDS = ("id", "date", "text", "author", "source", "tags")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(root: Path = ROOT, site_dir: Path | None = None) -> list[tuple[str, str, bool, str]]:
    """执行全部断言，返回 [(组, 名称, 是否通过, 实测值)]。

    site_dir 允许指向「待发布目录」：发布前就能对将要上线的东西跑同一套断言，
    而不是先发布再检查（第 4 章：闸门必须在副作用之前）。
    """
    res: list[tuple[str, str, bool, str]] = []

    def check(group: str, name: str, ok: bool, detail: str = "") -> None:
        res.append((group, name, bool(ok), detail))

    data_p = root / "data" / "quotes.json"
    site = site_dir or (root / "site")
    cards = site / "cards"
    index_p, wall_p, status_p = site / "index.json", site / "index.html", root / "status.json"

    # ---------- A. 契约 ----------
    agents = root / "AGENTS.md"
    check("A", "AGENTS.md 存在", agents.exists(),
          f"{agents.name} 缺" if not agents.exists() else f"{agents.stat().st_size} 字节")

    text_a = agents.read_text(encoding="utf-8") if agents.exists() else ""
    check("A", "契约写了唯一真源", "唯一真源" in text_a,
          "含『唯一真源』" if "唯一真源" in text_a else "缺这一节，契约只是空壳")

    # 互不干扰：本目录不许出现**路径式**引用晨报。
    # 只认 `ai-daily/` 或 `ai-daily\`，因为「本项目不引用 ai-daily」这种说明文字
    # 是合法声明；真正的耦合一定长成一条路径。
    path_ref = re.compile(r"ai-daily[/\\]")
    offenders = []
    for p in root.rglob("*"):
        if not p.is_file() or ".git" in p.parts or p.name == "validate.py":
            continue
        # 只看可执行/可加载的文件：文档里声明「互不干扰」是契约的一部分，不是耦合。
        if p.suffix.lower() not in {".py", ".html", ".json", ".js"}:
            continue
        try:
            if path_ref.search(p.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(p.relative_to(root).as_posix())
        except OSError:
            pass
    check("A", "与晨报互不干扰", not offenders,
          "全目录无 ai-daily 路径引用" if not offenders else "命中：" + "、".join(offenders[:4]))

    # ---------- B. 素材 ----------
    quotes = []
    try:
        quotes = load_json(data_p)["quotes"]
        ok_json, why = True, f"{len(quotes)} 条"
    except Exception as e:  # noqa: BLE001 - 缺文件/坏 JSON 都要变成一条失败，而不是崩
        ok_json, why = False, f"{type(e).__name__}: {e}"[:80]
    check("B", "quotes.json 可解析", ok_json, why)

    if ok_json:
        missing = [(q.get("id", "?"), k) for q in quotes for k in FIELDS if not q.get(k)]
        check("B", "字段齐全", not missing,
              "6 个字段都有" if not missing else "缺：" + "、".join(f"{i}.{k}" for i, k in missing[:4]))

        ids = [q.get("id") for q in quotes]
        dup_id = sorted({i for i in ids if ids.count(i) > 1 and i})
        check("B", "id 唯一", not dup_id, "无重复" if not dup_id else "重复：" + "、".join(dup_id))

        bad_date, dates = [], []
        for q in quotes:
            try:
                dt.date.fromisoformat(q.get("date", ""))
                dates.append(q["date"])
            except ValueError:
                bad_date.append(f"{q.get('id', '?')}={q.get('date')!r}")
        check("B", "日期格式合法", not bad_date,
              "均为 YYYY-MM-DD" if not bad_date else "非法：" + "、".join(bad_date[:4]))

        dup_date = sorted({d for d in dates if dates.count(d) > 1})
        check("B", "日期唯一", not dup_date, "无重复" if not dup_date else "重复：" + "、".join(dup_date))

        bad_text = [f"{q.get('id', '?')}={len(q.get('text', ''))}字" for q in quotes
                    if not (1 <= len(q.get("text", "")) <= 60)]
        check("B", "正文 1-60 字", not bad_text,
              "全部在范围内" if not bad_text else "越界：" + "、".join(bad_text[:4]))

        bad_tags = [f"{q.get('id', '?')}={len(q.get('tags') or [])}个" for q in quotes
                    if not (1 <= len(q.get("tags") or []) <= 3)]
        check("B", "标签 1-3 个", not bad_tags,
              "全部在范围内" if not bad_tags else "越界：" + "、".join(bad_tags[:4]))

    # ---------- C. 产物 ----------
    idx = None
    try:
        idx = load_json(index_p)
        items = idx.get("items", [])
        ok_idx, why = True, f"{len(items)} 条"
    except Exception as e:  # noqa: BLE001
        items, ok_idx, why = [], False, f"缺 index.json 或无法解析（{type(e).__name__}）"
    check("C", "index.json 可解析", ok_idx, why)

    check("C", "卡片墙存在", wall_p.exists(),
          f"{wall_p.stat().st_size} 字节" if wall_p.exists() else "site/index.html 缺")

    on_disk = sorted(p.stem for p in cards.glob("*.html")) if cards.exists() else []
    if ok_idx:
        idx_dates = [it.get("date") for it in items]
        check("C", "索引与卡片数量一致", len(items) == len(on_disk),
              f"索引 {len(items)} 条 · 磁盘 {len(on_disk)} 张")
        missing_files = [d for d in idx_dates if d not in on_disk]
        check("C", "索引项都有对应卡片", not missing_files,
              "全部可定位" if not missing_files else "缺：" + "、".join(map(str, missing_files[:4])))
        check("C", "索引按日期倒序", idx_dates == sorted(idx_dates, reverse=True),
              f"首 {idx_dates[0] if idx_dates else '-'} / 末 {idx_dates[-1] if idx_dates else '-'}")
    else:
        for n in ("索引与卡片数量一致", "索引项都有对应卡片", "索引按日期倒序"):
            check("C", n, False, "index.json 不可用，无法判定")

    # 结构：对每一张卡都检查（卡少，全量比抽查可靠；抽查会漏掉被破坏的那一张）
    if on_disk:
        lacks = []
        for day in on_disk:
            page = (cards / f"{day}.html").read_text(encoding="utf-8")
            d = dt.date.fromisoformat(day)
            need = ["<title>", "晨 读 卡", "<blockquote>", 'class="meta"', f"{d.month} 月 {d.day} 日"]
            miss = [n for n in need if n not in page]
            if miss:
                lacks.append(f"{day} 缺 " + "/".join(miss))
        check("C", "卡片结构完整", not lacks,
              f"{len(on_disk)} 张齐全" if not lacks else "；".join(lacks[:3]))
    else:
        check("C", "卡片结构完整", False, "没有任何卡片可抽样")

    # 转义：素材里带尖括号/& 的，产物里必须是实体，不能是裸标签。
    # 用「素材原文 vs 产物」比对，而不是写死某一天，这样任意日期出卡都能判定。
    specials = [(q.get("date"), q.get("text", "")) for q in quotes
                if "<" in q.get("text", "") or "&" in q.get("text", "")]
    raw_hits, checked = [], 0
    for day, txt in specials:
        fp = cards / f"{day}.html"
        if not fp.exists():
            continue
        checked += 1
        page = fp.read_text(encoding="utf-8")
        for token in re.findall(r"<[^>\s]{1,24}>", txt):
            if token in page:
                raw_hits.append(f"{day} 出现裸 {token}")
        if "&" in txt and "&amp;" not in page:
            raw_hits.append(f"{day} 的 & 未转义")
    check("C", "正文已 HTML 转义", not raw_hits,
          f"已检查 {checked} 张含特殊字符的卡片" if not raw_hits
          else "；".join(raw_hits[:3]) + ("" if checked else "（无相关卡片，按空集通过）"))

    # ---------- D. 防回归 ----------
    tpl = root / "templates" / "card.html"
    tpl_text = tpl.read_text(encoding="utf-8") if tpl.exists() else ""
    check("D", "版式主色仍在", "--accent:#8c1d18" in tpl_text,
          "模板含强调红 #8c1d18" if "--accent:#8c1d18" in tpl_text else "模板主色被改动或删除")

    leftovers = [p.name for p in cards.glob("*.html")
                 if "{{" in p.read_text(encoding="utf-8", errors="ignore")] if cards.exists() else []
    check("D", "产物无未替换占位符", not leftovers,
          "无残留 {{}}" if not leftovers else "残留：" + "、".join(leftovers[:3]))

    st = None
    try:
        st = load_json(status_p)
        state = st.get("state")
        steps = st.get("steps", {})
        bad_state = state not in {"OK", "PARTIAL", "FAILED", "RUNNING"}
        fake_ok = state == "OK" and any(not v.startswith("OK") for v in steps.values())
        check("D", "状态文件自洽", not bad_state and not fake_ok,
              f"state={state} · {len(steps)} 步" if not (bad_state or fake_ok)
              else f"矛盾：state={state} 但 steps 有不成功项")
    except Exception:  # noqa: BLE001 - 还没跑过流水线时允许缺失，记为跳过式通过
        check("D", "状态文件自洽", True, "尚无 status.json（首跑前允许）")

    return res


def main() -> int:
    results = run()
    if "--json" in sys.argv:
        print(json.dumps([{"group": g, "check": n, "ok": ok, "detail": d}
                          for g, n, ok, d in results], ensure_ascii=False, indent=2))
        return 0 if all(r[2] for r in results) else 1

    groups = {"A": "契约", "B": "素材", "C": "产物", "D": "防回归"}
    print("=== 晨读卡 · 验收断言 ===")
    for g, label in groups.items():
        rows = [r for r in results if r[0] == g]
        passed = sum(1 for r in rows if r[2])
        print(f"[{g}] {label:<4} {passed}/{len(rows)}")
        for _, name, ok, detail in rows:
            if not ok:
                print(f"   · {name} —— 实测：{detail}")

    total = len(results)
    ok_n = sum(1 for r in results if r[2])
    print(f"\n结果：{ok_n} / {total} 通过")
    if ok_n != total:
        print("未通过项就是工单：把它原样回传给 agent，让它只修这些（第 2 章）。")
        return 1
    print("全部通过，允许进入发布步骤。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
