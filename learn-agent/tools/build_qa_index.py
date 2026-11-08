"""从教材 HTML 抽取全部练习题与自检题，生成《教程问答.md》第二部分。

设计要点（对应教材第 3 章）：
  1. 内容与版式分离：题目只在教材里维护，这里是自动派生，不手抄。
  2. 幂等：只替换 BEGIN/END 标记之间的区块，重复运行字符数不变。
  3. 失败可定位：抽不到题时明确报错，而不是静默生成空清单。

用法：python learn-agent/tools/build_qa_index.py
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TUTORIAL = ROOT / "AI-Agent-运用完全教程.html"
QA = ROOT / "教程问答.md"
BEGIN = "<!-- 原题清单 BEGIN -->"
END = "<!-- 原题清单 END -->"


def clean(raw: str) -> str:
    """把一段 HTML 片段压成一行纯文本。"""
    raw = re.sub(r"<pre\b.*?</pre>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    # 题目里常含 <style>、<code> 这类标签文字：转义后 Markdown 才不会把它们当标签吞掉
    raw = raw.replace("<", "&lt;").replace(">", "&gt;")
    # 剥标签留下的空格不要贴到中文标点前
    raw = re.sub(r"\s+([，。、；：！？）」])", r"\1", raw)
    raw = re.sub(r"([（「])\s+", r"\1", raw)
    return raw


def extract() -> tuple[str, int, int, int]:
    if not TUTORIAL.exists():
        raise SystemExit(f"找不到教材：{TUTORIAL}")
    src = TUTORIAL.read_text(encoding="utf-8")

    out: list[str] = []
    n_sec = n_block = n_item = 0

    # 按 <section id="..."> 切分，每段只包含一个章节
    for sec in re.split(r'(?=<section id=")', src)[1:]:
        m_id = re.search(r'<section id="([^"]+)"', sec)
        if not m_id:
            continue
        sid = m_id.group(1)
        m_h2 = re.search(r"<h2>(.*?)</h2>", sec, re.S)
        title = clean(m_h2.group(1)) if m_h2 else sid

        blocks: list[str] = []
        # 每个 drill 块取到下一个 box 或 section 结束为止
        for chunk in sec.split('<div class="box drill">')[1:]:
            chunk = re.split(r'<div class="box|</section>', chunk)[0]
            m_lb = re.search(r'<span class="lb">(.*?)</span>', chunk, re.S)
            label = clean(m_lb.group(1)) if m_lb else "练习"
            items = [clean(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", chunk, re.S)]
            if not items:  # 少数块用 <p> 而不是 <li>
                items = [clean(x) for x in re.findall(r"<p>(.*?)</p>", chunk, re.S)]
            items = [x for x in items if x]
            if not items:
                continue
            n_block += 1
            n_item += len(items)
            body = "\n".join(f"- {x}" for x in items)
            blocks.append(f"**{label}**（{len(items)} 条）\n\n{body}")

        if not blocks:
            continue
        n_sec += 1
        out.append(f"### {sid} · {title}\n\n"
                   f"> 教材锚点：`AI-Agent-运用完全教程.html#{sid}`\n\n"
                   + "\n\n".join(blocks))

    if n_item == 0:
        raise SystemExit("抽取到 0 条题目：教材结构可能变了，请检查 .box.drill 标记")

    header = (f"共 **{n_sec} 章 / {n_block} 个练习块 / {n_item} 条题目**，"
              f"由 `tools/build_qa_index.py` 自动抽取自教材。\n")
    return header + "\n" + "\n\n---\n\n".join(out) + "\n", n_sec, n_block, n_item


def main() -> int:
    body, n_sec, n_block, n_item = extract()
    if not QA.exists():
        raise SystemExit(f"找不到问答文件：{QA}")
    text = QA.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise SystemExit("问答文件缺少 BEGIN/END 标记，拒绝改写")

    new_block = f"{BEGIN}\n{body}\n{END}"
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    updated = pattern.sub(lambda _: new_block, text, count=1)

    if updated != text:
        QA.write_text(updated, encoding="utf-8")
        print(f"已更新：{QA.name}")
    else:
        print("内容无变化（幂等）")
    print(f"抽取结果：{n_sec} 章 / {n_block} 个练习块 / {n_item} 条题目")
    print(f"文件大小：{QA.stat().st_size} 字节 | 字符数 {len(updated)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
