#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第 7 章配套：一键回归套件 verify_all

把散落的临时验证串成一条命令。设计要点不是「检查多」，而是：
  - 默认只读，不改运行中的 ai-daily；
  - SKIP 必须显式列出，绝不把「没测」说成「通过」；
  - 已知技术债可以显式跳过，但不能假装它绿了。

用法：
  python verify_all.py                  # 全部只读检查（含契约漂移）
  python verify_all.py --skip-contract  # 把第 1 章未落地的契约标为 SKIP
  python verify_all.py --online         # 额外比对线上 APK 与本地 md5
  python verify_all.py --json           # 输出结构化报告
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1] / "ai-daily"
sys.path.insert(0, str(HERE))
import validate          # noqa: E402
import check_contract    # noqa: E402

def _online_apk() -> str:
    """线上 APK 地址由 ai-daily/site/config.js 的 siteUrl 派生，不另存一份明文。"""
    cfg = PROJECT / "site" / "config.js"
    try:
        m = re.search(r'\bsiteUrl\s*:\s*"([^"]*)"', cfg.read_text(encoding="utf-8"))
        url = m.group(1).strip() if m else ""
    except OSError:
        url = ""
    if not url or "__SITE_URL__" in url:
        return ""
    base, _, query = url.partition("?")
    return base.rstrip("/") + "/ai-daily.apk" + ("?" + query if query else "")


ONLINE_APK = _online_apk()


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def check_structure():
    validate.results.clear()
    old = sys.argv
    sys.argv = ["validate.py", str(PROJECT)]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            code = validate.main()
    finally:
        sys.argv = old
    bad = [f"[{g}] {n} {d}" for g, n, ok, d in validate.results if not ok]
    return code == 0, f"{len(validate.results) - len(bad)}/{len(validate.results)} 条断言", bad


def check_contract_drift():
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        code = check_contract.scan(PROJECT)
    fails = [l.strip() for l in buf.getvalue().splitlines() if l.startswith("[FAIL]")]
    return code == 0, (f"{len(fails)} 项漂移" if fails else "0 项漂移"), fails


def check_idempotence():
    # 用沙盒流水线而不是 build_index.py：后者硬编码了跨任务目录（第 1 章 C5 漂移），
    # 复制到沙盒会被真实目录污染。改用纯沙盒才测得准，也不碰运行中的项目。
    r = subprocess.run([sys.executable, str(HERE / "pipeline.py"), "--twice"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = r.returncode == 0 and "完全一致" in r.stdout
    detail = "沙盒流水线连跑两次，4 份中间产物 md5 一致" if ok else "产物不一致或脚本报错"
    return ok, detail, ([] if ok else [r.stdout[-400:], r.stderr[-300:]])


def check_artifacts():
    apk, site_apk = PROJECT / "AI晨报.apk", PROJECT / "site" / "ai-daily.apk"
    if not apk.exists():
        return False, "APK 不存在", ["缺少 ai-daily/AI晨报.apk"]
    with zipfile.ZipFile(apk) as z:
        names = z.namelist()
    need = ["classes.dex", "assets/site/index.html", "assets/site/issues.js"]
    missing = [n for n in need if n not in names]
    sig = [n for n in names if n.startswith("META-INF/")]
    same = site_apk.exists() and md5(apk) == md5(site_apk)
    detail = f"dex/assets 齐全；v1 签名文件 {len(sig)} 个；本地与 site 副本 md5 " + ("一致" if same else "不一致")
    return (not missing and bool(sig) and same), detail, [f"缺 {missing}" ] if missing else []


def check_online():
    import urllib.request
    if not ONLINE_APK:
        return False, "未配置线上入口（site/config.js 的 siteUrl 是占位），无法比对", ["缺少入口地址"]
    site_apk = PROJECT / "site" / "ai-daily.apk"
    with urllib.request.urlopen(ONLINE_APK, timeout=15) as r:
        data = r.read()
    ok = hashlib.md5(data).hexdigest() == md5(site_apk)
    return ok, f"线上 {len(data)} 字节，md5 " + ("一致" if ok else "不一致"), ([] if ok else ["线上包与本地不一致"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-contract", action="store_true")
    ap.add_argument("--online", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    report = []
    print(f"=== 一键回归套件（只读）· {PROJECT} ===\n")

    for key, label, fn in [
        ("structure", "报纸结构断言", check_structure),
        ("idempotence", "流水线幂等", check_idempotence),
        ("artifacts", "APK 内容完整性", check_artifacts),
    ]:
        ok, detail, bad = fn()
        report.append({"check": key, "result": "PASS" if ok else "FAIL", "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {key:<14} {detail}")
        for b in bad:
            print("        " + b)

    if a.skip_contract:
        report.append({"check": "contract", "result": "SKIP",
                       "detail": "第 1 章契约尚未落地，显式跳过（不是通过）"})
        print("[SKIP] contract       第 1 章契约尚未落地，显式跳过（不是通过）")
    else:
        ok, detail, bad = check_contract_drift()
        report.append({"check": "contract", "result": "PASS" if ok else "FAIL", "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {'contract':<14} {detail}")
        for b in bad:
            print("        " + b)

    if a.online:
        try:
            ok, detail, bad = check_online()
        except Exception as e:
            ok, detail, bad = False, f"请求失败：{e}", [str(e)]
        report.append({"check": "online", "result": "PASS" if ok else "FAIL", "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {'online':<14} {detail}")
    else:
        report.append({"check": "online", "result": "SKIP", "detail": "加 --online 启用"})
        print("[SKIP] online         加 --online 启用（比对线上 APK md5）")

    skips = [
        ("browser", "CDP 390px 真实视口", "node ai-daily/tools/probe.js <url> <shot> measure"),
        ("golden", "golden sample 截图比对", "建立 learn-agent/golden/ 后比对关键区域哈希"),
        ("signing", "APK 密码学验签 v1/v2/v3", "python ai-daily/tools/build_apk.py 打包时已完成；此处只查内容完整性"),
    ]
    for key, label, cmd in skips:
        report.append({"check": key, "result": "SKIP", "detail": label, "enable": cmd})
        print(f"[SKIP] {key:<14} {label}  →  {cmd}")

    npass = sum(1 for r in report if r["result"] == "PASS")
    nfail = sum(1 for r in report if r["result"] == "FAIL")
    nskip = sum(1 for r in report if r["result"] == "SKIP")
    print(f"\n--- 结论：PASS {npass} / FAIL {nfail} / SKIP {nskip} ---")
    print("SKIP 不计入通过；报告里没测的项目就是没测。")
    if a.json:
        print("\n" + json.dumps({"project": str(PROJECT), "report": report,
                                 "summary": {"pass": npass, "fail": nfail, "skip": nskip}},
                                ensure_ascii=False, indent=2))
    return 1 if nfail else 0


if __name__ == "__main__":
    raise SystemExit(main())
