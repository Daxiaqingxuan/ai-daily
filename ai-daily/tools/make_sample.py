# -*- coding: utf-8 -*-
"""生成第 16 版样张：拿 1106 的样式 + 16 版报头/报尾模板 + 004 期提案内容，拼一份单页预览。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # ai-daily/
TPL = ROOT / "parts" / "_template"
OLD = ROOT / "parts" / "1106"

style = (OLD / "00-style.html").read_text(encoding="utf-8")
style += "\n" + (TPL / "00-style-extra.html").read_text(encoding="utf-8")

mast = (TPL / "00-masthead.html").read_text(encoding="utf-8")
mast = (mast.replace("YYYY 年 M 月 D 日　星期X", "2026 年 11 月 7 日　星期六")
            .replace("第 00N 期", "第 004 期"))

tail = (TPL / "00-tail.html").read_text(encoding="utf-8")
tail = (tail.replace("第 00N 期　YYYY-MM-DD", "第 004 期　2026-11-07")
            .replace("〔只列真正读过的来源，写清是公告、模型卡、榜单快照还是访谈〕",
                     "月之暗面模型卡、Anthropic 定价公告、Terminal-Bench 榜单快照、arXiv 预印本、本报访谈记录（三支团队，匿名）。")
            .replace("〔本期主线是什么；哪些数字未独立复现；哪些口径是本报自设、照抄会失真〕",
                     "本期以「智能体怎么被验收」为主线。凡标注「未独立复现」的数字取自公开页面，未做二次验证；评分为本报自设口径，照抄会失真。")
            .replace("〔有错就写清错在哪、怎么改的；没错就写「本期无更正」〕", "本期无更正。")
            .replace("〔列前几期，格式：第 00X 期（YYYY-MM-DD）〕", "第 003 期（2026-11-06）　第 002 期（2026-11-05）　第 001 期（2026-11-04）"))

# 复用语料：003 期的名词速查
old15 = (OLD / "p15.html").read_text(encoding="utf-8")
m = re.search(r'<div class="gloss" id="gloss">.*?</div>\s*</div>\s*(?=<footer)', old15, re.S)
gloss = m.group(0).rsplit("</div>", 1)[0] + "</div>" if m else ""

P16 = """
  <section class="section" id="p16">
    <div class="section-head">
      <span class="sec-label" role="heading" aria-level="2">本报提案 · 这一期想怎么改</span>
      <span class="sec-page">第 16 版 / 共 16 版</span>
    </div>

    <p class="sec-lede">本版每期由四个身份各提一条改动建议，编号 <b>P004-1…4</b>：<b>读者</b>说哪里读着费劲，<b>编辑</b>说哪里做起来费劲，<b>创刊人</b>说哪里该往前一步，<b>AI</b> 说哪里可以自动化。<b>默认不执行</b>——创刊人点名「采纳 P004-2」才进施工；没人提，下一期自动记「否决（沉默）」。</p>

    <div class="props">
      <article class="prop">
        <div class="prop-h"><span class="prop-role">读者</span><span class="prop-id">P004-1</span></div>
        <h4>头版加一块「三行摘要」，手机上首屏读完</h4>
        <p>现在头版是 700 字长文，390px 宽的手机首屏只露标题和两行导语，<b>要滑三屏才知道今天发生了什么</b>。加三行、每行 30 字以内，放在头条下方。</p>
        <dl class="prop-meta">
          <dt>为什么</dt><dd>手机读者平均只读 2.4 版，头版留不住人，后面 15 版白写</dd>
          <dt>成本</dt><dd>小 · 约 0.5 小时；每期多写 90 字</dd>
        </dl>
        <div class="prop-st">待定 · <b>沉默即否决</b></div>
      </article>

      <article class="prop">
        <div class="prop-h"><span class="prop-role">编辑</span><span class="prop-id">P004-2</span></div>
        <h4>名词第一次出现就给解释，别全堆到报尾</h4>
        <p>术语现在集中在报尾「名词速查」，读到第 5 版卡住，要翻到底再翻回来——手机上是 <b>14 屏的距离</b>。改成首次出现加虚线下划线，点一下弹解释；报尾 13 词表保留做索引。</p>
        <dl class="prop-meta">
          <dt>为什么</dt><dd>每期至少 6 个新词，卡住的位置都在正文中段</dd>
          <dt>成本</dt><dd>中 · 约 3 小时；每期多 15 分钟标注</dd>
        </dl>
        <div class="prop-st">待定 · <b>沉默即否决</b></div>
      </article>

      <article class="prop">
        <div class="prop-h"><span class="prop-role">创刊人</span><span class="prop-id">P004-3</span></div>
        <h4>能只分享一版，而不是整期</h4>
        <p>整期发出去，对方往往只看头版。每一版给一个「分享这一版」，链接带锚点（<code>?d=2026-11-07#p05</code>），对方打开<b>直接落到那一版</b>。现有 <code>issueUrl()</code> 已经支持 <code>d</code> 参数，加 <code>#pNN</code> 就够。</p>
        <dl class="prop-meta">
          <dt>为什么</dt><dd>能指着某一版说「看这个」，才算真传播</dd>
          <dt>成本</dt><dd>中 · 约 2 小时；16 个按钮会压版面，可能改成浮动按钮</dd>
        </dl>
        <div class="prop-st">待定 · <b>沉默即否决</b></div>
      </article>

      <article class="prop">
        <div class="prop-h"><span class="prop-role">AI</span><span class="prop-id">P004-4</span></div>
        <h4>每期产出一份 manifest.json，让「完整」可断言</h4>
        <p>现在验证靠 curl 四处 + 肉眼，没有机器可读的凭证。每期写一份 <code>manifest.json</code>：期号、版数、字数、md5、生成时间。谁都能一条命令判断<b>这期是否完整</b>。</p>
        <dl class="prop-meta">
          <dt>为什么</dt><dd>「文件存在」不等于「内容对」，这条能把肉眼检查变成断言</dd>
          <dt>成本</dt><dd>小 · 约 0.3 小时；在拼版脚本里加 10 行</dd>
        </dl>
        <div class="prop-st">待定 · <b>沉默即否决</b></div>
      </article>
    </div>

    <p class="prop-rule"><b>怎么算采纳：</b>创刊人在当期明确说「采纳 P004-2」才算；说「先放着」算待定，最多挂三期；<b>没说就是否决，不再追问</b>。已采纳的写进 <code>提案台账.md</code>，在下一期的台账里标「已落地」。</p>

    <div class="table-wrap">
      <table class="prop-ledger">
        <caption>提案台账 · 全量明细见 提案台账.md，本表只放最近 8 条</caption>
        <thead>
          <tr><th>编号</th><th>视角</th><th>一句话</th><th>状态</th></tr>
        </thead>
        <tbody>
          <tr><td class="id">P004-1</td><td>读者</td><td>头版加三行摘要</td><td class="st-wait">待定</td></tr>
          <tr><td class="id">P004-2</td><td>编辑</td><td>名词首次出现给解释</td><td class="st-wait">待定</td></tr>
          <tr><td class="id">P004-3</td><td>创刊人</td><td>单版分享</td><td class="st-wait">待定</td></tr>
          <tr><td class="id">P004-4</td><td>AI</td><td>每期产出 manifest.json</td><td class="st-wait">待定</td></tr>
        </tbody>
      </table>
    </div>

    <aside class="razor">
      <div class="razor-h">
        <span class="razor-mark">锐评</span>
        <span class="razor-src">本报评论员 · 针对本版四条提案</span>
      </div>
      <p>四条里最不像提案的是 P004-4，因为它不改善阅读，只改善<b>「你敢不敢说这期是完整的」</b>。但恰恰是它最该先做：一份没人验过的报纸，改版改得再漂亮，也只是把不确定性藏得更深。<b>先让机器能判真假，再谈让读者读得舒服。</b></p>
    </aside>
  </section>
"""

html = (
    "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"UTF-8\">\n"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
    "<title>AI 晨报 · 2026年11月7日 · 第 004 期 · 智能体专版（共 16 版）· 样张</title>\n"
    "<style>" + style + "</style>\n</head>\n<body>\n<div class=\"page\" id=\"top\">\n"
    + mast + P16 + gloss + tail + "\n</div>\n</body>\n</html>\n"
)

out = TPL / "样张-第16版.html"
out.write_text(html, encoding="utf-8", newline="\n")
print("写出", out, len(html.encode("utf-8")), "字节")
print("section", html.count("<section"), "gloss", html.count('id="gloss"'), "razor", html.count("razor"))
