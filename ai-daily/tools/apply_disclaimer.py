#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 config.js 的内容声明派生到所有静态落点（幂等，bytes 级精确替换）。

用法：
    python tools/apply_disclaimer.py            # 写入；重复跑结果字节不变
    python tools/apply_disclaimer.py --check   # 只报告漂移，不写盘（有漂移退出码 1）

只改根目录各期成品、已定稿的 parts 片段、模板、样张与 README.md。
``site/`` 下的静态副本不在这里写，跑 ``build_index.py`` 单向同步。
Windows 上不用 write_text（会把 LF 写成 CRLF），全部按 bytes 精确替换。
"""
import argparse
import re
import sys
from pathlib import Path

import disclaimer as D

OLD_LINE = re.compile(rb'[ \t]*<p class="disclaimer">.*?</p>[ \t]*(\r?\n)?', re.S)
MARK = re.compile(re.escape(D.START.encode("utf-8")) + rb".*?" +
                  re.escape(D.END.encode("utf-8")), re.S)


def plan_html(path, t):
    """删掉旧的声明行，在 </footer> 前重新插入由 config.js 派生的一行。"""
    b = path.read_bytes()
    cleaned, n = OLD_LINE.subn(b"", b)
    if n > 1:
        raise RuntimeError("%s 里有 %d 行旧声明，拒绝猜测该留哪行" % (path, n))
    i = cleaned.find(b"</footer>")
    if i < 0:
        raise RuntimeError("%s 找不到 </footer>" % path)
    j = cleaned.rfind(b"\n", 0, i)
    if j < 0:
        raise RuntimeError("%s 的 </footer> 前没有换行，插入位置不明" % path)
    nl = b"\r\n" if b"\r\n" in cleaned else b"\n"
    # 缩进跟上一行正文（报尾 <p>）对齐，而不是跟 </footer> 的闭合缩进
    prev = cleaned[:j].rstrip(b"\r\n").split(b"\n")[-1]
    indent = re.match(rb"[ \t]*", prev).group(0)
    line = D.line(t).encode("utf-8")
    return cleaned[:j + 1] + indent + line + nl + cleaned[j + 1:]


def plan_readme(path, t):
    b = path.read_bytes()
    payload = (D.START + t + D.END).encode("utf-8")
    out, n = MARK.subn(lambda m: payload, b)
    if n != 1:
        raise RuntimeError("README.md 的声明标记必须恰好一对，实际 %d 处" % n)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查不写盘")
    a = ap.parse_args()

    t = D.text()
    print("声明原文（唯一事实源 site/config.js）：%s" % t)
    plans = [(p, plan_html(p, t)) for p in D.html_targets()]
    plans.append((D.README, plan_readme(D.README, t)))

    drift = 0
    for p, out in plans:
        if not p.exists():
            raise RuntimeError("目标不存在：%s" % p)
        if p.read_bytes() == out:
            print("  = %s" % p.relative_to(D.PROJECT))
            continue
        drift += 1
        print("  %s %s" % ("!" if a.check else "+", p.relative_to(D.PROJECT)))
        if not a.check:
            p.write_bytes(out)

    print("共 %d 个文件%s；site/ 副本请接着跑 build_index.py 同步。"
          % (drift, "有漂移" if drift else "已一致"))
    return 1 if (a.check and drift) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("[apply_disclaimer] 失败：%s" % exc, file=sys.stderr)
        raise SystemExit(2)
