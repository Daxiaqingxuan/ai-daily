# -*- coding: utf-8 -*-
"""
交付前自检示例 —— 配套《AI Agent 运用完全教程》第 2 章

用法：
    python validate.py                       # 默认检查同级工作区的 ai-daily/
    python validate.py D:/path/to/ai-daily   # 指定项目根目录

设计原则（比检查项本身更重要）：
  1. 规则是「可执行的代码」，不是写在规范里给人读的一句话。
  2. 每条断言要能定位到具体文件、给出具体数字，失败信息可直接回传给 agent。
  3. 退出码 0 / 1 决定下游动作：0 才允许发布，1 就带着失败原文让 agent 重试。
  4. 断言要精确，避免误报；写断言的过程会逼你把含糊的规则说清楚。
"""
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "ai-daily"

results = []


def check(group, name, ok, detail=""):
    results.append((group, name, bool(ok), detail))
    mark = "OK  " if ok else "FAIL"
    line = f"  [{mark}] {name}"
    if detail:
        line += f"  ·  {detail}"
    print(line)


def md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def body_text(html):
    """只留「正文」：脚本、样式、代码块不算正文，避免命令行示例里的引号造成误报。"""
    t = re.sub(r"<(script|style|code|pre)\b[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"<[^>]+>", " ", t)


def issue_from(text):
    m = re.search(r"第\s*(\d{3})\s*期", text)
    return m.group(1) if m else ""


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_ROOT
    site = root / "site"
    print(f"检查项目：{root}\n")

    # ---------- A. 报纸结构 ----------
    print("[A] 每期报纸的结构")
    papers = sorted(root.glob("AI晨报-*.html"))
    check("A", "至少存在一期报纸", bool(papers), f"共 {len(papers)} 期")
    if not papers:
        return finish()

    for p in papers:
        t = p.read_text(encoding="utf-8")
        tag = p.name
        n_sec = len(re.findall(r"<section\b", t))
        n_razor = len(re.findall(r'class="razor["\s]', t))
        n_plain = len(re.findall(r'class="plain["\s]', t))
        check("A", f"{tag} · 15 个版块", n_sec == 15, f"实测 {n_sec}")
        check("A", f"{tag} · 15 条锐评", n_razor == 15, f"实测 {n_razor}")
        check("A", f"{tag} · 5 个说人话框", n_plain == 5, f"实测 {n_plain}")
        check("A", f"{tag} · 共 15 版口径唯一",
              set(re.findall(r"共\s*(\d+)\s*版", t)) == {"15"},
              str(sorted(set(re.findall(r"共\s*(\d+)\s*版", t)))))
        check("A", f"{tag} · viewport 存在", 'name="viewport"' in t)

        title = re.search(r"<title>(.*?)</title>", t, re.S)
        no = issue_from(title.group(1)) if title else ""
        col = re.search(r'class="colophon"[^>]*>(.{0,400})', t, re.S)
        tail = issue_from(col.group(1)) if col else ""
        check("A", f"{tag} · 报头/报尾期号一致", bool(no) and no == tail,
              f"报头 {no or '—'} / 报尾 {tail or '—'}")

        # 规范写的是「正文只用中文引号」。这里必须排除 code/pre，否则命令行示例会误报。
        n_quote = body_text(t).count('"')
        check("A", f"{tag} · 正文无半角直引号", n_quote == 0, f"实测 {n_quote}")

    # ---------- B. 索引一致性 ----------
    print("\n[B] issues.js 与报纸是否对得上")
    idx = site / "issues.js"
    check("B", "索引文件存在", idx.exists())
    if not idx.exists():
        return finish()
    m = re.search(r"window\.AI_DAILY_ISSUES\s*=\s*(\{.*\})\s*;", idx.read_text(encoding="utf-8"), re.S)
    check("B", "索引可解析为 JSON", bool(m))
    if not m:
        return finish()
    data = json.loads(m.group(1))
    issues = data.get("issues", [])
    check("B", "索引与报纸期数一致", len(issues) == len(papers),
          f"索引 {len(issues)} / 文件 {len(papers)}")
    check("B", "索引按日期倒序",
          [x["date"] for x in issues] == sorted((x["date"] for x in issues), reverse=True))
    check("B", "generatedAt 非空", bool(data.get("generatedAt")), str(data.get("generatedAt")))
    for it in issues:
        f = site / it["file"]
        src = root / it["file"]
        check("B", f"{it['date']} · 报纸已同步进 site/", f.exists() and src.exists(),
              f"site/ {'有' if f.exists() else '缺'} · 源 {'有' if src.exists() else '缺'}")
        if f.exists() and src.exists():
            a, b = md5(f), md5(src)
            check("B", f"{it['date']} · 与源文件字节一致", a == b,
                  "md5 相同" if a == b else f"site {a[:8]} ≠ 源 {b[:8]}")
        check("B", f"{it['date']} · 版数为 15", it.get("pages") == 15, str(it.get("pages")))
        if src.exists():
            title = re.search(r"<title>(.*?)</title>", src.read_text(encoding="utf-8"), re.S)
            check("B", f"{it['date']} · 期号与报纸一致",
                  issue_from(title.group(1) if title else "") == it.get("issue"))

    # ---------- C. 入口页防回归 ----------
    print("\n[C] 入口页：把踩过的坑固定成断言")
    entry = site / "index.html"
    check("C", "入口页存在", entry.exists())
    if entry.exists():
        e = entry.read_text(encoding="utf-8")
        check("C", "hidden 兜底仍在（防 .btn 覆盖 hidden 复发）",
              re.search(r"\[hidden\]\s*\{[^}]*display\s*:\s*none", e) is not None)
        check("C", "读取索引的 script 标签仍在", 'src="issues.js"' in e)
        check("C", "APK 刷新按钮默认隐藏", re.search(r'id="apkBtn"\s+hidden', e) is not None)
    return finish()


def finish():
    bad = [r for r in results if not r[2]]
    total = len(results)
    print("\n" + "=" * 52)
    print(f"结果：{total - len(bad)} / {total} 条通过")
    if bad:
        print("未通过（把这些原文回传给 agent，让它自己改）：")
        for g, n, _, d in bad:
            print(f"  · [{g}] {n} {d}")
        print("=" * 52)
        return 1
    print("全部通过 → 允许进入发布步骤")
    print("=" * 52)
    return 0


if __name__ == "__main__":
    sys.exit(main())
