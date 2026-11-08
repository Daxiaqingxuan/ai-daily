#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""拼版：把 parts/<MMDD>/ 下的版面片段拼成一期晨报，写盘前做断言。

用法：
    python tools/assemble_issue.py --parts parts/1106 --date 2026-11-06 --issue 003
    python tools/assemble_issue.py --parts parts/1107 --date 2026-11-07 --issue 004   # 16 版
    # 特刊按当天序列编号：003 之后的第二版叫 003-2
    python tools/assemble_issue.py --parts parts/1106sp --date 2026-11-06 --issue 003-2 \
        --slug=-特刊 --label 傍晚特刊 --no-status --no-site

版式：
    15 版  —— 001~003 的旧版式（末版的片段里自带报尾、目录、名词速查）
    16 版  —— 从 004 起，多一块「本报提案」；报尾拆到 00-tail.html

片段约定（同目录）：
    00-style.html        必填，全站样式
    00-masthead.html     必填，报头（含 15 或 16 条导航）
    00-style-extra.html  选填，追加样式（16 版时放提案版样式）
    pNN.html             必填，p01…pNN 连续
    00-tail.html         选填，公共报尾（右侧目录 / 手机目录 / 报尾）

设计要点（和教程里的四条铁律对应）：
  1. 只做一件事：拼装 + 校验 + 原子写。不生成内容。
  2. 写盘前断言，任一条不过就不落盘（避免半成品覆盖好文件）。
  3. 原子写：先写 .tmp 再 os.replace，中途失败不留半个文件。
  4. 幂等：同样的片段跑两次，产物字节一致（无时间戳）。
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys

CJK_WEEKDAY = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
ALLOWED_PAGES = (15, 16)

# P005-2 论据标记：词表固定，页面上只许出现这几档，免得每期自己发明说法。
SRC_LABELS = ("厂商口径", "本报未复现", "预印本", "公开报道", "本报实测", "本报自设")
# 事实卡的 strength → 该版必须出现的标记
STRENGTH_LABEL = {
    "vendor": "厂商口径",
    "preprint": "预印本",
    "media": "公开报道",
    "measured": "本报实测",
    "estimate": "本报自设",
}
FACTS_OPEN = '<script type="application/json" id="ai-daily-facts">'
# P005-3：从 004 期起，正刊必须写主线声明与事实卡（特刊是当天第 2 版，不强制）
NEED_THREAD_FROM = 4

# P006 版级来源：这一版的信息主要来自哪里。
# 注意标的是「信息来自哪」，不是「谁执笔」——全部版面都由 AI 执笔，报尾有内容声明。
# 两者混在一起就会出现「AI 写的稿子标成官方」这种假标，所以图例里必须写死这句。
ORG_LABELS = {
    "official": "官方",
    "thirdparty": "第三方信息网",
    "measured": "本报实测",
    "ai": "AI 生成",
}
ORG_MAX_AI = 4
SOURCE_KINDS = ("官方发布", "媒体报道", "预印本", "公开榜单")
SOURCES_SLOT = "<!-- SOURCES -->"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def build_head(css, title):
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n"
        "<meta charset=\"UTF-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>" + title + "</title>\n"
        "<style>" + css + "</style>\n</head>\n<body>\n<div class=\"page\" id=\"top\">\n"
    )


def seg(full, label, size=1200):
    i = full.find(label)
    return full[i:i + size] if i >= 0 else ""


def div_block(full, start):
    """从 start（某个 <div 的位置）起，按 div 深度切出完整块。

    不能用正则 `<div class="gloss".*?</div>`：gloss 里嵌着 gloss-grid 和 dl，
    非贪婪会停在第一个 </div>，抓不全词条。
    """
    if start < 0:
        return ""
    depth = 0
    for m in re.finditer(r"<div\b[^>]*>|</div>", full[start:]):
        if m.group(0).startswith("</"):
            depth -= 1
            if depth == 0:
                return full[start:start + m.end()]
        else:
            depth += 1
    return full[start:]


def load_json_opt(path):
    """读可选的期次数据文件；不存在返回 None，坏 JSON 直接抛（不许静默放行）。"""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def origin_chip(org, note=""):
    """版级来源小标。note 进 title，鼠标悬停能看这一版主要靠什么。"""
    tip = (' title="%s"' % note) if note else ""
    return ('<span class="src-org src-org-%s"%s>来源 · %s</span>'
            % (org, tip, ORG_LABELS[org]))


def inject_origin(html, pid, blocks):
    """把 00-blocks.json 里的版级来源渲染进版头。

    版号本来独占右端，直接塞第三个 flex 子项会被 space-between 推到中间，
    所以把「标签 + 版号」包成一个右侧组。头版没有 section-head，挂在 kicker 上。
    已经手写过 src-org 的版面不再注入（由 A14 校验它写对没有）。
    """
    rec = ((blocks or {}).get("pages") or {}).get(pid)
    if not rec or 'class="src-org' in html:
        return html
    org = rec.get("origin")
    if org not in ORG_LABELS:
        return html
    chip = origin_chip(org, rec.get("note") or "")

    def wrap(m):
        return '<span class="sec-right">' + chip + m.group(1) + "</span>"

    out, n = re.subn(r'(<span class="sec-page">[^<]*</span>)', wrap, html, count=1)
    if n:
        return out

    def kicker(m):
        return m.group(1) + chip + m.group(2)

    out, n = re.subn(r'(<div class="kicker">[^<]*)(</div>)', kicker, html, count=1)
    return out if n else html


def render_sources(src):
    """报尾信源表：一条一行，带归属方、被引内容、来源类型。

    用列表而不是一段长文字，是因为「引用自谁」要能被逐条核；写成一句话
    混在一起，读者没法判断哪条是哪家说的，也谈不上许可归属。
    """
    items = (src or {}).get("sources") or []
    lis = []
    for s in items:
        lis.append(
            '<li class="src-li"><span class="src-out">%s</span>'
            '<span class="src-what">%s</span>'
            '<span class="src-kind">%s</span></li>'
            % (s.get("outlet") or "", s.get("item") or "", s.get("kind") or ""))
    return (
        '<div class="sources" data-slot="sources">\n'
        '      <div class="sources-h"><b>信息源与归属</b>'
        '<i>%s</i></div>\n'
        '      <ul>\n        %s\n      </ul>\n'
        '      <p class="sources-note">以上名称与商标归各权利人；'
        '本报只引用事实，不使用其原文表述，也不代表其立场。</p>\n'
        '    </div>' % (src.get("policy") or "", "\n        ".join(lis)))


def sections_of(full):
    """按 <section> 切块，返回 [(pNN, html)]；版面不嵌套，顺序即版序。

    不能切到「下一个 <section」为止：最后一版会把报尾（词表、图例）也吞进来，
    跑偏判定和事实卡核对都会误伤。
    """
    out = []
    for m in re.finditer(r'<section[^>]*\bid="(p\d\d)"', full):
        end = full.find("</section>", m.end())
        out.append((m.group(1), full[m.start(): end + len("</section>") if end > 0
                             else len(full)]))
    return out


def check(fragments, full, date, issue, n_pages, thread=None, facts=None,
          blocks=None, sources=None):
    """返回 (错误列表, 统计字典)。任何错误都不落盘。"""
    errs = []
    stat = {"pages": n_pages}
    want = ["p%02d" % i for i in range(1, n_pages + 1)]

    # A1 版数 = 片段数
    stat["sections"] = len(re.findall(r"<section\b", full))
    if stat["sections"] != n_pages:
        errs.append("A1 版数应为 %d，实际 %d" % (n_pages, stat["sections"]))

    # A2 版面 id 连续 p01..pNN，且顺序正确
    ids = re.findall(r'<section[^>]*\bid="(p\d\d)"', full)
    if ids != want:
        errs.append("A2 版面 id 不连续：%s" % (",".join(ids) or "空"))

    # A3 导航条数 = 版数，锚点都能落地
    nav = re.search(r'<nav class="mast-nav">(.*?)</nav>', full, re.S)
    if not nav:
        errs.append("A3 找不到报头导航")
    else:
        hrefs = re.findall(r'href="#(p\d\d)"', nav.group(1))
        stat["nav"] = len(hrefs)
        if hrefs != want:
            errs.append("A3 导航锚点与版面不一致：%s" % ",".join(hrefs))
        missing = [h for h in hrefs if h not in ids]
        if missing:
            errs.append("A3 导航指向不存在的版面：%s" % ",".join(missing))

    # A4 期号出现在标题、报头、页脚
    for label in ("<title>", '<div class="mast-top">', '<footer class="colophon">'):
        s = seg(full, label, 900)
        if "第 %s 期" % issue not in s:
            errs.append("A4 %s 处缺「第 %s 期」" % (label, issue))

    # A4c 带后缀的期号（特刊 003-2）不许在报头/标题/报尾残留裸期号：
    #     这三处是复制模板时最容易漏改的，且「第 003 期」在页面上看不出错，
    #     读者会以为特刊和正刊是同一期。正文里提到正刊不算错，故只查三处。
    if "-" in issue:
        bare = issue.split("-", 1)[0]
        for label in ("<title>", '<div class="mast-top">', '<footer class="colophon">'):
            if re.search(r"第\s*%s\s*期" % re.escape(bare), seg(full, label, 900)):
                errs.append("A4c %s 处期号没改成「第 %s 期」（仍写着第 %s 期）"
                            % (label, issue, bare))


    # A4b 版数在标题、报头、页脚三处一致（15/16 混用必红）
    for label in ("<title>", '<div class="mast-top">', '<footer class="colophon">'):
        s = seg(full, label, 900)
        if "共 %d 版" % n_pages not in s:
            errs.append("A4b %s 处版数不是「共 %d 版」" % (label, n_pages))

    # A4d 每版页眉「第 NN 版 / 共 M 版」的 M 必须等于总版数，页码要连续。
    #     A4b 只查标题/报头/页脚三处，页眉是复制模板的批量产物：003-2 扩到 16 版时
    #     前 14 个页眉原样留着「共 15 版」，读者在第 15 版看到「共 15 版」，
    #     翻过去还有第 16 版——三处对的、正文全错，只看 A4b 会盖绿章。
    secs = re.findall(
        r'<span class="sec-page">第\s*(\d+)\s*版\s*/\s*共\s*(\d+)\s*版</span>', full)
    if len(secs) != n_pages - 1:              # 第 01 版用头条代替页眉
        errs.append("A4d 页眉 %d 条，应为 %d 条（第 01 版无页眉）"
                    % (len(secs), n_pages - 1))
    nums = [int(a) for a, _ in secs]
    if nums != list(range(2, n_pages + 1)):
        errs.append("A4d 页眉页码不连续：%s" % (nums or "无"))
    wrong = sorted({int(b) for _, b in secs if int(b) != n_pages})
    if wrong:
        errs.append("A4d %d 处页眉版数写成「共 %s 版」，应为「共 %d 版」"
                    % (len([1 for _, b in secs if int(b) != n_pages]),
                       "/".join(map(str, wrong)), n_pages))

    # A5 不残留上一期字样。
    #    报头/标题查上一期的日期；正文只查「第 NNN 期」，避免误伤「11 月 6 日」这类正常引用。
    d = datetime.date(int(date[:4]), int(date[5:7]), int(date[8:10]))
    prev = d - datetime.timedelta(days=1)
    # 期号可能带后缀（003-2 是当天的第 2 版），取主号算上一期
    prev_issue = "%03d" % (int(issue.split("-", 1)[0]) - 1)
    body = re.sub(r"<p>\s*<b>往期：</b>.*?</p>", "", full, flags=re.S)
    for stale in (prev.isoformat(), "%d 月 %d 日" % (prev.month, prev.day)):
        for label in ("<title>", '<div class="mast-top">'):
            if stale in seg(full, label, 900):
                errs.append("A5 报头残留上期日期：%s" % stale)
    if "第 %s 期" % prev_issue in body:
        errs.append("A5 正文残留上期期号：第 %s 期" % prev_issue)

    # A6 每版都要有锐评块
    for i, frag in enumerate(fragments, 1):
        if "razor" not in frag:
            errs.append("A6 第 %02d 版缺锐评块" % i)

    # A7 每版都要有版头页码（第 01 版允许用头条替代）
    for i, frag in enumerate(fragments, 1):
        if i == 1:
            continue
        if "sec-page" not in frag:
            errs.append("A7 第 %02d 版缺页码" % i)

    # A8 标签配平（粗检）+ 体积下限
    for tag in ("div", "article", "aside", "section", "table", "ul", "ol", "p", "figure", "svg"):
        o = len(re.findall(r"<%s\b" % tag, full))
        c = len(re.findall(r"</%s>" % tag, full))
        if o != c:
            errs.append("A8 <%s> 未配平：开 %d / 闭 %d" % (tag, o, c))

    stat["bytes"] = len(full.encode("utf-8"))
    if stat["bytes"] < 45000:
        errs.append("A8 产物过小（%d 字节），疑似片段缺失" % stat["bytes"])

    # A9 文中注解与报尾名词速查必须是同一套词。
    #    文中虚线词若在报尾查不到，读者点开找不到索引，等于两套平行术语表。
    plain = lambda s: re.sub(r"<[^>]+>", "", s).strip()
    key = lambda s: re.sub(r"[（(][^）)]*[）)]|[\s·/／]", "", plain(s)).lower()

    # 只认名词速查块内的 dt：提案/决议卡也用 dl，直接全文抓会多数出七八条
    gloss_html = div_block(full, full.find('<div class="gloss"'))
    terms = [plain(t) for t in re.findall(
        r'<span class="term"[^>]*>(.*?)<i class="tip">', full, re.S)]
    dts = [plain(d) for d in re.findall(r"<dt>(.*?)</dt>", gloss_html, re.S)]
    stat["terms"] = len(terms)
    stat["gloss"] = len(dts)

    def covered(term, dt_raw):
        a = key(term)
        if not a:
            return False
        # 报尾常写「量化 / Q4 / Q2」这种多写法，先拆再逐个别比
        return any(p and (p in a or a in p)
                   for p in (key(x) for x in re.split(r"[/／]", plain(dt_raw))))

    for t in terms:
        if dts and not any(covered(t, d) for d in dts):
            errs.append("A9 文中注解「%s」在报尾名词速查里没有词条" % t)

    # A9b 报尾标题自称的词数必须等于词条数（写「13 个词」就该有 13 条）
    m = re.search(r"名词速查[^<]*?(\d+)\s*个词", full)
    if m and int(m.group(1)) != len(dts):
        errs.append("A9b 报尾标题写「%s 个词」，实际 %d 条" % (m.group(1), len(dts)))

    # A9c 报头读报指南/正文提到「报尾 N 词表」时，N 也要对得上
    for m in re.finditer(r"报尾\s*(\d+)\s*词表", full):
        if int(m.group(1)) != len(dts):
            errs.append("A9c 报头/正文写「报尾 %s 词表」，实际 %d 条"
                        % (m.group(1), len(dts)))

    # A10 论据标记（P005-2）。
    #     跑偏那次的教训：同一页里既有「本报未复现」，也有直接引用的数字，排版上
    #     没有区别，读者无法判断哪句能信。统一成行内小标后，标记本身就是一道闸门。
    #     001–003 等历史期没有这套标记，不追溯；从 004 期起的新正刊必须齐。
    secs_map = dict(sections_of(full))
    main_no = int(issue.split("-", 1)[0])
    need = main_no >= NEED_THREAD_FROM and "-" not in issue

    raw_tags = re.findall(r'<span class="src-tag[^"]*">(.*?)</span>', full, re.S)
    tags = [plain(t) for t in raw_tags]
    stat["src_tags"] = len(tags)
    unknown = sorted({t for t in tags if t not in SRC_LABELS})
    if unknown:
        errs.append("A10 论据标记用了未登记的词：%s（只许 %s）"
                    % ("、".join(unknown), " / ".join(SRC_LABELS)))
    if need and not tags:
        errs.append("A10 全文一处论据标记都没有（事实卡覆盖的版面必须有）")
    legend = div_block(full, full.find('<div class="src-legend"'))
    if need and not legend:
        errs.append("A10c 报尾缺论据标记图例（.src-legend）")
    elif legend:
        lack = [l for l in SRC_LABELS if l not in legend]
        if lack:
            errs.append("A10c 报尾图例缺 %s" % "、".join(lack))

    # A11 主线声明（P005-3）。跑偏的根因不是写错数字，是开工时没有一句话规定
    #     「这一期只回答什么」。声明放在报头 data-thread 里，拼版时对账。
    if need and not thread:
        errs.append("A11 正刊从 004 期起必须写 parts/<MMDD>/00-thread.json（本期主线）")
    if thread:
        name = (thread.get("thread") or "").strip()
        if not (3 <= len(name) <= 20):
            errs.append("A11 主线名长度不对：%r（应 3–20 字）" % name)
        m = re.search(r'data-thread="([^"]*)"', full)
        if not m:
            errs.append("A11 报头没有 data-thread 声明（复制模板时漏了，主线无从校验）")
        elif m.group(1).strip() != name:
            errs.append("A11 报头主线「%s」与 00-thread.json「%s」不一致"
                        % (m.group(1).strip(), name))
        if name and ("本期主线：%s" % name) not in full:
            errs.append("A11 报尾没有回显「本期主线：%s」" % name)

    # A12 跑偏熔断（P005-3）。命中主线之外题材的版面超过阈值就 BLOCK：
    #     原 004 期 16 版里 10 版写行情，A1–A9 一条都没拦住。
    if thread:
        off = [t for t in (thread.get("offTopicTerms") or []) if t]
        limit = int(thread.get("maxOffTopicPages", 7))
        exempt = set(thread.get("exemptPages") or [])
        plain_of = lambda s: re.sub(r"<[^>]+>", "", s)
        hits = []
        for pid, html in sections_of(full):
            if pid in exempt:
                continue
            got = [t for t in off if t in plain_of(html)]
            if got:
                hits.append((pid, got))
        stat["off_topic"] = len(hits)
        if len(hits) > limit:
            errs.append("A12 跑偏熔断：%d 版命中本期主线之外的题材（上限 %d 版）——%s"
                        % (len(hits), limit, "、".join(p for p, _ in hits)))
        for pid, got in hits:
            if pid == "p01":
                errs.append("A12 跑偏熔断：头版命中「%s」，头条不该是主线之外的话题"
                            % "、".join(got))

    # A13 事实卡（P005-4）。数字写在正文里、来源写在报尾，下一期复核只能重读
    #     16 版。把断言/数值/来源/时点/强度做成机器可读字段，才谈得上「可校验」。
    if need and not facts:
        errs.append("A13 正刊从 004 期起必须写 parts/<MMDD>/00-facts.json（事实卡）")
    if facts:
        items = facts.get("facts") or []
        if len(items) < 5:
            errs.append("A13 事实卡只有 %d 条，少于 5 条" % len(items))
        ids = [f.get("id") or "" for f in items]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            errs.append("A13 事实卡 id 重复：%s" % "、".join(dup))
        flat_of = lambda s: re.sub(r"[ \t\r\n]+", "", re.sub(r"<[^>]+>", " ", s))
        for f in items:
            fid = f.get("id") or "?"
            for k in ("claim", "value", "page", "source", "asOf", "strength"):
                if not str(f.get(k) or "").strip():
                    errs.append("A13 %s 缺字段 %s" % (fid, k))
            st = f.get("strength")
            if st not in STRENGTH_LABEL:
                errs.append("A13 %s 的 strength「%s」不在 %s"
                            % (fid, st, " / ".join(STRENGTH_LABEL)))
            rep = f.get("reproduced")
            if not isinstance(rep, bool):
                errs.append("A13 %s 的 reproduced 必须是 true/false" % fid)
            elif rep and st != "measured":
                errs.append("A13 %s 声称已复现，但 strength 不是 measured" % fid)
            elif (not rep) and st == "measured":
                errs.append("A13 %s strength 写了 measured，却说未复现" % fid)
            pg = f.get("page")
            if pg and pg not in secs_map:
                errs.append("A13 %s 指向不存在的版面 %s" % (fid, pg))
                continue
            # 数值必须出现在它自己那一版：写错版号、正文改数而卡没改，都会在这里红
            val = str(f.get("value") or "").replace(" ", "")
            if val and pg in secs_map and val not in flat_of(secs_map[pg]):
                errs.append("A13 %s 的数值「%s」在 %s 里找不到（事实卡与正文漂移）"
                            % (fid, val, pg))
            asof = str(f.get("asOf") or "")
            if asof > date:
                errs.append("A13 %s 的时点 %s 晚于出报日 %s" % (fid, asof, date))
        # A10b 覆盖：事实卡里每一条落在哪版，那版就必须有对应档的标记。
        # 这样「标记该不该加」不靠编辑记忆，而由事实卡驱动。
        for f in items:
            pg, st = f.get("page"), f.get("strength")
            want = STRENGTH_LABEL.get(st)
            if pg in secs_map and want and (">%s<" % want) not in secs_map[pg]:
                errs.append("A10b %s 引用了%s，但该版没有「%s」标记"
                            % (pg, f.get("claim") or "外部数字", want))
        stat["facts"] = len(items)
        stat["reproduced"] = sum(1 for f in items if f.get("reproduced") is True)

    # A14 版级来源（P006）。读者问得最多的一句是「这条消息哪来的」，
    #      而此前只有报尾一段笼统的「信息源」——16 版共用一段话，等于没标。
    #      现在每版头都必须有一个来源标，且口径只能取固定四档。
    if need and not blocks:
        errs.append("A14 正刊从 004 期起必须写 parts/<MMDD>/00-blocks.json（每版信息来源）")
    if blocks:
        pages = blocks.get("pages") or {}
        for pid, html in secs_map.items():
            rec = pages.get(pid) or {}
            org = rec.get("origin")
            if not org:
                errs.append("A14 %s 没有登记信息来源" % pid)
                continue
            if org not in ORG_LABELS:
                errs.append("A14 %s 的 origin「%s」不在 %s"
                            % (pid, org, " / ".join(ORG_LABELS)))
                continue
            if (">来源 · %s<" % ORG_LABELS[org]) not in html:
                errs.append("A14 %s 版头缺「来源 · %s」标签（被手工改掉或拼版时没注入）"
                            % (pid, ORG_LABELS[org]))
        ghost = sorted(set(pages) - set(secs_map))
        if ghost:
            errs.append("A14 登记了不存在的版面：%s" % "、".join(ghost))

        # A14b 「AI 生成」的版不许挂外部论据标记：一边说没有外部信源，
        #       一边标「厂商口径」，是自相矛盾的假标。
        for pid, html in secs_map.items():
            org = (pages.get(pid) or {}).get("origin")
            if org == "ai" and 'class="src-tag' in html:
                errs.append("A14b %s 标了「AI 生成」，却挂着外部论据标记——两者矛盾" % pid)

        # A14c 反过来：标了官方 / 第三方 / 实测的版，至少要有一处可核的东西。
        #      全版没有论据标记、也没有事实卡条目，说明这个「官方」是标签而非出处。
        fact_pages = {f.get("page") for f in ((facts or {}).get("facts") or [])}
        for pid, html in secs_map.items():
            org = (pages.get(pid) or {}).get("origin")
            if org in ("official", "thirdparty", "measured"):
                if 'class="src-tag' not in html and pid not in fact_pages:
                    errs.append("A14c %s 标了「来源 · %s」，但全版没有论据标记、"
                                "也没有事实卡条目——无从核对" % (pid, ORG_LABELS[org]))

        # A15 AI 生成占比。整份报纸都由 AI 执笔，但「通篇无外部信源」的版面
        #     必须少：这类版面再好看也不提供信息增量，多了就是自说自话。
        ai_pages = sorted(p for p in secs_map
                          if (pages.get(p) or {}).get("origin") == "ai")
        limit = int(blocks.get("maxAiPages", ORG_MAX_AI))
        stat["ai_pages"] = len(ai_pages)
        stat["ai_limit"] = limit
        if len(ai_pages) > limit:
            errs.append("A15 「AI 生成」版面 %d 版（%s），超过上限 %d 版"
                        % (len(ai_pages), "、".join(ai_pages), limit))
        # A15b 报尾自称的「本期 AI 生成 N 版」也要对得上：图例里那句是读者唯一
        #      能看到的口径，写死了就会慢慢和实际分家。
        m = re.search(r"本期 AI 生成 (\d+) 版", full)
        if m and int(m.group(1)) != len(ai_pages):
            errs.append("A15b 报尾写「本期 AI 生成 %s 版」，实际 %d 版"
                        % (m.group(1), len(ai_pages)))

    # A16 信源归属（P006）。引用外媒只列一串名字，读者没法判断许可与责任边界；
    #      一条一行写清「谁给的、给了什么、哪一类」，再对账渲染条数。
    if need and not sources:
        errs.append("A16 正刊从 004 期起必须写 parts/<MMDD>/00-sources.json（信源归属表）")
    if sources:
        items = sources.get("sources") or []
        if len(items) < 5:
            errs.append("A16 信源表只有 %d 条，少于 5 条" % len(items))
        ids = [s.get("id") or "" for s in items]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            errs.append("A16 信源 id 重复：%s" % "、".join(dup))
        for s in items:
            sid = s.get("id") or "?"
            for k in ("outlet", "item", "kind", "usage"):
                if not str(s.get(k) or "").strip():
                    errs.append("A16 %s 缺字段 %s" % (sid, k))
            if s.get("kind") not in SOURCE_KINDS:
                errs.append("A16 %s 的 kind「%s」不在 %s"
                            % (sid, s.get("kind"), " / ".join(SOURCE_KINDS)))
        if '<div class="sources"' not in full:
            errs.append("A16 报尾没有渲染信源表（00-tail.html 缺 %s 占位）" % SOURCES_SLOT)
        rendered = full.count('class="src-li"')
        if rendered and rendered != len(items):
            errs.append("A16 报尾信源表渲染了 %d 条，00-sources.json 有 %d 条（漂移）"
                        % (rendered, len(items)))
        stat["sources"] = len(items)

    return errs, stat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--issue", required=True,
                    help="三位期号，如 004；当天第二版（特刊）写 004-2")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--site-dir", default="site")
    ap.add_argument("--no-site", action="store_true",
                    help="不往 site/ 根同步（特刊只走 site/special/，避免同名副本没凭证）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="目标文件已存在且内容不同才需要；不带则拒绝覆盖")
    ap.add_argument("--no-status", action="store_true",
                    help="不写状态机（试拼 / 演练 / 特刊用）")
    ap.add_argument("--slug", default="",
                    help="文件名后缀，如 -特刊 → AI晨报-2026-11-06-特刊.html")
    ap.add_argument("--label", default="",
                    help="整段版名，默认「智能体专版」；特刊传「傍晚特刊」")
    a = ap.parse_args()

    if not re.fullmatch(r"\d{3}(-\d+)?", a.issue):
        print("期号格式不对：%s（应为主号 003，或当天第二版 003-2）" % a.issue)
        return 2

    d = a.parts
    css = read(os.path.join(d, "00-style.html"))
    extra = os.path.join(d, "00-style-extra.html")
    if os.path.exists(extra):
        css = css + "\n" + read(extra)
    mast = read(os.path.join(d, "00-masthead.html"))
    names = sorted(
        n for n in os.listdir(d)
        if re.fullmatch(r"p\d\d\.html", n)
    )
    n_pages = len(names)
    if n_pages not in ALLOWED_PAGES:
        print("片段数不对：期望 %s 个 pNN.html，实际 %d 个（%s）"
              % ("/".join(str(x) for x in ALLOWED_PAGES), n_pages, ",".join(names)))
        return 2
    frags = [read(os.path.join(d, n)) for n in names]

    # P006：版级来源与信源归属，都是期次级数据
    blocks = load_json_opt(os.path.join(d, "00-blocks.json"))
    sources = load_json_opt(os.path.join(d, "00-sources.json"))
    frags = [inject_origin(f, "p%02d" % (i + 1), blocks) for i, f in enumerate(frags)]

    tail = ""
    tail_path = os.path.join(d, "00-tail.html")
    if os.path.exists(tail_path):
        tail = "\n" + read(tail_path)
    if sources and SOURCES_SLOT in tail:
        tail = tail.replace(SOURCES_SLOT, render_sources(sources))

    # P005-3 / P005-4：主线声明与事实卡，都是期次级数据（不存在则由断言决定放不放行）
    thread = load_json_opt(os.path.join(d, "00-thread.json"))
    facts = load_json_opt(os.path.join(d, "00-facts.json"))
    facts_block = ""
    if facts:
        # 机器可读、键序固定 → 同样片段跑两次字节一致（幂等）
        facts_block = (FACTS_OPEN + json.dumps(
            facts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "</script>")

    # 版名默认取本期主线：标题里那句「· 从会答到会办 ·」不该靠命令行手打，
    # 否则试拼（selfcheck 不带 --label）与成品的标题字节数对不上，报出来的体积
    # 差几个字节，看着像漂移。
    edition = (a.label.strip() or (thread or {}).get("thread") or "智能体专版")
    title = "AI 晨报 · %s年%s月%s日 · 第 %s 期 · %s（共 %d 版）" % (
        a.date[:4], int(a.date[5:7]), int(a.date[8:10]), a.issue,
        edition, n_pages)
    full = (build_head(css, title) + mast + "\n".join(frags) + tail
            + facts_block + "</div>\n</body>\n</html>\n")

    errs, stat = check(frags, full, a.date, a.issue, n_pages, thread, facts,
                       blocks, sources)
    print("版数 %(sections)d  导航 %(nav)d  体积 %(bytes)d 字节" % stat)
    if stat.get("src_tags"):
        extra = "论据标记 %d 处" % stat["src_tags"]
        if "facts" in stat:
            extra += "  事实卡 %d 条（已复现 %d 条）" % (stat["facts"], stat["reproduced"])
        if "off_topic" in stat:
            extra += "  跑偏版 %d 版" % stat["off_topic"]
        print(extra)
    if "ai_pages" in stat:
        print("AI 生成版 %d 版（上限 %d）  信源 %d 条"
              % (stat["ai_pages"], stat["ai_limit"], stat.get("sources") or 0))
    if errs:
        print("校验未通过，未写盘：")
        for e in errs:
            print("  -", e)
        return 1
    print("校验通过（A1–A16）")

    if a.dry_run:
        print("dry-run，不写盘")
        return 0

    y, m, dd = int(a.date[:4]), int(a.date[5:7]), int(a.date[8:10])
    wd = CJK_WEEKDAY[datetime.date(y, m, dd).weekday()]
    fname = "AI晨报-%s%s.html" % (a.date, a.slug)
    p1 = os.path.join(a.out_dir, fname)
    os.makedirs(a.out_dir, exist_ok=True)

    # 同名冲突闸门：内容不同就必须显式 --force，避免把已发布的成品覆盖成另一版
    if os.path.exists(p1) and not a.force:
        old = read(p1)
        if old != full:
            print("目标已存在且内容不同：%s" % p1)
            print("  旧 %d 字节 / 新 %d 字节" % (len(old.encode("utf-8")), len(full.encode("utf-8"))))
            print("  确认要覆盖这一期（例如改了片段要重排），加 --force 再跑")
            return 3

    atomic_write(p1, full)
    print("写入", p1, "（%s %s）" % (a.date, wd))

    site = os.path.join(a.site_dir, fname)
    if a.no_site:
        print("跳过 site 根同步（--no-site）")
    elif os.path.isdir(a.site_dir):
        shutil.copyfile(p1, site)
        print("同步", site)

    # 状态机埋点：只记录，不影响出报结果；失败也不抛出
    if a.no_status:
        print("状态记录跳过（--no-status）")
        return 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import status as status_mod
        book = status_mod.Book()
        if book.d.get("date") != a.date:
            book.begin(a.date, a.issue)
        book.mark("parts", True, "%d 个片段" % len(names))
        book.mark("assemble", True, "%d 版 / %d 字节" % (n_pages, len(full.encode("utf-8"))))
        print("状态记录：parts=OK assemble=OK（%s）" % os.path.basename(str(status_mod.STATUS)))
    except Exception as exc:
        print("状态记录跳过（%s）" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
