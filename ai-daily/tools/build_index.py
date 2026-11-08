# -*- coding: utf-8 -*-
"""
AI 晨报入口 · 索引生成器

用法：python ai-daily/tools/build_index.py

做三件事：
  1. 扫描 ai-daily/ 下所有 AI晨报-YYYY-MM-DD.html，解析日期、期号、版数、头条、导语；
  2. 把每期报纸复制到 ai-daily/site/（发布目录，保持干净，不带浏览器配置等杂物）；
  3. 生成 ai-daily/site/issues.js，供入口页 index.html 读取。

每天晨报生成后运行一次，桌面图标与手机入口就会同步出现新一期、可翻往期。
"""
from pathlib import Path
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                 # ai-daily/
SITE = ROOT / "site"               # 发布目录
# 只扫 ai-daily/ 根目录。成品位置在 AGENTS.md §1 里唯一确定，
# 不再保留任何外部兜底路径：散落在别处的一期视为违规，不静默搬运。
SCAN_DIR = ROOT
NAME_RE = re.compile(r"^AI晨报-(\d{4}-\d{2}-\d{2})\.html$")
SPECIAL_RE = re.compile(r"^AI晨报-(\d{4}-\d{2}-\d{2})-特刊\.html$")
WEEK = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def strip_tags(raw: str) -> str:
    raw = re.sub(r"<br\s*/?>", " · ", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def first(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.S | re.I)
    return strip_tags(m.group(1)) if m else default


def parse(path: Path, date: str) -> dict:
    text = path.read_text(encoding="utf-8")
    title = first(r"<title>(.*?)</title>", text, "AI 晨报")
    m_issue = re.search(r"第\s*(\d+)\s*期", title)
    m_pages = re.search(r"共\s*(\d+)\s*版", title)
    y, mo, d = (int(x) for x in date.split("-"))
    dt = datetime.date(y, mo, d)
    return {
        "date": date,
        "dateCn": f"{y}年{mo}月{d}日",
        "dateShort": f"{mo}月{d}日",
        "weekday": WEEK[dt.weekday()],
        "issue": m_issue.group(1) if m_issue else "",
        "isSpecial": False,
        "issueLabel": f"第 {m_issue.group(1)} 期" if m_issue else "本期",
        "pages": int(m_pages.group(1)) if m_pages else 0,
        "headline": first(r"<h2[^>]*>(.*?)</h2>", text, "本期头条"),
        "deck": first(r'<p class="deck"[^>]*>(.*?)</p>', text, ""),
        "kicker": first(r'<div class="kicker"[^>]*>(.*?)</div>', text, ""),
        "file": path.name,
        "size": path.stat().st_size,
    }


def load_previous() -> dict:
    """读上次生成的 issues.js，用于保持 generatedAt 稳定（幂等）。"""
    p = SITE / "issues.js"
    try:
        txt = p.read_text(encoding="utf-8")
        body = txt[txt.index("{"): txt.rindex("}") + 1]
        data = json.loads(body)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def parse_special(path: Path, date: str) -> dict:
    """特刊按「当天第 2 版」编号（003-2），和正刊一起排进 issues。

    2026-11-06 改：早先特刊只放在 specials 里，读者在往期回顾里看不到它，
    像一条附注而不是一期报纸。现在它与正刊同列，只是编号带 -2。
    """
    text = path.read_text(encoding="utf-8")
    title = first(r"<title>(.*?)</title>", text, "AI 晨报 · 特刊")
    m_issue = re.search(r"第\s*(\d{3}(?:-\d+)?)\s*期", title)
    m_pages = re.search(r"共\s*(\d+)\s*版", title)
    y, mo, d = (int(x) for x in date.split("-"))
    issue = m_issue.group(1) if m_issue else ""
    return {
        "date": date,
        "dateCn": f"{y}年{mo}月{d}日",
        "dateShort": f"{mo}月{d}日",
        "weekday": WEEK[datetime.date(y, mo, d).weekday()],
        "issue": issue,
        "label": "特刊",
        "isSpecial": True,
        "issueLabel": (f"第 {issue} 期" if issue else "特刊"),
        "headline": first(r"<h2[^>]*>(.*?)</h2>", text, "特刊"),
        "deck": first(r'<p class="deck"[^>]*>(.*?)</p>', text, ""),
        "pages": int(m_pages.group(1)) if m_pages else 0,
        "file": f"special/{date}.html",
        "manifest": f"special/{date}.json",
        "size": path.stat().st_size,
    }


def sync_file(src: Path, dst: Path) -> bool:
    """内容一致就不动（保留 mtime，保证 manifest 幂等）。返回是否写过。"""
    if dst.exists() and dst.stat().st_size == src.stat().st_size \
            and dst.read_bytes() == src.read_bytes():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def refresh_apk() -> None:
    """索引落盘后重打安卓包，让离线兜底自动跟到当期。

    为什么挂在这里而不是靠人记：这是「纯自动更新」里最容易漏的一步——
    漏了线上完全正常，只有装过 App 的人离线打开看到旧报，没人会主动发现。
    内容没变时 --auto 会自己跳过；缺工具链返回 2，换台机器也不阻塞出报。
    """
    script = HERE / "build_apk.py"
    if not script.exists():
        return
    try:
        p = subprocess.run([sys.executable, str(script), "--auto"],
                           capture_output=True, timeout=900)
    except Exception as exc:
        print("[build_index] APK 重打没跑起来（%s）；selfcheck 第 17 项会拦发布" % exc)
        return
    out = (p.stdout or b"").decode("utf-8", "replace")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    head = next((l for l in lines if l.startswith(("版本：", "SKIP"))), "")
    if p.returncode == 0:
        print("[build_index] 离线包：%s" % (head or "已就绪"))
    elif p.returncode == 2:
        print("[build_index] 离线包跳过：本机没有 Android 工具链（不阻塞出报）")
    else:
        print("[build_index] ⚠ 离线包重打失败（退出码 %d）——selfcheck 第 17 项会拦住发布"
              % p.returncode)
        for l in lines[-3:]:
            print("    " + l)


def refresh_public() -> None:
    """索引落盘后重生成公开导读面（GitHub Pages 的 /docs）。

    和 refresh_apk 同一个道理：这一步漏了线上完全正常，只有访客看到旧卡片，
    没有任何人会主动发现。所以挂在链路里，不靠记性。生成是幂等的，内容没变
    就只有 mtime 变化（写盘仍会写，故调用方不必判重）。
    """
    script = HERE / "build_public.py"
    if not script.exists():
        return
    try:
        p = subprocess.run([sys.executable, str(script)],
                           capture_output=True, timeout=300)
    except Exception as exc:
        print("[build_index] 公开面没生成（%s）；selfcheck 第 19 项会拦发布" % exc)
        return
    out = (p.stdout or b"").decode("utf-8", "replace")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if p.returncode == 0:
        head = next((l for l in lines if l.startswith("[公开面] 期次")), "")
        print("[build_index] 公开面：%s" % (head.replace("[公开面] ", "") or "已就绪"))
    else:
        print("[build_index] ⚠ 公开面生成失败（退出码 %d）——selfcheck 第 19 项会拦住发布"
              % p.returncode)
        for l in (lines or ["(无输出)"])[-3:]:
            print("    " + l)


def main() -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    found = {}
    specials_src = {}
    for path in sorted(SCAN_DIR.glob("AI晨报-*.html")):
        m = NAME_RE.match(path.name)
        if m:
            found[m.group(1)] = path
            continue
        m = SPECIAL_RE.match(path.name)
        if m:
            specials_src[m.group(1)] = path
    papers = sorted(found.items(), reverse=True)   # 最新在前

    # 日期闸门：报纸日期必须是出报当天。提前拼好的「明天的报」不进索引——
    # 2026-11-06 踩过：004 标着 11-07，内容却全是 6 日的，桌面端打开就是假日期。
    today = os.environ.get("AI_DAILY_TODAY", "").strip() or datetime.date.today().isoformat()
    future = sorted(d for d in list(found) + list(specials_src) if d > today)
    if future:
        for d in future:
            print(f"  ! {d} 的报纸日期晚于今天（{today}），不收录、不同步")
        print("    报纸日期必须是出报当天；预热稿请放 ai-daily/_drafts/，不要落在根目录")
        found = {d: p for d, p in found.items() if d <= today}
        specials_src = {d: p for d, p in specials_src.items() if d <= today}
    papers = sorted(found.items(), reverse=True)

    issues = []
    for date, path in papers:
        issues.append(parse(path, date))
        sync_file(path, SITE / path.name)

    specials = []
    for date, path in sorted(specials_src.items(), reverse=True):
        item = parse_special(path, date)
        specials.append(item)
        if sync_file(path, SITE / item["file"]):
            print(f"  + 特刊已同步到 {item['file']}")

    # 特刊与正刊同列：往期回顾是一份序列，不该有一期躲在另一个区里。
    # 排序键 (日期, 期号) 倒序：同一天里 003-2 排在 003 上面（后出的在上）。
    issues.extend(specials)
    issues.sort(key=lambda it: (it["date"], it["issue"] or ""), reverse=True)

    main_no = {it["date"]: it["issue"] for it in issues if not it.get("isSpecial")}
    for sp in specials:
        base = main_no.get(sp["date"], "")
        if base and sp["issue"] and not sp["issue"].startswith(base + "-"):
            print(f"  ! 特刊 {sp['date']} 编号 {sp['issue']} 与当天正刊 {base} 不衔接"
                  f"（当天的第 2 版应写 {base}-2）")

    # 每期（含特刊）都生成 manifest：reader 与 curl 都拿得到「这期是否完整」
    try:
        sys.path.insert(0, str(HERE))
        import make_manifest
        for date, path in papers:
            data, _ = make_manifest.write_manifest(
                path, SITE / (path.stem + ".json"), "daily")
            if not data["ok"]:
                print("  ! %s manifest 自检未过：%s" % (
                    date, ", ".join(k for k, v in data["checks"].items() if v is False)))
        for item in specials:
            data, _ = make_manifest.write_manifest(
                SITE / item["file"], SITE / item["manifest"], "special")
            if not data["ok"]:
                print("  ! %s 特刊 manifest 自检未过：%s" % (
                    item["date"], ", ".join(k for k, v in data["checks"].items() if v is False)))
    except Exception as exc:
        print("  ! manifest 生成跳过（%s）" % exc)

    # site/ 里有、源里没有的期次：只报告，不删（删除属于破坏性操作）
    keep = {v.name for v in found.values()} | {p.name for p in specials_src.values()}
    orphans = sorted(p.name for p in SITE.glob("AI晨报-*.html") if p.name not in keep)

    prev = load_previous()
    if prev.get("issues") == issues and prev.get("specials") == specials \
            and prev.get("generatedAt"):
        generated_at = prev["generatedAt"]          # 内容没变，时间戳不刷新
    else:
        generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    payload = {
        "generatedAt": generated_at,
        "issues": issues,
        "specials": specials,
    }
    js = ("/* 由 tools/build_index.py 自动生成，请勿手工编辑 */\n"
          "window.AI_DAILY_ISSUES = " +
          json.dumps(payload, ensure_ascii=False, indent=2) + ";\n")
    (SITE / "issues.js").write_text(js, encoding="utf-8")

    print(f"[build_index] 共 {len(issues)} 期（含 {len(specials)} 份特刊），"
          f"索引已写入 {SITE / 'issues.js'}（更新于 {generated_at}）")
    for it in issues:
        mark = "*" if it.get("isSpecial") else "-"
        print(f"  {mark} {it['date']} {it['issueLabel']} 共{it['pages']}版 | {it['headline'][:36]}")
    if orphans:
        print("  ! site/ 里有多余期次（源已不存在，未删除，请人工确认）：" + "、".join(orphans))
    if not issues:
        print("  ! 没找到 AI晨报-*.html，请先生成晨报。")

    # 状态机埋点：只记当期（默认今天）；重扫历史期不参与状态判定
    if today in found:
        try:
            sys.path.insert(0, str(HERE))
            import status as status_mod
            # 状态机记的是「今天的正刊」；特刊是当天的第 2 版，不占期次位
            issue = next((it["issue"] for it in issues
                          if it["date"] == today and not it.get("isSpecial")), "")
            status_mod.note(today, issue, "index", True,
                            "%d 期（含 %d 特刊）已收录" % (len(issues), len(specials)))
            print("[build_index] 状态记录：index=OK")
        except Exception as exc:
            print("[build_index] 状态记录跳过（%s）" % exc)

    # 出报链路的一环：索引变了就把离线包也跟到当期（幂等，内容没变直接跳过）
    refresh_apk()

    # 同理：公开面（免访问码的导读 + 事实卡）也要跟到当期
    refresh_public()


if __name__ == "__main__":
    main()
