#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""反向验证 / 变异测试：故意把检查对象弄坏，确认自检真的会红。

用法：
    python tools/mutation_test.py

为什么存在：教材附录 F.5 说「没做过反向验证的自检项只能算写过」。
2026-11-06 当天确实做了五次（移走 json、塞回错版数、假装昨天、临时目录放未来期、
改了不发布），但全是一次性手工命令，没留下可复跑的入口——教案教了，生产项目却没固化。
这个脚本把它们收成一条命令，以后每加一条自检项，就在这里补一个变异。

两条曾经 SKIP 的也补齐了：
  - 术语缺词表：复制一份真实特刊（只有它有术语注解），把 gloss 块里的词条整批改错字；
  - 线上 sha 漂移：起一个 127.0.0.1 随机端口的本地假站点，把本地副本做等长替换，
    模拟「改了没发布」。不碰真实域名，也不制造线上事故。

每个带 fixture 的反例都先跑一次**正向对照**：底板必须先全绿。否则反例变红可能只是
server 没起来 / HTML 解析不了，那种「假红」比假绿更会骗人。

只读：所有反例都构造在临时目录或内存数据里，不改动 ai-daily/ 的任何成品。
退出码 0 = 每个变异都被对应检查项拦住；1 = 存在「假绿」检查项。
"""
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import disclaimer as D
import export_public as EXPORT
import make_manifest
import selfcheck as sc

REAL_ROOT, REAL_SITE = sc.ROOT, sc.SITE
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results = []


def expect_red(label, no, mutate, must_say=""):
    """跑一个变异，要求第 no 项必须产出一行 FAIL。"""
    sc.rows.clear()
    today = os.environ.get("AI_DAILY_TODAY")
    saved = (sc.ROOT, sc.SITE, sc.BASE, sc.HOST)
    try:
        mutate()
    except Exception as exc:                      # 变异脚本自己炸了也要报，不能静默
        results.append((FAIL, label, "变异构造异常：%s" % exc))
        print("[%s] %-32s 构造异常 %s" % (FAIL, label, exc))
        return
    finally:
        sc.ROOT, sc.SITE, sc.BASE, sc.HOST = saved
        if today is None:
            os.environ.pop("AI_DAILY_TODAY", None)
        else:
            os.environ["AI_DAILY_TODAY"] = today
    row = next((r for r in sc.rows if r["no"] == no), None)
    ok = bool(row) and row["status"] == FAIL and (not must_say or must_say in row["detail"])
    why = "" if ok else ("没变红 / 红错了地方：%s" % ((row or {}).get("detail") or "无此行"))
    results.append((PASS if ok else FAIL, label, why))
    print("[%s] %-32s → 第 %2d 项 %s" %
          (PASS if ok else FAIL, label, no, "按预期变红" if ok else why))


def expect_cmd_red(label, argv, keyword, cwd):
    """给生成器故意喂坏素材，要求它非 0 退出且报出指定断言。"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    out = (r.stdout or "") + (r.stderr or "")
    ok = r.returncode != 0 and keyword in out
    results.append((PASS if ok else FAIL, label, "" if ok else "退出码 %d" % r.returncode))
    print("[%s] %-32s → 生成器 %s" %
          (PASS if ok else FAIL, label, "拦住了" if ok else "没拦住（退出码 %d）" % r.returncode))


def site_fixture(tmp):
    """临时站点：复制索引与全部成品 html，够 check_index / check_manifest 用。"""
    site = tmp / "site"
    site.mkdir()
    shutil.copy2(REAL_SITE / "issues.js", site / "issues.js")
    for p in list(REAL_SITE.glob("AI晨报-*.html")) + list(REAL_SITE.glob("special/*.html")):
        dst = site / p.relative_to(REAL_SITE)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
    return site


def expect_contrast(ctrl_label, mut_label, no, check, mutate, must_say=""):
    """反例必须带正向对照：fixture 先全绿，弄坏后该项必须 FAIL。

    没有对照，「变红」可能只是 server 没起来或 HTML 解析不了——那是假红，
    比假绿更会骗人，因为它会让人误以为检查器在工作。
    """
    def row():
        return next((r for r in sc.rows if r["no"] == no), None)

    def emit(label, ok, why, tail):
        results.append((PASS if ok else FAIL, label, why))
        print("[%s] %-32s → 第 %2d 项 %s" % (PASS if ok else FAIL, label, no, tail))

    sc.rows.clear()
    try:
        check()
    except Exception as exc:
        ok, why = False, "对照检查抛异常：%s" % exc
    else:
        r0 = row()
        ok = bool(r0) and r0["status"] == PASS
        why = "" if ok else "底板本身不健康：%s" % ((r0 or {}).get("detail") or "无此行")
    emit(ctrl_label, ok, why, "对照全绿" if ok else why)
    if not ok:
        results.append((FAIL, mut_label, "底板不健康，反例结论不可信，未跑"))
        print("[%s] %-32s 反例结论不可信（未跑）" % (FAIL, mut_label))
        return

    try:
        mutate()
    except Exception as exc:
        results.append((FAIL, mut_label, "变异构造异常：%s" % exc))
        print("[%s] %-32s 构造异常 %s" % (FAIL, mut_label, exc))
        return
    sc.rows.clear()
    try:
        check()
    except Exception as exc:
        ok, why = False, "变异后检查抛异常：%s" % exc
    else:
        r1 = row()
        ok = (bool(r1) and r1["status"] == FAIL
              and (not must_say or must_say in r1["detail"]))
        why = "" if ok else "没变红 / 红错了地方：%s" % ((r1 or {}).get("detail") or "无此行")
    emit(mut_label, ok, why, "按预期变红" if ok else why)


def run_terms_mutation():
    """第 5 项：复制真实特刊（只有它有术语注解），把报尾词表整批写错字。"""
    with tempfile.TemporaryDirectory(prefix="mt-terms-") as t:
        site = Path(t) / "site"
        (site / "special").mkdir(parents=True)
        dst = site / "special/2026-11-06.html"
        shutil.copy2(REAL_SITE / "special/2026-11-06.html", dst)
        saved = sc.SITE
        sc.SITE = site
        try:
            def mutate():
                s = dst.read_bytes().decode("utf-8")
                gloss = make_manifest.block(s, '<div class="gloss"')
                i = s.find(gloss)
                if not gloss or i < 0:
                    raise RuntimeError("找不到 gloss 词表块")
                n = [0]

                def wrong(m):
                    n[0] += 1
                    return "<dt>ZZZ-词表整批写错-%d</dt>" % n[0]

                # 按 block() 的真实切块范围改，不能用第一个 </dl> 粗略截断
                new, cnt = re.subn(r"<dt>.*?</dt>", wrong, gloss, flags=re.S)
                if cnt < 2:
                    raise RuntimeError("只改到 %d 个词条，fixture 失效" % cnt)
                dst.write_bytes((s[:i] + new + s[i + len(gloss):]).encode("utf-8"))
                if not make_manifest.build(dst, "special")["missing_terms"]:
                    raise RuntimeError("词表改错字后仍无缺词，变异没生效")

            expect_contrast("术语词表底板（应全绿）", "术语注解缺词表", 5,
                            sc.check_terms, mutate)
        finally:
            sc.SITE = saved


def run_online_mutation(data):
    """第 13 项（线上可访问）：本地假站点 + 本地副本等长替换 → 模拟「改了没发布」。

    不碰真实域名、不制造线上事故；端口随机，HTTP 服务随临时目录一起销毁。
    """
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    with tempfile.TemporaryDirectory(prefix="mt-online-") as t:
        tmp = Path(t)
        online, local = tmp / "online", tmp / "site"
        online.mkdir()
        local.mkdir()
        (online / "special").mkdir()
        (local / "special").mkdir()
        # 假站点的文件清单从真实索引动态取：check_online 会请求「最新一期 +
        # 凭证 / 特刊 + 凭证」，写死四份的话每出一期新报，正向对照就会 404，
        # 变成「假站点没搭好」的假红。新增期次不用再改这段。
        rels, seen = ["index.html"], {"index.html"}
        for it in list(data.get("issues") or []) + list(data.get("specials") or []):
            f = it.get("file")
            if not f:
                continue
            for r in (f, it.get("manifest"), f.rsplit(".", 1)[0] + ".json"):
                if r and r not in seen:
                    seen.add(r)
                    rels.append(r)
        for r in rels:
            for dst in (online / r, local / r):
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REAL_SITE / r, dst)

        handler = functools.partial(Quiet, directory=str(online))
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        url = "http://127.0.0.1:%d/" % srv.server_address[1]
        saved = (sc.ROOT, sc.SITE, sc.BASE, sc.HOST)
        sc.BASE, sc.HOST, sc.SITE = url, url, local
        try:
            latest = (data.get("issues") or [{}])[0].get("file")
            if not latest:
                raise RuntimeError("索引里没有最新一期，线上反例无法构造")

            def mutate():
                # 改「最新一期」本地副本，模拟改了没发布；等长替换让体积不变，
                # 只有 sha256 能抓到。串取自各期都有的内容声明，纯中文等长。
                p = local / latest
                b = p.read_bytes()
                old, new = "产品演示".encode("utf-8"), "产品示例".encode("utf-8")
                if b.count(old) != 1 or len(old) != len(new):
                    raise RuntimeError("等长替换素材失效（%s）" % latest)
                p.write_bytes(b.replace(old, new, 1))

            expect_contrast("线上 sha 底板（应全绿）", "线上与本地 sha 漂移", 13,
                            lambda: sc.check_online(data), mutate, "线上与本地不一致")
        finally:
            sc.ROOT, sc.SITE, sc.BASE, sc.HOST = saved
            srv.shutdown()
            srv.server_close()
            th.join(timeout=3)


def run_disclaimer_mutation():
    """第 12 项：把一期报尾声明做等长替换，确认「单一事实源」对账会红。

    fixture 复制全部声明落点到临时项目（含 README 与入口页），先证明底板全绿，
    再弄坏一句话。只读真实成品，不动 ai-daily/ 的任何文件。
    """
    with tempfile.TemporaryDirectory(prefix="mt-disc-") as t:
        tmp = Path(t)
        root, site = tmp / "ai-daily", tmp / "ai-daily" / "site"
        for p in D.html_targets(REAL_ROOT):
            dst = root / p.relative_to(REAL_ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
        for p in D.site_targets(REAL_SITE) + [REAL_SITE / "config.js",
                                              REAL_SITE / "index.html"]:
            dst = site / p.relative_to(REAL_SITE)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
        shutil.copy2(D.README, tmp / "README.md")

        saved = (sc.ROOT, sc.SITE)
        sc.ROOT, sc.SITE = root, site
        try:
            def mutate():
                p = root / "AI晨报-2026-11-06.html"
                b = p.read_bytes()
                old, new = "产品演示".encode("utf-8"), "产品示例".encode("utf-8")
                if b.count(old) != 1 or len(old) != len(new):
                    raise RuntimeError("等长替换素材失效")
                p.write_bytes(b.replace(old, new, 1))

            expect_contrast("声明底板（应全绿）", "报尾声明与 config.js 漂移", 12,
                            sc.check_disclaimer, mutate, "声明行不是恰好 1 处")
        finally:
            sc.ROOT, sc.SITE = saved


def run_graph_mutations():
    """A10–A16（P005-2/3/4 与 P006）：拼版断言同样要有反向验证。

    共用一份正向对照：未改动的 parts/1107 必须先校验通过。底板不绿就不跑反例，
    否则「变红」可能只是素材坏了（假红），这比假绿更骗人。
    """
    with tempfile.TemporaryDirectory(prefix="mt-graph-") as t:
        tmp = Path(t)
        base = tmp / "base"
        shutil.copytree(REAL_ROOT / "parts" / "1107", base)
        asm = str(REAL_ROOT / "tools" / "assemble_issue.py")

        def argv(parts):
            return [sys.executable, asm, "--parts", str(parts), "--date", "2026-11-07",
                    "--issue", "004", "--label", "从会答到会办", "--dry-run", "--no-status"]

        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run(argv(base), cwd=REAL_ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        green = r.returncode == 0 and "校验通过" in (r.stdout or "")
        results.append((PASS if green else FAIL, "A10–A16 底板（应全绿）",
                        "" if green else "底板不绿，反例结论不可信"))
        print("[%s] %-32s → %s" % (PASS if green else FAIL, "A10–A16 底板（应全绿）",
                                   "A1–A16 全过" if green else "底板不绿（%d）" % r.returncode))
        if not green:
            tail = (r.stdout or "").strip().splitlines()[-3:]
            print("      底板报错：%s" % " / ".join(x.strip() for x in tail))
            for lab in ("A10 论据标记自造说法", "A11 报头主线与声明不符",
                        "A12 跑偏熔断（八版行情）", "A13 事实卡与正文漂移",
                        "A14 版级来源手写成另一档", "A14b AI 生成版挂着外部标记",
                        "A14c 无证据的版标成官方", "A15 AI 生成版超上限",
                        "A15b 报尾 AI 版数与实际不符", "A16 信源类型不在词表"):
                results.append((FAIL, lab, "底板不健康，反例结论不可信，未跑"))
            return

        def mutate_tag(d):
            p = d / "p01.html"
            s = p.read_bytes().decode("utf-8")
            if '<span class="src-tag">厂商口径</span>' not in s:
                raise RuntimeError("p01 里找不到厂商口径标记")
            p.write_bytes(s.replace('<span class="src-tag">厂商口径</span>',
                                    '<span class="src-tag">据说</span>', 1).encode("utf-8"))

        def mutate_thread(d):
            p = d / "00-masthead.html"
            s = p.read_bytes().decode("utf-8")
            if 'data-thread="从会答到会办"' not in s:
                raise RuntimeError("报头没有 data-thread 声明")
            p.write_bytes(s.replace('data-thread="从会答到会办"',
                                    'data-thread="行情复盘"', 1).encode("utf-8"))

        def mutate_offtopic(d):
            # 8 版塞进跑偏词，超过 00-thread.json 的 maxOffTopicPages（7）
            for i in (2, 4, 6, 8, 10, 12, 13, 15):
                p = d / ("p%02d.html" % i)
                s = p.read_bytes().decode("utf-8")
                p.write_bytes(s.replace("</section>",
                                        "<p>纳指收盘复盘</p></section>", 1).encode("utf-8"))

        def mutate_facts(d):
            p = d / "00-facts.json"
            v = json.loads(p.read_text(encoding="utf-8"))
            if not v.get("facts"):
                raise RuntimeError("事实卡为空")
            v["facts"][0]["value"] = "99.99%"
            p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")

        # ---- P006：版级来源 / AI 占比 / 信源归属 ----
        def mutate_org_manual(d):
            # 片段里手写一个错档的来源标：注入会被跳过，A14 必须发现它和事实源不符
            p = d / "p05.html"
            s = p.read_bytes().decode("utf-8")
            if '<span class="sec-page">' not in s:
                raise RuntimeError("p05 没有版号，注入点不对")
            tag = '<span class="src-org src-org-thirdparty">来源 · 第三方信息网</span>'
            p.write_bytes(s.replace('<span class="sec-page">', tag + '<span class="sec-page">',
                                    1).encode("utf-8"))

        def mutate_org_ai_with_tag(d):
            # p01 有论据标记，却被标成「AI 生成」：自相矛盾
            p = d / "00-blocks.json"
            v = json.loads(p.read_text(encoding="utf-8"))
            v["pages"]["p01"]["origin"] = "ai"
            p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")

        def mutate_org_fake_official(d):
            # p02 是社论，全版没有一处外部证据，却被标成「官方」
            p = d / "00-blocks.json"
            v = json.loads(p.read_text(encoding="utf-8"))
            v["pages"]["p02"]["origin"] = "official"
            p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")

        def mutate_ai_limit(d):
            p = d / "00-blocks.json"
            v = json.loads(p.read_text(encoding="utf-8"))
            v["maxAiPages"] = 2
            p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")

        def mutate_ai_claim(d):
            p = d / "00-tail.html"
            b = p.read_bytes()
            old = "本期 AI 生成 3 版".encode("utf-8")
            if b.count(old) != 1:
                raise RuntimeError("报尾没有『本期 AI 生成 3 版』")
            p.write_bytes(b.replace(old, "本期 AI 生成 5 版".encode("utf-8"), 1))

        def mutate_source_kind(d):
            p = d / "00-sources.json"
            v = json.loads(p.read_text(encoding="utf-8"))
            v["sources"][0]["kind"] = "据说"
            p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")

        for i, (label, fn, kw) in enumerate([
            ("A10 论据标记自造说法", mutate_tag, "A10"),
            ("A11 报头主线与声明不符", mutate_thread, "A11"),
            ("A12 跑偏熔断（八版行情）", mutate_offtopic, "A12"),
            ("A13 事实卡与正文漂移", mutate_facts, "A13"),
            ("A14 版级来源手写成另一档", mutate_org_manual, "A14"),
            ("A14b AI 生成版挂着外部标记", mutate_org_ai_with_tag, "A14b"),
            ("A14c 无证据的版标成官方", mutate_org_fake_official, "A14c"),
            ("A15 AI 生成版超上限", mutate_ai_limit, "A15 "),
            ("A15b 报尾 AI 版数与实际不符", mutate_ai_claim, "A15b"),
            ("A16 信源类型不在词表", mutate_source_kind, "A16"),
        ], 1):
            work = tmp / ("m%d" % i)
            shutil.copytree(base, work)
            try:
                fn(work)
            except Exception as exc:
                results.append((FAIL, label, "变异构造异常：%s" % exc))
                print("[%s] %-32s 构造异常 %s" % (FAIL, label, exc))
                continue
            expect_cmd_red(label, argv(work), kw, REAL_ROOT)


def run_rules_mutation():
    """第 14 项：把规则文档的条数改错 → 必须红。

    副本在临时目录里改，真实文档一个字节都不动；先跑正向对照，
    否则「变了红」也可能只是导入失败之类的假红。
    """
    src = REAL_ROOT.parent / "项目框架与规则.md"
    if not src.exists():
        results.append((SKIP, "规则对账底板", "工作区没有规则文档"))
        print("[SKIP] %-32s → 没有规则文档" % "规则对账底板")
        return
    with tempfile.TemporaryDirectory(prefix="mt-rules-") as t:
        doc = Path(t) / "rules.md"
        doc.write_bytes(src.read_bytes())

        def mutate():
            s = doc.read_text(encoding="utf-8")
            m = re.search(r"(###\s+4\.\d+\s+L2[^（(]*[（(])(\d+)", s)
            if not m:
                raise RuntimeError("找不到 L2 的条数声明")
            doc.write_text(s[:m.start(2)] + str(int(m.group(2)) + 1) + s[m.end(2):],
                           encoding="utf-8", newline="")

        expect_contrast("规则对账底板（应全绿）", "规则条数写错", 14,
                        lambda: sc.check_rules(doc=doc), mutate, "实际")


def run_products_mutation():
    """第 14 项：产物清单的「小计」分项写错 → 必须红。

    这是最容易漏的一种漂移：总数被 doc_sync 自动改对了，分类小计还停在旧值。
    实测过——第 28 项加进去后总数变 28，小计仍是「文档 7」，
    5+4+2+7+5+3 = 26 ≠ 28，而检查器报「对得上」。
    副本在临时目录里改，真实清单不动。
    """
    src = REAL_ROOT.parent / "产物清单.md"
    if not src.exists():
        results.append((SKIP, "产物小计底板", "工作区没有 产物清单.md"))
        print("[SKIP] %-32s → 没有 产物清单.md" % "产物小计底板")
        return
    with tempfile.TemporaryDirectory(prefix="mt-products-") as t:
        prod = Path(t) / "产物清单.md"
        prod.write_bytes(src.read_bytes())

        def mutate():
            s = prod.read_bytes().decode("utf-8")
            m = re.search(r"小计：([^=\n]*)=(\s*\*\*\d+\*\*)", s)
            if not m:
                raise RuntimeError("找不到小计行")
            body = m.group(1)
            mm = re.search(r"\s(\d+)\s*·", body)     # 只改第一个分项，总数保持正确
            if not mm:
                raise RuntimeError("小计行里找不到分项数字")
            body2 = body[:mm.start(1)] + str(int(mm.group(1)) + 1) + body[mm.end(1):]
            prod.write_bytes((s[:m.start(1)] + body2 + s[m.end(1):]).encode("utf-8"))

        expect_contrast("产物清单底板（应全绿）", "产物小计分项写错", 14,
                        lambda: sc.check_rules(products=prod), mutate, "小计")


def run_ci_mutation():
    """第 15 项：往 ci.yml 里塞 markdown 引用符 → 必须红。

    这正是真实翻车的样子：文件开头三行 `> ` 让 pyyaml 报 ScannerError，
    Actions 不加载，而 README 一直宣传四矩阵 CI。副本在临时目录里改。
    """
    src = REAL_ROOT.parent / ".github" / "workflows" / "ci.yml"
    if not src.exists():
        results.append((SKIP, "CI 合法性底板", "工作区没有 ci.yml"))
        print("[SKIP] %-32s → 没有 ci.yml" % "CI 合法性底板")
        return
    with tempfile.TemporaryDirectory(prefix="mt-ci-") as t:
        ci = Path(t) / "ci.yml"
        ci.write_bytes(src.read_bytes())

        def mutate():
            ci.write_bytes(b"> markdown leaked in\n" + ci.read_bytes())

        # readme 指向不存在的路径，隔离矩阵核对，专测 YAML 结构这一路
        absent = Path(t) / "no-readme.md"
        expect_contrast("CI 合法性底板（应全绿）", "ci.yml 混入 markdown", 15,
                        lambda: sc.check_ci(ci_path=ci, readme_path=absent), mutate,
                        "引用符")

        # 第二组：dependabot.yml 不盯 Actions。用干净副本重开，免得继承上一条的伤。
        ci.write_bytes(src.read_bytes())
        dep = Path(t) / "dependabot.yml"
        good = ('version: 2\nupdates:\n  - package-ecosystem: "github-actions"\n'
                '    directory: "/"\n    schedule:\n      interval: "weekly"\n')
        dep.write_text(good, encoding="utf-8")

        def mutate_dep():
            dep.write_text(good.replace("github-actions", "pip"), encoding="utf-8")

        expect_contrast("dependabot 底板（应全绿）", "dependabot 不盯 Actions", 15,
                        lambda: sc.check_ci(ci_path=ci, readme_path=absent, dep_path=dep),
                        mutate_dep, "github-actions")


def run_secret_mutation():
    """新检查项：密钥扫描器本身要被检查。

    反例：临时目录里种一行明文入口地址，`--dir --strict` 必须退出码 1 并点名「入口地址」。
    正向对照：同一套目录去掉那一行必须先 0 命中——否则「变红」可能只是脚本根本没跑起来。
    附带一条：输出里不许出现明文本身，扫描器不能变成新的泄露点。
    """
    with tempfile.TemporaryDirectory(prefix="mt-secret-") as t:
        root = Path(t)
        (root / "ok.md").write_text("这里没有敏感内容\n", encoding="utf-8")
        cmd = [sys.executable, str(REAL_ROOT / "tools" / "secret_scan.py"),
               "--dir", str(root), "--strict"]
        env = dict(os.environ, PYTHONIOENCODING="utf-8")

        def go():
            return subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", env=env)

        clean = go()
        ok = clean.returncode == 0 and "0 FAIL" in clean.stdout
        results.append((PASS if ok else FAIL, "密钥扫描底板（应全绿）",
                        "" if ok else "退出码 %d：%s" % (clean.returncode,
                                                       clean.stdout[-200:])))
        print("[%s] %-32s → %s" % (PASS if ok else FAIL, "密钥扫描底板（应全绿）",
                                   "0 命中" if ok else "底板不绿，反例无意义"))

        # 变量名别叫 secret/password：扫描器按 `键 = "值"` 的字面形状判硬编码口令，
        # 叫 secret 会被自己误报（第一次跑就是这么红的，算是反向验证了它真在工作）。
        planted = "SHOULD-NOT-PRINT-9F2A"
        (root / "leak.md").write_text(
            "入口 https://x.example/?sharecode=%s\n" % planted, encoding="utf-8")
        dirty = go()
        ok2 = (dirty.returncode == 1 and "入口地址" in dirty.stdout
               and planted not in dirty.stdout)
        why = ""
        if not ok2:
            why = "退出码 %d / 没点名 / 输出泄露了明文" % dirty.returncode
        results.append((PASS if ok2 else FAIL, "明文写进文件（且输出打码）", why))
        print("[%s] %-32s → %s" % (PASS if ok2 else FAIL, "明文写进文件（且输出打码）",
                                   "拦住了且已打码" if ok2 else why))


def run_apk_mutation():
    """第 17 项：APK 快照与当期一致。

    反例全在临时目录里造，不碰真包：包内还是上一期 / 当期正文改过没重打 /
    索引列了包里没有的文件。正向对照用真包，先确认它绿——否则「变红」
    可能只是我把路径写错了。
    """
    import zipfile

    data = sc.load_issues()
    live = next((x for x in data["issues"] if not x.get("isSpecial")), None)
    apk = REAL_SITE / "ai-daily.apk"
    if not live or not apk.exists():
        results.append((SKIP, "APK 快照（第 17 项）", "本机没有 APK"))
        print("[SKIP] %-30s → %s" % ("APK 快照（第 17 项）", "本机没有 APK"))
        return

    def verdict(apk_path, site_path):
        sc.rows.clear()
        sc.check_apk(data, apk_path=apk_path, site=site_path)
        row = sc.rows[-1]
        return row["status"], row["detail"]

    st, detail = verdict(apk, REAL_SITE)
    ok = st == PASS
    results.append((PASS if ok else FAIL, "APK 快照底板（应全绿）", "" if ok else detail))
    print("[%s] %-30s → %s" % (PASS if ok else FAIL, "APK 快照底板（应全绿）",
                               "真包与当期一致" if ok else detail))

    html_name = "AI晨报-%s.html" % live["date"]
    src = (REAL_SITE / html_name).read_bytes()

    with tempfile.TemporaryDirectory(prefix="mt-apk-") as t:
        tmp = Path(t)
        site = tmp / "site"
        site.mkdir()
        shutil.copy2(REAL_SITE / html_name, site / html_name)
        shutil.copy2(REAL_SITE / "issues.js", site / "issues.js")

        def build(name, issues_obj, html):
            p = tmp / name
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("assets/site/issues.js",
                           "window.AI_DAILY_ISSUES = %s;\n"
                           % json.dumps(issues_obj, ensure_ascii=False))
                z.writestr("assets/site/issue-%s.html" % live["date"], html)
            return p

        # ① 包里还是上一期
        stale = json.loads(json.dumps(data))
        for x in stale["issues"]:
            if not x.get("isSpecial"):
                x["issue"] = "003"
                break
        s1, d1 = verdict(build("stale.apk", stale, src), site)
        ok1 = s1 == FAIL and "第 003 期" in d1
        results.append((PASS if ok1 else FAIL, "包里是上一期", "" if ok1 else d1))
        print("[%s] %-30s → %s" % (PASS if ok1 else FAIL, "包里是上一期",
                                   "拦住了" if ok1 else d1))

        # ② 当期正文改过、包没重打
        s2, d2 = verdict(build("drift.apk", data, src + b"<!-- x -->"), site)
        ok2 = s2 == FAIL and "不是同一份" in d2
        results.append((PASS if ok2 else FAIL, "正文改了没重打", "" if ok2 else d2))
        print("[%s] %-30s → %s" % (PASS if ok2 else FAIL, "正文改了没重打",
                                   "拦住了" if ok2 else d2))

        # ③ 包内索引列了包里没有的文件
        ghost = json.loads(json.dumps(data))
        ghost["issues"].insert(0, {"date": live["date"], "issue": live["issue"],
                                   "isSpecial": False, "file": "ghost.html"})
        s3, d3 = verdict(build("ghost.apk", ghost, src), site)
        ok3 = s3 == FAIL and "404" in d3
        results.append((PASS if ok3 else FAIL, "索引列了幽灵文件", "" if ok3 else d3))
        print("[%s] %-30s → %s" % (PASS if ok3 else FAIL, "索引列了幽灵文件",
                                   "拦住了" if ok3 else d3))


def run_manifest_mutation():
    """第 18 项：更新清单与包一致。

    这一项管的是「App 里那个弹窗会不会出现」。坏掉的形态都很安静：
    清单不跟包走 → 所有人永远收不到；清单超前于包 → 提示了却下到同一个包；
    源码里的检查被删 → 清单再准也没人读。
    """
    apk = REAL_SITE / "ai-daily.apk"
    mf = REAL_SITE / sc.update_manifest_name()
    if not apk.exists() or not mf.exists():
        results.append((SKIP, "更新清单（第 18 项）", "本机没有 APK 或清单"))
        print("[SKIP] %-30s → %s" % ("更新清单（第 18 项）", "本机没有 APK 或清单"))
        return

    base = json.loads(mf.read_text(encoding="utf-8"))
    src = REAL_ROOT / "apk" / "src" / "cn" / "aidaily" / "app" / "MainActivity.java"

    def verdict(site_dir, src_path=None):
        sc.rows.clear()
        sc.check_update_manifest(site=site_dir, src=src_path)
        row = sc.rows[-1]
        return row["status"], row["detail"]

    with tempfile.TemporaryDirectory(prefix="mt-mf-") as t:
        tmp = Path(t)
        site = tmp / "site"
        site.mkdir()
        shutil.copy2(mf, site / mf.name)
        shutil.copy2(apk, site / apk.name)

        st, detail = verdict(site)
        ok = st == PASS
        results.append((PASS if ok else FAIL, "更新清单底板（应全绿）", "" if ok else detail))
        print("[%s] %-30s → %s" % (PASS if ok else FAIL, "更新清单底板（应全绿）",
                                   "清单与包一致" if ok else detail))

        def write(obj):
            (site / mf.name).write_text(
                json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        # ① 包换了、清单没换（sha 还是旧的）
        bad = dict(base)
        bad["sha256"] = "0" * 64
        write(bad)
        s1, d1 = verdict(site)
        ok1 = s1 == FAIL and "sha256" in d1
        results.append((PASS if ok1 else FAIL, "清单 sha 与包不符", "" if ok1 else d1))
        print("[%s] %-30s → %s" % (PASS if ok1 else FAIL, "清单 sha 与包不符",
                                   "拦住了" if ok1 else d1))

        # ② 字节数对不上（包截断 / 清单写错）
        bad = dict(base)
        bad["bytes"] = int(base["bytes"]) + 1
        write(bad)
        s2, d2 = verdict(site)
        ok2 = s2 == FAIL and "字节" in d2
        results.append((PASS if ok2 else FAIL, "清单字节数不符", "" if ok2 else d2))
        print("[%s] %-30s → %s" % (PASS if ok2 else FAIL, "清单字节数不符",
                                   "拦住了" if ok2 else d2))

        # ③ 源码里的检查被删掉了（清单还在，但没人读）
        write(base)
        stub = tmp / "MainActivity.java"
        stub.write_text("class MainActivity { }\n", encoding="utf-8")
        s3, d3 = verdict(site, stub)
        ok3 = s3 == FAIL and "没人读" in d3
        results.append((PASS if ok3 else FAIL, "App 不再检查版本", "" if ok3 else d3))
        print("[%s] %-30s → %s" % (PASS if ok3 else FAIL, "App 不再检查版本",
                                   "拦住了" if ok3 else d3))

        # ④ 清单根本没生成 / 没发布
        (site / mf.name).unlink()
        s4, d4 = verdict(site)
        ok4 = s4 == FAIL and "永远收不到" in d4
        results.append((PASS if ok4 else FAIL, "缺更新清单", "" if ok4 else d4))
        print("[%s] %-30s → %s" % (PASS if ok4 else FAIL, "缺更新清单",
                                   "拦住了" if ok4 else d4))


def run_export_mutation():
    """推送前复检（export_public.py --verify）自己要被检查。

    底板是一棵最小的合格导出树：占位 config.js + .gitattributes + 单提交。
    五个变异各打一条检查：改脏工作区、抽掉 * -text、种明文、抽掉所有提交、
    徽章还指着占位仓库。任何一条不红，都说明「推之前再看一眼」是句空话。
    """
    with tempfile.TemporaryDirectory(prefix="mt-export-") as t:
        root = Path(t)
        (root / "ai-daily" / "site").mkdir(parents=True)
        (root / "ai-daily" / "site" / "config.js").write_text(
            'var C = { siteUrl: "__SITE_URL__" };\n', encoding="utf-8")
        (root / ".gitattributes").write_text("* -text\n", encoding="utf-8")
        (root / "README.md").write_text("# 样例\n", encoding="utf-8")

        def git(*args):
            return subprocess.run(["git"] + list(args), cwd=str(root),
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")

        git("init", "-q", "-b", "main")
        git("add", "-A")
        git("-c", "user.name=rehearsal", "-c", "user.email=rehearsal@users.noreply.github.com",
            "commit", "-q", "-m", "初始提交")

        env = dict(os.environ, PYTHONIOENCODING="utf-8")

        def go():
            return subprocess.run(
                [sys.executable, str(REAL_ROOT / "tools" / "export_public.py"),
                 "--verify", str(root)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", env=env)

        # 正向对照：底板必须先过。它的身份是 rehearsal，会被身份检查拦——那属于
        # 「这条检查有效」的证据，但会让底板不绿，所以只把身份换成合格值。
        git("-c", "user.name=n", "-c", "user.email=tester@users.noreply.github.com",
            "commit", "-q", "--amend", "--reset-author", "--no-edit")
        base = go()
        ok0 = base.returncode == 0
        results.append((PASS if ok0 else FAIL, "导出复检底板（应全绿）",
                        "" if ok0 else base.stdout[-240:]))
        print("[%s] %-32s → %s" % (PASS if ok0 else FAIL, "导出复检底板（应全绿）",
                                   "9 项全 PASS" if ok0 else "底板不绿，反例无意义"))

        def case(name, expect, prepare, undo):
            prepare()
            r = go()
            ok = r.returncode == 1 and expect in r.stdout
            results.append((PASS if ok else FAIL, name,
                            "" if ok else "退出码 %d，未点名「%s」" % (r.returncode, expect)))
            print("[%s] %-32s → %s" % (PASS if ok else FAIL, name,
                                       "拦住了" if ok else "没拦住 / 没点名"))
            undo()

        (root / "README.md").write_text("# 改脏\n", encoding="utf-8")
        case("改脏的工作区", "工作区干净",
             lambda: None, lambda: git("checkout", "--", "README.md"))

        case("丢掉 .gitattributes", "钉住行尾",
             lambda: (root / ".gitattributes").unlink(),
             lambda: git("checkout", "--", ".gitattributes"))

        def plant():
            # 假码拆开拼：源码里不留可被 secret_scan 扫到的字面量（写死会把自己扫红）
            fake = "ABC" + "123XYZ"
            (root / "leak.md").write_text(
                "入口 https://x.example/?sharecode=%s\n" % fake, encoding="utf-8")

        case("推送前有人塞了明文", "严格密钥扫描",
             plant, lambda: (root / "leak.md").unlink())

        # 分支保护禁掉 force push 之后，公开仓库只能原地追加提交，复检判的是
        # 「至少一个提交」而不是「恰好一个」。对应的反例于是变成「一个都没有」。
        saved = {}

        def drop_head():
            saved["sha"] = git("rev-parse", "HEAD").stdout.strip()
            git("update-ref", "-d", "HEAD")

        def restore_head():
            git("update-ref", "HEAD", saved["sha"])

        case("导出树没有任何提交", "提交数至少 1", drop_head, restore_head)

        # 徽章指向不存在的仓库：图是坏的，第一屏就露怯。占位没注入 = 忘了 --repo。
        def plant_slug():
            (root / "README.md").write_text(
                "# 样例\n\n[![ci](https://github.com/%s/actions/workflows/ci.yml/badge.svg)]\n"
                % EXPORT.REPO_PLACEHOLDER, encoding="utf-8")

        case("徽章还指着占位仓库", "仓库地址已注入", plant_slug,
             lambda: git("checkout", "--", "README.md"))


def run_export_coverage_mutation():
    """第 16 项：已入库、但导出白名单没覆盖到的文件，必须红。

    这是「本机全绿、公开仓库静默少文件」的唯一防线——导出是白名单，
    新目录默认不进，所以这个失败模式是默认结局而不是意外。
    """
    base = ["README.md", "LICENSE", "ai-daily/site/config.js"]
    tracked = list(base)
    expect_contrast("导出覆盖底板（应全绿）", "入库文件进不了公开树", 16,
                    lambda: sc.check_export_coverage(tracked=tracked, picked=list(base)),
                    lambda: tracked.append("ai-daily/_private/notes.md"),
                    "ai-daily/_private/notes.md")


def run_public_mutation():
    """第 19 项：公开面混进访问码 / 卡片页被删 → 必须红。

    公开面是唯一一处主动把内容放到访问码之外的地方，所以两种失败都必须拦住：
    ① 生成器把 sharecode 写进了页面（不可撤销：Pages 有 CDN 缓存，可能已被抓取）；
    ② 索引更新了、公开面还是旧的（访客看到过期卡片，线上一切正常，没人会发现）。
    两种情况都在临时副本里造，真实 docs/ 一个字节不动。
    """
    real = REAL_ROOT.parent / "docs"
    if not (real / "index.html").is_file():
        results.append((SKIP, "公开面底板", "docs/ 还没生成"))
        print("[SKIP] %-32s → docs/ 还没生成" % "公开面底板")
        return
    m = re.search(r"sharecode=([A-Za-z0-9_-]{4,})", sc.SITE_URL or "")
    if not m:
        results.append((SKIP, "公开面底板", "拿不到入口访问码，造不出泄露反例"))
        print("[SKIP] %-32s → 拿不到入口访问码" % "公开面底板")
        return
    secret = m.group(1)

    with tempfile.TemporaryDirectory(prefix="mt-public-") as t:
        tmp = Path(t) / "docs"
        shutil.copytree(real, tmp, ignore=shutil.ignore_patterns("screenshots", "*.png"))

        def plant_leak():
            (tmp / "leak.txt").write_text("入口 sharecode=" + secret + "\n", encoding="utf-8")

        expect_contrast("公开面底板（应全绿）", "公开面混进访问码", 19,
                        lambda: sc.check_public(docs=tmp), plant_leak, "访问码")

    with tempfile.TemporaryDirectory(prefix="mt-public2-") as t:
        tmp = Path(t) / "docs"
        shutil.copytree(real, tmp, ignore=shutil.ignore_patterns("screenshots", "*.png"))
        victim = sorted((tmp / "cards").glob("*-F*.html"))
        if not victim:
            results.append((SKIP, "公开面卡片被删", "没有卡片页可删"))
            print("[SKIP] %-32s → 没有卡片页可删" % "公开面卡片被删")
            return

        def drop_card():
            victim[0].unlink()

        expect_contrast("公开面卡片齐全（应全绿）", "公开面卡片被删", 19,
                        lambda: sc.check_public(docs=tmp), drop_card, "过期")


def run():
    data = sc.load_issues()                      # 真实索引，作为反例的底板

    # 第 1 项：把 p07 页眉塞回「共 15 版」，A4d 必须在落盘前拦住
    with tempfile.TemporaryDirectory(prefix="mt-assemble-") as t:
        tmp = Path(t)
        parts = tmp / "parts"
        shutil.copytree(REAL_ROOT / "parts" / "1106sp", parts)
        p07 = parts / "p07.html"
        b = p07.read_bytes()
        old, new = "共 16 版".encode("utf-8"), "共 15 版".encode("utf-8")
        if b.count(old) < 1:
            raise SystemExit("p07 里找不到「共 16 版」，变异构造失败")
        p07.write_bytes(b.replace(old, new, 1))
        expect_cmd_red(
            "A4d 页眉版数写错",
            [sys.executable, str(REAL_ROOT / "tools" / "assemble_issue.py"),
             "--parts", str(parts), "--date", "2026-11-06", "--issue", "003-2",
             "--slug=-特刊", "--label", "傍晚特刊", "--dry-run", "--no-status"],
            "A4d", REAL_ROOT)

    # 第 2 项 a：索引里的 size 写错
    def size_wrong():
        bad = json.loads(json.dumps(data))
        bad["issues"][0]["size"] += 1
        sc.check_index(bad)
    expect_red("索引 size 与文件不符", 2, size_wrong, "大小不符")

    # 第 2 项 b：等长替换——bytes 数不变，旧版「只比 size」必然漏，
    # 只有新增的「源 ↔ 副本逐字节比对」能红。这条专治「两份真相」。
    def equal_length_drift():
        with tempfile.TemporaryDirectory(prefix="mt-drift-") as t:
            site = site_fixture(Path(t))
            p = site / "AI晨报-2026-11-06.html"
            b = p.read_bytes()
            old = "本期因故延后发布".encode("utf-8")
            new = ("改" * (len(old) // 3)).encode("utf-8")   # 同为 24 字节
            if old not in b or len(new) != len(old):
                raise RuntimeError("等长替换构造失败")
            p.write_bytes(b.replace(old, new, 1))
            sc.SITE = site
            sc.check_index(sc.load_issues())
    expect_red("站点副本等长漂移", 2, equal_length_drift, "内容不一致")

    # 第 3 / 4 项：缺凭证、凭证 sha 与成品不符
    def no_json():
        with tempfile.TemporaryDirectory(prefix="mt-nojson-") as t:
            site = Path(t) / "site"
            site.mkdir()
            (site / "AI晨报-2099-01-01.html").write_text("<html></html>", encoding="utf-8")
            sc.SITE = site
            sc.check_manifest()
    expect_red("成品缺同名 json", 3, no_json, "缺")

    def bad_json():
        with tempfile.TemporaryDirectory(prefix="mt-badjson-") as t:
            site = Path(t) / "site"
            site.mkdir()
            (site / "AI晨报-2099-01-01.html").write_text("<html></html>", encoding="utf-8")
            (site / "AI晨报-2099-01-01.json").write_text(
                json.dumps({"sha256": "0" * 64, "bytes": 13, "ok": True, "checks": {}}),
                encoding="utf-8")
            sc.SITE = site
            sc.check_manifest()
    expect_red("凭证 sha 与成品不符", 4, bad_json)

    # 第 6 项：坏 JSON
    def broken_json():
        with tempfile.TemporaryDirectory(prefix="mt-json-") as t:
            site = Path(t) / "site"
            site.mkdir()
            shutil.copy2(REAL_SITE / "issues.js", site / "issues.js")
            (site / "broken.json").write_text("{not json", encoding="utf-8")
            sc.SITE = site
            sc.check_json()
    expect_red("JSON 写坏", 6, broken_json)

    # 第 7 项：期序乱（同号 + 未来期）
    def bad_sequence():
        sc.check_sequence({"issues": [
            {"date": "2026-11-06", "issue": "003", "file": "a.html", "size": 1},
            {"date": "2026-11-06", "issue": "003", "isSpecial": True,
             "file": "s.html", "size": 1},
            {"date": "2026-11-05", "issue": "005", "file": "b.html", "size": 1},
        ], "specials": []})
    expect_red("期号重复 / 序列错乱", 7, bad_sequence)

    # 第 8 项：假装是昨天，今天的报纸就都成了「未来期」
    def fake_yesterday():
        os.environ["AI_DAILY_TODAY"] = "2026-11-05"
        sc.check_dategate(data)
    expect_red("假装昨天（日期闸门）", 8, fake_yesterday, "晚于今天")

    # 第 9 项：入口页缺特刊入口
    def bad_entry():
        with tempfile.TemporaryDirectory(prefix="mt-entry-") as t:
            site = Path(t) / "site"
            site.mkdir()
            (site / "index.html").write_text("<html><body>无入口</body></html>", encoding="utf-8")
            sc.SITE = site
            sc.check_entry()
    expect_red("入口页缺特刊横幅", 9, bad_entry, "缺")

    # 第 10 项：状态机五阶段全空
    def bad_status():
        with tempfile.TemporaryDirectory(prefix="mt-status-") as t:
            root = Path(t)
            (root / "status.json").write_text(
                json.dumps({"date": "2026-11-06", "issue": "003", "steps": {}}),
                encoding="utf-8")
            sc.ROOT = root
            sc.check_status("2026-11-06", False)
    expect_red("状态机五阶段全空", 10, bad_status)

    # 第 11 项：成品全文写错版数（当年 14 处页眉的事故）
    def bad_pages():
        with tempfile.TemporaryDirectory(prefix="mt-pages-") as t:
            tmp = Path(t)
            (tmp / "AI晨报-2099-01-01.html").write_text(
                '<section id="p01">一</section><section id="p02">二</section>'
                '<p>共 15 版</p>', encoding="utf-8")
            empty = tmp / "site"
            empty.mkdir()
            sc.ROOT, sc.SITE = tmp, empty
            sc.check_pages()
    expect_red("全文版数与实际页数不符", 11, bad_pages, "共 15 版")

    # 第 5 / 13 项：这两条曾因「缺 fixture」「不便制造线上事故」而 SKIP，
    # 现在用真实特刊副本 + 本地 127.0.0.1 假站点补齐，各自先跑正向对照。
    run_terms_mutation()
    run_online_mutation(data)
    run_disclaimer_mutation()          # 第 12 项：声明的单一事实源
    run_rules_mutation()               # 第 14 项：规则文档与代码对账
    run_products_mutation()            # 第 14 项：产物清单小计分项与类别列一致
    run_ci_mutation()                  # 第 15 项：CI 工作流可解析
    run_secret_mutation()              # 安全：扫描器自己要被检查（含正向对照 + 打码）
    run_export_mutation()              # 安全：推送前复检自己要被检查
    run_apk_mutation()                 # 第 17 项：离线快照过期 / 改报没重打 / 幽灵条目
    run_manifest_mutation()            # 第 18 项：更新清单与包脱节 / App 不再检查
    run_export_coverage_mutation()     # 第 16 项：已入库必须等于将公开
    run_public_mutation()              # 第 19 项：公开面泄露访问码 / 卡片过期
    run_graph_mutations()              # 第 1 项：A10–A16（标记 / 主线 / 熔断 / 事实卡 / 版级来源）

    npass = sum(1 for s, _, _ in results if s == PASS)
    nfail = sum(1 for s, _, _ in results if s == FAIL)
    nskip = sum(1 for s, _, _ in results if s == SKIP)
    print("\n--- 结论：PASS %d / FAIL %d / SKIP %d ---" % (npass, nfail, nskip))
    print("SKIP 不计入通过：没测就是没测，报告要敢说；本次 SKIP %d 项。" % nskip)
    return 1 if nfail else 0


if __name__ == "__main__":
    raise SystemExit(run())
