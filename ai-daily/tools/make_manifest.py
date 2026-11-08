#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从成品 HTML 反解出一份 manifest.json（P004-4）。

用法：
    python tools/make_manifest.py AI晨报-2026-11-06-特刊.html --out site/special/2026-11-06.json
    python tools/make_manifest.py AI晨报-2026-11-06.html --kind daily
    python tools/make_manifest.py --all          # 所有正刊 + 特刊，一次刷齐

设计要点：
  1. 只读成品，不读拼版过程——换个拼版脚本也照样能出凭证。
  2. 字段固定，便于 `curl ... | python -c` 比对；bytes 与 sha256 对的是**这个文件本身**。
  3. 不用 now() 当时间戳，取文件 mtime：文件不变 → JSON 不变 → 重跑幂等。
  4. 检查项用 True / False / None 三态；None = 本期不适用，不参与 ok 判定。
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # ai-daily/
SITE = ROOT / "site"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_of(html):
    """去掉脚本、样式、标签，留下可读文字。"""
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    body = body.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"[ \t\r\n]+", "", body)


def block(html, marker):
    """按 div 深度切出以 marker 开头的整块，避免 gloss 里嵌套 div 被截断。"""
    i = html.find(marker)
    if i < 0:
        return ""
    depth = 0
    for m in re.finditer(r"<div\b[^>]*>|</div>", html[i:]):
        if m.group(0).startswith("</"):
            depth -= 1
            if depth == 0:
                return html[i:i + m.end()]
        else:
            depth += 1
    return html[i:]


def build(path, kind="daily"):
    """解析一份成品，返回 manifest 字典。解析不出期号/日期时抛 ValueError。"""
    path = Path(path)
    html = path.read_text(encoding="utf-8")

    title = re.search(r"<title>(.*?)</title>", html, re.S)
    title = re.sub(r"\s+", " ", title.group(1)).strip() if title else ""
    m_issue = re.search(r"第\s*(\d{3}(?:-\d+)?)\s*期", title)
    m_date = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", title)
    if not (m_issue and m_date):
        raise ValueError("标题里解析不到期号或日期：%s" % title)
    issue = m_issue.group(1)
    date = "%s-%02d-%02d" % (m_date.group(1), int(m_date.group(2)), int(m_date.group(3)))
    m_pages = re.search(r"共\s*(\d+)\s*版", title)

    ids = re.findall(r'<section[^>]*\bid="(p\d\d)"', html)
    nav = re.search(r'<nav class="mast-nav">(.*?)</nav>', html, re.S)
    nav_ids = re.findall(r'href="#(p\d\d)"', nav.group(1)) if nav else []

    gloss_html = block(html, '<div class="gloss"')
    dts = re.findall(r"<dt>(.*?)</dt>", gloss_html, re.S)
    plain = lambda s: re.sub(r"<[^>]+>", "", s).strip()
    key = lambda s: re.sub(r"[（(][^）)]*[）)]|[\s·/／]", "", plain(s)).lower()

    terms = [plain(t) for t in re.findall(
        r'<span class="term"[^>]*>(.*?)<i class="tip">', html, re.S)]

    def covered(term, dt_raw):
        a = key(term)
        if not a:
            return False
        return any(p and (p in a or a in p)
                   for p in (key(x) for x in re.split(r"[/／]", plain(dt_raw))))

    missing = [t for t in terms if dts and not any(covered(t, d) for d in dts)]
    m_claim = re.search(r"名词速查[^<]*?(\d+)\s*个词", html)
    digest_items = len(re.findall(r"<li>", block(html, '<div class="digest"')))
    # 全文每一处「共 N 版」都要等于实际页数。标题只是其中一处，
    # 页眉是批量复制模板的产物，最容易整批漏改（003-2 曾 14 处写 15）。
    page_claims = [int(x) for x in re.findall(r"共\s*(\d+)\s*版", html)]

    # P005-4 事实卡：拼版时以 <script id="ai-daily-facts"> 嵌进成品，
    # 凭证里再做一次「数值还在不在正文」，挡住「改了正文没改卡」。
    m_facts = re.search(
        r'<script type="application/json" id="ai-daily-facts">(.*?)</script>',
        html, re.S)
    facts_data, items = None, []
    if m_facts:
        try:
            facts_data = json.loads(m_facts.group(1))
            items = facts_data.get("facts") or []
        except ValueError:
            facts_data, items = {}, []
    flat = re.sub(r"[ \t\r\n]+", "", text_of(html))
    fact_missing = [str(f.get("id") or "?") for f in items
                    if str(f.get("value") or "").replace(" ", "") not in flat]
    fact_sourced = bool(items) and all(
        str(f.get("source") or "").strip() and str(f.get("asOf") or "").strip()
        for f in items)

    checks = {
        "pages_eq_nav": len(ids) == len(nav_ids),
        "nav_matches_sections": nav_ids == ids,
        "sections_continuous": ids == ["p%02d" % i for i in range(1, len(ids) + 1)],
        "issue_in_title": ("第 %s 期" % issue) in title,
        # 必查项一律布尔：解析不到就是 False，不许用 None 蒙混过关
        "pages_in_title": bool(m_pages) and int(m_pages.group(1)) == len(ids),
        "pages_all_match": bool(page_claims) and all(x == len(ids) for x in page_claims),
        # 三行摘要只有 16 版/特刊才有；没有这版式时记 None，不算失败
        "digest_three": (digest_items == 3) if 'class="digest"' in html else None,
        "glossary_count_matches": (int(m_claim.group(1)) == len(dts)) if m_claim else None,
        "terms_in_glossary": (not missing) if terms else None,
        # 事实卡：有就必查（数值都在正文里、每条都有来源与时点）；没有这一版式记 None
        "facts_card_valid": (not fact_missing and fact_sourced) if items else (
            False if m_facts else None),
    }

    return {
        "issue": issue,
        "date": date,
        "kind": kind,
        "file": path.name,
        "title": title,
        "pages": len(ids),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "chars": len(text_of(html)),
        "terms": len(terms),
        "glossary": len(dts),
        "facts": ({
            "count": len(items),
            "reproduced": sum(1 for f in items if f.get("reproduced") is True),
            "byStrength": {k: sum(1 for f in items if f.get("strength") == k)
                           for k in sorted({str(f.get("strength")) for f in items})},
            "asOf": (facts_data or {}).get("asOf"),
            "ids": [f.get("id") for f in items],
        } if items else None),
        "missing_terms": missing,
        "generatedAt": datetime.datetime.fromtimestamp(
            path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        "checks": checks,
        "ok": all(v is not False for v in checks.values()),
    }


def write_manifest(html_path, out_path=None, kind="daily"):
    """生成并写盘，返回 (data, out_path)。"""
    html_path = Path(html_path)
    data = build(html_path, kind)
    out = Path(out_path) if out_path else html_path.with_suffix(".json")
    # path 相对站点根，便于人直接在 json 里看出这张凭证对应哪个页面
    try:
        rel = out.parent.relative_to(SITE).as_posix()
        data["path"] = ("" if rel == "." else rel + "/") + data["file"]
    except ValueError:
        data["path"] = data["file"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return data, out


def report(data, out):
    print("写入 %s" % out)
    print("  %s %s / %s / %d 版 / %d 字节 / %d 处注解 / 词表 %d 条"
          % (data["kind"], data["issue"], data["date"], data["pages"],
             data["bytes"], data["terms"], data["glossary"]))
    bad = [k for k, v in data["checks"].items() if v is False]
    print("  自检 %s" % ("全过" if not bad else "未过：" + ", ".join(bad)))
    if data.get("facts"):
        f = data["facts"]
        print("  事实卡 %d 条（已复现 %d 条）· 强度分布 %s"
              % (f["count"], f["reproduced"],
                 "、".join("%s %d" % (k, v) for k, v in f["byStrength"].items())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html", nargs="?", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--kind", default="daily", help="daily / special")
    ap.add_argument("--all", action="store_true", help="重刷 site/ 下所有成品")
    a = ap.parse_args()

    if a.all:
        targets = []
        for p in sorted(SITE.glob("AI晨报-*.html")):
            targets.append((p, SITE / (p.stem + ".json"),
                            "special" if "特刊" in p.name else "daily"))
        for p in sorted(SITE.glob("special/*.html")):
            targets.append((p, p.with_suffix(".json"), "special"))
        n_ok = n_bad = 0
        for html, out, kind in targets:
            data, out = write_manifest(html, out, kind)
            report(data, out)
            n_ok += 1 if data["ok"] else 0
            n_bad += 0 if data["ok"] else 1
        print("共 %d 份，通过 %d，未过 %d" % (len(targets), n_ok, n_bad))
        return 0 if n_bad == 0 else 1

    if not a.html:
        print("缺参数：要么给 html，要么用 --all")
        return 2
    if not os.path.exists(a.html):
        print("找不到文件：%s" % a.html)
        return 2
    try:
        data, out = write_manifest(a.html, a.out or None, a.kind)
    except ValueError as exc:
        print(exc)
        return 1
    report(data, out)
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
