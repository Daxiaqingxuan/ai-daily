# AI 晨报 · 项目契约（agent 落地前必读）

> 本文件是 `ai-daily/` 这条线的**执行契约**，比文档更具体；冲突时以本文件为准。
> 全局视图（两条线边界、目录树）见 `../项目框架与规则.md`；给人看的一页入口见 `../README.md`（只做导航，**不降级**本契约）。
> 改约定：先改这里，再改代码，最后同步 `../项目框架与规则.md`。

## 1. 路径（最容易出错，写在最前）

| 用途 | 位置 |
| --- | --- |
| 报纸源文件 | `ai-daily/AI晨报-YYYY-MM-DD.html` —— **唯一保存位置** |
| 版面片段 | `ai-daily/parts/<MMDD>/pNN.html` + `00-style.html` + `00-masthead.html` + `00-tail.html` |
| 主线声明 | `ai-daily/parts/<MMDD>/00-thread.json` —— 本期主线一句话 + 跑偏词 + 阈值；004 期起正刊必填，缺了拼不上版 |
| 事实卡 | `ai-daily/parts/<MMDD>/00-facts.json` —— 断言 / 数值 / 版面 / 来源 / 时点 / 强度 / 是否复现；004 期起正刊必填 |
| 版级来源 | `ai-daily/parts/<MMDD>/00-blocks.json` —— 16 版各一行：官方 / 第三方信息网 / 本报实测 / AI 生成 + 上限；004 期起正刊必填 |
| 信源归属 | `ai-daily/parts/<MMDD>/00-sources.json` —— 谁给的 / 给了什么 / 哪一类 / 怎么用；报尾「信息源与归属」由它渲染 |
| 许可 | 根目录 `LICENSE`（代码 MIT）/ `LICENSE-CONTENT.md`（报纸内容 CC BY 4.0）/ `NOTICE.md`（第三方归属与商标） |
| 16 版骨架 | `ai-daily/parts/_template/` —— 出报时复制，别直接改 |
| 提案台账 | `ai-daily/提案台账.md` —— 提案状态与计数，出报前先结算 |
| 发布目录 | `ai-daily/site/` —— 桌面端与线上都从这里读 |
| 期刊索引 | `site/issues.js` —— 由 `tools/build_index.py` 生成，**禁止手工编辑** |
| 运行状态 | `ai-daily/status.json` —— 由 `tools/status.py` 写，记录当期走到哪一步（git 忽略） |
| 入口页 | `site/index.html` |
| 入口配置 | `site/config.js` —— `siteUrl` 是分享链接的固定基址，改域名必须同步改它；`disclaimer` 是内容声明的唯一事实源 |
| 人类入口 / 免责 | `../README.md` —— 是什么 / 怎么跑 / 两条线边界 / 免责；免责段由 `config.js` 派生，不替代本契约 |
| 特刊 | `site/special/<date>.html` + 同名 `.json`（manifest）；源文件 `AI晨报-<date>-特刊.html`；期号接当天正刊（`003-2`） |
| 桌面快捷方式 | `%USERPROFILE%\Desktop\AI 晨报.lnk` |
| 线上入口 | `site/config.js` 的 `siteUrl` —— **唯一事实源**；仓库其他位置一律 `__SITE_URL__` 占位，由 `tools/secret_scan.py` 守住 |
| 过程产物 | `ai-daily/_process/` —— 临时工作区（探针、试排），已进 `.gitignore`，**用完即清** |

**反例（真实踩过）**：定时流程曾把报纸写进自己的 `automation-*/` 工作目录，桌面与手机全读不到。路径只在这里定义一次。

## 2. 不变量（改代码不得破坏）

1. 每期 **16 版**（001–003 为 15 版旧版式），第 16 版固定是「本报提案」；每版末尾一条锐评、报尾名词速查（词数随当期，标题数字须与条数一致）。
2. 报头 / 报尾 / `issues.js` 的期号与日期一致；期号三位连续，`2026-11-04 = 001`。
3. 360px 视口下 `scrollWidth === clientWidth`；宽表包 `.table-wrap`，宽图包 `.fig-scroll`。
4. `[hidden]` 必须有 `display:none !important` 兜底，否则 `.btn` 的 display 会覆盖它。
5. 线上域名与访问码固定；重新发布不得改 `domainPrefix`。
6. 出报后**直接发布到线上，不再逐次征询**（2026-11-06 用户长期授权）；发布只覆盖既有链接，不得改域名与访问码。
7. 正文只用中文引号「」；命令行示例代码块不算正文。
8. 源目录与 `site/` 的内容必须一致，`site/` 只能由 `build_index.py` 单向写入。
9. 分享链接只由 `index.html` 的 `issueUrl()` 构造：`站点根 + sharecode + d=YYYY-MM-DD`，不得手拼或在别处另写一套；`siteUrl` 只在 `config.js` 定义一次。
10. 分享必须有两条可用路径：`navigator.share` 走系统面板，不可用或失败时复制链接；`file://` 打开时也要能给出线上链接。
11. 微信 / QQ 不做「一键直发」的假动作：先复制链接，再给粘贴指引；在微信内置浏览器里改给「右上角 ···」的菜单引导。
12. **提案默认不执行**：第 16 版每期四条（读者 / 编辑 / 创刊人 / AI 各一），只有用户明确说「采纳 P004-2」才动工；没说就是否决（沉默），不得自行实施、不得追问。
13. 提案编号 `P<期号>-<序号>`，台账在 `提案台账.md`；每期出报前先结算上期（到期转「否决（沉默）」），再登记本期。
14. 术语注解只写成 `<span class="term" tabindex="0">词<i class="tip">解释</i></span>`；气泡必须 `position:fixed` 并由脚本夹在视口内——用 `position:absolute` 会把 `scrollWidth` 撑破（实测 390 → 597）。
15. 每份成品（正刊与特刊）都要有同名 `manifest.json`，由 `build_index.py` 自动生成；`ok` 不为 true 视为这期没做完。
16. 特刊是**当天的第 2 版**，期号 `NNN-2`（如 `003-2`），接在当天正刊后面；和正刊一样进 `issues` 数组（`isSpecial: true`），不再单列 `#shelfSpecial` 区。文件名 `AI晨报-<date>-特刊.html`，线上路径 `site/special/<date>.html` + 同名 json。
17. 特刊必须三处可见：首屏横幅 `#spbar`（在读当天正刊时出现）、往期回顾同列排序（同一天 `003-2` 排在 `003` 上面）、深链 `?d=<date>&s=1`。缺一个都算「没同步到桌面端和手机端」。
18. 文中每个 `<span class="term">` 的词，报尾词表必须有词条且词形一致；报头写「报尾 N 词表」时 N 也要等于条数——由 A9 / A9b / A9c 在落盘前拦。
19. **报纸日期必须是出报当天**，不得提前把明天的期号发出去。预热稿放 `ai-daily/_drafts/`，不进根目录；`build_index.py` 会跳过并告警未来期，`selfcheck.py` 的「日期闸门」检查项会红（引用名称，不写编号）。
20. **版数必须全文一致**：每一处「共 N 版」（标题、报头、页脚、15 个页眉、目录）都等于实际 `section` 数。页眉是复制模板的批量产物，扩版最容易整批漏改——`A4d` 在拼版落盘前拦，`selfcheck.py` 的「全文版数一致」检查项独立扫源与站点副本复核。
21. **事实只有一份**：根目录成品是源，`site/` 副本必须逐字节一致（自检「索引与文件一致」项对账）；检查项名称与数量只由 `selfcheck.py --list` 给出，文档不抄第二遍；每加一条自检项，必须在 `mutation_test.py` 补一个带正向对照的变异（底板先全绿，再弄坏看它红）。
22. **内容声明只有一份**：文案只在 `site/config.js` 的 `disclaimer` 写一遍；各期报尾、模板、样张、`../README.md` 由 `tools/apply_disclaimer.py` 派生，`site/index.html` 分享面板运行时读同一常量。改文案 = 改 `config.js` 一处 → 跑 `apply_disclaimer.py` → `build_index.py` 同步 → 自检「内容声明一致」项对账 → 发布。不得在任何页面再手写一句。新期从 `_drafts/` 预热转正时，必须把该期 `00-tail.html` 登记进 `tools/disclaimer.py` 的 `SOURCE_HTML` 并跑一次 `apply_disclaimer.py`，否则新期会漏声明。
23. **主线先写死，再动笔**（P005-3）：开写前先落 `parts/<MMDD>/00-thread.json`，报头 `data-thread` 与它一致，报尾回显「本期主线：X」。`A11` 对账这三处，`A12` 做跑偏熔断——命中 `offTopicTerms` 的版面超过 `maxOffTopicPages`（默认 7 版）或头版命中，**直接拼不上版**，不是提醒。主线名同时充当标题里的版名，别在命令行另传 `--label`。
24. **外部数字必须带标记**（P005-2）：正文里凡引用外部数字，就地给一个 `<span class="src-tag">`，词表固定六档（厂商口径 / 本报未复现 / 预印本 / 公开报道 / 本报实测 / 本报自设），报尾 `.src-legend` 给图例。`A10` 拦词表外的自造说法，`A10b` 由事实卡驱动——某版被事实卡指到，那版就必须有对应档的标记，不靠编辑记性。
25. **事实卡与正文同源**（P005-4）：每条外部数字在 `00-facts.json` 占一行，`value` 必须与正文逐字一致（`A13` 在该版文本里找，不是全文找）。`reproduced: true` 只允许出现在 `strength: measured` 上。事实卡随成品内嵌为 `<script id="ai-daily-facts">`，`make_manifest.py` 解析后写进凭证——改了正文没改卡，凭证这一关会红。
26. **每版都要标信息来源，AI 生成版要少**（P006）：`00-blocks.json` 给 16 版各定一个 `origin`（`official` / `thirdparty` / `measured` / `ai`），拼版时渲染成版头小标「来源 · X」。这个标说的是**信息主要来自哪**，不是谁执笔——全部版面都由 AI 执笔（报尾有声明），把 AI 写的稿子标成「官方」就是假标，所以 `A14c` 要求非 AI 版至少有一处论据标记或一条事实卡；`A14b` 反过来禁止 AI 版挂外部标记。AI 生成版不得超过 `maxAiPages`（默认 4 版），报尾图例里那句「本期 AI 生成 N 版」也要对得上（`A15b`）。
27. **引用谁要写清归属**（P006）：正文用了谁的公告、模型卡、报道、预印本，就在 `00-sources.json` 记一条（`outlet` 归属方 / `item` 被引内容 / `kind` 四档 / `usage` 使用方式），报尾「信息源与归属」由它渲染成一条一行，`A16` 核对字段与渲染条数。只做事实性引用、不转载全文；许可与商标边界写在根目录 `NOTICE.md`。
28. **文档数字由脚本维护**：`../项目框架与规则.md` 的各级条数、总数、`A1–Ax`、脚本数量，`../产物清单.md` 的项数与分组数，都交给 `tools/doc_sync.py --fix` 自动对齐；`§4.7 断言索引` 与 `§八 变更记录` 是生成区，手改会被下一次运行覆盖。`selfcheck.py` 第 14 项拦「改完还对不上」：规则引用了不存在的断言或脚本、清单列了已删的路径、条数与实际不符。代码里新增断言时，先去 §四 补一条规则再跑 `--fix`；只加断言不补规则不会变红，但第 14 项会一直提示「没有规则引用」。
29. **CI 文件必须真的能被解析**：`.github/workflows/ci.yml` 里混进任何 markdown（开头 `> ` 引用符、``` 围栏）都会让 YAML 报 ScannerError，Actions 静默不加载，而 README 照旧宣传矩阵——一个从没跑过的检查被判成绿的，比没有 CI 更糟。`selfcheck.py` 第 15 项用纯标准库查结构（首行是键、无引用符/围栏、有 jobs/runs-on/steps），装了 pyyaml 再真解析一次，并核对 README 宣传的平台与 Python 版本确实在文件里、`.github/dependabot.yml` 还在盯 `github-actions`；`mutation_test.py` 有对应反例。
30. **明文只能有一处**：入口地址只允许出现在 `site/config.js` 的 `siteUrl`；其余位置（文档 / 脚本 / 示例 / 模板 / APK 源码）一律 `__SITE_URL__` 占位——`selfcheck.py` 的线上检查、`build_apk.py` 的打包注入都从它派生。`tools/secret_scan.py` 默认扫已入库文件，白名单只有config.js，多写一处就红。签名口令走 `AI_DAILY_APK_PASS` 或 `ai-daily/.local/apk.json`，不进代码。
31. **公开仓库只能另造，不能清洗**：本仓库的历史含明文且不可改写，永不直接 push；公开仓库由 `tools/export_public.py` 白名单复制 + 占位注入 + 严格验收 + 单次初始提交生成，CI 的 `security` 作业每次 push 复查；导出后到 push 前跑一次 `tools/export_public.py --verify <导出目录>`（严格扫描 / 白名单 / 无二进制 / 行尾钉住 / 占位 / 工作区干净 / 单提交 / 身份不是占位）。APK 与二维码内嵌入口地址，一律 gitignore，只在本机生成。威胁模型与 GitHub 侧开关写在根目录 `SECURITY.md`。
32. **已入库 = 将公开**：导出是白名单，新增目录默认不进，所以「本机全绿、公开仓库静默少文件」是默认结局而不是意外。`selfcheck.py` 第 16 项逐个核对 `git ls-files` 与导出集，缺一个就红。真要放私有文件就别入库，别在导出脚本里开豁免。
33. **离线包随出报自动更新**：`build_index.py` 末尾调 `build_apk.py --auto`，不靠人记得手跑；版本号由打包日期派生（`YYMMDD*100 + 当日序号`）——写死常量会让新包被系统当成同一版本，覆盖安装静默失败。内容指纹未变就跳过，缺 Android 工具链返回 2 不阻塞出报。`selfcheck.py` 第 17 项比对「包内当期正文 == 站点当期正文」并检查包内索引没有幽灵条目。
34. **更新清单与包同源**：`site/version.json` 由 `build_apk.py` 在打包成功后写，字段 `code/name/sha256/bytes` 全部来自刚刚签完名的那个包——不许手工维护，也不许另写一份。App 启动后拉它比 `versionCode`（自己的版本号从 PackageManager 读，不注入常量），有新版才弹窗；请求必须带 `sharecode`（线上无码即 403），失败一律静默。同日重打时 `versionName` 追加 `.<当日序号>`，否则弹窗会显示与当前相同的版本号。`selfcheck.py` 第 18 项对账清单与包、与打包记录，并确认 `MainActivity.java` 里的检查逻辑还在；第 13 项线上检查也会拉一次清单（没发布 = 提示永远不出现）。
35. **模板必须与当期同源，徽章地址走注入**：`parts/_template/00-style-extra.html` 是三行摘要、术语气泡、手机报头压缩与窄屏目录按钮的唯一样式追加源，必须与最近一期保持一致——它曾落后于当期，照模板复制会**静默丢样式**，而这类丢失自检看不出来，只有肉眼能发现。改样式永远改这份 + 当期那份，别只改当期。README 顶部的 CI 徽章地址用 `__REPO_SLUG__` 占位，导出时由 `export_public.py --repo owner/name` 注入；`--verify` 有「仓库地址已注入」一项，残留占位意味着徽章是坏图。

36. **公开面是唯一主动出访问码的地方，所以它必须有硬断言**：`tools/build_public.py` 把各期事实卡生成到仓库根 `docs/`（GitHub Pages 的发布目录），一条断言一个 URL，带证据强度、所属版面与 Article 结构化数据。它只读 `issues.js` 与 `parts/<MMDD>/00-{facts,sources,blocks}.json`，**绝不读 `siteUrl`**——页面里出现 `sharecode` 就是不可撤销的泄露（Pages 有 CDN 缓存、可能已被抓取），所以 `selfcheck.py` 第 19 项把「无访问码」写成硬断言而不是靠人记。`build_index.py` 末尾自动重生成；`mutation_test.py` 有两条反例（混进访问码、卡片被删）。公开面只放导读与卡片，全文仍在受访问码保护的私有站点——**不要把它当成"另一个报纸站"来加功能**。信源表可以在公开面给外链：`00-sources.json` 的 `url` 只允许 `http(s)`，**没有稳定单一出处就留空**——概括性条目（「本周报道」「每日通讯摘编」）宁可不给，也不拿频道首页或猜出来的 slug 凑数；期页渲染 `#sources` 锚点，第 19 项核对「外链数 == 数据里有 url 的条数」，缺一条即 FAIL。

## 3. 常用命令

```
python tools/assemble_issue.py --parts parts/<MMDD> --date YYYY-MM-DD --issue 00N
python tools/assemble_issue.py --parts parts/<MMDD>sp --date YYYY-MM-DD --issue 00N-2 \
        --slug=-特刊 --label 傍晚特刊 --no-status --no-site --force   # 特刊：当天第 2 版
python tools/assemble_issue.py ... --dry-run      # 只校验不落盘（不写状态）
python tools/assemble_issue.py ... --force        # 目标已存在且内容不同才需要
python tools/assemble_issue.py ... --no-status    # 试拼：不写状态机
python tools/assemble_issue.py ... --no-site      # 特刊用：只写根目录，special/ 交给 build_index
python tools/build_index.py                       # 扫描 → 同步 site/ 与 special/ → 重写 issues.js → 生成每期 json
python tools/apply_disclaimer.py                  # 改了 config.js 的 disclaimer 后：派生四期报尾/模板/样张/README（幂等）
python tools/apply_disclaimer.py --check          # 只报告漂移不写盘；有漂移退出码 1
python tools/selfcheck.py [--pre|--online]        # 交付前自检；项数以 --list 为准，有 FAIL 退出码 1
python tools/selfcheck.py --list                  # 自检项名称 + 排障提示（文档的唯一来源，别再抄表格）
python tools/mutation_test.py                    # 反向验证：每个检查项一个反例 + 正向对照，确认真的会红
python tools/status.py --status                   # 今天这期走到哪一步
python tools/status.py --gate                     # 发布前闸门：0 允许 / 1 拒绝
python tools/status.py --mark deploy=OK verify=OK # 发布后记录（只写已经验证过的）
python tools/status.py --ticket                   # 失败工单（原样回传修）
python tools/boot_check.py --status               # ok / missing / drift + 状态机摘要
python tools/build_apk.py --auto                  # 重打安卓包（出报链路已自动调；手跑加 --auto 才判重）
python tools/make_sample.py                       # 重生成第 16 版样张（改提案版样式后看它）
python tools/make_qr.py <url> <out> <标题> <行1> <行2>
python tools/make_manifest.py --all               # 重刷所有成品凭证（一般不用手跑，build_index 会做）
node tools/probe.js <url> <out.png> [measure|share|flow|channels|paper|wide|gloss|special]   # CDP 探针（自己起浏览器；measure 就是手机视口测量）
python tools/doc_sync.py [--fix]                  # 规则文档/产物清单对账（--fix 自动对齐数字）
python tools/doctor.py [--json]                   # 环境体检：版本 / 语法 / 可选依赖 / 浏览器 / 行尾
```

`probe.js` 现在自己找浏览器、自己起无头 CDP（端口 9333）、跑完自己收，不再需要手敲 `msedge --headless`；找不到浏览器时用 `CHROME_PATH` 指定。它用 `Emulation.setDeviceMetricsOverride` 模拟手机，比 `--screenshot` 可靠。
`SCROLL=<选择器>` 环境变量：截图前把该元素滚进视口（报尾、图例都在长页末尾，不滚只能截到首屏）。
`assemble_issue.py` 落盘前跑 A1–A16：004 期起正刊缺 `00-thread.json` / `00-facts.json` / `00-blocks.json` / `00-sources.json` 直接拒拼；标记用了词表外的说法、版级来源标错、AI 生成版超上限也拒拼。
报纸页用 `paper`（首屏摘要位置 + 六个气泡边界 + scrollWidth）、`wide`（列出超宽元素）、`gloss`（速查栅格宽度）；入口页用 `measure|share|flow|channels`，`special` 专查特刊入口（横幅高度、书架卡、深链 `?s=1`）。
试拼/演练时把状态写到临时文件：`AI_DAILY_STATUS=/tmp/s.json`（或直接用 `--no-status`），别污染当期 `status.json`。

## 4. 每期交付流程（顺序不可换）

```
结算上期提案（到期转否决，登记本期四条，更新台账）
     → 写 parts/<MMDD>/00-thread.json（本期主线）、00-facts.json（事实卡骨架）、
       00-blocks.json（16 版来源，AI 生成 ≤ 4 版）、00-sources.json（信源归属）
     → 取材 → 写 parts/<MMDD>/p01…p16（外部数字就地加 src-tag）
     → assemble_issue（A1–A16 断言，原子写；自动记 parts/assemble）
     → build_index（同步 site/ 与 special/ + 重建 issues.js + 生成每期 json；自动记 index）
     → doc_sync --fix（会话开始 hook 已自动跑过一次；这里再跑一遍，顺手拿提案）
     → selfcheck --pre（有 FAIL 就停在此处；项数以 `selfcheck.py --list` 为准，文档不写死）
     → mutation_test（新增或改过检查项后必跑：证明检查器真的会红）
     → status.py --gate（BLOCK 就不许发布）
     → 直接发布 site/（长期授权，不再征询）
     → selfcheck --online（线上可访问也要过）
     → status.py --mark deploy=OK verify=OK
```

任何一步失败：`status.py --ticket` 出工单，保留现场、把错误原文回传给 agent 重试；**不得跳过校验直接发布**，也不得把半截产物当成功。

**整期重制**：成片若被判定偏离本报主线（整版写行情、宏观，不写 AI 与智能体），按整期重制处理——期号与日期不变，`assemble_issue.py --force` 覆盖，报尾「更正与说明」写明原委；本期四条提案随重制版重写，编号不变，仍按「沉默即否决」走。重制不等于追加一期，不动 `issues` 期序。2026-11-07 首次执行（原 004 期为市场复盘版，整期替换为「从会答到会办」）。

## 5. 验收

**先跑命令，再看人眼。** 每次对外说「完成 / 已发布」之前必须执行：

```
python tools/selfcheck.py            # 严格：五阶段全绿
python tools/selfcheck.py --pre      # 发布前：只看 parts/assemble/index
python tools/selfcheck.py --online   # 加验线上可访问
python tools/mutation_test.py        # 反向验证：新增/改过检查项后必跑
```

全 PASS 才能说完成；**有 FAIL 就原样贴出来**，不许只报通过项、不许用「应该没问题」代替。

**检查项的名称、数量、排障提示只有一个来源：`python tools/selfcheck.py --list`。**
本文档不再抄一份表格（曾出现脚本 12 项、文档只列 10 项的漂移）；新增检查项时改 `ITEMS` 一处即可，同时在 `mutation_test.py` 补一个变异，证明新项会红。

命令管不到的部分仍要人眼确认：

- 期号与日期一致、版数齐全（新期 16 版；001–003 保持 15 版原样）。
- 两张图无裁切；360/390px 视口 `scrollWidth === clientWidth`。
- 第 16 版四条齐（读者/编辑/创刊人/AI 各一），编号与当期期号一致，台账已更新。
- 改过入口页后：顶栏按钮在 390px 下不出屏、分享面板能开能关、三个渠道点下去都有反馈、链接带当期 `d=`（特刊还带 `s=1`）。
- 特刊：`site/special/<date>.html` 与 `.json` 都在，`site/` 根下不留同名副本；往期回顾里它和正刊排在一起，编号 `003-2`，不是另外一区。

## 6. 触发与发布（2026-11-06 起变更）

- **没有任何定时自动化**。原来的 08:00 出报、10:00 补发已删除。
- 触发是 `SessionStart` hook：配置在 `~/.workbuddy/settings.json`，入口 `tools/boot_check.cmd`（ASCII-only 包装，勿加中文注释）。
- 三态：`ok` 静默 / `missing` 注入**自动补报** / `drift` 注入**自动收尾**（site 缺失、内容不一致、索引未收录、status 显示 deploy/verify 未完成）。
- **自动任务（23:40 用户明确推翻 23:10 的 A+C）**：`missing` / `drift` 注入的是完整自动任务，不是提醒。指令要求立即执行、不等待用户消息、不询问确认，按 §4 顺序走完：`selfcheck.py --pre` → `status.py --gate` → 直接发布 `site/` → `selfcheck.py --online` → `status.py --mark deploy=OK verify=OK`。任一 FAIL / BLOCK 立即停止：不得发布、不得说完成，原样贴出失败项并 `status.py --ticket` 出工单。
- **机制边界（不许说成已经全自动）**：官方文档把 SessionStart 的 `additionalContext` 定义为「注入上下文」，用途是初始化环境 / 注入项目上下文 / 加载规范，**不负责自动发起一轮模型推理**；站点发布工具也只在会话内可用，hook 脚本调不到。因此「打开客户端、一条消息都不发就出报」在现有机制下没有保证。会话里只要有一轮推理（用户发任意一条消息，或客户端在启动时处理注入上下文），整条链路就会自动跑完，无需描述需求或确认。
- **文案不可漂移**：`boot_check.py` 的 `REQUIRED_CONTEXT` 锁住不可删的步骤与红线，`python tools/boot_check.py --check` 体检两种状态的注入文案；注入前也会校验并写日志。改文案必须同步改这个常量。
- **cwd 兜底（23:15 修）**：SessionStart 事件里的 `cwd` 常为空（19:39 之后全是空），旧判定让 hook 连提醒都没注入。`boot_check.py` 现在先用 `transcript_path` / `workspace` 等路径正向命中，明确指向别处才静默；完全拿不到路径时按 hook 安装位置（脚本就在本项目 `tools/` 下）判定，日志记 `guard=installed`。
- **发布是自动环节**：通过 `status.py --gate` 后直接发布，不再询问「要不要同步线上」；发布后 `selfcheck.py --online` 验证并记 `deploy/verify`。这是 2026-11-06 用户给出的长期授权，不是单轮同意。

## 7. 明确禁止

- 把报纸存到 `ai-daily/` 之外的任何目录。
- 手工编辑 `issues.js`（下次 `build_index.py` 会覆盖）。
- 在没有确认当日报纸是否已存在的情况下直接写盘（11-06 曾两版互相覆盖）。
- 用「文件存在」判断出报成功。
- 没有备份就覆盖入口页、快捷方式或 `site/` 下的既有文件。
- 把第 16 版的提案当成 TODO 自动执行——**沉默就是否决**，只有用户点名「采纳 Pxxx」才动工。
- 自检有 FAIL 时说「已完成」「已发布」；也不许只报通过项、隐去失败项。

## 8. 本机环境事实（别让 agent 重复踩）

- PowerShell 的 `WScript.Shell` COM 被安全策略拦截 → 用 `make_shortcut.py` 生成 `.lnk` 二进制。
- Edge headless `--window-size=390` 有「Windows 最小窗口约 500px」假象 → 测手机排版必须用 CDP `Emulation.setDeviceMetricsOverride`。
- `msedge --headless --screenshot` 单命令跑的是**桌面模式**（窗口 390 也一样），会把顶栏误报成溢出 → 布局结论只看 CDP mobile 模式（`tools/probe.js`）。
- 线上静态服务只回 `Last-Modified`、无 `Cache-Control` → 必须靠 `sw.js` 的 `no-store` + 索引时间戳兜住，改前端后必须重新发布才生效。
- 线上子资源靠 `__wb_rsc` cookie 放行，第一次带 `sharecode` 访问后约一个月有效；既无 cookie 又无码会 403。
- 默认 PyPI 源装不上 `qrcode` → 用阿里云镜像。
- **主链路零第三方依赖**（2026-11-07 实测）：干净 venv（未装任何包）跑 `selfcheck.py --pre` 12/12；全新 clone 跑 11 PASS / 1 SKIP（SKIP 是本地 `status.json`，新克隆仓没有属预期）。所以「换台机器跑不起来」的真实原因是**行尾**，不是缺包。
- **Windows 默认 `core.autocrlf=true`，clone 会把 CRLF/LF 混排文件的裸 LF 补成 CRLF**：实测一期成品 120952 → 122418 字节，自检第 2、4 项直接红，且看起来像内容漂移。仓库根已加 `.gitattributes`（`* -text`）钉死字节；改动它之前先想清楚 sha256 对账。
- `.cmd` 里出现任何非 ASCII 字节都会让 cmd.exe 解析断裂（按 OEM 代码页读）。
- `boot_check.cmd` 不再优先取某个固定版本的 Python：先试 PATH 上的 `python` 是否 ≥ 3.10，再扫 `~/.workbuddy/binaries/python/versions/*` 逐个验版本。
- `aapt` 读不了中文文件名（报 `Illegal byte sequence`）→ 先复制成 ASCII 名再 `dump badging`。
- 工作区可能被挂成两条路径（`%USERPROFILE%\WorkBuddy\<任务目录>` 是链接，实体的 git 仓库在 D 盘），两者是同一份；`Path.resolve()` 后一致即正常。
