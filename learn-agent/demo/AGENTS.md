# AGENTS.md · 晨读卡（learn-agent/demo）

> 本文件是这个项目**唯一的约定来源**。任何脚本、任何 agent、任何人要改这个项目，先读这里。
> 代码与本文件冲突时，以本文件为准，并把代码改回来。
>
> 对应教材：第 0 章「无状态 → 约定必须落文件」、第 1 章「唯一真源」。

## 1. 这个项目是什么

每天生成一张「晨读卡」：一句短语 + 出处 + 标签；另有一面卡片墙 `index.html` 供翻阅。

业务规模只有晨报的 1/20，但工程结构和晨报**完全同构**：

```
契约 → 断言 → 流水线 → 状态 → 闸门 → 回归
```

**完全独立**：本目录不读写 `ai-daily/` 的任何文件，也不被 `ai-daily/` 引用。
在这里练坏了，只影响这里；晨报照常运行。

## 2. 唯一真源

| 东西 | 唯一位置 | 谁写 | 谁读 |
|---|---|---|---|
| 素材（每句话） | `data/quotes.json` | 人（只增不改） | `tools/build.py` |
| 单卡版式 | `templates/card.html` | 人 | `tools/build.py` |
| 卡片墙版式 | `templates/wall.html` | 人 | `tools/build.py` |
| 验收标准 | `tools/validate.py` | 人 | `build.py` / `gate.py` / `verify.py` |
| 产物索引 | `site/index.json` | `build.py` 全量重建 | `validate.py` / 卡片墙 |
| 运行状态 | `status.json` | `gate.py` | 补发/续跑逻辑 |
| 临时中间产物 | `stages/` | `build.py` | 只有 `build.py` |

**规则**：同一件事只允许写在上面某一行里。别的地方需要它，只能引用，不能复制一份。

## 3. 目录结构

```
demo/
  AGENTS.md              ← 你在这里
  指导手册.md             ← 逐步教学：每步怎么做、为什么
  data/quotes.json       ← 素材（唯一真源）
  templates/
    card.html            ← 单卡模板（{{占位符}}）
    wall.html            ← 卡片墙模板
  tools/
    validate.py          ← 断言（18 条）
    build.py             ← 五阶段流水线
    gate.py              ← 状态机 + 发布闸门
    verify.py            ← 一键回归
  stages/                ← 中间产物（可再生，别提交）
  site/                  ← 最终产物（要提交，它是被直接访问的东西）
  status.json            ← 运行状态（要提交，失败时靠它定位）
```

## 4. 常用命令

```bash
python tools/validate.py                    # 只判定，不生成；退出码 0/1
python tools/build.py --date 2026-11-06     # 跑完整五阶段
python tools/gate.py --date 2026-11-06      # 断言不过就不发布
python tools/gate.py --break                # 故意破坏一次，看闸门怎么拦
python tools/verify.py                      # 一条命令跑全部检查
```

约定：**所有命令的退出码为 0 才算通过**。不要用「看输出像不像成功」来判断。

## 5. 不变量（改代码不许破坏）

1. **素材只读**：`build.py` 不许改写 `data/quotes.json`。
2. **日期唯一**：一个日期只能有一条素材；重复必须在 `validate.py` 里被抓住。
3. **索引全量重建**：`site/index.json` 每次从 `site/cards/` 重新算，不做增量追加（天然幂等）。
4. **原子写**：`site/` 下的文件先写 `.tmp`、校验通过后 `os.replace`，任何时刻不能出现半截文件。
5. **文本必须转义**：`text` / `author` / `source` 插入 HTML 前必须 `html.escape`。
6. **产物可追溯**：`site/index.json` 的每一条都必须能在 `site/cards/` 找到对应文件。
7. **本目录不出现 `ai-daily`**：任何脚本、模板、文档都不许引用晨报的路径。

第 5 条是真实教训：素材里有一条带 `<`、`>`、`&` 的句子，不转义会被浏览器当标签吞掉，页面直接少字。

## 6. 权限档

| 动作 | 档 | 规则 |
|---|---|---|
| 读素材、跑 `validate.py`、跑 `verify.py` | A | 可自动执行 |
| 写 `site/`、`stages/`、`status.json` | B | 可自动执行，做完在输出里报备 |
| 改 `data/quotes.json`、改模板、删文件 | C | 必须先问，得到当轮明确同意才做 |
| 对外发布（部署到公网） | C | **本项目不包含**，故意留白 |

`gate.py` 里用一个 `guard()` 函数把 C 档变成真的过不去的检查，而不是文档里的一句话。

## 7. 失败与状态

- 每个阶段成功写 `status.json` 的 `steps.<名字>`，最后汇总 `state`。
- 三态：`OK`（全绿）/ `PARTIAL`（有成功步骤，可定点补偿）/ `FAILED`（全断）。
- `resume_from` 指向第一个没成功的阶段，`gate.py --resume` 从那里续跑。
- 同一日期连续失败 3 次 → `error = CIRCUIT_OPEN`，停止自动重试，等人介入。
- **判据看 `state` 和退出码，不看文件是否存在**：半截文件存在 ≠ 成功。

## 8. 已知限制

- 素材是本地示例，不是真实名人引用；`author` 一律写「示例·编辑部」，避免伪造。
- 只支持一天一张卡；不做多语言、不做搜索。
- 没有后端、没有数据库、没有外部依赖：`python` 标准库之外什么都不用装。
- 本项目不发布到公网。想练发布，用 `/tmp` 里的副本，别在这里加部署脚本。
