#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把私有工作区导出成一个可公开的仓库。

为什么不能直接 push：
  这个仓库的历史里有明文入口地址、内嵌地址的 APK（classes.dex 与
  assets/site/config.js 各一份）、二维码与 .workbuddy 记忆。**历史不可改写**，
  删当前文件没用。唯一干净的路径是「白名单复制 → 占位注入 → 单次初始提交」。

三步：
  1. 白名单复制：只认下面的 ALLOW，新冒出来的目录默认不进（黑名单是漏的）。
  2. 占位注入：入口地址从 site/config.js 现取，替换成 __SITE_URL__ 后写入。
     脚本自己不留明文，也就不存在「导出工具成为新的泄露点」。
  3. 三道验收：严格密钥扫描（不做白名单豁免）、禁入路径与二进制、可选单提交演练。

用法：
    python ai-daily/tools/export_public.py --dry-run              # 只看清单
    python ai-daily/tools/export_public.py                       # 写到 ../ai-daily-public
    python ai-daily/tools/export_public.py --out ../ai-daily-public --force
    python ai-daily/tools/export_public.py --git-init --name "…" --email "…"
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                       # ai-daily/
PROJECT = ROOT.parent

sys.path.insert(0, str(HERE))
import secret_scan as S                  # noqa: E402

# ---- 白名单：只复制这里点到的 ----
ALLOW_FILES = {
    "LICENSE",
    "LICENSE-CONTENT.md",
    "NOTICE.md",
    "README.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    ".gitignore",
    ".gitattributes",
    ".github/workflows/ci.yml",
    ".github/dependabot.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/content_correction.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    "项目框架与规则.md",
    "产物清单.md",
    "ai-daily/AGENTS.md",
    "ai-daily/requirements.txt",
    "ai-daily/提案台账.md",
    "ai-daily/apk/AndroidManifest.xml",
}
ALLOW_DIRS = (
    "ai-daily/tools",
    "ai-daily/parts",
    "ai-daily/site",
    "ai-daily/apk/src",
    "learn-agent",
    "docs",                              # README 截图：展示用，不含入口地址
)
# 每期成品在 ai-daily/ 根目录，是这个项目的「源」；site/ 只是副本。
ALLOW_RE = (
    re.compile(r"^ai-daily/AI晨报-[\w.\-]+\.html$"),
)

# ---- 排除：白名单目录里也不带走的东西 ----
EXCLUDE_FILES = {
    "learn-agent/demo/status.json",      # demo 的运行态
}
EXCLUDE_DIRS = (
    "ai-daily/_drafts",
    "ai-daily/_process",
    "ai-daily/shots",
    "ai-daily/.local",
    "ai-daily/tools/.boot-state",
    "ai-daily/apk/.build",
    "ai-daily/parts/1106/dist",
    "learn-agent/demo/stages",
    "__pycache__",
)
EXCLUDE_SUFFIX = (".apk", ".pyc", ".log", ".idsig", ".tmp")
EXCLUDE_NAME_RE = re.compile(r"^AI晨报-.*\.png$")       # 二维码卡片：图里就是入口地址
BINARY_SUFFIX = {".png", ".jpg", ".ico", ".woff", ".woff2", ".ttf", ".mp4"}

PLACEHOLDER = "__SITE_URL__"
PLACEHOLDER_HOST = "https://your-site.example/"

# README 顶部的 CI 徽章要指向真实仓库。仓库还不存在时无从填起，所以同样走占位：
# 开发树里留 __REPO_SLUG__，导出时用 --repo owner/name 注入，推送前复检会拦残留。
REPO_PLACEHOLDER = "__REPO_SLUG__"


def repo_slug():
    """`owner/name`。没配就返回空串——导出照做，复检会明确报「徽章还指着占位」。"""
    slug = os.environ.get("AI_DAILY_REPO", "").strip().strip("/")
    return slug if slug.count("/") == 1 and " " not in slug else ""


# 只在这几个文件里替换。全局替换会把 export_public.py 自己的常量名与
# AGENTS.md 的说明也换掉——公开树里的脚本会当场自毁（常量变成 owner/name）。
REPO_FILES = {"README.md", "CHANGELOG.md"}


def repo_left(out):
    """导出树里还剩多少处 __REPO_SLUG__（只看该注入的那几个文件）。"""
    mark = REPO_PLACEHOLDER.encode("utf-8")
    return sum((out / rel).read_bytes().count(mark)
               for rel in REPO_FILES if (out / rel).is_file())


def site_url():
    """读入口地址。已经是占位就返回空串——没有明文可注入，导出照做（演练 / 二次导出）。"""
    p = (ROOT / "site" / "config.js")
    m = re.search(r'\bsiteUrl\s*:\s*"([^"]*)"', p.read_text(encoding="utf-8"))
    url = (m.group(1).strip() if m else "")
    if not url or PLACEHOLDER in url:
        return ""
    return url


def allowed(rel):
    if rel in ALLOW_FILES:
        return True
    if any(rx.match(rel) for rx in ALLOW_RE):
        return True
    return any(rel == d or rel.startswith(d + "/") for d in ALLOW_DIRS)


def excluded(rel):
    if rel in EXCLUDE_FILES:
        return "运行态文件"
    for d in EXCLUDE_DIRS:
        if rel == d or rel.startswith(d + "/"):
            return "目录" + d
    name = rel.rsplit("/", 1)[-1]
    if name.lower().endswith(EXCLUDE_SUFFIX):
        return "后缀 " + name.rsplit(".", 1)[-1]
    if EXCLUDE_NAME_RE.match(name):
        return "二维码卡片"
    return ""


def collect():
    picked, skipped = [], []
    for dirpath, dirnames, filenames in os_walk(PROJECT):
        rel_dir = Path(dirpath).relative_to(PROJECT).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir + "/"
        for fn in sorted(filenames):
            rel = rel_dir + fn
            if not allowed(rel):
                skipped.append((rel, "不在白名单"))
                continue
            why = excluded(rel)
            if why:
                skipped.append((rel, why))
                continue
            picked.append(rel)
    return sorted(picked), skipped


# 这些目录名一律不进（同时在 walk 时剪掉，避免把 .build 里几千个文件扫一遍）
SKIP_NAMES = {".git", "__pycache__", "node_modules", ".build", "stages",
              "_process", "_drafts", "shots", ".local", "dist", ".boot-state"}


def os_walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_NAMES)
        yield dirpath, dirnames, filenames


def inject(data, url):
    """把入口地址换成占位符；只对 UTF-8 文本生效。无明文时原样返回。"""
    if not url:
        return data, 0
    if url.encode("utf-8") not in data:
        return data, 0
    origin = (url.split("?", 1)[0].rstrip("/") + "/").encode("utf-8")
    n = data.count(url.encode("utf-8"))
    data = data.replace(url.encode("utf-8"), PLACEHOLDER.encode("utf-8"))
    n2 = data.count(origin)
    data = data.replace(origin, PLACEHOLDER_HOST.encode("utf-8"))
    return data, n + n2


def export(out, force, dry):
    picked, skipped = collect()
    url = site_url()
    print("导出源：%s" % PROJECT)
    print("目标  ：%s" % out)
    print("白名单命中 %d 个文件，跳过 %d 个" % (len(picked), len(skipped)))

    if dry:
        for rel in picked:
            print("  + %s" % rel)
        if skipped:
            print("  —— 跳过 %d 个，按原因归并：" % len(skipped))
            reasons = {}
            for rel, why in skipped:
                reasons.setdefault(why, []).append(rel)
            for why, rels in sorted(reasons.items()):
                print("     %-12s %d 个，如 %s" % (why, len(rels), rels[0]))
        return 0

    if out.exists():
        if not force:
            raise SystemExit("目标已存在：%s（加 --force 覆盖）" % out)
        if out.resolve() in (PROJECT.resolve(), PROJECT.resolve().parent):
            raise SystemExit("拒绝清空：目标是项目自身或其父目录")
        shutil.rmtree(out)
    out.mkdir(parents=True)

    n_inject = 0
    slug = repo_slug()
    n_repo = 0
    for rel in picked:
        src, dst = PROJECT / rel, out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        if src.suffix.lower() not in BINARY_SUFFIX:
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                pass
            else:
                data, k = inject(data, url)
                n_inject += k
                if slug and rel in REPO_FILES:
                    mark = REPO_PLACEHOLDER.encode("utf-8")
                    n_repo += data.count(mark)
                    data = data.replace(mark, slug.encode("utf-8"))
        dst.write_bytes(data)

    print("占位注入：%d 处（%s）" % (
        n_inject,
        "入口地址 → " + PLACEHOLDER if url else "源里已是占位，无需注入"))
    if slug:
        print("           %d 处（仓库地址 → %s）" % (n_repo, slug))
    elif repo_left(out):
        print("           ！%s 未注入：README 的 CI 徽章是坏的（推送前用 "
              "--repo owner/name 重导）" % REPO_PLACEHOLDER)
    return verify(out)


def verify(out):
    """导出树的三道验收。任何一道不过就不许往外说「可以发了」。"""
    ok = True

    hits, n = S.scan_dir(out, strict=True)
    hard = [h for h in hits if h[0] == "FAIL"]
    warn = [h for h in hits if h[0] == "WARN"]
    print("\n[1/3] 严格密钥扫描：%d 个文件，%d FAIL / %d WARN" % (n, len(hard), len(warn)))
    for h in hard[:10]:
        print("      %s %s %s" % (h[0], h[1], h[2]))
    if hard:
        ok = False

    # 禁入物：导出后不应存在的路径/后缀
    bad = []
    for p in out.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(out).as_posix()
        if excluded(rel) or not allowed(rel):
            bad.append(rel)
    print("[2/3] 禁入路径与后缀：%s" % ("0 处" if not bad else "%d 处" % len(bad)))
    for rel in bad[:10]:
        print("      ! %s" % rel)
    ok = ok and not bad

    binaries = [p.relative_to(out).as_posix() for p in out.rglob("*")
                if p.is_file() and p.suffix.lower() in BINARY_SUFFIX]
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print("[3/3] 体积与二进制：%.1f KB；%d 个图片/字体（无 APK、无二维码）"
          % (size / 1024.0, len(binaries)))

    print("\n%s" % ("验收通过：这棵树可以提交" if ok else "验收未通过：不许发布"))
    return 0 if ok else 1


def git_init(out, name, email):
    """单提交演练：证明「clean 仓库」不是嘴上说的。"""
    def run(args):
        p = subprocess.run(args, cwd=str(out), capture_output=True)
        if p.returncode != 0:
            raise SystemExit("git 失败：%s\n%s" % (" ".join(args),
                             p.stderr.decode("utf-8", "replace")[:400]))
        return p.stdout.decode("utf-8", "replace").strip()

    run(["git", "init", "-q", "-b", "main"])
    run(["git", "add", "-A"])
    ident = ["-c", "user.name=" + name, "-c", "user.email=" + email]
    run(["git"] + ident + ["commit", "-q", "-m", "初始提交：白名单导出 + 占位注入"])
    count = run(["git", "rev-list", "--count", "HEAD"])
    hits, n = S.scan_history(str(out))
    hard = [h for h in hits if h[0] == "FAIL"]
    print("\n[演练] 提交数 %s；历史扫描 %d 个提交，%d FAIL" % (count, n, len(hard)))
    for h in hard[:10]:
        print("      %s %s %s" % (h[0], h[1], h[2]))
    if count != "1" or hard:
        raise SystemExit("演练失败：提交数应为 1 且历史必须 0 命中")


def _disp_w(s):
    """东亚宽字符按 2 列算，否则中文标签会把表格挤歪。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def verify_tree(out):
    """推送前复检：验收一棵「已经导出」的树，不重新导出。

    导出 → 人手改了点东西 → 推之前再确认一次。检查项与 export 的验收同源，
    另加三条只有「已建仓库」才谈得上的：工作区干净、提交数为 1、身份不是占位。
    """
    checks = []

    def add(ok, name, detail=""):
        checks.append((ok, name, detail))

    files = [p for p in out.rglob("*")
             if p.is_file() and ".git" not in p.relative_to(out).parts]
    rels = [p.relative_to(out).as_posix() for p in files]

    hits, n = S.scan_dir(out, strict=True)
    hard = [h for h in hits if h[0] == "FAIL"]
    add(not hard, "严格密钥扫描", "%d 个文件，%d 命中" % (n, len(hard)))
    for h in hard[:8]:
        print("        %s %s %s" % (h[0], h[1], h[2]))

    bad = [r for r in rels if excluded(r) or not allowed(r)]
    add(not bad, "白名单与禁入物", "0 处异常" if not bad else "%d 处，如 %s" % (len(bad), bad[0]))

    bins = [r for r in rels if r.lower().endswith(EXCLUDE_SUFFIX)]
    add(not bins, "无 APK / 日志 / 运行态", "0 个" if not bins else "%s" % bins[0])

    attr = out / ".gitattributes"
    ok_attr = attr.exists() and "* -text" in attr.read_text(encoding="utf-8", errors="replace")
    add(ok_attr, ".gitattributes 钉住行尾",
        "* -text 在，检出字节 == 仓库字节" if ok_attr
        else "缺 * -text：Windows 检出会把裸 LF 补成 CRLF，自检按 sha256 对账立刻红")

    cfg = out / "ai-daily" / "site" / "config.js"
    cfg_txt = cfg.read_text(encoding="utf-8", errors="replace") if cfg.exists() else ""
    ok_cfg = PLACEHOLDER in cfg_txt
    add(ok_cfg, "入口地址是占位",
        "%s 在 config.js 里" % PLACEHOLDER if ok_cfg else "config.js 里找不到 %s" % PLACEHOLDER)

    left = repo_left(out)
    add(not left, "仓库地址已注入",
        "无 %s 残留" % REPO_PLACEHOLDER if not left else
        "%d 处 %s：徽章图是坏的，导出时加 --repo owner/name" % (left, REPO_PLACEHOLDER))

    if (out / ".git").exists():
        def git(*args):
            return subprocess.run(["git"] + list(args), cwd=str(out),
                                  capture_output=True).stdout.decode("utf-8", "replace").strip()

        count = git("rev-list", "--count", "HEAD") or "0"
        add(count == "1", "提交数为 1", "实际 %s 个提交" % count)

        dirty = git("status", "--porcelain")
        n_dirty = len(dirty.splitlines())
        add(not dirty, "工作区干净",
            "无未提交改动" if not dirty else "有 %d 个未提交改动" % n_dirty)

        emails = set(git("log", "--format=%ae").split())
        placeholder_local = {"rehearsal", "test", "your-name", "name"}
        bad_id = sorted(e for e in emails
                        if e.endswith("@local") or "example.com" in e
                        or e.split("@", 1)[0].lower() in placeholder_local)
        if bad_id:
            id_note = "用了 %s（应为 <id>+<用户名>@users.noreply.github.com）" % bad_id[0]
        elif len(emails) == 1:
            id_note = sorted(emails)[0]
        else:
            id_note = "%d 个不同身份" % len(emails)
        add(not bad_id, "提交身份不是占位", id_note)
    else:
        add(False, "已建 git 仓库", "没有 .git：复检应指向准备推送的那棵树")

    width = max(_disp_w(c[1]) for c in checks) + 2
    print("推送前复检 · %s" % out)
    print("-" * 66)
    for ok, name, detail in checks:
        pad = " " * (width - _disp_w(name))
        print("%s  %s%s%s" % ("PASS " if ok else "FAIL ", name, pad,
                              ("  " + detail) if detail else ""))
    fails = [c for c in checks if not c[0]]
    print("-" * 66)
    print("结论：%d 项，%d PASS / %d FAIL" % (len(checks), len(checks) - len(fails), len(fails)))
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PROJECT.parent / "ai-daily-public"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", metavar="DIR",
                    help="不导出，只对已有的导出树做推送前复检")
    ap.add_argument("--git-init", action="store_true",
                    help="导出后做一次单提交演练（默认不保留 .git）")
    ap.add_argument("--keep-git", action="store_true", help="保留演练用的 .git")
    ap.add_argument("--name", default="rehearsal")
    ap.add_argument("--email", default="rehearsal@example.com")
    ap.add_argument("--repo", default="",
                    help="GitHub 仓库 owner/name：注入 README 的 CI 徽章地址")
    a = ap.parse_args()
    if a.repo:
        os.environ["AI_DAILY_REPO"] = a.repo

    if a.verify:
        target = Path(a.verify).resolve()
        if not target.is_dir():
            raise SystemExit("不是目录：%s" % target)
        return verify_tree(target)

    out = Path(a.out).resolve()
    if PROJECT.resolve() in out.parents or out == PROJECT.resolve():
        raise SystemExit("目标不能放在项目里面：%s" % out)
    if a.email.endswith("@local"):
        raise SystemExit("提交身份不能用 @local：%s" % a.email)

    rc = export(out, a.force, a.dry_run)
    if rc or a.dry_run:
        return rc

    if a.git_init:
        git_init(out, a.name, a.email)
        if not a.keep_git:
            shutil.rmtree(out / ".git")
            print("[演练] 已删除演练用的 .git（身份是 %s）—— 正式发布会用你自己的"
                  "GitHub noreply 重新 init，避免带着占位身份推上去" % a.email)
    else:
        print("\n下一步（正式发布）：")
        print("  cd %s && git init -b main && git add -A" % out)
        print("  git -c user.name=… -c user.email=…（用 GitHub noreply 地址）commit -m …")
        print("  git remote add origin <新建的空仓库> && git push -u origin main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
