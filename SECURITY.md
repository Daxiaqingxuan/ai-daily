# 安全策略

## 这个仓库在保护什么

一句话：**一个私有入口的访问码**，以及「这台机器上这个项目怎么跑」。

不是用户数据——这个项目没有账号系统、没有服务端、不收集访问者信息，它就是一套静态站点
构建脚本加一份 AI 生成的报纸。所以这里的「安全」不是防入侵，而是**防不可撤销的泄露**：
Git 提交一旦推上公开远端，就等于永久公开，删文件、改配置、`--amend` 都救不回来。

## 不公开的东西

| 类别 | 具体 | 为什么 | 公开仓库怎么替代 |
| --- | --- | --- | --- |
| 入口地址 | `ai-daily/site/config.js` 的 `siteUrl`（含 `sharecode`） | 它就是那份报纸的门禁 | 导出时替换成 `__SITE_URL__` 占位 |
| 安卓包 | `ai-daily/site/ai-daily.apk`、`ai-daily/AI晨报.apk` | `classes.dex` 与 `assets/site/config.js` 各内嵌一份入口地址，二进制改不了 | 只发 `ai-daily/apk/` 源码，读者自己打包 |
| 二维码 | `AI晨报-手机入口.png`、`AI晨报-安卓版下载.png` | 图里画的就是入口地址 | `python tools/make_qr.py <你的链接>` |
| 工作区状态 | `.workbuddy/`、`.wbapp_*.genie` | 记忆、应用清单、任务态——是「本机怎么用」而不是「项目是什么」 | 不在仓库里 |
| 运行态 | `status.json`、`learn-agent/demo/stages/`、`*.log`、`parts/*/dist/` | 脚本可再生的中间件，入库只会漂移 | 由脚本现生成 |
| 本机私有值 | `ai-daily/.local/`（APK 签名口令） | 凭据 | 见下节 |

## 本地怎么跑：需要自己填的两个值

1. **入口地址** —— `ai-daily/site/config.js` 的 `siteUrl`。它同时是 `selfcheck.py`
   线上检查、APK 打包注入的事实源，改这一处就够。
2. **APK 签名口令** —— 环境变量 `AI_DAILY_APK_PASS`，或 `ai-daily/.local/apk.json`
   的 `keystorePass`。缺了 `build_apk.py` 会直接退出，不会拿默认口令凑合。

两个都在 `.gitignore` 里。写完跑一次 `python ai-daily/tools/secret_scan.py`，
它会告诉你有没有多写一处。

## 四道防线

| 层 | 谁 | 管什么 |
| --- | --- | --- |
| 忽略 | `.gitignore` | `.workbuddy/`、`*.apk`、二维码、`stages/`、`.local/`、日志、运行态 |
| 扫描 | `ai-daily/tools/secret_scan.py` | 默认查已入库文件；`--history` 查全部提交；`--dir` 查任意目录；命中内容打码后输出 |
| 导出 | `ai-daily/tools/export_public.py` | 白名单复制 + 占位注入 + 严格验收 + 单提交演练 |
| CI | `.github/workflows/ci.yml` | `security` 作业在每次 push / PR 上跑扫描，红了就是红了 |

导出之后、push 之前还有一条复检：

```
python ai-daily/tools/export_public.py --verify <导出目录>
```

它查的是「这棵树现在能不能推」：工作区是否干净、提交数是否为 1、身份是不是占位、
`.gitattributes` 有没有保住行尾、入口地址是否已是占位、有没有混进二进制。CI 里也跑同一条，
所以「手工改过导出树再 push」这条路会红。

扫描器的唯一白名单是 `ai-daily/site/config.js`——它是入口地址的唯一事实源。
导出验收用 `--strict` 关掉白名单，所以「注入失败」不会被同一条规则放过去。

## 这个仓库是怎么来的

上游开发仓库的历史里有明文入口地址（2026-11-07 实测：7 次提交命中）。**Git 历史不可改写**，
所以这里的做法不是「清洗历史」，而是**另造一个仓库**：

```
python ai-daily/tools/export_public.py --out <空目录> --git-init \
    --name "<你的名字>" --email "<你的 GitHub noreply>"
```

它按白名单复制 150 余个文件、把入口地址换成占位符、跑严格扫描，再做一次单提交演练
（`rev-list --count` 必须是 1，历史扫描必须 0 命中）。演练用的 `.git` 默认会被删掉，
免得带着占位身份推上去。

同理：**如果你 fork 了这份代码又把自己的入口写进任何文件，请不要提交**。
入口地址一旦进了公开历史，就再也删不掉了。

## 仓库作者身份

提交请用 GitHub 提供的 noreply 地址（`<id>+<用户名>@users.noreply.github.com`），
不要用真实邮箱，也不要用 `@local` 这种看起来像内部账号的写法——它会被永久写进每一个提交。

## GitHub 侧要打开的开关

推上去之后，下面几项在仓库 Settings 里逐项确认（它们不在代码里，漏了代码也管不到）：

- **Settings → Code security**：Secret scanning、Push protection 打开。
- **Dependabot**：仓库里已有 `.github/dependabot.yml`（每周一 09:00 查 `github-actions`），
  还需要在 Settings 里把 alerts 与 security updates 打开——配置文件只负责「查什么」，不负责「是否启用」。
- **Actions → General → Workflow permissions**：选 *Read repository contents*，不要给写权限。
- **Branches → main 保护**：Require a pull request、禁止 force push、禁止删除。
- 任何 `secrets.*` 都不许 `echo` 进日志；CI 里也没有需要它们的步骤。

## 报告问题

用 GitHub 的 **Private vulnerability reporting**（Security → Advisories）提交，或开 issue 时
只写「有安全问题，请给私下渠道」，不要贴细节。为了验证问题去扫别人的站点不在授权范围内。
