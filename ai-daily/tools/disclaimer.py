#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""内容声明的唯一事实源与落点清单。

文案只在 ``site/config.js`` 的 ``disclaimer`` 字段里写一遍：
  - 各期成品 / parts 片段 / 模板 / 样张 / README：由 ``apply_disclaimer.py`` 派生；
  - ``site/`` 静态副本：由 ``build_index.py`` 从根目录成品单向同步；
  - 阅读器分享面板：运行时读同一个常量，不再硬编码一句。

改文案的正确顺序：改 config.js 一处 → ``apply_disclaimer.py`` →
``build_index.py``（同步站点副本并重生成凭证） → 自检 → 发布。
自检的「内容声明一致」项会拿这里的目标清单逐份对账。
"""
import re
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent                       # ai-daily/
PROJECT = ROOT.parent                     # 仓库根
CONFIG = ROOT / "site" / "config.js"
README = PROJECT / "README.md"

CONST_RE = re.compile(r'\bdisclaimer\s*:\s*"([^"]+)"')
START = "<!-- disclaimer:start -->"
END = "<!-- disclaimer:end -->"

# 已定稿期的版面源文件（中间件）。只列已定稿的，绝不包含 _drafts/——
# 预热稿不是交付物，也不该被自检绑住。004 期（2026-11-07）已从预热转正，
# 故 parts/1107/00-tail.html 在此登记，改文案时由 apply_disclaimer.py 一起派生。
SOURCE_HTML = (
    "parts/_template/00-tail.html",
    "parts/_template/样张-第16版.html",
    "parts/1106/p15.html",
    "parts/1106sp/00-tail.html",
    "parts/1107/00-tail.html",
)


def text(config=None):
    """从 config.js 解析声明原文；解析不到就报错，绝不给兜底文案。"""
    s = Path(config or CONFIG).read_text(encoding="utf-8")
    m = CONST_RE.search(s)
    if not m:
        raise RuntimeError("config.js 里解析不到 disclaimer 常量")
    return m.group(1)


def line(t=None):
    """静态 HTML 里的报尾声明行。"""
    return '<p class="disclaimer">%s</p>' % (t or text())


def papers(root=None):
    return sorted(Path(root or ROOT).glob("AI晨报-*.html"))


def html_targets(root=None):
    """需要派生声明的根目录成品 + 源片段（不含 site/ 副本）。"""
    r = Path(root or ROOT)
    return papers(r) + [r / p for p in SOURCE_HTML]


def site_targets(site=None):
    """站点副本（含特刊），只用于核对，不直接写。"""
    s = Path(site or (ROOT / "site"))
    return sorted(s.glob("AI晨报-*.html")) + sorted(s.glob("special/*.html"))
