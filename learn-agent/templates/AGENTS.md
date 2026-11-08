# AI 晨报 · 项目契约（给 agent 读的唯一入口）

> **本文件是唯一真源。** 版式规范、自动化提示词、工作日志都不得与它冲突。
> 要改约定，先改这里，再同步别处。新会话的 agent 第一件事就是读它。

## 1. 路径（最容易出错，写在最前）

| 用途 | 位置 |
| --- | --- |
| 报纸源文件 | `ai-daily/AI晨报-YYYY-MM-DD.html` —— **唯一保存位置** |
| 发布目录 | `ai-daily/site/` —— 桌面端 `file://` 与线上站点都从这里读 |
| 期刊索引 | `site/issues.js` —— 由 `tools/build_index.py` 生成，**禁止手工编辑** |
| 入口页 | `site/index.html` |
| 桌面快捷方式 | `%USERPROFILE%\Desktop\AI 晨报.lnk` |
| 线上入口 | `site/config.js` 的 `siteUrl` —— 唯一事实源，其余位置写 `__SITE_URL__` 占位 |
| 自检脚本 | `learn-agent/examples/validate.py` |

**反例（真实踩过）**：主自动化曾把报纸存到自己 `automation-*/` 工作目录，桌面与手机全读不到。路径只在这里写一次，别处一律引用。

## 2. 不变量（改代码时不得破坏）

1. 每期 15 版、每版末尾一条锐评（共 15）、5 个「说人话」框、报尾 13 词名词速查。
2. 报头 / 报尾 / `issues.js` 的期号与日期一致；期号按天递增（2026-11-04 = 001）。
3. 360px 视口下 `scrollWidth === clientWidth`；宽表包 `.table-wrap`，宽图包 `.fig-scroll`。
4. `[hidden]` 必须有 `display:none !important` 兜底，否则 `.btn` 的 display 会覆盖它。
5. 线上域名与访问码固定；重新发布不得改 `domainPrefix`。
6. 发布操作必须先在本轮对话获得明确同意（`userAskedToPublish=true`）。
7. 正文只用中文引号「」；命令行示例代码块不算正文。

## 3. 常用命令

```
python tools/build_index.py                  # 扫描报纸 → 同步 site/ → 重写 issues.js
python learn-agent/examples/validate.py .    # 交付自检，退出码 0 才允许发布
python learn-agent/examples/repair_loop.py --gate .   # 发布闸门（只判定不改文件）
python learn-agent/examples/verify_all.py --online --json  # 一键回归，SKIP 项需人工补
python tools/build_apk.py                    # 重打安卓包（联网看新报时不必重打）
python tools/make_qr.py <url> <out> <标题> <行1> <行2>
node tools/probe.js <url> <shot.png> measure       # 真实手机视口测量 + 截图
```

## 4. 交付流程（顺序不可换）

```
生成报纸 → 写临时文件 → 校验 → 原子改名落盘
        → build_index.py → validate.py（必须退出码 0）
        → 重新发布 site/ → 写 status.json
```

任何一步失败：保留现场、把错误原文回传给 agent 重试；**不得跳过校验直接发布**，也不得把半截产物当成成功。

## 5. 验收

`validate.py` 全绿（当前 32 / 32 条）是发布的必要条件，不是充分条件。
FAIL 时把「未通过」清单原样回传给 agent，让它自己改，改完再跑一遍。

## 6. 本机环境事实（别让 agent 重复踩）

- PowerShell 的 `WScript.Shell` COM 被安全策略拦截 → 用 `make_shortcut.py` 直接生成 `.lnk` 二进制。
- Edge headless `--window-size=390` 有「Windows 最小窗口约 500px」假象 → 测手机排版必须用 CDP `Emulation.setDeviceMetricsOverride`。
- 线上子资源靠 `__wb_rsc` cookie 放行，sharecode 首次访问后约一个月有效；既无 cookie 又无码会 403。
- 默认 PyPI 源装不上 `qrcode` → 用阿里云镜像。
- 发布同意**不跨轮**：改动已上线的站点后要重新发布，当轮先问用户。

## 7. 明确禁止

- 把报纸存到自动化自身的工作目录。
- 手工编辑 `issues.js`（下次 `build_index.py` 会覆盖）。
- 没有备份就覆盖入口页、快捷方式或自动化提示词。
- 用「文件存在」判断出报成功。
