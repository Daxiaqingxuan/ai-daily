#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境体检：换一台机器，先跑这一条，再谈出报。

为什么要有这个脚本：出报主链路只用标准库，但周边脚本（图标、二维码、APK、
布局探针）各有各的依赖；而「克隆下来就跑不起来」的真实原因往往不是缺包，
是**行尾被 Git 改过**——自检按 sha256 逐字节对账，一改就红，看起来像内容漂移。

所以这里查三类事：
1. 硬门槛：Python 版本、脚本能否编译（语法层面能不能跑）；
2. 软依赖：Pillow / qrcode / Node / 浏览器（缺了只影响辅助脚本）；
3. 字节一致性：工作区文件是否还和凭证里记的大小一致（查行尾转换）。

只用标准库。退出码：有 FAIL 返回 1，只有 WARN 返回 0。
"""
import argparse
import json
import os
import py_compile
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # ai-daily/
REPO = ROOT.parent
TOOLS = ROOT / "tools"
MIN_PY = (3, 10)

OK, WARN, FAIL = "OK", "WARN", "FAIL"
rows = []


def add(level, name, detail):
    rows.append((level, name, detail))


def check_python():
    v = sys.version_info
    cur = "%d.%d.%d" % (v[0], v[1], v[2])
    need = "%d.%d" % MIN_PY
    if (v[0], v[1]) >= MIN_PY:
        add(OK, "Python 版本", "%s（需 ≥ %s）" % (cur, need))
    else:
        add(FAIL, "Python 版本", "%s 太旧，需 ≥ %s" % (cur, need))


def check_compile():
    bad = []
    files = sorted(TOOLS.glob("*.py"))
    tmp = tempfile.mkdtemp()
    for f in files:
        try:
            py_compile.compile(str(f), cfile=os.path.join(tmp, f.stem + ".pyc"),
                              doraise=True)
        except Exception as exc:
            bad.append("%s（%s）" % (f.name, str(exc).splitlines()[0][:60]))
    shutil.rmtree(tmp, ignore_errors=True)
    if bad:
        add(FAIL, "脚本可编译", "%d 个脚本有语法错误：%s" % (len(bad), "；".join(bad[:3])))
    else:
        add(OK, "脚本可编译", "%d 个脚本语法正常" % len(files))


def check_optional():
    lack = []
    for mod, why in (("PIL", "图标 / 二维码 / APK"), ("qrcode", "二维码卡片")):
        try:
            __import__(mod)
        except Exception:
            lack.append("%s（%s）" % (mod, why))
    if lack:
        add(WARN, "可选依赖", "未装 %s；只影响辅助脚本，出报不需要"
            % "、".join(lack))
    else:
        add(OK, "可选依赖", "Pillow / qrcode 都在")


def check_node():
    node = shutil.which("node")
    if node:
        add(OK, "Node", node)
    else:
        add(WARN, "Node", "没找到 node；tools/probe.js（布局探针）跳过，不影响出报")


def find_browser():
    env = os.environ.get("CHROME_PATH")
    cands = []
    if env:
        cands.append(env)
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
            if not base:
                continue
            cands += [
                os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
            ]
    elif sys.platform == "darwin":
        cands += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    else:
        for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
            p = shutil.which(name)
            if p:
                cands.append(p)
    for c in cands:
        if c and os.path.exists(c):
            return c
    for name in ("msedge", "chrome", "google-chrome"):
        p = shutil.which(name)
        if p:
            return p
    return ""


def check_browser():
    exe = find_browser()
    if exe:
        add(OK, "浏览器（探针用）", exe)
    else:
        add(WARN, "浏览器（探针用）",
            "没找到 Edge / Chrome；tools/probe.js 量不了布局，不影响出报")


def check_line_endings():
    """工作区文件大小 vs 凭证记录。不一致基本就是 checkout 改了行尾。"""
    if not (REPO / ".gitattributes").exists():
        add(FAIL, "行尾固定", "仓库根缺 .gitattributes（clone 时会把 CRLF 混排文件改字节）")
        return
    text = (REPO / ".gitattributes").read_text(encoding="utf-8", errors="ignore")
    if "-text" not in text:
        add(FAIL, "行尾固定", ".gitattributes 没有 `* -text`，行尾仍会被转换")
        return
    jsons = sorted((ROOT / "site").glob("AI晨报-*.json"))
    if not jsons:
        add(WARN, "行尾固定", "找不到任何期次凭证，跳过大小对账")
        return
    mf = json.loads(jsons[-1].read_text(encoding="utf-8"))
    p = ROOT / mf.get("path", "")
    want = int(mf.get("bytes") or 0)
    if not p.exists():
        add(WARN, "行尾固定", "凭证指向的成品不存在：%s" % p.name)
        return
    got = p.stat().st_size
    if got == want:
        add(OK, "行尾固定", "%s 字节数与凭证一致（%d）" % (p.name, got))
    else:
        add(FAIL, "行尾固定",
            "%s 实际 %d 字节，凭证记 %d——多半是 clone 时行尾被转换，"
            "确认仓库根有 `* -text` 后重新检出" % (p.name, got, want))


def check_encoding():
    fs = sys.getfilesystemencoding()
    lvl = OK if fs.lower().replace("-", "") in ("utf8",) else WARN
    add(lvl, "文件名编码", "filesystemencoding=%s%s"
        % (fs, "" if lvl == OK else "；中文文件名可能出问题，建议 UTF-8 区域设置"))


def check_data():
    d = ROOT / "parts"
    issues = sorted(x for x in d.iterdir() if x.is_dir() and x.name.isdigit()) if d.is_dir() else []
    if not issues:
        add(WARN, "期次目录", "parts/ 下没有 MMDD 目录")
        return
    latest = issues[-1]
    lack = [n for n in ("00-thread.json", "00-facts.json", "00-blocks.json", "00-sources.json")
            if not (latest / n).exists()]
    if lack:
        add(WARN, "期次数据", "parts/%s 缺 %s（004 期起的正刊会被断言拦下）"
            % (latest.name, "、".join(lack)))
    else:
        add(OK, "期次数据", "parts/%s 主线 / 事实卡 / 板块来源 / 信源表齐全" % latest.name)


def main():
    ap = argparse.ArgumentParser(description="AI 晨报环境体检")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args()

    check_python()
    check_compile()
    check_optional()
    check_node()
    check_browser()
    check_line_endings()
    check_encoding()
    check_data()

    n_fail = sum(1 for r in rows if r[0] == FAIL)
    n_warn = sum(1 for r in rows if r[0] == WARN)
    if a.json:
        print(json.dumps({
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "items": [{"level": l, "name": n, "detail": d} for l, n, d in rows],
            "ok": len(rows) - n_fail - n_warn, "warn": n_warn, "fail": n_fail,
        }, ensure_ascii=False, indent=2))
        return 1 if n_fail else 0

    print("AI 晨报环境体检 · Python %s · %s"
          % (sys.version.split()[0], sys.platform))
    print("-" * 66)
    for l, n, d in rows:
        print("%-4s %-16s %s" % (l, n, d))
    print("-" * 66)
    print("结论：%d 项，%d OK / %d WARN / %d FAIL"
          % (len(rows), len(rows) - n_fail - n_warn, n_warn, n_fail))
    if n_fail:
        print("有 FAIL：先解决再出报。")
    elif n_warn:
        print("只有 WARN：主链路可以走，辅助脚本按需补装。")
    else:
        print("全部通过。")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
