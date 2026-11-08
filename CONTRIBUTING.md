# 参与贡献

这是一个人的项目，但不是一个只能一个人改的项目。下面写清哪些事欢迎、哪些事会被退回，以及提交前必须跑什么。

## 最快的三种参与方式

**1. 报一个问题。** 用 [Bug 报告](../../issues/new?template=bug_report.yml)，写清系统、Python 版本、你跑的那条命令、完整报错。如果是渲染问题，附一张截图比描述十句管用。

**2. 指出内容错误。** 报纸正文里的数字、日期、归属写错了，直接开 [内容勘误](../../issues/new?template=content_correction.yml)，注明是哪一期、哪一版、哪句话。这类反馈优先级高于功能建议——事实错了，别的都是次要的。

**3. 改代码。** 先开 issue 说清要改什么，再提 PR。没人喜欢在 PR 里第一次看到「我想重构整个渲染层」。

## 本地跑起来

主链路零第三方依赖，Python 3.10+ 即可，不用先 `pip install`：

```bash
git clone <this-repo> && cd <this-repo>
python ai-daily/tools/doctor.py          # 环境体检
python ai-daily/tools/selfcheck.py --pre # 发布前自检
```

想直接看报纸：用浏览器打开 `ai-daily/site/index.html`。

图标、二维码、APK 三个辅助脚本需要 `Pillow` / `qrcode`（`ai-daily/requirements.txt`）；Android 打包另需 JDK + build-tools。缺这些工具时主链路照跑，相关检查会跳过，不会假绿。

## 提交前必须过的四道门

```bash
python ai-daily/tools/doctor.py            # 体检
python ai-daily/tools/selfcheck.py --pre   # 18 项自检，必须 0 FAIL
python ai-daily/tools/mutation_test.py     # 反向验证：每条断言一个反例
python ai-daily/tools/secret_scan.py       # 已入库文件里不得有凭据
```

四条全绿再提 PR。CI 会在 Ubuntu / Windows × Python 3.10 / 3.13 上重跑一遍；只在本机绿、CI 红，说明有环境假设没写进代码。

**看到 FAIL 不要说「基本完成」。** 这个项目的自检结果只有两种：全绿，或者没做完。

## 三条硬约束

**一、主链路不引入第三方依赖。** `ai-daily/tools/` 下跑出报、拼版、自检的那批脚本，只许用标准库。加一个 `requests` 很舒服，代价是换台机器第一句就 `ModuleNotFoundError`，而这个项目的卖点之一正是「克隆下来就能跑」。

**二、行尾是内容的一部分。** 仓库根 `.gitattributes` 写着 `* -text`，检出字节必须与仓库字节一致——自检按 sha256 逐字节对账，行尾被 Git 改写会红一片。写文件用 `bytes` 或 `newline=""`；在 Windows 上用 `Path.write_text()` 会把 LF 悄悄翻成 CRLF。

**三、入口地址只写一处。** 只有 `ai-daily/site/config.js` 的 `siteUrl` 能写真实地址，其余位置一律 `__SITE_URL__` / `__SITE_HOST__` 占位，打包与导出时注入。多写一处，`secret_scan.py` 会红——这不是洁癖，公开仓库里不能有可用的访问码。

## 会被退回的改动

- **重写渲染层 / 换框架。** 报纸是纯静态 HTML，没有构建步骤是有意为之：十年后双击还能打开。
- **把域名、访问码、令牌写进任何新文件**，包括测试夹具、示例配置、截图。
- **加定时任务、自启、云函数。** 出报靠会话触发是刻意选择，见 `README.md` 的「边界」。
- **只改文档不跑脚本。** 条数、断言范围、清单项数由 `ai-daily/tools/doc_sync.py` 生成，手改数字下一轮就会被改回去。

## 关于「提案」

报纸第 16 版每期会登四条提案（读者 / 编辑 / 创刊人 / AI 各一条）。这是这个项目接受内容建议的正式通道：提案登出后若无人采纳，到期自动作废（沉默即否决）。想改报纸的方向，走这条路比开 issue 更有效。

## 许可

代码按 [MIT](LICENSE) 授权，报纸内容按 [CC BY 4.0](LICENSE-CONTENT.md) 授权。提 PR 即表示你同意以这两个许可发布你的贡献。第三方内容与商标见 [NOTICE.md](NOTICE.md)。
