# 更新日志

按日期倒序。格式接近 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号只在公开仓库打 tag 时使用——`v1.0.0` 即首次公开的那一份。

期号与日期不是版本号：报纸每天一期，工具链随时改。看「今天我该知道什么」翻期号，看「这套工具变了什么」翻这里。

## [v1.1.0] — 2026-11-08

**加了一个免访问码的公开面**：全文仍在受访问码保护的私有站点，但导读、事实卡与归档索引现在任何人都能打开——每张事实卡一个独立网址，带证据强度与所属版面。

### 新增

- **公开导读面**（`docs/`，GitHub Pages 发布）：首页 + 归档索引 + 每期导读 + 30 张事实卡页（005 期 18 张、004 期 12 张）。一条断言一个 URL，带 `value` / `strength` / `asOf` / 版面归属 / 信源条数与 `Article` 结构化数据。
- **`tools/build_public.py`**：只读 `issues.js` 与 `parts/<MMDD>/00-{facts,sources,blocks}.json`，**不读 `siteUrl`**；`--check` 抹平生成时间戳后逐页比对，可做幂等断言。
- **自检第 19 项**：公开面不得出现 `sharecode`（不可撤销泄露）、必须与生成结果一致、`sitemap` 覆盖卡片数。
- **反向验证 +4 条**（55 → 59）：公开面混进访问码、卡片页被删，各带正向对照。
- **`CODE_OF_CONDUCT.md`**：Contributor Covenant 2.1 中文改编，举报走 Issue 或 `SECURITY.md`。
- **`.github/workflows/codeql.yml`**：Python + JavaScript 静态分析，`build-mode: none`（本项目不编译），每周一增量扫描。

### 变更

- **`build_index.py`** 收尾多一步：索引落盘后自动重生成公开面，和重打 APK 同一个道理——漏了线上完全正常，只有访客看到旧卡片。
- **自检第 15 项**扩到「所有 workflow 都能解析」：一个坏文件不会报错，它只是从没出现在 Actions 页面上。
- **导出白名单**新增 `CODE_OF_CONDUCT.md`、`codeql.yml`、`public_site.json`——白名单默认不进，不显式加就是公开仓库静默少文件。
- **分支保护**：`main` 禁 force push、禁删除、管理员同样受限；更新改走「备份 `.git` → 重导出 → 普通提交」。

### 边界

- 公开面只放导读与卡片，**不放 16 版正文**。想看全文仍需访问码——这是故意的，不是没做完。

## [v1.0.0] — 2026-11-08

首次公开。仓库里同时是**一套每天出刊的报纸**（001–005 期，005 期起 16 版）和**一条带闸门的出刊流水线**。

### 新增

- **报纸**：005 期（2026-11-08）主线「谁验过，才算数」——18 条事实卡、23 条信源、42 处论据标记；004 期（2026-11-07）为首份 16 版正刊；003-2 为晚间特刊。
- **断言**：拼版 A1–A16（版数、期号、页码、标签配平、术语对账、论据标记、主线熔断、事实卡、版级来源、信源归属），落盘前跑，缺一条就不许发布。
- **自检 18 项**（`selfcheck.py --pre` / `--online`）：索引与文件、逐字节副本、期序与日期闸门、状态机、全文版数、内容声明单一事实源、线上 sha256、导出覆盖、APK 快照与更新清单。
- **反向验证 55 条**（`mutation_test.py`）：每条断言配一个反例，且必带正向对照；SKIP 计为未测，不计入通过。
- **安全四道闸**：`secret_scan.py`（tracked / history / dir 三口径）→ `export_public.py`（白名单导出 + 占位注入 + 严格扫描）→ `--verify`（推送前 9 项复检）→ CI `security` 作业。
- **安卓壳**：离线快照随出刊自动重打（`build_index.py` 收尾调 `build_apk.py --auto`），版本号由打包日期派生（`YYMMDD*100 + 当日序号`），启动后自查 `version.json` 提示新版本。
- **文档**：`README.md`（访客视角 + 两张实拍图）、`CONTRIBUTING.md`、`SECURITY.md`、`NOTICE.md`、`.github/` 的 issue 表单与 PR 模板、`docs/screenshots/`。

### 变更

- **入口地址收敛到一处**：只在 `site/config.js` 的 `siteUrl` 写明文，其余落点（README 截图外的一切文本、APK 源码、二维码说明）都是占位或派生。
- **规则文档自动同步**：`doc_sync.py --fix` 从代码推导各文档里的条数、断言范围、脚本数、产物清单分类小计；语义变更只出提案，不自动改。
- **CI**：Ubuntu / Windows × Python 3.10 / 3.13 四矩阵 + `security` 作业，`permissions: contents: read`。
- **README 徽章**：CI 徽章地址在源里留占位符，导出时由 `export_public.py --repo owner/name` 注入，推送前复检会拦残留。

### 修复

- **Windows CI 的中文输出**：GitHub 的 Windows runner 是 en-US locale，控制台编码 cp1252，`doctor.py` 首行的中文标题直接抛 `UnicodeEncodeError`，首次推送时两个 Windows 组合全红而 Ubuntu 全绿——不是逻辑问题，是控制台打不出中文。已在 workflow 顶层固定 `PYTHONIOENCODING: utf-8`，现在五个作业全绿。
- **模板样式回退**：`parts/_template/00-style-extra.html` 曾落后于当期，缺三行摘要、术语气泡、手机报头压缩与窄屏目录按钮规则——照模板复制会静默丢样式。已把模板对齐到当期完整版。
- **手机目录按钮压字**：原为 78×36 常驻药丸，`position:fixed` 在右下角盖住三行摘要末行；改为 42×42 圆点，下滚 200px 收起、上滚还原、开面板强制可见。
- **离线包丢特刊**：快照只复制站点顶层，`special/` 从未进包而索引里有条目，离线点开 404；改为递归打包并断言「索引无幽灵条目」。
- **产物清单分类小计**：`doc_sync` 原先只改总数不改分项，新增条目后出现「总数对、分项错」；现由同一函数按类别列重算，fix 与 check 共用。
- **CI 曾整体失效**：`.github/workflows/ci.yml` 前三行残留 Markdown 引用符导致 YAML 解析失败、Actions 从不加载；已修并加第 15 项看住。

### 已知边界

- 线上入口受访问码保护，不在仓库里公开；克隆下来读本地站点即可。
- 手机端装过旧包的用户不会自动升级，只会收到「有新版本」提示——检查逻辑必须先随包进去一次。
- 报纸内容由 AI 生成，用于产品演示，不构成事实报道；引用只做事实性转述。

[v1.0.0]: https://github.com/Daxiaqingxuan/ai-daily/releases/tag/v1.0.0
