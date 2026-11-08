#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""交付前自检：把「说完成之前必须验过什么」变成一条命令。

用法：
    python tools/selfcheck.py                    # 查当期（status.json 的日期）
    python tools/selfcheck.py --date 2026-11-06
    python tools/selfcheck.py --online           # 额外验线上四处
    python tools/selfcheck.py --pre              # 发布前跑：deploy/verify 未记不算失败

只读：不改任何文件，不发布。任何一项 FAIL → 退出码 1，不许对外说「已完成」。
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                       # ai-daily/
SITE = ROOT / "site"

# 线上入口不在这里存第二份：唯一事实源是 site/config.js 的 siteUrl，
# 部署时浏览器读的也是它。公开仓库里该值是 __SITE_URL__ 占位，于是本文件
# 自动变成「未配置」——--online 会明确报错，而不是拿一份旧地址假绿。
# 想临时指向别的站点（演练 / 假站）用环境变量，不写进文件。
PLACEHOLDER = "__SITE_URL__"


def _site_url():
    try:
        s = (SITE / "config.js").read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r'\bsiteUrl\s*:\s*"([^"]*)"', s)
    return m.group(1).strip() if m else ""


SITE_URL = os.environ.get("AI_DAILY_SITE_URL", "").strip() or _site_url()
BASE = "" if (not SITE_URL or PLACEHOLDER in SITE_URL) else SITE_URL
HOST = (BASE.split("?", 1)[0].rstrip("/") + "/") if BASE else ""

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
rows = []

# 单一事实源：名称 + 排障提示都只在这里写一遍。
# 文档用 `selfcheck.py --list` 引用，不再抄一份会漂的表格；加检查只改这里和下方调用。
ITEMS = [
    (1, "拼版断言 A1–A16", "缺版、期号/版数不一致、注解词查不到、主线与报头不符、跑偏超阈值、事实卡与正文漂移、版级来源缺失或标错、AI 生成版超上限、信源表与正文不一致"),
    (2, "索引与文件一致", "build_index.py 没跑；site/ 大小不符，或副本与源内容不一致"),
    (3, "每期都有 manifest", "出了新成品但没生成同名 json"),
    (4, "manifest 与文件对得上", "成品改过、json 还是旧的（sha/bytes 不符）"),
    (5, "术语：注解能查到词条", "文中加了虚线词，报尾词表没补"),
    (6, "JSON 全部可解析", "手改坏了 issues.js / config.js / 某份 json"),
    (7, "期序与编号", "排序乱、期号重复或跳号、特刊没接成 003-2"),
    (8, "日期闸门（不许提前）", "根目录/站点/索引/状态机里出现晚于今天的期次"),
    (9, "入口页能进特刊", "特刊没进 issues，或横幅/同列排序/深链被删"),
    (10, "状态机五阶段", "某阶段没记，或发布后没 --mark"),
    (11, "全文版数一致", "扩版后页眉没跟着改；站点副本残留旧版数"),
    (12, "内容声明一致（单一事实源）",
     "config.js 改了没跑 apply_disclaimer.py；某期报尾漏写或写了两遍；分享面板又硬编码一句"),
    (13, "线上可访问（--online）", "没发布、缓存给旧版、或线上内容与本地 sha 不符"),
    (14, "规则与清单对账",
     "规则文档写着 A1–A13 而代码已到 A16；条数/脚本数与实际不符；清单列着已删掉的文件。跑 python tools/doc_sync.py --fix 自动对齐"),
    (15, "CI 与自动化配置合法",
     "ci.yml 里混进了 markdown（引用符 `> `、代码围栏 ```）导致 ScannerError、Actions 不加载；缺 jobs/runs-on/steps；README 宣传的平台或 Python 版本在文件里找不到；缺 dependabot.yml 或它没盯 github-actions"),
    (16, "导出覆盖索引",
     "已入库的文件不在导出白名单里——公开仓库会静默少文件，而本机一切正常（白名单是「只复制点到的」，新增目录默认不进）"),
    (17, "APK 快照与当期一致",
     "改了当期正文却没重打 APK：线上一切正常，只有装过 App 的人离线打开看到旧报；或包里 issues.js 列了包里没有的文件（离线点开 404）"),
    (18, "更新清单与包一致",
     "version.json 没跟着包更新（所有装了 App 的人都收不到「有新版本」）、清单超前于包（提示了却下到同一个包），或 MainActivity 里的检查逻辑被删"),
]


def add(no, name, status, detail):
    rows.append({"no": no, "name": name, "status": status, "detail": detail})


def rel(p):
    try:
        return str(Path(p).relative_to(ROOT))
    except Exception:
        return str(p)


# ---------- 1 拼版断言 ----------
def check_assemble(date, issue):
    tag = date[5:7] + date[8:10]
    day = ROOT / "parts" / tag
    sp = ROOT / "parts" / (tag + "sp")
    # 特刊是当天的第 2 版，期号要接 -2；正刊没编号时只能原样透传
    sp_no = (issue + "-2") if issue.isdigit() else issue
    out = []
    for d, no, extra in ((day, issue, []),
                         (sp, sp_no, ["--slug=-特刊", "--label", "傍晚特刊"])):
        if not d.exists():
            continue
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        cmd = [sys.executable, "tools/assemble_issue.py", "--parts", str(d),
               "--date", date, "--issue", no, "--dry-run", "--no-status"] + extra
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        head = (r.stdout or "").strip().splitlines()
        stat = next((l for l in head if l.startswith("版数")), "")
        if r.returncode != 0 or "校验通过" not in (r.stdout or ""):
            bad = [l.strip("- ").strip() for l in head if l.strip().startswith("-")]
            out.append((FAIL, "%s 未过：%s" % (d.name, "；".join(bad) or "退出码 %d" % r.returncode)))
        else:
            out.append((PASS, "%s %s" % (d.name, stat)))
    if not out:
        return add(1, "拼版断言 A1–A16", SKIP, "parts/%s 不存在（历史期或未落片段）" % tag)
    bad = [o for o in out if o[0] == FAIL]
    add(1, "拼版断言 A1–A16", FAIL if bad else PASS, " / ".join(o[1] for o in out))


# ---------- 2 索引与文件 ----------
def load_issues():
    txt = (SITE / "issues.js").read_text(encoding="utf-8")
    body = txt[txt.index("{"): txt.rindex("}") + 1]
    return json.loads(body)


def check_index(data):
    bad = []
    sp_count = 0
    synced = 0
    for it in data.get("issues", []):
        p = SITE / it["file"]
        if it.get("isSpecial"):
            sp_count += 1
            if it.get("manifest") and not (SITE / it["manifest"]).exists():
                bad.append("%s 缺凭证 %s" % (it["file"], it["manifest"]))
        if not p.exists():
            bad.append("%s 缺文件" % it["file"])
        elif p.stat().st_size != it.get("size"):
            bad.append("%s 大小不符 %d≠%d" % (it["file"], p.stat().st_size, it.get("size")))
    for sp in data.get("specials", []):
        p = SITE / sp["file"]
        if not p.exists():
            bad.append("%s 缺文件" % sp["file"])
        elif p.stat().st_size != sp.get("size"):
            bad.append("%s 大小不符" % sp["file"])
    # 「根目录成品 → site/ 副本」是单向同步，但同步跑没跑过必须能被独立证明。
    # 只比 size 会漏掉等长替换（改一个词、改一处版数），所以逐字节比一次。
    # 这是「让事实只有一份」的对账：允许两份文件存在，不允许两份内容不同。
    for p in sorted(SITE.glob("AI晨报-*.html")) + sorted(SITE.glob("special/*.html")):
        src = ROOT / ("AI晨报-%s-特刊.html" % p.stem) if p.parent.name == "special" \
            else ROOT / p.name
        if not src.exists():
            continue                      # 站点里的历史遗留副本，交给人工确认
        synced += 1
        if src.read_bytes() != p.read_bytes():
            bad.append("%s 与源 %s 内容不一致（等长替换只能靠字节比对发现）"
                       % (rel(p), src.name))
    n = len(data.get("issues", []))
    add(2, "索引与文件一致", FAIL if bad else PASS,
        "；".join(bad) if bad else
        "%d 期（含 %d 特刊），大小与凭证吻合；%d 份站点副本与源逐字节一致"
        % (n, sp_count, synced))


# ---------- 3 / 4 manifest ----------
def check_manifest():
    import make_manifest
    htmls = [p for p in sorted(SITE.glob("AI晨报-*.html"))] + \
            [p for p in sorted(SITE.glob("special/*.html"))]
    missing, mismatch, notok = [], [], []
    for h in htmls:
        j = h.with_suffix(".json")
        if not j.exists():
            missing.append(h.name)
            continue
        d = json.loads(j.read_text(encoding="utf-8"))
        if d.get("sha256") != make_manifest.sha256(h) or d.get("bytes") != h.stat().st_size:
            mismatch.append(h.name)
        if not d.get("ok"):
            bad = [k for k, v in d.get("checks", {}).items() if v is False]
            notok.append("%s(%s)" % (h.name, ",".join(bad) or "?"))
    add(3, "每期都有 manifest", FAIL if missing else PASS,
        "缺 " + "、".join(missing) if missing else "%d/%d 份成品都有同名 json" % (len(htmls) - len(missing), len(htmls)))
    add(4, "manifest 与文件对得上", FAIL if (mismatch or notok) else PASS,
        "；".join(mismatch + notok) if (mismatch or notok) else "%d 份 sha256/bytes 一致且自检全过" % len(htmls))


# ---------- 5 术语一致 ----------
def check_terms():
    import make_manifest
    bad, total_t, total_g = [], 0, 0
    for h in sorted(list(SITE.glob("AI晨报-*.html")) + list(SITE.glob("special/*.html"))):
        d = make_manifest.build(h, "special" if "特刊" in h.name else "daily")
        total_t += d["terms"]
        total_g += d["glossary"]
        if d["missing_terms"]:
            bad.append("%s：%s" % (h.name, "、".join(d["missing_terms"])))
        if d["checks"].get("glossary_count_matches") is False:
            bad.append("%s：标题词数与词条数不符" % h.name)
    add(5, "术语：注解能查到词条", FAIL if bad else PASS,
        "；".join(bad) if bad else "累计 %d 处注解 / %d 条词条，无遗漏" % (total_t, total_g))


# ---------- 6 JSON / JS 可解析 ----------
def check_json():
    bad = []
    for j in list(SITE.glob("*.json")) + list(SITE.glob("special/*.json")):
        try:
            json.loads(j.read_text(encoding="utf-8"))
        except Exception as exc:
            bad.append("%s %s" % (j.name, exc))
    try:
        load_issues()
    except Exception as exc:
        bad.append("issues.js %s" % exc)
    for m in SITE.glob("*.webmanifest"):
        try:
            json.loads(m.read_text(encoding="utf-8"))
        except Exception as exc:
            bad.append("%s %s" % (m.name, exc))
    n = len(list(SITE.glob("*.json"))) + len(list(SITE.glob("special/*.json")))
    add(6, "JSON 全部可解析", FAIL if bad else PASS,
        "；".join(bad) if bad else "issues.js + %d 份 json / webmanifest" % n)


# ---------- 7 期序与编号 ----------
def check_sequence(data):
    """一期一条记录、倒序排列、特刊编号接在当天正刊后面。

    2026-11-06 踩过：特刊只挂在 specials 里，往期回顾看不到；期号又写成 003，
    和正刊同号。这两条现在都在这里卡住。
    """
    issues = data.get("issues", [])
    bad = []
    keys = [(it.get("date", ""), it.get("issue") or "") for it in issues]
    if keys != sorted(keys, reverse=True):
        bad.append("排序不是「日期+期号」倒序：%s" % "、".join("%s/%s" % k for k in keys))

    seen = {}
    for it in issues:
        no = it.get("issue") or ""
        if not no:
            bad.append("%s 解析不到期号" % it.get("file", "?"))
            continue
        if no in seen:
            bad.append("期号重复：第 %s 期" % no)
        seen[no] = it

    mains = {it["date"]: it for it in issues if not it.get("isSpecial")}
    for it in issues:
        if not it.get("isSpecial"):
            continue
        m = mains.get(it["date"])
        if not m:
            bad.append("%s 有特刊但当天没有正刊" % it["date"])
            continue
        want = (m.get("issue") or "") + "-2"
        if it.get("issue") != want:
            bad.append("%s 特刊编号是 %s，按当天序列应为 %s"
                       % (it["date"], it.get("issue") or "空", want))

    nos = sorted(int(it["issue"]) for it in issues
                 if not it.get("isSpecial") and str(it.get("issue", "")).isdigit())
    if nos and nos != list(range(1, len(nos) + 1)):
        bad.append("正刊期号不连续：%s" % "、".join("%03d" % n for n in nos))

    # specials 是 issues 里特刊的副本（给横幅用），两处必须同一批，不能各自漂
    a = sorted((it.get("file"), it.get("size")) for it in issues if it.get("isSpecial"))
    b = sorted((it.get("file"), it.get("size")) for it in data.get("specials", []))
    if a != b:
        bad.append("specials 与 issues 里的特刊不是同一批（%d vs %d）" % (len(b), len(a)))

    add(7, "期序与编号", FAIL if bad else PASS,
        "；".join(bad) if bad else
        "%d 期倒序排列，正刊 001–%03d 连续，特刊 %s 接在当天正刊后"
        % (len(issues), nos[-1] if nos else 0,
           "、".join(it["issue"] for it in issues if it.get("isSpecial")) or "无"))


# ---------- 8 日期闸门 ----------
def check_dategate(data):
    """报纸日期必须是出报当天：不许提前把明天的期号发出去。

    根因事故：11-06 傍晚拼了 2026-11-07 的 004 并发布，桌面端打开是「明天的报」，
    内容却全是今天的。更麻烦的是 status.json 会被写成 11-07，第二天启动检查
    看到「已完成」直接静默，当天的报就没人做了。
    """
    today = os.environ.get("AI_DAILY_TODAY", "").strip() or datetime.date.today().isoformat()
    bad = []
    rx = re.compile(r"AI晨报-(\d{4}-\d{2}-\d{2})")
    for p in sorted(list(ROOT.glob("AI晨报-*.html")) + list(SITE.glob("AI晨报-*.html"))):
        m = rx.match(p.name)
        if m and m.group(1) > today:
            bad.append("%s 晚于今天" % rel(p))
    for it in data.get("issues", []):
        if it.get("date", "") > today:
            bad.append("索引收录了未来期 %s" % it.get("date"))
    try:
        st = json.loads((ROOT / "status.json").read_text(encoding="utf-8"))
        if (st.get("date") or "") > today:
            bad.append("状态机记着未来期 %s（次日会被误判为已出报）" % st.get("date"))
    except Exception:
        pass
    add(8, "日期闸门（不许提前）", FAIL if bad else PASS,
        "；".join(bad) if bad else
        "根目录 / 站点 / 索引 / 状态机都不晚于今天（%s）" % today)


# ---------- 9 入口页有特刊入口 ----------
def check_entry():
    p = SITE / "index.html"
    s = p.read_text(encoding="utf-8")
    need = {
        "issues 统一序列": "DATA.issues",
        "特刊标记": "isSpecial",
        "首屏特刊条": 'id="spbar"',
        "特刊深链": "u.searchParams.set('s'",
    }
    bad = [k for k, v in need.items() if v not in s]
    if 'id="shelfSpecial"' in s:
        bad.append("旧的 shelfSpecial 独立区还在（特刊应并入同一个列表）")
    add(9, "入口页能进特刊", FAIL if bad else PASS,
        "缺 " + "、".join(bad) if bad else "横幅 / 同列排序 / 深链 ?s=1 都在")


# ---------- 10 状态机 ----------
def check_status(date, pre):
    try:
        d = json.loads((ROOT / "status.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return add(10, "状态机五阶段", SKIP, "读不到 status.json（%s）" % exc)
    steps = d.get("steps") or {}
    order = ["parts", "assemble", "index", "deploy", "verify"]
    if pre:
        order = order[:3]
    bad = [k for k in order if not str(steps.get(k, "")).startswith("OK")]
    detail = " / ".join("%s=%s" % (k, str(steps.get(k, "-")).split(":")[0]) for k in order)
    add(10, "状态机%s" % ("（发布前口径）" if pre else "五阶段"),
        FAIL if bad else PASS,
        (detail + "；缺 " + "、".join(bad)) if bad else detail)


# ---------- 11 全文版数一致 ----------
def check_pages():
    """成品全文每一处「共 N 版」都必须等于真实页数。

    2026-11-06 事故：特刊从 15 版扩到 16 版，前 14 个页眉仍是「共 15 版」，
    标题/报头/报尾却是 16 —— A4b 只查这三处，于是拼版通过、凭证 ok、自检全绿，
    读者在第 15 版看到「共 15 版」，翻过去还有第 16 版。这里不信任任何单点，
    直接扫全文，按实际 section 数量对账。
    """
    # 源与站点副本都扫：副本是另一份真相，不能默认它跟源一致。
    files = sorted(ROOT.glob("AI晨报-*.html")) + \
        sorted(SITE.glob("AI晨报-*.html")) + \
        sorted(SITE.glob("special/*.html"))
    bad = []
    for p in files:
        html = p.read_text(encoding="utf-8")
        n = len(re.findall(r'<section[^>]*\bid="p\d\d"', html))
        if not n:
            bad.append("%s 解析不到版面 section" % p.name)
            continue
        claims = [int(x) for x in re.findall(r"共\s*(\d+)\s*版", html)]
        wrong = sorted({c for c in claims if c != n})
        if not claims:
            bad.append("%s 全文找不到「共 N 版」" % p.name)
        elif wrong:
            cnt = sum(1 for c in claims if c != n)
            bad.append("%s：实际 %d 版，%d 处写成「共 %s 版」"
                       % (p.name, n, cnt, "/".join(map(str, wrong))))
    add(11, "全文版数一致", FAIL if bad else PASS,
        "；".join(bad) if bad else "%d 份成品，全文版数与实际页数一致" % len(files))


# ---------- 12 内容声明一致 ----------
def check_disclaimer():
    """内容声明只许有一份事实源：site/config.js 的 disclaimer。

    各期成品、站点副本、模板、样张、parts 片段、README 都由
    apply_disclaimer.py / build_index.py 派生；分享面板运行时读同一常量，
    不许再硬编码一句。这里逐份对账，防止「三处手写、三个月后必漂」。
    """
    import disclaimer as D
    bad = []
    try:
        t = D.text(SITE / "config.js")
    except Exception as exc:
        return add(12, "内容声明一致", FAIL,
                   "config.js 解析不到 disclaimer：%s" % exc)

    line = D.line(t)
    targets = D.html_targets(ROOT) + D.site_targets(SITE)
    for p in targets:
        if not p.exists():
            bad.append("%s 缺文件" % rel(p))
            continue
        s = p.read_text(encoding="utf-8", errors="replace")
        n_line = len(re.findall(r'<p class="disclaimer">.*?</p>', s, flags=re.S))
        if s.count(line) != 1 or n_line != 1:
            bad.append("%s 声明行不是恰好 1 处（找到 %d 个声明块 / %d 个正确块）"
                       % (p.name, n_line, s.count(line)))
        if s.count(t) != 1:
            bad.append("%s 声明原文出现 %d 次" % (p.name, s.count(t)))

    try:
        r = (ROOT.parent / "README.md").read_text(encoding="utf-8")
        if r.count(D.START) != 1 or r.count(D.END) != 1:
            bad.append("README 的声明标记不成对")
        elif D.START + t + D.END not in r:
            bad.append("README 免责与 config.js 不一致")
        if r.count(t) != 1:
            bad.append("README 声明原文出现 %d 次" % r.count(t))
    except Exception as exc:
        bad.append("README 读不到：%s" % exc)

    try:
        idx = (SITE / "index.html").read_text(encoding="utf-8", errors="replace")
        if 'id="shareDisclaimer"' not in idx:
            bad.append("分享面板缺声明节点")
        if "CFG.disclaimer" not in idx:
            bad.append("分享面板没有读 config.js 的 disclaimer")
        if t in idx:
            bad.append("分享面板把声明又硬编码了一遍")
    except Exception as exc:
        bad.append("入口页读不到：%s" % exc)

    add(12, "内容声明一致", FAIL if bad else PASS,
        "；".join(bad) if bad else
        "%d 份静态落点 + README + 分享面板，均以 config.js 为准" % len(targets))


# ---------- 14 规则与清单对账 ----------
def check_rules(doc=None, products=None):
    """规则文档 / 产物清单里写的数字，必须等于代码与磁盘里的事实。

    为什么值当一项：文档落后于代码就开始骗人——写着 A1–A13 而代码已经 A16，
    下一个按文档验收的人会漏掉三条断言；清单列着已删除的脚本，新接手的人会去找。
    机械项交给 doc_sync.py --fix 自动改，这里卡的是「改完还对不上」的部分。
    """
    try:
        import doc_sync
    except Exception as exc:
        return add(14, "规则与清单对账", SKIP, "导入 doc_sync 失败：%s" % exc)
    issues, meta = doc_sync.check(doc, products)
    if not meta:
        return add(14, "规则与清单对账", SKIP, "找不到规则文档（可能只检出 ai-daily）")
    hard = [i for i in issues if i["sev"] == doc_sync.FAIL]
    soft = [i for i in issues if i["sev"] == doc_sync.WARN]
    if hard:
        return add(14, "规则与清单对账", FAIL,
                   "；".join(i["msg"] for i in hard[:3])
                   + "  ← 跑 python tools/doc_sync.py --fix")
    detail = "规则 %d 条 · 断言 %d 个/%d 个触发点 · 脚本 %d 个 · 清单路径全在" % (
        meta["rules"], meta["assertions"], meta["triggers"], meta["scripts"])
    if soft:
        detail += "；提示 " + "；".join(i["msg"] for i in soft[:3])
    add(14, "规则与清单对账", PASS, detail)


# ---------- 15 CI 工作流合法 ----------
REPO = HERE.parent.parent                # 仓库根
CI_FILE = REPO / ".github" / "workflows" / "ci.yml"


def check_ci(ci_path=None, readme_path=None, dep_path=None):
    """CI 文件必须是能解析的 YAML，且 README 宣传的矩阵与文件一致。

    为什么值当一项：这份文件曾经前三行是 markdown 引用符（`> `），
    pyyaml 直接 ScannerError，Actions 根本不加载，而 README 照旧宣传
    「Ubuntu 与 Windows × Python 3.10/3.13」——一个从来没跑过的检查
    被判成绿的，比没有 CI 更糟。纯标准库做结构检查，装了 pyyaml 再真解析一次。

    两个路径参数只给反向验证用：副本在临时目录里改坏，真实文件不动。
    """
    ci = Path(ci_path) if ci_path else CI_FILE
    if not ci.exists():
        return add(15, "CI 与自动化配置合法", SKIP, "找不到 .github/workflows/ci.yml（可能只检出 ai-daily）")
    text = ci.read_text(encoding="utf-8")
    bad = []

    # 1) markdown 混进 YAML：引用符 / 代码围栏 / 首行不是键
    if re.search(r"^>\s", text, re.M):
        bad.append("含 markdown 引用符行（^> ）")
    if "```" in text:
        bad.append("含 markdown 代码围栏（```）")
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not re.match(r"^(name|#)", first):
        bad.append("首行不是 name: 或注释，实际是「%s」" % first[:24])

    # 2) 结构必需项
    for key in ("jobs:", "runs-on:", "steps:"):
        if key not in text:
            bad.append("缺 %s" % key)

    # 3) 真解析（可选依赖，缺了只当没查）
    try:
        import yaml
    except Exception:
        parsed = None
    else:
        try:
            parsed = yaml.safe_load(text)
        except Exception as exc:
            bad.append("YAML 解析失败：%s" % str(exc).splitlines()[0][:70])
            parsed = None
        else:
            if not isinstance(parsed, dict):
                bad.append("解析结果不是映射")
            else:
                # pyyaml 按 YAML 1.1 会把裸 on: 读成 True，两种键名都接受
                if "jobs" not in parsed:
                    bad.append("解析后没有 jobs")

    # 4) README 宣传的矩阵必须真的在文件里
    readme = Path(readme_path) if readme_path else (REPO / "README.md")
    claim = ""
    if readme.exists():
        rt = readme.read_text(encoding="utf-8")
        if "ci.yml" in rt:
            for token in ("Ubuntu", "Windows", "3.10", "3.13"):
                if token in rt and token.lower() not in text.lower():
                    bad.append("README 写了 %s，CI 文件里没有" % token)
            claim = "；README 宣传的矩阵已核对"

    # 5) 依赖更新：只有 Actions 会随时间腐烂（主链路零第三方依赖）
    dep = Path(dep_path) if dep_path else (REPO / ".github" / "dependabot.yml")
    if not dep.exists():
        bad.append("缺 .github/dependabot.yml（action 大版本没人盯，某天会莫名变红）")
    else:
        dt = dep.read_text(encoding="utf-8")
        if "github-actions" not in dt:
            bad.append("dependabot.yml 没盯 github-actions")
        try:
            import yaml
        except Exception:
            pass
        else:
            try:
                yaml.safe_load(dt)
            except Exception as exc:
                bad.append("dependabot.yml 解析失败：%s" % str(exc).splitlines()[0][:60])

    # 6) 其余 workflow 也必须是能解析的 YAML。一个坏文件不会报错，它只是
    #    「在 Actions 页面上从没出现过」——比跑红更难发现，所以在这里拦。
    #    dependabot.yml 不是 workflow（没有 on/jobs），反向验证会把它和 ci.yml
    #    放同一目录，所以按文件名排除，而不是靠结构判断。
    others = sorted(p for p in ci.parent.glob("*.yml")
                    if p.resolve() != ci.resolve()
                    and p.name.lower() not in ("dependabot.yml", "dependabot.yaml"))
    for other in others:
        otext = other.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"^on:", otext, re.M):
            bad.append("%s 缺 on:" % other.name)
        if "jobs:" not in otext:
            bad.append("%s 缺 jobs:" % other.name)
        try:
            import yaml as _yaml
        except Exception:
            break
        try:
            if not isinstance(_yaml.safe_load(otext), dict):
                bad.append("%s 解析结果不是映射" % other.name)
        except Exception as exc:
            bad.append("%s 解析失败：%s" % (other.name, str(exc).splitlines()[0][:50]))

    if bad:
        return add(15, "CI 与自动化配置合法", FAIL, "；".join(bad[:4]))
    mode = "pyyaml 已解析" if parsed else "仅结构检查（无 pyyaml）"
    add(15, "CI 与自动化配置合法", PASS,
        "%d 字节，%s，含 jobs/runs-on/steps%s；%d 个 workflow 均可解析；dependabot 盯 github-actions"
        % (len(text.encode("utf-8")), mode, claim, len(others) + 1))


# ---------- 16 导出覆盖索引 ----------
def check_export_coverage(tracked=None, picked=None):
    """已入库 = 将公开：索引里的每个文件都必须能进导出集。

    为什么值当一项：导出是白名单，**新增目录默认不进**。所以「本机看着一切正常、
    公开仓库静默少文件」是默认结局，不是意外。反过来也说明本仓库现在没有
    「私有但要入库」的东西——真有的话，先把它移出索引，别在这里开豁免。

    tracked / picked 两个参数只给反向验证用，正常调用都从现场取。
    """
    if tracked is None:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=str(REPO), capture_output=True)
        if out.returncode != 0:
            return add(16, "导出覆盖索引", SKIP, "不在 git 仓库里，无法对账")
        tracked = [f for f in out.stdout.decode("utf-8", "replace").split("\0") if f]

    if picked is None:
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import export_public as E
        except Exception as exc:
            return add(16, "导出覆盖索引", SKIP, "导入 export_public 失败：%s" % exc)
        picked = E.collect()[0]
    pset = set(picked)

    missing = sorted(t for t in tracked if t not in pset)
    if missing:
        return add(16, "导出覆盖索引", FAIL,
                   "%d 个已入库文件不会进公开仓库：%s（补进 export_public 的白名单，"
                   "或把它们移出索引）" % (len(missing), "、".join(missing[:4])))
    add(16, "导出覆盖索引", PASS,
        "%d 个已入库文件全部在导出集内（导出比索引多 %d 个，是还没提交的新文件）"
        % (len(tracked), max(0, len(pset) - len(tracked))))


# ---------- 13 线上 ----------
def check_apk(data, apk_path=None, site=None):
    """APK 里的离线快照必须是当期，且包内索引与包内文件严格对应。

    纯自动更新最容易漏的一环：正文改了、报纸发了、APK 没重打。线上完全正常，
    只有装过 App 的人离线打开会看到旧报——没有任何人会主动发现这件事。
    """
    site = Path(site or SITE)
    apk = Path(apk_path) if apk_path else site / "ai-daily.apk"
    if not apk.exists():
        return add(17, "APK 快照与当期一致", SKIP,
                   "本机没有 site/ai-daily.apk（公开树 / 新克隆不带二进制）")

    import zipfile
    try:
        z = zipfile.ZipFile(apk)
    except zipfile.BadZipFile as exc:
        return add(17, "APK 快照与当期一致", FAIL, "APK 打不开：%s" % exc)

    with z:
        names = set(z.namelist())
        if "assets/site/issues.js" not in names:
            return add(17, "APK 快照与当期一致", FAIL,
                       "包里没有 assets/site/issues.js：离线入口必然白屏")
        raw = z.read("assets/site/issues.js").decode("utf-8")
        packed = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])

        live = next((x for x in data.get("issues", []) if not x.get("isSpecial")), None)
        cur = next((x for x in packed.get("issues", []) if not x.get("isSpecial")), None)
        if not live:
            return add(17, "APK 快照与当期一致", FAIL, "站点索引里没有正刊")
        if not cur:
            return add(17, "APK 快照与当期一致", FAIL, "包内索引里没有正刊")
        if cur.get("issue") != live.get("issue"):
            return add(17, "APK 快照与当期一致", FAIL,
                       "包里是第 %s 期，站点已经是第 %s 期：跑 "
                       "python tools/build_apk.py --auto" % (cur.get("issue"), live.get("issue")))

        rel = "assets/site/issue-%s.html" % live["date"]
        src = site / ("AI晨报-%s.html" % live["date"])
        if rel not in names:
            return add(17, "APK 快照与当期一致", FAIL, "包里缺当期的 %s" % rel)
        if not src.exists():
            return add(17, "APK 快照与当期一致", FAIL,
                       "站点缺当期源文件 %s" % src.name)
        if hashlib.sha256(z.read(rel)).digest() != hashlib.sha256(src.read_bytes()).digest():
            return add(17, "APK 快照与当期一致", FAIL,
                       "包里当期正文与站点不是同一份（改了报没重打 APK）")

        listed = {x.get("file") for x in
                  list(packed.get("issues") or []) + list(packed.get("specials") or [])}
        dangling = sorted(f for f in listed
                          if f and ("assets/site/" + f) not in names)
        if dangling:
            return add(17, "APK 快照与当期一致", FAIL,
                       "包内索引列了包里没有的文件（离线点开 404）：%s"
                       % "、".join(dangling[:3]))
        n_asset = sum(1 for n in names if n.startswith("assets/site/"))

    try:
        st = json.loads((ROOT / ".local" / "apk-build.json").read_text(encoding="utf-8"))
        ver = "versionCode %s" % st.get("code")
    except Exception:
        ver = "无打包记录"
    add(17, "APK 快照与当期一致", PASS,
        "第 %s 期 · 离线 %d 期 / %d 个文件 · %s · %.2f MB"
        % (live["issue"], len(packed.get("issues") or []), n_asset,
           ver, apk.stat().st_size / 1048576))


def update_manifest_name():
    """清单文件名不在两处写字面量：能从打包脚本取就取。"""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import build_apk as B
        return B.MANIFEST_NAME
    except Exception:
        return "version.json"


def check_update_manifest(site=None, src=None):
    """第 18 项：App 内「有新版本」靠的清单必须与包同源。

    两种坏法都不响：清单没跟着包走 → 所有人永远收不到提示；清单超前于包 →
    提示了却下到同一个包，用户点过一次就再也不信这个弹窗了。还有第三种：
    MainActivity 里的检查逻辑被删掉，清单再新也没人读。
    """
    site = Path(site or SITE)
    mp = site / update_manifest_name()
    if not mp.exists():
        return add(18, "更新清单与包一致", FAIL,
                   "缺 %s：装了 App 的人永远收不到「有新版本」"
                   "（跑 python tools/build_apk.py --auto）" % mp.name)
    try:
        d = json.loads(mp.read_text(encoding="utf-8"))
        code = int(d["code"])
        name = str(d["name"])
        sha = str(d["sha256"])
        size = int(d["bytes"])
    except Exception as exc:
        return add(18, "更新清单与包一致", FAIL, "清单读不出来：%s" % exc)
    if d.get("schema") != 1:
        return add(18, "更新清单与包一致", FAIL,
                   "schema 是 %r，App 只认 1" % (d.get("schema"),))
    if code <= 0:
        return add(18, "更新清单与包一致", FAIL, "versionCode 不是正数：%s" % code)
    if not str(d.get("file") or "").endswith(".apk"):
        return add(18, "更新清单与包一致", FAIL, "file 字段没指向安装包")

    # 源码里没有检查逻辑，清单再准也是摆设
    src = Path(src) if src else (
        ROOT / "apk" / "src" / "cn" / "aidaily" / "app" / "MainActivity.java")
    try:
        jsrc = src.read_text(encoding="utf-8")
    except OSError:
        jsrc = ""
    if "version.json" not in jsrc or "selfCode" not in jsrc:
        return add(18, "更新清单与包一致", FAIL,
                   "MainActivity.java 里的更新检查不见了：清单还在，但没人读它")

    apk = site / "ai-daily.apk"
    if not apk.exists():
        return add(18, "更新清单与包一致", SKIP,
                   "清单格式 OK（%s / versionCode %s），本机没有 APK 可对账" % (name, code))

    raw = apk.read_bytes()
    if len(raw) != size:
        return add(18, "更新清单与包一致", FAIL,
                   "清单写 %d 字节，实际包 %d 字节：包换了，清单没换" % (size, len(raw)))
    if hashlib.sha256(raw).hexdigest() != sha:
        return add(18, "更新清单与包一致", FAIL,
                   "清单 sha256 与包不符：提示会指向一个和清单对不上的包")

    try:
        st = json.loads((ROOT / ".local" / "apk-build.json").read_text(encoding="utf-8"))
    except Exception:
        st = {}
    if st and (st.get("code") != code or st.get("name") != name):
        return add(18, "更新清单与包一致", FAIL,
                   "清单写 %s/%s，打包记录是 %s/%s"
                   % (name, code, st.get("name"), st.get("code")))

    add(18, "更新清单与包一致", PASS,
        "%s / versionCode %d · %d 字节 · 与包内 sha256 一致" % (name, code, size))


def check_public(docs=None):
    """第 19 项：公开面（GitHub Pages 的 /docs）完整、与生成一致、且不含入口地址。

    这一项存在的理由和别的项不一样：公开面是**唯一一处主动把内容放出访问码之外**
    的地方。一旦生成器把 siteUrl 或 sharecode 写进页面，泄露是不可撤销的（Pages 有
    CDN 缓存、可能已被抓取）。所以「无访问码」必须是硬断言，而不是靠人记得检查。

    docs 可指向临时副本——反向验证要造「公开面里混进访问码」的反例。
    """
    docs = Path(docs) if docs else (ROOT.parent / "docs")
    idx = docs / "index.html"
    if not idx.is_file():
        return add(19, "公开面完整且无入口地址", FAIL,
                   "docs/index.html 不存在：公开面未生成（python tools/build_public.py）")

    script = HERE / "build_public.py"
    if not script.is_file():
        return add(19, "公开面完整且无入口地址", FAIL,
                   "build_public.py 不见了，公开面没有人能重建")

    try:
        p = subprocess.run([sys.executable, str(script), "--check", "--out", str(docs)],
                           capture_output=True, timeout=300)
    except Exception as exc:
        return add(19, "公开面完整且无入口地址", FAIL, "公开面对账跑不起来：%s" % exc)
    if p.returncode != 0:
        raw = (p.stdout or b"").decode("utf-8", "replace") + (p.stderr or b"").decode("utf-8", "replace")
        first = next((l.strip() for l in raw.splitlines() if l.strip()), "与生成结果不一致")
        return add(19, "公开面完整且无入口地址", FAIL,
                   "公开面过期或有多余页：%s（重跑 build_index.py）" % first)

    # 安全断言：入口地址里的 sharecode 不得出现在任何公开面文件里
    secret = ""
    m = re.search(r"sharecode=([A-Za-z0-9_-]{4,})", SITE_URL or "")
    if m:
        secret = m.group(1)
    leaked = []
    if secret:
        for f in docs.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in (".html", ".xml", ".txt", ".css", ".json", ".js"):
                continue
            try:
                if secret in f.read_text(encoding="utf-8", errors="replace"):
                    leaked.append(str(f.relative_to(docs)).replace("\\", "/"))
            except OSError:
                continue
    if leaked:
        return add(19, "公开面完整且无入口地址", FAIL,
                   "访问码出现在公开面：%s——立刻删除该文件并重新发布" % "、".join(leaked[:3]))

    cards = [f for f in (docs / "cards").glob("*.html") if re.match(r"\d{4}-\d{2}-\d{2}-F\d+", f.name)]
    sm = docs / "sitemap.xml"
    locs = len(re.findall(r"<loc>", sm.read_text(encoding="utf-8", errors="replace"))) if sm.is_file() else 0
    robots_txt = (docs / "robots.txt").read_text(encoding="utf-8", errors="replace") if (docs / "robots.txt").is_file() else ""
    if "Sitemap:" not in robots_txt:
        return add(19, "公开面完整且无入口地址", FAIL,
                   "robots.txt 没指向 sitemap：检索器找不到卡片页")
    if locs < len(cards) + 2:
        return add(19, "公开面完整且无入口地址", FAIL,
                   "sitemap 只有 %d 条，少于卡片数 %d：有页面没进索引" % (locs, len(cards)))

    # 信源外链：数据里写了几条 url，期页信源表就该渲染出几处外链。
    # 少一条不是「样式问题」——读者会以为那条信源本来就没有出处，而这正是本报的卖点。
    want, bad_url = 0, []
    for src_json in sorted((ROOT / "parts").glob("*/00-sources.json")):
        try:
            src_data = json.loads(src_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for s in (src_data.get("sources") or []):
            u = (s.get("url") or "").strip()
            if not u:
                continue
            if not u.startswith(("http://", "https://")) or any(c in u for c in ' <>"\'`'):
                bad_url.append("%s/%s" % (src_json.parent.name, s.get("id")))
            else:
                want += 1
    if bad_url:
        return add(19, "公开面完整且无入口地址", FAIL,
                   "信源链接格式不合法（必须 http(s) 且不含空白引号）：%s" % "、".join(bad_url[:3]))
    got = 0
    for f in (docs / "issues").glob("*.html"):
        try:
            got += f.read_text(encoding="utf-8", errors="replace").count('rel="noopener noreferrer"')
        except OSError:
            continue
    if got != want:
        return add(19, "公开面完整且无入口地址", FAIL,
                   "期页信源外链 %d 条，数据里有 %d 条：渲染漏了（重跑 build_public.py）"
                   % (got, want))

    add(19, "公开面完整且无入口地址", PASS,
        "%d 张事实卡 · sitemap %d 条 · 信源外链 %d 条 · 与生成结果一致 · 无访问码"
        % (len(cards), locs, got))


def check_online(data):
    """线上检查要带 sharecode 换来的 cookie，中文文件名要 percent-encode。"""
    if not BASE:
        return add(13, "线上可访问", FAIL,
                   "未配置线上入口：site/config.js 的 siteUrl 是占位或为空"
                   "（临时指定可设 AI_DAILY_SITE_URL）")
    import http.cookiejar
    import urllib.parse

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    ua = {"User-Agent": "ai-daily-selfcheck"}

    bad, ok = [], 0
    # 同一天两期时「最新一期」就是特刊，按 rel 去重，别把同一份文件报两遍
    ordered = [("入口", "")]
    if data.get("issues"):
        latest = data["issues"][0]
        ordered.append(("最新一期", latest["file"]))
        ordered.append(("最新一期凭证", latest["file"].rsplit(".", 1)[0] + ".json"))
        main = next((it for it in data["issues"] if not it.get("isSpecial")), None)
        if main and main["file"] != latest["file"]:
            ordered.append(("最新正刊", main["file"]))
    for sp in data.get("specials", [])[:1]:
        ordered.append(("特刊", sp["file"]))
        if sp.get("manifest"):
            ordered.append(("特刊凭证", sp["manifest"]))
    targets, seen = [], set()
    for name, rel in ordered:
        if rel in seen:
            continue
        seen.add(rel)
        targets.append((name, rel))
    # 本地有包就一起验：这是「重打」链路上唯一的静默失败点——包换了但没发布，
    # 线上报纸全对、只有下载安装的人拿到旧包。
    if (SITE / "ai-daily.apk").exists():
        targets.append(("安卓包", "ai-daily.apk"))
    # 清单没发布 = 提示永远不出现，而本机全绿。和「包换了没发布」同一类静默失败。
    mp = SITE / update_manifest_name()
    if mp.exists():
        targets.append(("更新清单", mp.name))

    try:
        opener.open(urllib.request.Request(BASE, headers=ua), timeout=10).read()
    except Exception as exc:
        return add(13, "线上可访问", FAIL, "入口打不开：%s" % exc)

    for name, rel in targets:
        url = HOST + urllib.parse.quote(rel) if rel else BASE
        try:
            with opener.open(urllib.request.Request(url, headers=ua),
                             timeout=60 if rel.endswith(".apk") else 10) as r:
                body = r.read()
                if r.status != 200:
                    bad.append("%s %d" % (name, r.status))
                    continue
                ok += 1
                # 本地改了没发布，也会在这里现形：只验 200 是另一种假绿
                local = SITE / rel if rel else None
                if local and local.exists():
                    if hashlib.sha256(body).hexdigest() != hashlib.sha256(
                            local.read_bytes()).hexdigest():
                        bad.append("%s 线上与本地不一致（改了没发布？）" % name)
        except Exception as exc:
            bad.append("%s %s" % (name, exc))
    add(13, "线上可访问", FAIL if bad else PASS,
        "；".join(bad) if bad else
        "%d/%d 全部 200；成品与本地 sha256 逐一比对通过" % (ok, len(targets)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--online", action="store_true")
    ap.add_argument("--pre", action="store_true", help="发布前口径：只卡前三阶段")
    ap.add_argument("--list", action="store_true", help="只列检查项，供文档引用")
    a = ap.parse_args()

    if a.list:
        for no, name, hint in ITEMS:
            print("%2d  %-22s | %s" % (no, name, hint))
        return 0

    if a.date:
        date = a.date
    else:
        try:
            st = json.loads((ROOT / "status.json").read_text(encoding="utf-8"))
            date = st.get("date") or datetime.date.today().isoformat()
        except Exception:
            date = datetime.date.today().isoformat()

    data = load_issues()
    issue = next((it["issue"] for it in data.get("issues", [])
                  if it.get("date") == date and not it.get("isSpecial")), "") or "?"

    check_assemble(date, issue)
    check_index(data)
    check_manifest()
    check_terms()
    check_json()
    check_sequence(data)
    check_dategate(data)
    check_entry()
    check_status(date, a.pre)
    check_pages()
    check_disclaimer()
    if a.online:
        check_online(data)
    check_rules()
    check_ci()
    check_export_coverage()
    check_apk(data)
    check_update_manifest()
    check_public()

    print("AI 晨报自检 · %s 第 %s 期 · %s" % (date, issue,
          datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    print("-" * 66)
    for r in rows:
        print("%d  %-18s %-4s  %s" % (r["no"], r["name"], r["status"], r["detail"]))
    print("-" * 66)
    n_fail = sum(1 for r in rows if r["status"] == FAIL)
    n_skip = sum(1 for r in rows if r["status"] == SKIP)
    n_pass = len(rows) - n_fail - n_skip
    print("结论：%d 项，%d PASS / %d FAIL / %d SKIP%s"
          % (len(rows), n_pass, n_fail, n_skip,
             "" if n_fail == 0 else "  ← 有 FAIL，不许说完成"))
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
