## 这个 PR 做了什么

<!-- 一句话。如果要改报纸版式或加断言，先链接对应的 issue。 -->

## 提交前跑过

- [ ] `python ai-daily/tools/doctor.py`
- [ ] `python ai-daily/tools/selfcheck.py --pre`（0 FAIL）
- [ ] `python ai-daily/tools/secret_scan.py`
- [ ] 若改了断言或检查项：`python ai-daily/tools/mutation_test.py`（SKIP 必须 0）

## 三条硬约束

- [ ] 没有给主链路引入第三方依赖
- [ ] 没有新增明文入口地址（只有 `site/config.js` 的 `siteUrl` 可以写）
- [ ] 新写/修改的文件行尾没被 Git 改写（`.gitattributes` 已钉死 `* -text`）

## 其他

<!-- 截图、权衡、你放弃的方案。有争议的改动请写清为什么这样选。 -->
