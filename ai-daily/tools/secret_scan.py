#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""密钥与个人信息扫描：把「不许进仓库的东西」变成一条命令。

口径（选一个）：
    python tools/secret_scan.py                 # 已入库文件（默认；CI 跑这个）
    python tools/secret_scan.py --all           # 连未入库的也扫（看 .gitignore 有没有漏）
    python tools/secret_scan.py --dir <目录>     # 扫任意目录（导出树验收）
    python tools/secret_scan.py --history       # 扫全部提交历史（公开仓库必须 0）

两级判定：
    FAIL  已构成泄露：入口地址、云厂商密钥、私钥、硬编码口令、认证类文件
    WARN  只暴露环境：本机绝对路径、非真实邮箱式身份

唯一白名单是 `ai-daily/site/config.js`——入口地址的唯一事实源，只有它允许出现
`sharecode=`。`--strict` 关掉白名单，导出树必须用严格口径跑。

输出里的命中内容一律打码：扫描器自己不能变成新的泄露点。
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                       # ai-daily/
PROJECT = ROOT.parent

ALLOW_LOCAL = ("ai-daily/site/config.js",)

# (级别, 名称, 正则)
RULES = [
    ("FAIL", "入口地址", re.compile(r"sharecode=[A-Za-z0-9]{6,}")),
    ("FAIL", "AWS 密钥", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("FAIL", "GitHub 令牌", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("FAIL", "私钥", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("FAIL", "模型服务密钥", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("FAIL", "硬编码口令", re.compile(
        r"(?i)\b(?:password|passwd|keystorepass|storepass|secret|api_?key)\b"
        r"\s*[:=]\s*[\"'][^\"'\s]{6,}[\"']")),
    ("WARN", "本机绝对路径", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9._-]+")),
    ("WARN", "非真实邮箱", re.compile(r"\b[A-Za-z0-9._%+-]+@local\b")),
]

# 文件名即证据：见到就不该入库，不必读内容
BAD_NAMES = re.compile(r"(?i)\.(jks|keystore|p12|pfx|pem|key|env)$|^\.env")
BINARY_EXT = {".apk", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip",
              ".jar", ".dex", ".ico", ".woff", ".woff2", ".ttf", ".mp4"}

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".edge-1", ".edge-2"}


def redact(line, m):
    """保留上下文、抹掉命中本身：扫描器不能制造新的明文。"""
    s = line[:m.start()] + "«已隐去»" + line[m.end():]
    s = s.strip()
    return s if len(s) <= 120 else s[:117] + "..."


def is_binary(path):
    try:
        chunk = path.open("rb").read(8192)
    except OSError:
        return True
    return b"\x00" in chunk


def scan_file(path, rel, strict):
    """返回 [(级别, 名称, 位置, 摘要)]"""
    hits = []
    if BAD_NAMES.search(path.name):
        return [("FAIL", "认证类文件", rel, "文件名本身就是凭据，不该入库")]

    if path.suffix.lower() in BINARY_EXT or is_binary(path):
        # 二进制只在明确藏了入口地址时才报：图标里当然不会有 ASCII 源码
        try:
            raw = path.read_bytes()
        except OSError:
            return hits
        if b"sharecode=" in raw and not (not strict and rel in ALLOW_LOCAL):
            hits.append(("FAIL", "入口地址", rel + "（二进制）",
                         "文件里含 sharecode，删不掉也改不了，只能不进仓库"))
        return hits

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [("WARN", "读不了", rel, str(exc))]

    allowed = (not strict) and rel in ALLOW_LOCAL
    for no, line in enumerate(text.splitlines(), 1):
        for level, name, rx in RULES:
            m = rx.search(line)
            if not m:
                continue
            if allowed and name == "入口地址":
                continue
            hits.append((level, name, "%s:%d" % (rel, no), redact(line, m)))
    return hits


def walk(root):
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            yield p, p.relative_to(root).as_posix()


def scan_dir(root, strict=False):
    root = Path(root)
    hits, n = [], 0
    for p, rel in walk(root):
        n += 1
        hits.extend(scan_file(p, rel, strict))
    return hits, n


def scan_tracked(strict=False, repo=None):
    root = Path(repo or PROJECT)
    out = subprocess.run(["git", "ls-files", "-z"], cwd=str(root),
                         capture_output=True)
    if out.returncode != 0:
        raise SystemExit("不在 git 仓库里：%s" % root)
    files = [f for f in out.stdout.decode("utf-8", "replace").split("\0") if f]
    hits, n = [], 0
    for rel in files:
        p = root / rel
        if not p.is_file():
            continue                      # 已从索引删掉、磁盘还在的，不算入库
        n += 1
        hits.extend(scan_file(p, rel, strict))
    return hits, n


def scan_history(repo=None):
    """扫全部提交的 diff。

    不用 `git grep -E`：它走 POSIX ERE，不认 `(?:...)` 与 `(?i)`，模式会静默失效
    （实测第一次就扫出 0 命中——假绿的经典形态）。这里直接把 `git log -p` 的
    新增行喂给同一套 Python 正则，口径与工作区扫描完全一致。
    """
    p = subprocess.run(["git", "-c", "core.quotepath=false", "log",
                        "--all", "-p", "-U0", "--no-color", "--format=@@@%H"],
                       cwd=str(Path(repo or PROJECT)), capture_output=True)
    if p.returncode != 0:
        raise SystemExit("git log 失败：%s"
                         % p.stderr.decode("utf-8", "replace")[:200])

    hits, commits, cur, path = [], 0, "", ""
    for raw in p.stdout.decode("utf-8", "replace").splitlines():
        if raw.startswith("@@@"):
            cur, commits = raw[3:13], commits + 1
            continue
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            path = path[2:] if path.startswith("b/") else path
            continue
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        body = raw[1:]
        for level, name, rx in RULES:
            m = rx.search(body)
            if m:
                hits.append((level, name, "%s@%s" % (path, cur), redact(body, m)))
                break
    return hits, commits


def report(title, hits, scanned, unit="文件"):
    if title:
        print(title)
    fails = [h for h in hits if h[0] == "FAIL"]
    warns = [h for h in hits if h[0] == "WARN"]
    seen, shown = set(), 0
    for level, name, where, detail in fails + warns:
        key = (level, name, where)
        if key in seen:
            continue
        seen.add(key)
        if shown >= 30:
            continue
        shown += 1
        print("  %-4s %-10s %s" % (level, name, where))
        if detail:
            print("       %s" % detail)
    if len(seen) > shown:
        print("  ... 还有 %d 处未展开（去重后共 %d 处）" % (len(seen) - shown, len(seen)))
    print("-" * 66)
    print("结论：扫描 %d 个%s，%d FAIL / %d WARN"
          % (scanned, unit, len(fails), len(warns)))
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="", help="扫指定目录（导出树验收）")
    ap.add_argument("--all", action="store_true", help="连未入库文件一起扫")
    ap.add_argument("--history", action="store_true", help="扫全部提交历史")
    ap.add_argument("--strict", action="store_true", help="关掉 config.js 白名单")
    ap.add_argument("--repo", default="", help="换一个 git 仓库（导出树验收）")
    a = ap.parse_args()

    if a.history:
        hits, n = scan_history(a.repo or None)
        print("密钥与个人信息扫描 · 提交历史（%d 个提交）" % n)
        return report("", hits, n, "提交")

    if a.dir:
        root = Path(a.dir).resolve()
        if not root.is_dir():
            raise SystemExit("不是目录：%s" % root)
        hits, n = scan_dir(root, a.strict)
        return report("密钥与个人信息扫描 · 目录 %s" % root, hits, n)

    if a.all:
        hits, n = scan_dir(a.repo or PROJECT, a.strict)
        return report("密钥与个人信息扫描 · 工作区全部文件", hits, n)

    hits, n = scan_tracked(a.strict, a.repo or None)
    return report("密钥与个人信息扫描 · 已入库文件", hits, n)


if __name__ == "__main__":
    sys.exit(main())
