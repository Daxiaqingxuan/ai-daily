#!/usr/bin/env python3
"""生成免访问码的公开导读面（GitHub Pages 的 /docs）。

公开面只放三样东西：最新期导读、全部事实卡（每张一个 URL）、归档索引。
全文仍在受访问码保护的私有站点——这里不读 siteUrl，不放正文，也不含任何入口地址。

事实卡页是这套公开面的重点：一张卡一个 URL，带主张、数值、证据强度、版面归属、
信源说明与 Article 结构化数据。对手（aidailybrief.ai）有 3180 个这样的原子页，
但每条的 sources 字段是空数组；这里反过来，卡片少而字段全。

用法：
    python ai-daily/tools/build_public.py            # 生成到仓库 docs/
    python ai-daily/tools/build_public.py --check    # 只比对，不写盘
    python ai-daily/tools/build_public.py --out DIR  # 指定输出目录
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # ai-daily/
SITE = ROOT / "site"
PARTS = ROOT / "parts"
CONF = ROOT / "public_site.json"
DEFAULT_OUT = ROOT.parent / "docs"                     # 仓库根 docs/（Pages 发布目录）

CST = timezone(timedelta(hours=8))

STRENGTH_CN = {
    "vendor": "厂商口径",
    "preprint": "预印本",
    "media": "媒体报道",
    "official": "官方文件",
    "measured": "本报实测",
}

STAMP_RE = re.compile(r"生成于 \d{4}-\d{2}-\d{2} \d{2}:\d{2}")


def norm(text: str) -> str:
    """抹平页脚的生成时间戳再比对。

    页面上保留精确到分钟的生成时刻（透明度），但对账只比结构内容——否则
    --check 每跑一次都因为时间不同而失败，幂等断言等于没有。
    """
    return STAMP_RE.sub("生成于 <ts>", text)


# ---------------------------------------------------------------- 读取

def load_conf() -> dict:
    if CONF.is_file():
        return json.loads(CONF.read_text(encoding="utf-8"))
    return {"base": "", "title": "AI 晨报 · 公开导读"}


def load_issues() -> dict:
    txt = (SITE / "issues.js").read_text(encoding="utf-8")
    m = re.search(r"=\s*(\{[\s\S]*\})\s*;?\s*$", txt)
    if not m:
        raise SystemExit("issues.js 解析失败：找不到 window.AI_DAILY_ISSUES 对象")
    return json.loads(m.group(1))


def load_config_fields() -> dict:
    """只取 name 与 disclaimer。刻意不读 siteUrl——公开面不得含入口地址。

    这里不能用 unicode_escape 解码：config.js 本身是 UTF-8，中文会先按 UTF-8
    编成字节再按 latin-1 解回来，得到一串乱码。只处理引号与换行两种转义就够。
    """
    txt = (SITE / "config.js").read_text(encoding="utf-8")
    out = {}
    for key in ("name", "disclaimer"):
        m = re.search(key + r'\s*:\s*"((?:[^"\\]|\\.)*)"', txt)
        if m:
            out[key] = m.group(1).replace('\\"', '"').replace("\\n", "\n")
    return out


def page_label(pid: str) -> str:
    m = re.match(r"p0*(\d+)$", pid or "")
    return "第 %s 版" % m.group(1) if m else (pid or "—")


def mmdd(date_str: str) -> str:
    return date_str.replace("-", "")[4:]


def load_parts(date_str: str, is_special: bool):
    """返回 (facts, sources, blocks)；该期没有结构化文件时返回 (None, None, None)。"""
    cands = []
    base = mmdd(date_str)
    cands.append("1106sp" if base == "1106" and is_special else base)
    cands.append(base)
    for name in cands:
        d = PARTS / name
        if (d / "00-facts.json").is_file():
            facts = json.loads((d / "00-facts.json").read_text(encoding="utf-8"))
            sources = None
            blocks = None
            if (d / "00-sources.json").is_file():
                sources = json.loads((d / "00-sources.json").read_text(encoding="utf-8"))
            if (d / "00-blocks.json").is_file():
                blocks = json.loads((d / "00-blocks.json").read_text(encoding="utf-8"))
            return facts, sources, blocks
    return None, None, None


def facts_of(facts_json) -> list:
    if not facts_json:
        return []
    if isinstance(facts_json, list):
        return facts_json
    for key in ("facts", "items", "cards"):
        if isinstance(facts_json.get(key), list):
            return facts_json[key]
    return []


def sources_of(src_json) -> list:
    if not src_json:
        return []
    if isinstance(src_json, list):
        return src_json
    return src_json.get("sources") or []


def src_url(s) -> str:
    """信源原文链接：只认 http(s)，且不含空白与引号。

    宁可不给链接，也不能指向错地方——信源表的可信度就是靠这条守住的。
    """
    u = (s or {}).get("url") or ""
    u = u.strip()
    if not u.startswith(("http://", "https://")):
        return ""
    if any(ch in u for ch in ' <>"\'`'):
        return ""
    return u


def block_of(blocks_json, page_id: str) -> dict:
    if not blocks_json:
        return {}
    pages = blocks_json.get("pages") or {}
    if isinstance(pages, dict):
        return pages.get(page_id) or {}
    for p in pages:
        if p.get("id") == page_id:
            return p
    return {}


# ---------------------------------------------------------------- 样式

CSS = """
:root{
  --paper:#fbf8f0; --edge:#efeadd; --ink:#1b1a17; --ink-soft:#3a3934;
  --muted:#6d6a60; --accent:#8c1d18; --rule:#cfc8b6; --wash:#fffdf7;
  --sans:"Microsoft YaHei","PingFang SC","Hiragino Sans GB","Helvetica Neue",Arial,sans-serif;
  --serif:"Songti SC","STSong","Noto Serif SC","SimSun",Georgia,"Times New Roman",serif;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--serif);
  line-height:1.75;font-size:17px}
a{color:var(--accent);text-decoration:none;border-bottom:1px solid rgba(140,29,24,.28)}
a:hover{border-bottom-color:var(--accent)}
.wrap{max-width:720px;margin:0 auto;padding:28px 22px 64px}
.top{border-bottom:2px solid var(--ink);padding-bottom:10px;margin-bottom:26px}
.top a.brand{color:var(--ink);border:0;font-family:var(--serif);font-size:26px;
  font-weight:700;letter-spacing:.06em}
.top .nav{float:right;font-family:var(--sans);font-size:13px;line-height:38px}
.top .nav a{border:0;color:var(--muted);margin-left:14px}
.kicker{font-family:var(--sans);font-size:12px;letter-spacing:.16em;color:var(--accent);
  text-transform:uppercase;margin:0 0 8px}
h1.lede{font-size:27px;line-height:1.5;margin:0 0 12px;font-weight:700}
h1.card{font-size:24px;line-height:1.5;margin:0 0 18px;font-weight:700}
p.deck{font-size:17px;color:var(--ink-soft);margin:0 0 20px}
p{color:var(--ink-soft)}
.small{font-family:var(--sans);font-size:13px;color:var(--muted)}
.meta{font-family:var(--sans);font-size:13px;color:var(--muted);margin:0 0 22px}
.meta span+span:before{content:"·";margin:0 8px;color:var(--rule)}
.box{background:var(--wash);border:1px solid var(--edge);padding:18px 20px;margin:0 0 24px}
.value{font-size:40px;line-height:1.1;color:var(--accent);font-weight:700;margin:0 0 6px;
  font-family:var(--serif)}
.value small{font-size:15px;color:var(--muted);font-weight:400;margin-left:8px}
table.meta2{width:100%;border-collapse:collapse;font-family:var(--sans);font-size:14px;margin:0 0 22px}
table.meta2 th{text-align:left;font-weight:400;color:var(--muted);width:96px;
  padding:7px 0;vertical-align:top;border-top:1px solid var(--edge)}
table.meta2 td{padding:7px 0;border-top:1px solid var(--edge);color:var(--ink-soft)}
.badge{display:inline-block;font-family:var(--sans);font-size:12px;padding:1px 8px;
  border:1px solid var(--rule);border-radius:2px;color:var(--muted);margin-left:6px}
.badge.hi{color:var(--accent);border-color:rgba(140,29,24,.4)}
h2{font-size:15px;font-family:var(--sans);font-weight:700;letter-spacing:.04em;
  margin:32px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--rule)}
ul.plain{list-style:none;padding:0;margin:0}
ul.plain li{padding:11px 0;border-bottom:1px solid var(--edge)}
ul.plain li:last-child{border-bottom:0}
ul.plain .d{font-family:var(--sans);font-size:12px;color:var(--muted);display:block}
ul.plain .t{display:block;line-height:1.55}
.pager{margin:34px 0 0;font-family:var(--sans);font-size:14px;display:flex;
  justify-content:space-between;gap:12px;flex-wrap:wrap}
.note{font-size:14px;color:var(--muted);border-left:3px solid var(--rule);padding:2px 0 2px 12px;
  margin:0 0 24px;font-family:var(--sans);line-height:1.7}
footer{margin-top:44px;padding-top:14px;border-top:1px solid var(--rule);
  font-family:var(--sans);font-size:12px;color:var(--muted);line-height:1.8}
footer a{border:0;color:var(--muted)}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;
  background:#f2eee2;padding:1px 5px;border-radius:2px}
@media(max-width:600px){
  .wrap{padding:20px 16px 52px}
  h1.lede{font-size:22px} h1.card{font-size:20px} .value{font-size:32px}
  .top .nav{float:none;display:block;line-height:1.6;margin-top:6px}
  .top .nav a{margin:0 12px 0 0}
}
"""


# ---------------------------------------------------------------- 渲染

def esc(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def shell(title: str, desc: str, body: str, depth: int, conf: dict,
          canonical: str = "", jsonld: str = "") -> str:
    css = "../" * depth + "style.css"
    home = "../" * depth + "index.html"
    base = (conf.get("base") or "").rstrip("/")
    can = ('<link rel="canonical" href="%s/%s">' % (base, canonical)) if (base and canonical) else ""
    ld = ('<script type="application/ld+json">%s</script>' % jsonld) if jsonld else ""
    return (
        "<!doctype html>\n<html lang=\"zh-CN\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<title>%s</title>\n"
        "<meta name=\"description\" content=\"%s\">\n"
        "%s\n"
        "<link rel=\"stylesheet\" href=\"%s\">\n"
        "<meta property=\"og:type\" content=\"article\">\n"
        "<meta property=\"og:title\" content=\"%s\">\n"
        "<meta property=\"og:description\" content=\"%s\">\n"
        "%s\n%s\n"
        "</head>\n<body>\n<div class=\"wrap\">\n"
        "<div class=\"top\"><a class=\"brand\" href=\"%s\">%s</a>"
        "<span class=\"nav\"><a href=\"%s\">导读</a><a href=\"%s\">归档</a></span></div>\n"
        "%s\n</div>\n</body>\n</html>\n"
    ) % (esc(title), esc(desc), can, css, esc(title), esc(desc), ld, "",
         home, esc(conf.get("title") or "AI 晨报"),
         home, "../" * depth + "issues/index.html", body)


def render_index(conf: dict, issues: list, cards_by_date: dict, disclaimer: str, now: str) -> str:
    latest = issues[0] if issues else None
    body = []
    if latest:
        d = latest["date"]
        n = len(cards_by_date.get(d, []))
        body.append('<p class="kicker">最新一期 · %s</p>' % esc(latest.get("issueLabel", "")))
        body.append('<h1 class="lede">%s</h1>' % esc(latest.get("headline", "")))
        if latest.get("deck"):
            body.append('<p class="deck">%s</p>' % esc(latest["deck"]))
        meta = ['<span>%s</span>' % esc(latest.get("dateCn", d))]
        if latest.get("weekday"):
            meta.append('<span>%s</span>' % esc(latest["weekday"]))
        if latest.get("pages"):
            meta.append('<span>%d 个版面</span>' % int(latest["pages"]))
        if n:
            meta.append('<span>%d 张事实卡</span>' % n)
        body.append('<p class="meta">%s</p>' % "".join(meta))
        links = []
        links.append('<a href="issues/%s.html">读本期导读</a>' % d)
        if n:
            links.append('<a href="cards/index.html">看 %d 张事实卡</a>' % n)
        body.append('<p class="pager" style="margin-top:0">%s</p>' % " &nbsp; ".join(links))
        body.append(
            '<p class="note">公开面只放导读与结构化事实卡。完整 16 版全文在受访问码保护的私有站点，'
            '本页不含入口地址。</p>')

    body.append('<h2>这是个什么</h2>')
    body.append(
        '<p>每天自动出刊的中文 AI 报纸：16 个版面、一张事实卡对应一条可核查的断言、'
        '报尾列出全部信源。每一期在落盘前跑 16 条断言检查，数字、来源标记、信源对账'
        '任何一条不过就不许发布。</p>')
    body.append(
        '<p>这个公开面是它的切片：把每期的事实卡拆成独立页面，一条断言一个网址，'
        '带证据强度（厂商口径 / 预印本 / 媒体报道）与所属版面。目的很直接——'
        '让「这句话凭什么」可以被单独引用和检查。</p>')

    if cards_by_date:
        total = sum(len(v) for v in cards_by_date.values())
        body.append('<h2>事实卡 · 按期刊出</h2>')
        items = []
        for issue in issues:
            cards = cards_by_date.get(issue["date"]) or []
            if not cards:
                continue
            items.append(
                '<li><span class="d">%s · %s · %d 张</span>'
                '<a class="t" href="cards/index.html#%s">%s</a></li>'
                % (esc(issue.get("issueLabel", "")), esc(issue.get("dateCn", issue["date"])),
                   len(cards), esc(issue["date"]), esc(issue.get("headline", "")[:60])))
        body.append('<ul class="plain">%s</ul>' % "".join(items))
        body.append('<p class="small" style="margin-top:10px">共 %d 张，全部可在'
                    '<a href="cards/index.html">卡片总览</a>里逐条打开。</p>' % total)

    body.append('<h2>归档</h2>')
    rows = []
    for issue in issues[:8]:
        rows.append('<li><span class="d">%s · %s</span>'
                    '<a class="t" href="issues/%s.html">%s</a></li>'
                    % (esc(issue.get("dateCn", issue["date"])), esc(issue.get("issueLabel", "")),
                       esc(issue["date"]), esc(issue.get("headline", "")[:64])))
    body.append('<ul class="plain">%s</ul>' % "".join(rows))
    body.append('<p class="small" style="margin-top:10px"><a href="issues/index.html">全部归档 →</a></p>')

    body.append(footer(conf, disclaimer, now, 0))
    return shell("%s · 公开导读" % (conf.get("title") or "AI 晨报"),
                 "每日自动出刊的中文 AI 报纸公开导读：事实卡逐条带证据强度与信源说明。",
                 "\n".join(body), 0, conf, canonical="index.html")


def render_cards_index(conf, issues, cards_by_date, disclaimer, now) -> str:
    body = ['<p class="kicker">全部事实卡</p>',
            '<h1 class="lede">一条断言一个网址</h1>',
            '<p class="deck">每张卡带主张、数值、证据强度、所属版面与信源说明。'
            '点开任意一张可单独引用。</p>']
    for issue in issues:
        cards = cards_by_date.get(issue["date"]) or []
        if not cards:
            continue
        body.append('<h2 id="%s">%s · %s</h2>'
                    % (esc(issue["date"]), esc(issue.get("issueLabel", "")),
                       esc(issue.get("dateCn", issue["date"]))))
        rows = []
        for c in cards:
            rows.append('<li><span class="d">%s · %s</span>'
                        '<a class="t" href="%s-%s.html">%s — %s</a></li>'
                        % (esc(c["id"]), esc(STRENGTH_CN.get(c.get("strength"), c.get("strength", ""))),
                           esc(issue["date"]), esc(c["id"]),
                           esc(c.get("value", "")), esc(c.get("claim", ""))))
        body.append('<ul class="plain">%s</ul>' % "".join(rows))
    body.append(footer(conf, disclaimer, now, 1))
    return shell("全部事实卡 · %s" % (conf.get("title") or "AI 晨报"),
                 "逐条列出各期事实卡：断言、数值、证据强度与所属版面。",
                 "\n".join(body), 1, conf, canonical="cards/index.html")


def render_card(conf, issue, card, cards, blocks, sources, disclaimer, now) -> str:
    cid = card["id"]
    page_id = card.get("page", "")
    blk = block_of(blocks, page_id)
    strength = card.get("strength", "")
    strength_cn = STRENGTH_CN.get(strength, strength or "未标注")
    reproduced = bool(card.get("reproduced"))
    same = [c for c in cards if c.get("page") == page_id and c["id"] != cid]

    body = ['<p class="kicker">%s · %s · 事实卡 %s</p>'
            % (esc(issue.get("issueLabel", "")), esc(issue.get("dateCn", issue["date"])), esc(cid)),
            '<h1 class="card">%s</h1>' % esc(card.get("claim", "")),
            '<div class="box"><p class="value">%s<small>%s</small></p></div>'
            % (esc(card.get("value", "")),
               "本报沙箱复现" if reproduced else "引用值，未复现"),
            '<table class="meta2">']
    rows = [
        ("证据强度", '%s%s' % (esc(strength_cn),
                           '' if reproduced else '<span class="badge">未复现</span>')),
        ("来源", esc(card.get("source", "—"))),
        ("时点", esc(card.get("asOf", issue["date"]))),
    ]
    if page_id:
        rows.append(("所属版面", "%s%s" % (esc(page_label(page_id)),
                                       ('　' + esc(blk.get("note"))) if blk.get("note") else "")))
    if blk.get("origin"):
        origin_cn = {"official": "官方发布", "thirdparty": "第三方报道",
                     "measured": "本报实测", "ai": "本报观点"}.get(blk["origin"], blk["origin"])
        rows.append(("版面来源", esc(origin_cn)))
    if sources:
        linked = len([s for s in sources if src_url(s)])
        rows.append(("本期信源",
                     '<a href="../issues/%s.html#sources">%d 条%s</a>'
                     % (esc(issue["date"]), len(sources),
                        ("，%d 条可跳原文" % linked) if linked else "，见报尾信源表")))
    for k, v in rows:
        body.append("<tr><th>%s</th><td>%s</td></tr>" % (k, v))
    body.append("</table>")

    body.append('<p class="note">这张卡只陈述一个数字与它的出处关系。'
                '「未复现」表示数值来自引用而非本报沙箱实测——它仍然可核查，但不等于本报背书。</p>')

    if same:
        body.append("<h2>同一版的其他卡</h2>")
        rows = []
        for c in same[:6]:
            rows.append('<li><a class="t" href="%s-%s.html">%s — %s</a></li>'
                        % (esc(issue["date"]), esc(c["id"]), esc(c.get("value", "")),
                           esc(c.get("claim", ""))))
        body.append('<ul class="plain">%s</ul>' % "".join(rows))

    body.append('<p class="pager"><a href="index.html">← 全部事实卡</a>'
                '<a href="../issues/%s.html">本期导读（%s）→</a></p>'
                % (esc(issue["date"]), esc(issue.get("issueLabel", ""))))
    body.append(footer(conf, disclaimer, now, 1))

    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": card.get("claim", ""),
        "abstract": "%s：%s" % (card.get("claim", ""), card.get("value", "")),
        "datePublished": card.get("asOf", issue["date"]),
        "isAccessibleForFree": True,
        "isPartOf": {"@type": "PublicationIssue",
                     "issueNumber": issue.get("issue", ""),
                     "datePublished": issue["date"]},
        "publisher": {"@type": "Organization", "name": conf.get("title") or "AI 晨报"},
        "creditText": card.get("source", ""),
    }, ensure_ascii=False, separators=(",", ":"))
    return shell("%s — %s · %s" % (card.get("value", ""), card.get("claim", ""),
                                   issue.get("issueLabel", "")),
                 "%s：%s（%s，%s）" % (card.get("claim", ""), card.get("value", ""),
                                    strength_cn, card.get("asOf", issue["date"])),
                 "\n".join(body), 1, conf,
                 canonical="cards/%s-%s.html" % (issue["date"], cid), jsonld=jsonld)


def render_issue(conf, issue, cards, sources, disclaimer, now) -> str:
    d = issue["date"]
    body = ['<p class="kicker">%s · 本期导读</p>' % esc(issue.get("issueLabel", "")),
            '<h1 class="lede">%s</h1>' % esc(issue.get("headline", ""))]
    if issue.get("deck"):
        body.append('<p class="deck">%s</p>' % esc(issue["deck"]))
    meta = ['<span>%s</span>' % esc(issue.get("dateCn", d))]
    if issue.get("weekday"):
        meta.append('<span>%s</span>' % esc(issue["weekday"]))
    if issue.get("pages"):
        meta.append('<span>%d 个版面</span>' % int(issue["pages"]))
    if cards:
        meta.append('<span>%d 张事实卡</span>' % len(cards))
    if sources:
        meta.append('<span>%d 条信源</span>' % len(sources))
        n_link = len([s for s in sources if src_url(s)])
        if n_link:
            meta.append('<span>%d 条可跳原文</span>' % n_link)
    body.append('<p class="meta">%s</p>' % "".join(meta))
    body.append('<p class="note">完整版面（16 版正文、术语气泡、报尾信源表）在受访问码保护的'
                '私有站点；这里给的是可公开的导读与卡片。</p>')
    if cards:
        body.append("<h2>本期事实卡</h2>")
        by_page = {}
        for c in cards:
            by_page.setdefault(c.get("page", ""), []).append(c)
        for pid in sorted(by_page):
            blk = {}
            body.append('<ul class="plain">%s</ul>' % "".join(
                '<li><span class="d">%s · %s</span><a class="t" href="../cards/%s-%s.html">%s — %s</a></li>'
                % (esc(c["id"]), esc(STRENGTH_CN.get(c.get("strength"), c.get("strength", ""))),
                   esc(d), esc(c["id"]), esc(c.get("value", "")), esc(c.get("claim", "")))
                for c in by_page[pid]))
    if sources:
        n_link = len([s for s in sources if src_url(s)])
        body.append('<h2 id="sources">本期信源</h2>')
        body.append('<p class="note">%d 条，其中 %d 条能点到原文或官方页面。'
                    '其余条目是概括性信源（如「本周报道」「每日通讯摘编」），'
                    '没有单一稳定地址，本报不做猜测性链接。</p>' % (len(sources), n_link))
        rows = []
        for s in sources:
            label = "%s · %s" % (esc(s.get("outlet", "")), esc(s.get("item", "")))
            u = src_url(s)
            if u:
                label = ('<a class="t" href="%s" rel="noopener noreferrer" target="_blank">%s</a>'
                         % (esc(u), label))
            rows.append('<li><span class="d">%s · %s</span>%s</li>'
                        % (esc(s.get("id", "")), esc(s.get("kind", "")), label))
        body.append('<ul class="plain">%s</ul>' % "".join(rows))
    body.append('<p class="pager"><a href="index.html">← 归档</a>'
                '<a href="../index.html">返回导读首页 →</a></p>')
    body.append(footer(conf, disclaimer, now, 1))
    return shell("%s · %s" % (issue.get("issueLabel", d), conf.get("title") or "AI 晨报"),
                 issue.get("headline", ""), "\n".join(body), 1, conf,
                 canonical="issues/%s.html" % d)


def render_archive(conf, issues, cards_by_date, disclaimer, now) -> str:
    body = ['<p class="kicker">归档</p>', '<h1 class="lede">全部期次</h1>']
    rows = []
    for issue in issues:
        n = len(cards_by_date.get(issue["date"]) or [])
        extra = " · %d 张卡" % n if n else ""
        rows.append('<li><span class="d">%s · %s%s</span>'
                    '<a class="t" href="%s.html">%s</a></li>'
                    % (esc(issue.get("dateCn", issue["date"])), esc(issue.get("issueLabel", "")),
                       extra, esc(issue["date"]), esc(issue.get("headline", ""))))
    body.append('<ul class="plain">%s</ul>' % "".join(rows))
    body.append('<p class="pager"><a href="../index.html">← 返回导读首页</a></p>')
    body.append(footer(conf, disclaimer, now, 1))
    return shell("归档 · %s" % (conf.get("title") or "AI 晨报"),
                 "全部期次索引。", "\n".join(body), 1, conf, canonical="issues/index.html")


def footer(conf, disclaimer, now, depth: int = 1) -> str:
    up = "../" * depth
    return ('<footer>%s<br>公开面由 <code>ai-daily/tools/build_public.py</code> 生成于 %s；'
            '正文仍在受访问码保护的私有站点。<br>'
            '<a href="%sindex.html">导读</a> · <a href="%scards/index.html">事实卡</a> · '
            '<a href="%sissues/index.html">归档</a></footer>'
            % (esc(disclaimer), esc(now), up, up, up))


def sitemap(conf, paths) -> str:
    base = (conf.get("base") or "").rstrip("/")
    items = "".join("  <url><loc>%s/%s</loc></url>\n" % (base, p) for p in paths)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            "%s</urlset>\n" % items)


def robots(conf) -> str:
    base = (conf.get("base") or "").rstrip("/")
    return "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % base


# ---------------------------------------------------------------- 主流程

def build(out: Path, check: bool = False) -> int:
    conf = load_conf()
    data = load_issues()
    issues = sorted(data["issues"], key=lambda x: (x["date"], x.get("issue", "")), reverse=True)
    cfg = load_config_fields()
    disclaimer = cfg.get("disclaimer", "本报内容由 AI 自动生成，用于产品演示，不构成事实报道。")
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")

    cards_by_date = {}
    src_by_date = {}
    blk_by_date = {}
    for issue in issues:
        f, s, b = load_parts(issue["date"], bool(issue.get("isSpecial")))
        cards = facts_of(f)
        if cards:
            cards_by_date[issue["date"]] = cards
            src_by_date[issue["date"]] = sources_of(s)
            blk_by_date[issue["date"]] = b

    files = {}
    files["index.html"] = render_index(conf, issues, cards_by_date, disclaimer, now)
    if cards_by_date:
        files["cards/index.html"] = render_cards_index(conf, issues, cards_by_date, disclaimer, now)
    for issue in issues:
        cards = cards_by_date.get(issue["date"]) or []
        files["issues/%s.html" % issue["date"]] = render_issue(
            conf, issue, cards, src_by_date.get(issue["date"]), disclaimer, now)
        for card in cards:
            files["cards/%s-%s.html" % (issue["date"], card["id"])] = render_card(
                conf, issue, card, cards, blk_by_date.get(issue["date"]),
                src_by_date.get(issue["date"]), disclaimer, now)
    files["issues/index.html"] = render_archive(conf, issues, cards_by_date, disclaimer, now)

    paths = sorted(files) + ["sitemap.xml", "robots.txt"]
    files["sitemap.xml"] = sitemap(conf, paths)
    files["robots.txt"] = robots(conf)
    files["style.css"] = CSS.lstrip("\n")

    changed = []
    for rel, text in sorted(files.items()):
        p = out / rel
        blob = text.encode("utf-8")
        if check:
            if not p.is_file() or norm(p.read_text(encoding="utf-8", errors="replace")) != norm(text):
                changed.append(rel)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)

    if check:
        extra = []
        for sub in ("cards", "issues"):
            d = out / sub
            if d.is_dir():
                for p in d.glob("*.html"):
                    rel = "%s/%s" % (sub, p.name)
                    if rel not in files:
                        extra.append(rel)
        if changed or extra:
            print("[公开面] 与生成结果不一致：%d 个待更新" % len(changed))
            for rel in changed[:8]:
                print("  - " + rel)
            for rel in extra[:8]:
                print("  ! 多余文件 " + rel)
            return 1
        print("[公开面] 一致：%d 个页面" % len(files))
        return 0

    stale = []
    for sub in ("cards", "issues"):
        d = out / sub
        if d.is_dir():
            for p in d.glob("*.html"):
                rel = "%s/%s" % (sub, p.name)
                if rel not in files:
                    stale.append(rel)
                    p.unlink()
    (out / ".nojekyll").write_bytes(b"")

    cards = sum(len(v) for v in cards_by_date.values())
    print("[公开面] 已生成 %d 个文件到 %s" % (len(files) + 1, out))
    print("[公开面] 期次 %d · 事实卡 %d · 清理陈旧页 %d"
          % (len(issues), cards, len(stale)))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成免访问码的公开导读面")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录（默认仓库 docs/）")
    ap.add_argument("--check", action="store_true", help="只比对，不写盘")
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    if not (SITE / "issues.js").is_file():
        print("找不到 site/issues.js，先跑 build_index.py", file=sys.stderr)
        return 2
    return build(out, check=args.check)


if __name__ == "__main__":
    sys.exit(main())
