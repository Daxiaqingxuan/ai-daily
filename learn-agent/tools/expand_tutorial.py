#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教材增补构建脚本（本身就是第 3 章的一个实例：内容与版式分离、脚本拼装、幂等）

把 EXTRA 里每章的增补片段插入 AI-Agent-运用完全教程.html 的对应 section。
幂等：用 <!-- extra:ID --> / <!-- /extra:ID --> 标记；重复运行只替换、不叠加。

用法：python learn-agent/tools/expand_tutorial.py
"""
from __future__ import annotations

import re
from pathlib import Path

if hasattr(__import__("sys").stdout, "reconfigure"):
    __import__("sys").stdout.reconfigure(encoding="utf-8")

TUTORIAL = Path(__file__).resolve().parents[1] / "AI-Agent-运用完全教程.html"

SELF_CHECK = '  <div class="box drill"><span class="lb">本章自检</span>'

ANCHORS = {
    "ch3": SELF_CHECK, "ch4": SELF_CHECK, "ch5": SELF_CHECK,
    "ch6": SELF_CHECK, "ch7": SELF_CHECK, "ch8": SELF_CHECK,
    "apxA": '  <p>学完的判断标准不是',
    "apxB": None, "apxC": None,
    "apxD": '  <div class="box proj"><span class="lb">最后一句</span>',
    "apxF": None,
}

EXTRA: dict[str, str] = {}

EXTRA["ch3"] = r'''
  <h3>现场演示：把 12 段提示词换成 6 个阶段</h3>
  <p>配套脚本 <code>examples/pipeline.py</code> 在临时沙盒里跑完整链路，每一步产物都落盘、都带 md5，能单独抽查：</p>
  <pre><code>$ python examples/pipeline.py
=== 完整流水线（6 个阶段，每步产物落盘）===
  [collect  ] 素材落盘（3 条）              md5=47bfd11d44
  [verify   ] 独立核对通过                  md5=736227d132
  [write    ] 只写正文片段，模型看不到 CSS   md5=d14914b267
  [assemble ] 脚本拼装整页                  md5=3d3b2b2b8b
  [validate ] 断言通过（3 段正文、viewport、style 齐全）
  [publish  ] （模拟）发布 + 写状态文件      md5=22945f53d1
最终产物：material.json / material.checked.json / body.md / paper.html / status.json</code></pre>
  <p>三个开关对应本章三件事：<code>--from write</code> 复用前序产物、只重跑 write 之后四步（实测 4 份产物 md5 与首次完全相同）；<code>--twice</code> 连跑两次比对全部中间产物，结论「完全一致 → 幂等」；<code>--bad-material</code> 注入「素材 99.9k ≠ 口径表 12.4k」的跨来源数字冲突，流水线停在 <code>verify</code>，现场只剩 <code>material.json</code>。</p>
  <div class="box why"><span class="lb">关键差别</span>旧链路里「事实核查」混在写作中，素材错了只能整期重来；拆成独立阶段后，坏数据在进入写作前就被拦下，而且<b>现场留下一份可检查的 material.json</b>，一眼能看出是哪条数字不对。这就是「可验证性设计」的收益。</div>

  <h3>阶段边界怎么划</h3>
  <table>
    <tr><th>判据</th><th>该问自己的问题</th><th>不满足会怎样</th></tr>
    <tr><td>产物可被断言检查</td><td>这一步的输出能不能用代码判断对错？</td><td>只能靠人眼，等于没分阶段</td></tr>
    <tr><td>失败不污染上游</td><td>这一步崩了，前面的产物还完好吗？</td><td>要重跑整条链路</td></tr>
    <tr><td>重跑不破坏下游</td><td>单独重跑它，后面的结果会变吗？</td><td>不敢重试，也无法补偿</td></tr>
  </table>
  <p><code>pipeline.py</code> 里给每个阶段写了 <code>REQUIRED</code> 前置产物表：从 <code>write</code> 续跑时若 <code>material.checked.json</code> 不存在，会明确报「缺少前序产物，请先跑完整流水线」，而不是抛一个 <code>FileNotFoundError</code> 让你猜。<b>阶段之间的依赖也要写成代码。</b></p>
  <div class="box proj"><span class="lb">一个跨章节的真实代价</span>第 7 章的回归套件本想「把 <code>build_index.py</code> 复制进沙盒连跑两次测幂等」，但它硬编码了另一个自动化的工作目录（第 1 章 C5 漂移），复制过去会被真实目录污染，测不准。最后套件改用纯沙盒的 <code>pipeline.py --twice</code>。<b>流水线能不能被安全地搬进测试环境，取决于唯一真源有没有守住。</b></div>

  <h3>中间产物要结构化，不要自由文本</h3>
  <p>素材阶段强制每条带 <code>id / source / date / number</code> 四个字段，核查阶段就能写机器比对，而不是请模型「自己记得别写错」：</p>
  <pre><code>material.json
{ "items": [
  {"id":"repo-a","source":"github","date":"2026-11-05","number":"12.4k"},
  {"id":"repo-b","source":"github","date":"2026-11-05","number":"8.1k"}
]}

verify(items, published_facts):
  for it in items:
    for k in ("source","date","number"):
      assert it.get(k), f"{it['id']} 缺 {k}"
    assert published_facts[it["id"]] == it["number"],
           f"{it['id']} 数字冲突"          # 跨版一致性在这里被机器抓住</code></pre>
  <p>注意失败信息带 <code>id</code> 和实测数字——这和第 2 章「失败信息是给 agent 的输入」是同一条原则，只不过用在了流水线中间而不是最终交付。</p>

  <h4>12 段提示词 → 6 个阶段的映射</h4>
  <table>
    <tr><th>原提示词段落</th><th>阶段</th><th>产物</th><th>谁执行</th></tr>
    <tr><td>①② 十二路检索、锐评素材</td><td>collect</td><td><code>material.json</code></td><td>agent</td></tr>
    <tr><td>自洽硬检查的数字部分</td><td>verify</td><td><code>material.checked.json</code></td><td>脚本</td></tr>
    <tr><td>③–⑩ 15 版正文、锐评</td><td>write</td><td><code>body.md</code></td><td>agent</td></tr>
    <tr><td>复用 144KB 样板与 CSS</td><td>assemble</td><td>整页 HTML</td><td>脚本</td></tr>
    <tr><td>版式规范、跨版一致性</td><td>validate</td><td>断言结果</td><td>脚本</td></tr>
    <tr><td>刷索引、重新发布</td><td>publish</td><td><code>status.json</code></td><td>脚本（需授权）</td></tr>
  </table>
  <div class="box drill"><span class="lb">补充动手练</span>
    <ol>
      <li>跑 <code>python examples/pipeline.py --from write</code>，看它如何复用前序产物；再删掉 <code>material.checked.json</code> 重跑，读它的报错。</li>
      <li>给 <code>verify</code> 加一条「同一 id 的 date 必须相同」的断言，然后故意改坏一条做变异测试。</li>
    </ol>
  </div>
'''

EXTRA["ch4"] = r'''
  <h3>原子写的完整实现（可运行）</h3>
  <p><code>examples/pipeline.py</code> 里每个阶段都走同一个函数。它把「校验」做成参数传进来，校验不过就删临时文件、<b>目标文件一个字节都不动</b>：</p>
  <pre><code>def atomic_write(path, text, validator=None):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    if validator:
        code, why = validator(tmp)          # 先校验临时文件
        if code != 0:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"原子写被拦下：{why}（目标文件未被触碰）")
    os.replace(tmp, path)                   # 同分区改名是原子的
    return md5(path)

# assemble 阶段注入骨架校验：缺 style 或 viewport 就拒绝落盘
atomic_write("paper.html", html, validator=check_skeleton)</code></pre>
  <p>为什么是 <code>os.replace</code> 而不是「先删旧文件再写」：前者在文件系统层面是一步完成，任何时刻的观察者看到的<b>要么是旧文件、要么是完整新文件</b>；后者中间存在一个「文件不存在」或「写了一半」的窗口。你补发检查用「文件存在」判断成功，正好会踩进这个窗口。</p>

  <h3>现场演示：副作用被挡在下游之外</h3>
  <pre><code>$ python examples/pipeline.py --bad-material
  [collect] 素材落盘（3 条）  md5=fa9c596d4a
已拦下：事实核查未过：repo-a 数字冲突：素材 99.9k ≠ 口径表 12.4k
现场产物：['material.json']
→ 没有 body.md / paper.html / status.json：坏素材没有流到下游</code></pre>
  <p>注意这里拦截发生在<b>任何写操作之前</b>：<code>collect</code> 已经落盘的是可丢弃的中间产物，而 <code>publish</code> 这个真正有外部影响的动作根本没被执行。权限设计的第一原则不是「拦住坏人」，是<b>让危险动作排在最后、且前面有闸门</b>。</p>

  <h3>把 A / B / C 三档写成代码，而不是写成口号</h3>
  <p>契约里写「C 档必须先问」只是文字；脚本里应该有一道真的过不去的检查：</p>
  <pre><code>PERMISSION = {
  "read":       "A",   # 读文件、跑只读命令、跑 validate.py
  "write_local":"B",   # 写项目内文件、重打 APK（做完报备）
  "deploy":     "C",   # 重新发布站点（当轮明确授权）
  "delete":     "C",
}
def guard(action, approved=False):
    level = PERMISSION[action]
    if level == "C" and not approved:
        raise PermissionError(f"{action} 属于 C 档：未获本轮授权，拒绝执行")
    return True

# 发布闸门：先校验，再授权，最后才动手
guard("deploy", approved=user_said_yes_this_turn)
if run("validate.py").returncode != 0:
    raise SystemExit("断言未过，禁止发布")     # 闸门在副作用之前</code></pre>
  <div class="box warn"><span class="lb">本机真实案例，三条都踩过</span>① PowerShell 的 <code>WScript.Shell</code> COM 被安全策略拦截，创建 <code>.lnk</code> 失败 → 改成直接生成原生二进制，属于「换执行方式」而非提权；② 旧的浏览器式 <code>.url</code> 是<b>先归档备份再替换</b>，没有直接删除；③ 每次重新发布线上站点都在当轮先确认，且「同意不跨轮」。<b>这三条应该写进 AGENTS.md 第 7 节，而不是只留在工作日志里。</b></div>
  <div class="box proj"><span class="lb">工具描述也是上下文</span>给工具写说明时写边界不写自由：「只允许在 <code>ai-daily/site/</code> 下写文件；不允许删除；发布前必须通过 <code>validate.py</code>」。模型看得见这段描述，写得模糊等于悄悄放权——这是第 1 章信息密度原则在权限上的应用。</div>
'''

EXTRA["ch5"] = r'''
  <h3>现场演示：状态机的四种结局</h3>
  <p><code>examples/status.py</code> 用四个场景把「文件存在 ≠ 成功」跑成了可观察的事实：</p>
  <pre><code>=== 场景 1 · 全绿 ===
  state=OK       steps=generate:OK validate:OK index:OK publish:OK
  should_skip(2026-11-05) = True   resume_from = None

=== 场景 2 · 发布失败 ===
  state=PARTIAL  steps=generate:OK validate:OK index:OK publish:FAILED
  resume_from = publish   → 只重跑 publish，前三步产物保留

=== 场景 3 · 半截文件 ===
  文件存在 = True（43 字节，只写了 6 版）
  state=FAILED   should_skip(2026-11-07) = False  → 补发检查会正确触发

=== 场景 4 · 连续失败 ===
  第 1/2 次：FAILED    第 3 次：FAILED  error=CIRCUIT_OPEN</code></pre>
  <p>场景 3 就是你补发检查现在最危险的地方：它只看 <code>AI晨报-YYYY-MM-DD.html</code> 在不在。换成 <code>should_skip()</code> 后，半截文件不会被当成「今天已出报」。</p>

  <h3>状态机的最小实现</h3>
  <pre><code>STEPS = ["generate", "validate", "index", "publish"]

def mark(step, ok, detail=""):
    d["steps"][step] = ("OK:" + detail) if ok else ("FAILED:" + detail)
    save()                                  # 每步都落盘，崩溃也知道断在哪

def finish():
    vals = [d["steps"].get(s, "PENDING") for s in STEPS]
    if all(v.startswith("OK") for v in vals):      d["state"] = "OK"
    elif any(v.startswith("FAILED") for v in vals):
        d["state"] = "PARTIAL" if any(v.startswith("OK") for v in vals) else "FAILED"
    if d["state"] == "FAILED" and d["attempt"] &gt;= 3:
        d["error"] = "CIRCUIT_OPEN：停止重试，等人介入"

def resume_from():                          # 补偿：从第一个没成功的步骤续跑
    return next((s for s in STEPS if not d["steps"].get(s,"").startswith("OK")), None)

def should_skip(date):                      # 只看状态，不看文件
    return d.get("date") == date and d.get("state") == "OK"</code></pre>
  <div class="box why"><span class="lb">两个容易漏掉的顺序</span>① <b>开工先写 RUNNING，收工才写 OK</b>：如果一上来就写 OK，中途崩了反而留下「成功」的假状态；② <b>状态文件自己也要原子写</b>（<code>status.py</code> 里用的 <code>atomic_json</code> 就是 <code>os.replace</code>），否则状态文件本身可能半截。<b>判据自己不能被判据的故障骗过。</b></div>

  <h3>给你两条自动化的改造清单</h3>
  <p>把现在「一段提示词串到底」改成下面这个形状。注意每一步都有退出码检查、失败即中止、且 <code>finally</code> 里一定留状态：</p>
  <pre><code># 8:00 每日出报
book.begin(today)
try:
    generate()                              # 写临时文件 → 校验 → 原子改名
    book.mark("generate", True, "15 版")
    r = run("validate.py"); book.mark("validate", r.code == 0, r.summary)
    if r.code != 0: raise GateBlocked(r.stdout)      # 原文留给下一轮 agent
    run("build_index.py"); book.mark("index", True)
    guard("deploy", approved=True_asked_this_turn)
    deploy(); book.mark("publish", True)
except Exception as e:
    book.mark(current_step, False, str(e)[:200])     # 失败原文，不转述
finally:
    book.finish()                           # OK / PARTIAL / FAILED 三选一

# 每 3 小时补发检查（先读状态，再决定做不做）
if StatusBook("status.json").should_skip(today):
    print("今日晨报已出且校验通过，无需补发"); return
if attempts_today &gt;= 3:
    print("CIRCUIT_OPEN，等人介入"); return          # 防止反复补发</code></pre>
  <p>这里有个和第 2 章闭环呼应的地方：<code>GateBlocked(r.stdout)</code> 把失败原文留下来，下一轮 agent 拿到的就是「15 条锐评 实测 14」这种能直接动手的信息，而不是人转述的「校验没过」。</p>
  <div class="box proj"><span class="lb">PARTIAL 是省钱的状态</span>出报成功、索引刷好、发布超时，标 PARTIAL 并记录 <code>resume_from = publish</code>。下次只需补一次发布，不用重新检索 12 路、重写 15 版。<b>状态越细，补偿越便宜。</b></div>
  <div class="box drill"><span class="lb">补充动手练</span>
    <ol>
      <li>跑 <code>python examples/status.py --json</code>，看最后一份状态文件的完整字段。</li>
      <li>把「当天已尝试次数」加进状态，验证第 3 次会写 <code>CIRCUIT_OPEN</code> 而第 4 次不再执行。</li>
    </ol>
  </div>
'''


EXTRA["ch6"] = r'''
  <h3>六条命令的最小闭环（在临时目录里练，不碰真实项目）</h3>
  <p>不用先学分支、rebase、远程。下面这一段可以整段复制到一个空目录里跑，跑完你就理解了九成收益：</p>
  <pre><code>mkdir git-drill &amp;&amp; cd git-drill &amp;&amp; git init
printf 'v1 正确的入口页\n' &gt; index.html
git add -A &amp;&amp; git commit -m "基线：入口页 v1"        # 改动前先有快照
printf 'v2 被 agent 改坏了\n' &gt; index.html             # 模拟一次失误
git diff                                              # 看清楚改了哪几行
git checkout -- index.html                            # 一句话回滚
cat index.html                                        # → v1 正确的入口页

git checkout -b try-new-layout                        # 开分支放心试
# 满意：git checkout main; git merge try-new-layout
# 不满意：git checkout main                            # 一行丢掉整个实验</code></pre>
  <p>重点是<b>顺序</b>：先 commit 再让 agent 动手。改完再提交也有历史，但「改动前快照」才是你敢放手的原因——它保证任何时刻都有一个已知良好的状态可以回去。</p>

  <h3>.gitignore 该写什么（按你的项目实测）</h3>
  <pre><code># ai-daily/.gitignore
.edge-*/            # CDP/无头浏览器的用户数据目录，几十 MB 且每次都变
.edge-check*/
.edge-online/
shots/              # 验证截图，可再生
apk/.build/         # APK 编译中间产物（dex、未签名包）
*.tmp               # 原子写的临时文件
__pycache__/
# 保留：AI晨报-*.html、site/、tools/、apk/src、AndroidManifest.xml
# 判断标准：丢了能不能用一条命令重新生成？能 → 忽略；不能 → 提交。</code></pre>
  <p>注意 <code>site/issues.js</code> 虽然由脚本生成，但<b>要提交</b>：它是两端阅读器直接读的索引，提交后出问题时能一眼看出「索引有没有被改坏」。可再生不等于不该跟踪，看它是否在运行时被直接消费。</p>

  <h3>diff 是最省 token 的上下文（量化）</h3>
  <table>
    <tr><th>给 agent 的内容</th><th>体量</th><th>信息密度</th></tr>
    <tr><td>整份样板 HTML</td><td>144481 B ≈ 48k tokens</td><td>99% 是不变 CSS 与旧正文</td></tr>
    <tr><td>整份入口页重读</td><td>19055 B ≈ 6k tokens</td><td>大部分与本次改动无关</td></tr>
    <tr><td><code>git diff</code> 一次改动</td><td>通常几十行 ≈ 0.3–1k tokens</td><td>几乎全是「变了什么」</td></tr>
  </table>
  <p>新会话接手时，先给 <code>git log --oneline -5</code> 和 <code>git diff HEAD~1</code>，比把三个文件全文贴进上下文有效得多。这是第 1 章「信息密度」原则最具体的一次应用：<b>版本控制不只是备份，也是上下文压缩工具。</b></p>
  <div class="box proj"><span class="lb">落地顺序</span>① 给 <code>ai-daily/</code> 打第一个基线 commit；② 把「改动前先 commit」写进 <code>AGENTS.md</code> 第 4 节；③ 每次交付一个 commit，信息写「做了什么」而不是 <code>update</code>；④ 大改版式时开分支。四步都不需要额外工具。</div>
'''

EXTRA["ch7"] = r'''
  <h3>现场演示：把临时验证串成一条命令</h3>
  <p><code>examples/verify_all.py</code> 把前面几章散落的检查收进一个只读套件。默认实测：</p>
  <pre><code>$ python examples/verify_all.py
[PASS] structure      32/32 条断言
[PASS] idempotence    沙盒流水线连跑两次，4 份中间产物 md5 一致
[PASS] artifacts      dex/assets 齐全；v1 签名文件 3 个；本地与 site 副本 md5 一致
[FAIL] contract       4 项漂移（C1 契约落地 / C2 结构 / C3 被加载 / C5 跨任务特例）
[SKIP] online         加 --online 启用
[SKIP] browser        CDP 390px 真实视口
[SKIP] golden         golden sample 截图比对
[SKIP] signing        APK 密码学验签
--- 结论：PASS 3 / FAIL 1 / SKIP 4 ---     退出码 1

$ python examples/verify_all.py --skip-contract
--- 结论：PASS 3 / FAIL 0 / SKIP 5 ---     退出码 0

$ python examples/verify_all.py --online --skip-contract
[PASS] online         线上 185915 字节，md5 一致
--- 结论：PASS 4 / FAIL 0 / SKIP 4 ---     退出码 0</code></pre>
  <div class="box why"><span class="lb">这章最重要的一条</span><b>SKIP 不计入通过。</b>浏览器视口、golden 截图、密码学验签这次都没跑，报告就如实列 4 条 SKIP 并给出启用命令。把「没测」写成「通过」是评估里最常见的自欺；<code>--skip-contract</code> 允许把已知技术债显式标为跳过，但绝不把它染绿。<b>报告的价值在于它敢说哪些没验证。</b></div>
  <p>另外注意：套件默认会报契约 4 项 FAIL，这不是 bug，是第 1 章的落地作业还没做。等 <code>AGENTS.md</code> 拷进项目、脚本引用它、跨任务硬编码清掉，这一项会自己变绿。</p>

  <h3>质量评估：把你第 14 版的量表搬到 agent 交付上</h3>
  <p>「星探指数」五项各 20 分、入选线 70、四项一票否决——这套设计完全可以直接用来评价 agent 每次交付：</p>
  <table>
    <tr><th>维度</th><th>满分</th><th>怎么给分（可查证）</th></tr>
    <tr><td>验收通过度</td><td>20</td><td><code>validate.py</code> 首次全绿 20，返工一轮扣 5</td></tr>
    <tr><td>约束遵守</td><td>20</td><td>路径 / 期号 / 引号 / 不变量逐条核对</td></tr>
    <tr><td>事实可追溯</td><td>20</td><td>每个数字有 source 与 date，跨版无冲突</td></tr>
    <tr><td>最小改动</td><td>20</td><td><code>git diff</code> 只含本次该改的文件</td></tr>
    <tr><td>失败透明</td><td>20</td><td>未验证项写进说明，不把未知说成通过</td></tr>
  </table>
  <p>一票否决：改了运行中自动化却没备份、发布未经授权、把 SKIP 算成 PASS。<b>量表的关键不是分数，是每一项都能拿出证据</b>，否则又变回「感觉这期不错」。</p>

  <h3>golden sample 怎么建、三个指标怎么记</h3>
  <pre><code>learn-agent/golden/
  AI晨报-2026-11-05.html     # 人工确认「这期是好的」
  expected.json               # {"sections":15,"razors":15,"issue":"002","plain":5}
# 以后换版式 / 换模型：跑 verify_all.py，再比 expected.json

metrics.csv                  # 每天一行，能被看到才会被改善
date,first_pass,rounds,silent_fail_hours,note
2026-11-05,0,6,,v1→v6 靠人眼
2026-11-06,1,1,0,接了闸门与 status.json</code></pre>
  <p>三个运营指标：<b>一次通过率</b>（首次就绿的比例，直接反映第 1、2 章成效）、<b>返工轮次</b>（你的基线是 6 轮，目标 1–2）、<b>静默故障时长</b>（从发生到被发现）。不需要看板，一个 CSV 就够。</p>
  <div class="box drill"><span class="lb">补充动手练</span>
    <ol>
      <li>跑 <code>python examples/verify_all.py --json</code>，把结构化报告存成文件，看 SKIP 项是否被如实记录。</li>
      <li>故意删掉 <code>[hidden]</code> 兜底，跑套件确认 structure 会红；改回来再跑一次。</li>
      <li>给评分表加一条你自己的一票否决项，并说明它对应哪次真实故障。</li>
    </ol>
  </div>
'''

EXTRA["ch8"] = r'''
  <h3>现场演示：四个机制，四种结局</h3>
  <p><code>examples/agent_loop.py</code> 用确定性规则模拟 <code>model.decide()</code>，不调用真实模型也能把四种情况跑通：</p>
  <pre><code>=== 正常：只读三件 + 授权写入 ===
  调用：['read_sensors','list_processes','read_log','write_diagnosis']
  花费：480 tokens / 步数 4    落库诊断：1 条

=== 未授权：只给只读工具 ===
  调用：['read_sensors','list_processes','read_log']
  拦截：副作用工具未授权：只读完成，不写入    落库诊断：0 条

=== 成本上限（200）===
  调用：['read_sensors']
  拦截：成本上限：120 + 120 &gt; 200

=== 模型幻觉调用未知工具 ===
  调用：['read_sensors','list_processes']
  拦截：白名单拦下未知工具 delete_logs</code></pre>
  <p>最后一个用例最关键：<b>模型「想」调一个不存在的工具时，外壳直接拒掉</b>，而不是把错误抛给下游或让它换个名字再试。白名单不是文档里的一句话，是循环里的一行 <code>if name not in TOOLS</code>。</p>

  <h3>工具契约：把边界写成 schema，而不是写在提示词里</h3>
  <pre><code>{
  "read_sensors":  { "side_effect": false, "args": {},
                     "desc": "只读：返回 CPU/GPU 温度、占用率、风扇转速" },
  "list_processes":{ "side_effect": false, "args": {},
                     "desc": "只读：按 GPU 占用排序列出进程" },
  "read_log":      { "side_effect": false, "args": {"n": "1-20"},
                     "desc": "只读：最近 n 条系统日志" },
  "write_diagnosis":{ "side_effect": true, "needs_approval": true,
                     "desc": "唯一写操作：把一句带依据的诊断记入日志" }
}</code></pre>
  <p>每个工具都写清 <code>side_effect</code> 和参数范围。这段 schema 本身就是喂给模型的上下文——写得含糊等于放权；写成结构化字段，外壳就能在调用前机械判断该不该拦。</p>

  <h3>trace 该记什么，以及四级放行顺序</h3>
  <table>
    <tr><th>字段</th><th>为什么必须有</th></tr>
    <tr><td>step / tool / args</td><td>复盘「它为什么这么做」，而不是只看最终结果</td></tr>
    <tr><td>result</td><td>区分「模型说错了」和「工具返回错了」</td></tr>
    <tr><td>cost / 累计 spent</td><td>成本上限才有依据，不是拍脑袋</td></tr>
    <tr><td>event：TOOL / BLOCKED</td><td>被拦也要留痕，否则你以为它没尝试过</td></tr>
  </table>
  <p>放行顺序永远不能跳：<b>只读 → 可观测 → dry-run → 才给写权限（且配回滚）</b>。方案 B「晨报事实核查 agent」之所以是最低风险的起点，是因为它<b>只有否决权、没有发布权</b>：输出一份冲突清单，由人决定是否采纳，连写权限都不用给。</p>
  <div class="box proj"><span class="lb">方案 A 怎么评价它说得对不对</span>监测器诊断 agent 的输出不能只写「温度偏高」，必须<b>引用 trace 里的具体读数</b>（如「GPU 97%、blender.exe 占 71%、驱动 26.9.1」）。评估方式：把诊断里的每个数字回查 <code>read_sensors</code> / <code>list_processes</code> 的返回值，对不上就判失败。这样第 2 章的断言就能复用在自然语言输出上——<b>让「有依据」变成可机器核对的事</b>。</div>
  <div class="box drill"><span class="lb">补充动手练</span>
    <ol>
      <li>跑 <code>python examples/agent_loop.py</code>，对照完整 trace JSON 找出每一步的 cost 与 event。</li>
      <li>把 <code>token_budget</code> 改成 1000，观察它是否会走到 <code>write_diagnosis</code>；再改 <code>max_steps=2</code> 看步数上限。</li>
      <li>给 <code>write_diagnosis</code> 加一个 dry-run 模式：只打印将要写入的内容，不落库。</li>
    </ol>
  </div>
'''

EXTRA["apxA"] = r'''
  <h3>逐周命令清单（把表格变成能直接跑的动作）</h3>
  <pre><code># 第 1 周 · 上下文工程 + 验收前置
cp learn-agent/templates/AGENTS.md ai-daily/AGENTS.md     # 按实际路径表改一遍
python learn-agent/examples/validate.py ai-daily           # 32/32
python learn-agent/examples/check_contract.py ai-daily     # 看 4 项漂移
python learn-agent/examples/repair_loop.py                 # 闭环演示
python learn-agent/examples/repair_loop.py --gate ai-daily # 发布闸门
验收：故意删一条锐评 → validate.py 退出 1 → 不发布

# 第 2 周 · 流水线 + 权限
python learn-agent/examples/pipeline.py                    # 6 阶段
python learn-agent/examples/pipeline.py --from write       # 续跑
python learn-agent/examples/pipeline.py --twice            # 幂等
python learn-agent/examples/pipeline.py --bad-material     # 事实核查拦截
验收：断在任一步能只补那一步；A/B/C 三档写进 AGENTS.md 第 7 节

# 第 3 周 · 状态 + 回滚
python learn-agent/examples/status.py --json
cd ai-daily &amp;&amp; git init &amp;&amp; git add -A &amp;&amp; git commit -m "基线"
验收：连续 3 天无人干预正常出报；git diff 能定位；一句话回滚

# 第 4 周 · 回归 + 产品化
python learn-agent/examples/verify_all.py --online --json
python learn-agent/examples/agent_loop.py
验收：改版式后套件报出退化；原型只有只读工具且留全 trace</code></pre>
  <p>四条「现在就能跑」的命令里，前两条是只读体检，后两条在临时沙盒里造文件，<b>都不会碰正在运行的 ai-daily</b>。想练手不用担心搞坏日报。</p>

  <h3>怎么判断「学完了」</h3>
  <ul class="chk">
    <li>整套链路连续跑一周、你一次都没手动补过，且每天 <code>status.json</code> 都是 OK。</li>
    <li>出问题时五分钟内能说出断在 <code>generate / validate / index / publish</code> 的哪一步，依据是状态和断言原文，不是回忆。</li>
    <li>你敢让 agent 直接改运行中的项目，因为改动前有 commit、改动后有闸门、失败有状态、发布有授权。</li>
  </ul>
  <p>三条都不是「读完了 8 章」，而是可验证的行为。<b>判断标准必须是能观察的事实</b>——这和整套教材讲的是同一件事。</p>
'''

EXTRA["apxB"] = r'''
  <h3>本轮新发现的五条（都来自刚才真实跑出来的 bug）</h3>
  <table>
    <tr><th style="width:34%">反模式</th><th>真实后果</th><th>改成 / 章节</th></tr>
    <tr><td>断言失败信息不带实测值</td><td>「报纸已同步进 site/」没有 detail，工单里只有「不通过」，agent 无从下手</td><td>补成「site/ 缺 · 源 有」· 第 2 章</td></tr>
    <tr><td>把 SKIP 算作通过</td><td>浏览器视口、验签都没跑，报告却显示全绿</td><td>SKIP 显式列出且不计入 PASS · 第 7 章</td></tr>
    <tr><td>阶段续跑缺少前置检查</td><td><code>--from write</code> 在空沙盒抛 FileNotFoundError，看不出该先跑哪步</td><td>REQUIRED 表 + 可读报错 · 第 3 章</td></tr>
    <tr><td>状态常量大小写不一致</td><td>trace 记 <code>TOOL</code>、决策数 <code>tool</code>，循环空转六步重复读传感器</td><td>常量统一，且加循环上限 · 第 8 章</td></tr>
    <tr><td>代码里跨任务硬编码</td><td>构建脚本被复制进沙盒后仍去扫真实目录，幂等测不准</td><td>唯一真源 + 沙盒流水线 · 第 1、3 章</td></tr>
  </table>
  <p>这五条有个共同点：<b>都是「看起来能跑、实际没跑对」</b>，人眼扫一遍几乎发现不了，只有把断言、闭环、回归真正跑起来才暴露。这也是为什么故障复盘的产出应该是一条断言，而不是一句「以后注意」。</p>
  <div class="box drill"><span class="lb">怎么用这张表</span>每次 agent 交付后，花两分钟从上到下扫一遍，命中任何一条就先别发布。等附录 D 的清单脚本化之后，这张表里能自动检测的部分应该交给 <code>verify_all.py</code>，人只负责需要判断的几条。</div>
'''

EXTRA["apxC"] = r'''
  <h3>补充术语</h3>
  <table>
    <tr><th style="width:24%">词</th><th>这里指什么</th></tr>
    <tr><td><b>发布闸门</b></td><td>校验退出码决定是否允许发布；在副作用动作之前，不在之后。</td></tr>
    <tr><td><b>失败工单</b></td><td>把断言的失败原文（含实测值）结构化后回传给 agent 的输入，不是日志。</td></tr>
    <tr><td><b>熔断</b></td><td>连续 N 次失败就停止重试、留状态、等人介入，防止无限循环。</td></tr>
    <tr><td><b>SKIP</b></td><td>明确记录「本次没测」及启用方式；绝不计入通过数。</td></tr>
    <tr><td><b>dry-run</b></td><td>只打印将要执行的动作与参数，不产生任何副作用。</td></tr>
    <tr><td><b>trace</b></td><td>每步工具调用、参数、返回、成本、是否被拦的完整记录。</td></tr>
    <tr><td><b>schema</b></td><td>中间产物或工具参数的字段约定；结构化才能被断言检查。</td></tr>
    <tr><td><b>全量重建</b></td><td>每次重算整份索引而非追加；天然幂等，重跑不会重复。</td></tr>
    <tr><td><b>A/B/C 权限档</b></td><td>可自动 / 做完报备 / 必须先问，三档动作写进契约与 guard 函数。</td></tr>
    <tr><td><b>一次通过率</b></td><td>agent 首次交付就跑过全部断言的比例，反映上下文工程与验收前置的成效。</td></tr>
  </table>
  <h3>三组最容易混淆的</h3>
  <table>
    <tr><th>对比</th><th>区别</th></tr>
    <tr><td>幂等 / 原子写</td><td>幂等说「重跑结果一样」；原子写说「任一瞬间不会看到半截文件」。前者关于重复执行，后者关于并发可见性。</td></tr>
    <tr><td>PARTIAL / FAILED</td><td>PARTIAL 有成功步骤、可定点补偿；FAILED 全败或从第一步就断，需要整轮重来或人工介入。</td></tr>
    <tr><td>SKIP / PASS</td><td>PASS 是跑过且通过；SKIP 是根本没跑。报告里混在一起就等于撒谎。</td></tr>
  </table>
'''

EXTRA["apxD"] = r'''
  <h3>能脚本化的先脚本化，剩下的才靠人</h3>
  <p>这 15 条里，至少 9 条已经由配套脚本覆盖。交付前先跑这一条：</p>
  <pre><code>python learn-agent/examples/verify_all.py --online --json
# 覆盖：结构断言、幂等、APK 完整性、契约漂移、线上 md5
# 仍需人工：授权确认、commit 快照、golden 截图比对、真实视口 CDP、未验证项说明</code></pre>
  <table>
    <tr><th>清单条目</th><th>谁判</th><th>命令 / 依据</th></tr>
    <tr><td>路径唯一真源、契约被加载</td><td>脚本</td><td><code>check_contract.py</code> C1–C3</td></tr>
    <tr><td>验收断言全绿、失败原文未转述</td><td>脚本</td><td><code>validate.py</code> / <code>repair_loop.py --gate</code></td></tr>
    <tr><td>跨文件一致性、幂等、产物完整</td><td>脚本</td><td><code>verify_all.py</code></td></tr>
    <tr><td>改动前 commit、授权、未验证项说明</td><td>人</td><td><code>git status</code> + 当轮确认 + 交付说明</td></tr>
    <tr><td>真实视口、golden 截图、密码学验签</td><td>人 / 按需</td><td>套件里列为 SKIP 并给启用命令</td></tr>
  </table>

  <h3>交付说明模板</h3>
  <pre><code>做了什么：____（一句话）
改动文件：____（列具体路径）
验证结果：validate 32/32、verify_all PASS x / FAIL x / SKIP x
未验证项：____（照抄报告里的 SKIP，不许省略）
可回滚点：commit ____；失败时状态文件 ____
需要我确认的动作：____（C 档，逐条列）</code></pre>
  <p>最后一行「需要我确认的动作」不能省。C 档动作必须在当轮明确授权，同意不跨轮——这条是本项目踩出来的，写进模板才不会忘。</p>
'''

EXTRA["apxE"] = r'''
  <p>八章讲的是方法，这一节给你一个<b>能跑的同构样本</b>：<code>learn-agent/demo/</code>。业务是「每天生成一张晨读卡」，规模只有晨报的 1/20，但工程结构和晨报一模一样——契约、断言、五阶段流水线、状态机、发布闸门、回归套件，一样不少。它不读写 <code>ai-daily/</code> 的任何文件，练坏了只影响它自己。</p>

  <h3>为什么另起一个项目，而不是在晨报上练</h3>
  <p>不是怕你搞坏，是因为在晨报上练，出了问题你分不清是<b>方法错了</b>还是<b>这一期素材不好</b>。样本项目把业务复杂度压到最低，剩下的全是工程问题——正好是你要练的那部分。</p>
  <table>
    <tr><th style="width:26%">晨报</th><th style="width:24%">晨读卡</th><th>迁移时改什么</th></tr>
    <tr><td>15 个版面的报纸</td><td>1 张卡片</td><td>模板与 CSS</td></tr>
    <tr><td>12 路检索 + 15 版正文</td><td>1 条本地素材</td><td>素材来源换成检索结果</td></tr>
    <tr><td><code>issues.js</code> 往期索引</td><td><code>index.json</code> + 卡片墙</td><td>索引字段</td></tr>
    <tr><td><code>validate.py</code> 32 条断言</td><td>20 条断言</td><td>断言内容</td></tr>
    <tr><td><code>status.json</code> 状态机</td><td>同一套状态机</td><td><b>不用改</b></td></tr>
    <tr><td>发布到公网</td><td>不发布（故意留白）</td><td>加一步部署 + 授权</td></tr>
  </table>

  <h3>七步与八章的对应</h3>
  <table>
    <tr><th style="width:9%">步</th><th style="width:30%">做什么</th><th>命令</th><th style="width:22%">为什么（章节）</th></tr>
    <tr><td>1</td><td>立契约：唯一真源、不变量、权限档</td><td><code>python tools/validate.py</code></td><td>无状态 → 约定落文件（0、1）</td></tr>
    <tr><td>2</td><td>先写断言，再写生成器</td><td><code>python tools/validate.py</code></td><td>验收前置，先定义「对」（2）</td></tr>
    <tr><td>3</td><td>拆五阶段：select→render→index→precheck→publish</td><td><code>python tools/build.py --date 2026-11-06</code></td><td>可验证流水线（3）</td></tr>
    <tr><td>4</td><td>让输出可复现：排期时间 + 幂等</td><td><code>... --twice</code></td><td>非确定性来源（3）</td></tr>
    <tr><td>5</td><td>原子写与 HTML 转义</td><td><code>--date 2026-11-10</code> 后 grep 实体</td><td>副作用与注入（4）</td></tr>
    <tr><td>6</td><td>状态机 + 闸门 + 断点续跑</td><td><code>gate.py --break</code> / <code>--resume</code></td><td>失败之后怎么办（5）</td></tr>
    <tr><td>7</td><td>一键回归 + 变异测试 + 快照回滚</td><td><code>python tools/verify.py</code></td><td>评估与回滚（6、7）</td></tr>
  </table>

  <h3>实测：一条命令给出的三个答案</h3>
  <pre><code>$ python tools/verify.py
[PASS] contract     契约有效 · 零 ai-daily 路径引用
[PASS] assertions   20/20 通过
[PASS] idempotence  连跑两次，4 份中间产物 md5 一致
[PASS] mutation     破坏 2026-11-06.html 后断言返回 1（会红）
[PASS] escape       尖括号与 &amp; 均为实体
[SKIP] browser      加 --browser 启用（需本机 Edge，本次未跑）
--- 结论：PASS 5 / FAIL 0 / SKIP 1 ---     退出码 0</code></pre>
  <p>三个答案分别是：<b>现在对了吗</b>（assertions）、<b>重跑会变吗</b>（idempotence）、<b>坏了会红吗</b>（mutation）。第三个最容易被省略——不做变异测试，你不知道断言有没有在检查。</p>

  <h3>三个真实踩到的坑（都写进了手册）</h3>
  <table>
    <tr><th style="width:30%">坑</th><th>现象</th><th style="width:30%">正确做法</th></tr>
    <tr><td>断言按 ISO 日期查卡片</td><td>页面显示「11 月 6 日」，断言找 <code>2026-11-06</code>，把正确的卡拦下</td><td>按人看到的东西断言；先怀疑断言</td></tr>
    <tr><td>补偿点设成 <code>precheck</code></td><td>续跑仍然红——判定不负责修复</td><td>断点指向能重新生成产物的 <code>index</code></td></tr>
    <tr><td>「互不干扰」检查字眼</td><td>契约里「<b>不</b>引用 ai-daily」这句合法声明被误判</td><td>只认路径式引用 <code>ai-daily/</code></td></tr>
  </table>

  <div class="box why"><span class="lb">样本项目的价值不在代码</span>这 4 个脚本加起来不到 700 行，照抄到晨报也不能直接用。真正能带走的是<b>三处顺序</b>：断言写在生成之前、闸门排在发布之前、补偿点指向生成而不是判定。<b>顺序错了，代码再漂亮也救不回来。</b></div>

  <div class="box drill"><span class="lb">动手练</span>
    <ol>
      <li>跑 <code>python tools/gate.py --date 2026-11-09 --break</code>，把工单里的两条失败分别对应到「哪一步坏了」「该修哪个文件」。</li>
      <li>在 <code>data/quotes.json</code> 里加一条带 <code>&lt;</code> 的素材，出卡后确认页面上显示原文而不是少字。</li>
      <li>把 <code>updated</code> 改成 <code>datetime.now()</code>，跑 <code>--twice</code> 看幂等怎么红；再改回来。</li>
    </ol>
  </div>
  <p>完整逐步讲解见 <code>learn-agent/demo/指导手册.md</code>：每步都写了做什么、为什么、怎么算做对了、以及踩过的坑。</p>
'''


EXTRA["apxF"] = r'''
  <p>前八章讲「应该怎么设计」，附录 E 给了一个能跑的同构样本。这一节反过来：<b>拿 2026-11-06 这一天真实发生的六轮需求，看这些方法接得住接不住</b>。不教新概念，只练三种判断：检查器全绿为什么还会错、改一处要同步几处才算完成、以及怎么证明闸门真的会红。</p>

  <div class="box why"><span class="lb">怎么学这一节</span>先读 F.3（假绿）、F.4（五层闸门）、F.5（反向验证），再回头看 F.1 的时间线——先有判断框架，流水账才有用。练习一律改在 <code>learn-agent/demo/</code> 里，不要在 <code>ai-daily/</code> 上试，理由和附录 E 一样：生产项目里分不清「方法错了」还是「这期素材不好」。</div>

  <h3>F.1 一天的时间线：改动、暴露的问题、最后固化成什么</h3>
  <table>
    <tr><th style="width:13%">时段</th><th style="width:30%">做了哪些修改</th><th style="width:28%">暴露的问题</th><th>固化成的方法</th></tr>
    <tr><td>10:15–11:00</td><td>出 003 期；撤掉全部定时 automation；新增 <code>boot_check.py</code> 注册为 SessionStart hook</td><td>定时流程与手动拼版写同一个文件名，谁后写谁赢，且不报错；手机看到旧版是启发式缓存</td><td><b>同名闸门</b>（目标已存在且内容不同 → 退出码 3，要 <code>--force</code>）；hook 三态 ok / missing / drift；<code>sw.js</code> 导航 <code>no-store</code></td></tr>
    <tr><td>11:00–13:10</td><td>立契约 <code>AGENTS.md</code>、四级规则、五阶段状态机、分享三渠道、第 16 版提案模板</td><td>「发布成功」不等于「用户看得见」；状态漏记会让次日启动检查误判</td><td>状态机 parts/assemble/index/deploy/verify；提案<b>沉默即否决</b>；发布后 curl 验四处才记 OK</td></tr>
    <tr><td>17:30</td><td>采纳 P004 三条，出 16 版傍晚特刊：三行摘要、六处术语注解、每期 manifest</td><td>从 15 版复制成 16 版，<b>14 处页眉的「共 15 版」没跟着改</b>——当时没发现</td><td>（当时只修了气泡定位、词表一致性等表层问题，<b>漏掉的这条到 19:15 才被外部评审抓到</b>）</td></tr>
    <tr><td>18:40–19:15</td><td>补特刊三处入口、术语 A9 系列断言、每期 json、<code>selfcheck.py</code>；特刊改编号 003-2 并入正刊序列；撤下 11-07 未来期</td><td>特刊只在 <code>site/special/</code> 里，索引和入口都没有它；另一会话预拼了「明天的报」并发布</td><td>三处可见（横幅 / 书架 / 深链）；<b>日期闸门 R07</b> 查根目录、站点、索引、状态机四处；<code>issues</code> 按 <code>(date, issue)</code> 倒序</td></tr>
    <tr><td>19:15–19:30</td><td>复核外部评审 7 条，修「假绿」：A4d、<code>pages_all_match</code>、自检第 11/12 项、<code>--list</code>、<code>requirements.txt</code></td><td>自检 11 项全绿，读者却看到错版数；只验 HTTP 200 也是假绿</td><td>全文对账、必查项不许 None、线上 sha 比对、文档不再写死项数</td></tr>
    <tr><td>19:35</td><td>把「定时器未触发」等内部运营话术统一成「本期因故延后发布」，保留更正说明叙事</td><td>同类话术不只在一处：<b>已发布的 002 期也有</b>；新闻正文里的「官方补发脚本」长得像但不能一起替换</td><td>bytes 级精确替换 + 命中数校验；改完走「同步 → 凭证 → 自检 → 发布 → 抽检 → 记状态 → 提交」七步</td></tr>
  </table>
  <p>看最后一列：几乎每一轮的终点都不是「改好了」，而是<b>加了一道以后能自动拦住的闸门</b>。只改内容不做固化的修复，下次会换个样子回来。</p>

  <h3>F.2 先给故障分类，再动手修</h3>
  <table>
    <tr><th style="width:20%">类别</th><th style="width:38%">今天的实例</th><th>该由哪一层拦</th></tr>
    <tr><td>写入冲突</td><td>两版 003 互覆盖、同名文件谁后写谁赢</td><td>生成器落盘前的同名闸门</td></tr>
    <tr><td>一致性漂移</td><td>根目录与 <code>site/</code> 两份、术语注解与报尾词表、文档里的自检项数</td><td>单向同步 + 跨文件断言 + 单一事实源</td></tr>
    <tr><td>可见性</td><td>特刊没进索引、手机看到缓存旧版、发布成功但打不开</td><td>入口断言 + 线上验证（不是「文件存在」）</td></tr>
    <tr><td>假绿</td><td>14 处页眉写错版数却全绿、只验 200 不验内容</td><td>全量检查 + 三态收紧 + sha 对账</td></tr>
    <tr><td>边界越权</td><td>提前发布明天的报、提案没被点名就自行实施</td><td>L0 红线 + 默认行为写死</td></tr>
  </table>
  <p>分类不是为写报告，是为了问一句：<b>同一类故障是不是由同一道闸门在管？</b>如果两次「漂移」靠两个不同的补丁挡着，说明还没找到机制层。</p>

  <h3>F.3 假绿：今天最贵的一课</h3>
  <p>外部评审一句话戳中要害：特刊是 16 版，读者翻到第 15 版，页眉写着「共 15 版」，而自检盖的是全绿章。拆开来是三种形态，<b>每一种单看都很「合理」</b>。</p>

  <h4>① 抽样当全量</h4>
  <p>断言 A4b 检查了 <code>&lt;title&gt;</code>、报头、报尾三处的版数，三处都对；可页眉有 14 处，一处都没查。<code>make_manifest.py</code> 的 <code>pages_in_title</code> 更省事，只从标题取一个数。修法不是「再加一处抽查」，是<b>把检查对象从「代表样本」换成「全部实例」</b>：</p>
  <pre><code>claims = re.findall(r"共\s*(\d+)\s*版", full)      # 全文，不是前三处
if len(claims) != pages or any(int(x) != pages for x in claims):
    errs.append("A4d 全文 %d 处版数写法与实际 %d 版不符" % (len(claims), pages))

# 页眉还要单独对账：条数 = 版数 - 1，页码 p02..p16 连续
headers = re.findall(r"第\s*(\d+)\s*版\s*/\s*共\s*(\d+)\s*版", full)
assert len(headers) == pages - 1 and all(int(m) == pages for _, m in headers)</code></pre>

  <h4>② 三态里的 <code>None</code> 被放行</h4>
  <p>凭证里用 <code>True / False / None</code> 三态，<code>None</code> 表示「本期没这个版式，不参与判定」。但汇总写成了：</p>
  <pre><code>ok = all(v is not False for v in checks.values())   # None 也算过

# 正确做法：先分清「必查项」和「可选项」
REQUIRED = ("pages_eq_nav", "nav_matches_sections",
            "sections_continuous", "pages_all_match")
ok = (all(checks[k] is True for k in REQUIRED)          # 必查项取不到就判 False
      and all(v is not False for v in checks.values())) # 可选项只不许 False</code></pre>
  <p>「取不到值」和「检查通过」是两件事。把前者当成后者，等于给检查器留了一个静默的后门。</p>

  <h4>③ 只验可达，不验内容</h4>
  <p>线上检查原来只请求到 HTTP 200 就算过。改完本地文件没发布，200 照样有——于是又出现「本地是新版、线上是旧版、自检全绿」。修法是<b>比对内容摘要</b>：把本地成品的 sha256 与线上响应体算出来的 sha256 对齐，不一致就红。</p>

  <div class="box warn"><span class="lb">一句话定理</span>检查器只能证明它检查过的东西。<b>绿章的可信度等于覆盖面的下界，不等于通过项的数量。</b>所以「自检从 8 项加到 10 项」本身不提升安全性——新增的两项如果仍是抽样，错的东西照样在覆盖之外。</div>

  <h3>F.4 五层闸门：缺一层就漏一类</h3>
  <table>
    <tr><th style="width:16%">层</th><th style="width:32%">今天的实例</th><th style="width:26%">拦什么</th><th>为什么不能并到别层</th></tr>
    <tr><td>L0 红线（契约）</td><td>R06 自检有 FAIL 不许说完成；R07 报纸日期必须是出报当天</td><td>人和 agent 的行为</td><td>代码拦不住「嘴上说已完成」</td></tr>
    <tr><td>落盘前断言</td><td>A4b/A4c/A4d 版数与期号、A9 系列术语一致</td><td>生成物本身错</td><td>落盘后再查，读者已经能看到</td></tr>
    <tr><td>交付前自检</td><td><code>selfcheck.py</code>：索引、凭证、期序、日期、全文版数</td><td>跨文件一致性</td><td>单个生成器看不到别的文件</td></tr>
    <tr><td>发布后线上验证</td><td>curl 五处 200 + sha 比对 + 手机视口 CDP</td><td>部署漏文件、缓存给旧版</td><td>本地全绿推不出线上对</td></tr>
    <tr><td>状态机与凭证</td><td><code>status.json</code> 五阶段、每期同名 json</td><td>「谁在什么时候验过」</td><td>没记录就无法判断明天该不该重跑</td></tr>
  </table>
  <p>每一层都要能<b>独立说红</b>，而且红的时候给出「哪里 / 期望什么 / 实际什么」，不能只给一个退出码。</p>
  <div class="box proj"><span class="lb">最容易被跳过的是第五层</span>撤下 11-07 未来期时，除了移走文件、删站点副本、重建索引，还必须把 <code>status.json</code> 回滚到 11-06/003。否则次日的启动检查读到「11-07 已完成」，会判定 <code>ok</code> 而静默——<b>明天的报就没人做了</b>。状态不是日志，是下一轮决策的输入。</div>

  <h3>F.5 反向验证：修完还得证明闸门会红</h3>
  <p>「跑一遍全绿」只证明现在没坏；「故意弄坏看它红」才证明检查器在工作。今天在真实项目里做了五次：</p>
  <table>
    <tr><th style="width:42%">故意弄坏</th><th>期望谁红</th></tr>
    <tr><td>移走一份 json</td><td>自检「每期都有 manifest」红</td></tr>
    <tr><td>往 <code>p07.html</code> 塞回「共 15 版」</td><td>拼版断言 A4d 红，产物不许落盘</td></tr>
    <tr><td><code>AI_DAILY_TODAY=2026-11-05</code> 假装是昨天</td><td>日期闸门红（今天这份成了「未来期」）</td></tr>
    <tr><td>临时目录里放一份 11-07 的报纸</td><td><code>build_index.py</code> 跳过并告警，不同步</td></tr>
    <tr><td>本地改了文案但不发布</td><td>线上 sha 比对红——这次它真的红了，说明改动没同步</td></tr>
  </table>
  <p>这就是第 7 章的变异测试。<b>没做过反向验证的自检项，只能算「写过」，不能算「有用」。</b></p>
  <div class="box proj"><span class="lb">把一次性验证固化成命令</span>当天这五次全是手工命令，跑完就没了——教案教了，生产项目却没留下入口。后来补了 <code>python ai-daily/tools/mutation_test.py</code>：在临时目录里给每个检查项造一个反例（错版数、缺凭证、等长漂移、未来期……），要求对应检查项变红，反例不碰任何成品。<b>以后每加一条自检项，就在这里补一个变异</b>，否则新项只是「写过」。<br>最初有两项被如实标成 SKIP：术语缺词表缺 HTML fixture、线上 sha 要「改了没发布」不便制造事故。后来都用<b>隔离替身</b>补齐——复制一份真实特刊、把报尾词表整批改错字；起一个 <code>127.0.0.1</code> 随机端口的假站点，只对本地副本做等长替换。<b>不能制造的事故，就造一个隔离的替身</b>，不要因此把检查项留在「没测」里。<br>每个反例还必须先跑一次<b>正向对照</b>：底板全绿了，弄坏后的红才算数——否则服务没起来也会「变红」，那是<b>假红</b>，比假绿更骗人。跑完报告里 SKIP 也要写出来：没测就是没测。</div>

  <h3>F.6 漂移治理：让事实只有一份</h3>
  <ul>
    <li><b>单向同步 + 独立对账</b>：根目录成品 → <code>site/</code>，按内容比对，内容不变就不写（保住 mtime，manifest 才幂等）。但「同步跑没跑过」不能靠约定保证：自检再把源与副本<b>逐字节</b>比一次。只比 size 会漏掉等长替换——改一个词、改一处版数，字节数一模一样，两份真相从此分叉却无人报警。</li>
    <li><b>凭证对账</b>：每份成品有同名 json，记 <code>path / sha256 / bytes / terms / glossary / checks / ok</code>；自检第 4 项拿它跟实际文件逐个对。</li>
    <li><b>数字不手写第二遍</b>：文档里「自检 8 项 → 10 → 11 → 12」来回改了四轮。最后给脚本加 <code>--list</code>，三份文档统一改成「项数以 <code>--list</code> 为准」，不再写数字；<code>AGENTS.md</code> 里那张手抄的验收表也整个删掉（它一度停在 10 项，脚本已经 12 项），名称和排障提示都由 <code>--list</code> 输出。</li>
    <li><b>教材自己也是这套</b>：增补片段放在 <code>expand_tutorial.py</code> 的 <code>EXTRA</code> 里，靠 <code>&lt;!-- extra:ID --&gt;</code> 标记幂等替换；练习题只在教材写一份，<code>build_qa_index.py</code> 自动派生到《教程问答.md》。</li>
  </ul>
  <p>凡是「同一个事实需要在两处手写」的地方，迟早会漂。能派生就别抄，能比对就别记。</p>

  <h3>F.7 把判断写成规则，而不是靠记得</h3>
  <h4>日期闸门 R07：查四处，不是查一处</h4>
  <p>「不许提前发明天的报」听起来是常识，落地要查：根目录成品、<code>site/</code> 副本、<code>issues.js</code> 索引、<code>status.json</code> 状态机。少查一处，就会从那一处漏回读者面前。构建索引时还要主动跳过未来期并告警。</p>
  <h4>沉默即否决：把默认行为写死</h4>
  <p>第 16 版每期提四条建议，只有用户明确说「采纳 P004-2」才动工；没说就是否决，不自行实施、也不追问。规则的价值在于<b>把「要不要做」从 agent 的临场判断里拿走</b>。</p>
  <h4>发布 ≠ 可见：检查「能不能走到」，不是「文件在不在」</h4>
  <p>特刊当时确实发布成功了，但 <code>issues.js</code> 没有它、入口页没有它，两端都打不开。补齐首屏横幅、往期书架、深链 <code>?d=&amp;s=1</code> 三处才算完成；还要考虑 HTTP 启发式缓存与 Service Worker。</p>
  <h4>同一天两期：先定排序语义，再写页面</h4>
  <p>特刊不是单独的书架区，而是当天的第 2 版 <code>003-2</code>，排序键 <code>(date, issue)</code> 倒序。还有一个反直觉的决定：<b>默认落当天正刊</b>，不是「最新一期」——否则横幅形同废码。默认行为要跟着产品意图走，不能图省事。</p>

  <h3>F.8 评审也要验收；编辑决策别替用户做</h3>
  <p>那份外部评审列了 7 条，逐条核对的结果是：<b>5 条成立、2 条只对一半、3 处细节说错</b>。不核对就照单全收，会白改甚至改坏。</p>
  <table>
    <tr><th style="width:44%">评审原话</th><th>核对结果</th></tr>
    <tr><td>「全项目无来源声明」</td><td>不成立：每期报尾都有「信息源 / 编辑说明 / 本报由 AI 自动编撰」，缺的是项目级演示声明，不是来源</td></tr>
    <tr><td>「双份真相是 11-06 两版互覆盖的根源」</td><td>归因错：那次是拼版脚本同名覆盖，已有退出码 3 的闸门；单向复制反而是能自愈的</td></tr>
    <tr><td>「7 次新提交」</td><td>数字错：当天实际 17 次</td></tr>
  </table>
  <p>最后那轮「只去内部话术」最能说明边界：搜全项目后发现同类话术在 4 个文件里（含<b>已发布的 002 期</b>），但「官方补发 Q4 量化脚本」是新闻正文，长得像却不能替换；「要不要加一行本报告为演示」是编辑决定，用户没选就不做。<b>先分清楚哪些是工程问题、哪些是内容决定，再动手。</b></p>
  <div class="box warn"><span class="lb">四个会骗人的工程细节</span>① Windows 上 <code>Path.write_text()</code> 会把 LF 写成 CRLF，git diff 整文件炸开——用 bytes 级替换并校验每处只命中一次；② <code>msedge --headless --screenshot</code> 是桌面模式，会把 390px 顶栏误报成溢出，布局结论只认 CDP <code>mobile:true</code>；③ 线上中文路径要 percent-encode，还要先访问入口换到 cookie，否则 200 都拿不到；④ 后台进程不能用 shell <code>&amp;</code> 起，会被回收。</div>

  <h3>F.9 今天动过的东西（按用途，不按时间）</h3>
  <table>
    <tr><th style="width:22%">用途</th><th>文件</th></tr>
    <tr><td>生成与断言</td><td><code>tools/assemble_issue.py</code>（15/16 自适应、A4b/A4c/A4d/A9、<code>--slug/--label/--force/--no-site/--no-status</code>）、<code>tools/make_manifest.py</code>、<code>tools/build_index.py</code></td></tr>
    <tr><td>检查与状态</td><td><code>tools/selfcheck.py</code>（项数以 <code>--list</code> 为准；<code>--pre/--online</code>）、<code>tools/mutation_test.py</code>（反向验证）、<code>tools/status.py</code>、<code>tools/boot_check.py</code>、<code>tools/probe.js</code></td></tr>
    <tr><td>页面与入口</td><td><code>site/index.html</code>、<code>site/sw.js</code>、<code>site/config.js</code>、<code>parts/1106sp/</code>、<code>parts/_template/</code></td></tr>
    <tr><td>文档与治理</td><td><code>AGENTS.md</code>、<code>项目框架与规则.md</code>（四级规则）、<code>产物清单.md</code>（产出台账）、<code>提案台账.md</code>、<code>requirements.txt</code>、<code>.gitignore</code></td></tr>
    <tr><td>报纸成品</td><td>001–003 正刊 + <code>003-2</code> 特刊、四份同名 json、<code>_drafts/2026-11-07/</code>（预热稿，禁止直接发布）</td></tr>
  </table>

  <h3>F.10 三张可以抄走的清单</h3>
  <pre><code>【改一处文案之后】
搜全项目 → 分清「运营话术 / 正文内容」→ 改所有源（含备选版本）
→ 重跑单向同步 → 重生成凭证 → --pre → 发布 → --online + 线上抽检
→ 记 deploy/verify → git commit

【收到一份评审之后】
逐条核对（成立 / 部分成立 / 不成立，附证据）→ 只修成立的部分
→ 把根因固化成闸门 → 故意弄坏一次看它会不会红 → 再发布 → 复验

【说「已完成」之前】
--pre 全绿 → --online 全绿 → 没有「本地改了没发布」的漂移
→ 状态机五阶段齐 → 有一个可回滚的 commit → 未验证项如实列出</code></pre>

  <div class="box drill"><span class="lb">动手练</span>
    <ol>
      <li>在 <code>learn-agent/demo/</code> 里把 <code>validate.py</code> 的一条断言改成「只检查第一张卡片」，跑 <code>verify.py</code> 看它是否仍然全绿；再改回全量，用一句话说明抽样为什么危险。</li>
      <li>在 <code>ai-daily/tools/make_manifest.py</code> 里找出一处三态 <code>None</code>，判断它属于「必查项」还是「可选项」；把必查项取不到值的情况改成判 False，并故意让它取不到，确认 <code>ok</code> 变红。</li>
      <li>用 <code>AI_DAILY_TODAY</code> 分别模拟「昨天」和「明天」，写出日期闸门在两种情况下各应给什么结论，说明为什么状态机也必须一起查。</li>
      <li>从 R07（日期）、沉默即否决、发布≠可见里挑一条，写成一道能自动判定的断言，并指出它该放在 F.4 五层中的哪一层、为什么。</li>
      <li>挑一段已发布的正文，列出「改它之前要搜哪些位置、哪些字符串不能一起替换」，写成一份替换清单，再说明哪一步属于编辑决策、不该由你替用户定。</li>
    </ol>
  </div>

  <div class="box why"><span class="lb">带走的三个判断</span><b>① 绿章不等于对</b>——先问检查器覆盖了什么；<b>② 改完不等于完成</b>——源、副本、凭证、索引、状态、线上、提交七处对齐；<b>③ 修完不等于会防复发</b>——故意弄坏一次，看它会不会红。这三条比今天新增的任何一个脚本都值钱。</div>
'''


def main() -> int:
    t = TUTORIAL.read_text(encoding="utf-8")
    for sid, frag in EXTRA.items():
        begin, end = f"<!-- extra:{sid} -->", f"<!-- /extra:{sid} -->"
        block = begin + "\n" + frag.strip() + "\n" + end + "\n"
        pat = re.compile(r'(<section id="' + re.escape(sid) + r'">)(.*?)(</section>)', re.S)
        m = pat.search(t)
        if not m:
            print(f"[MISS] {sid}")
            continue
        body = m.group(2)
        if begin in body:
            body = re.sub(re.escape(begin) + r'.*?' + re.escape(end) + r'\n?',
                          lambda _: block, body, flags=re.S)
            act = "replace"
        else:
            anchor = ANCHORS.get(sid)
            if anchor and anchor in body:
                body = body.replace(anchor, block + anchor, 1)
            else:
                body = body.rstrip() + "\n\n" + block
            act = "insert"
        t = t[:m.start()] + m.group(1) + body + m.group(3) + t[m.end():]
        print(f"[{act:<7}] {sid}: +{len(frag)} chars")
    TUTORIAL.write_text(t, encoding="utf-8")
    print("教材总字符：", len(t))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
