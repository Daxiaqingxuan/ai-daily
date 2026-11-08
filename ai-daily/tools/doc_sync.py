#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文档对账：文档里写的数字，必须等于代码与磁盘里的事实。

为什么要这个工具
    规则文档和产物清单是手写的，代码是改出来的。两者一脱节，文档就开始骗人：
    写着 A1–A13 而代码已经到 A16，标题写 24 条实际 27 行，清单列着已经删掉的文件。
    靠人记必然漂，所以每次会话开始都对一遍，把可机械推导的部分直接改对。

自动改什么（--fix，幂等）
    规则各级条数 / 总数行 / 断言范围 A1–Ax / 脚本数量 /
    断言索引表（整块重生成）/ 产物清单三处计数 / 变更记录追加一行。
    只改数字与生成块；规则正文、产物取舍一律只提不改。

只提不改什么（写进提案）
    - 代码里有断言、但没有规则引用它（规则漏了）
    - 文档引用了不存在的断言或脚本（规则写错了）
    - 工具目录里有脚本没进文档（文档漏了）
    - 产物清单列了不存在的路径（清单过期）

谁来跑
    boot_check.py 会话开始自动 --fix 并写提案；
    selfcheck.py 第 14 项查「修完还对不上」的部分，FAIL 即不许发布。

用法：
    python tools/doc_sync.py                 # 只查，有 FAIL 退出 1
    python tools/doc_sync.py --fix           # 先机械修正再查
    python tools/doc_sync.py --fix --quiet   # 给 hook 用，不打印
    python tools/doc_sync.py --json          # 机器可读
"""
import argparse
import datetime
import difflib
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent          # ai-daily/tools
ROOT = HERE.parent                              # ai-daily
WS = ROOT.parent                                # 工作区根

RULES = WS / "项目框架与规则.md"
PRODUCTS = WS / "产物清单.md"
PROPOSAL = ROOT / "_process" / "doc-sync-proposal.md"

FAIL, WARN = "FAIL", "WARN"

# 规则文档：### 4.4 L2 工程约定（24 条）
LEVEL_RE = re.compile(r"^###\s+4\.\d+\s+(L\d)[^（(]*[（(](\d+)\s*条", re.M)
# 规则行：| **L38** | 正文 | 靠什么拦 |
RULE_RE = re.compile(r"^\|\s*\*\*([A-Z]\d{1,2})\*\*\s*\|(.+)\|\s*$", re.M)
TOTAL_RE = re.compile(r"数一下：([^\n]*)")
RANGE_RE = re.compile(r"A1([–—\-])A(\d{1,2})")
SCRIPT_N_RE = re.compile(r"(\d+)(\s*个脚本)")

# 产物清单
P_TOTAL_RE = re.compile(r"\*\*共\s*(\d+)\s*项。\*\*")
P_HEAD_RE = re.compile(r"##\s*二、\s*(\d+)\s*项总表")
P_ROW_RE = re.compile(r"^\|\s*(\d{2})\s*\|", re.M)
P_SUM_RE = re.compile(r"小计：[^\n]*=\s*\*\*(\d+)\*\*")
P_SUM_LINE_RE = re.compile(r"^小计：[^\n]*$", re.M)
P_GROUP_RE = re.compile(r"晨报\s*(\d+)\s*\+\s*教程\s*(\d+)\s*\+\s*演示\s*(\d+)")

BEGIN = "<!-- doc-sync:assertions:begin -->"
END = "<!-- doc-sync:assertions:end -->"
APX_HDR = "### 4.7 断言索引（自动生成，勿手改）"
LOG_HDR = "## 八、变更记录（自动追加）"

ROOT_FILES = {"README.md", "LICENSE", "LICENSE-CONTENT.md", "NOTICE.md",
              "产物清单.md", "项目框架与规则.md"}

ASSERT_RE = re.compile(r'errs\.append\("(A\d{1,2}[a-z]?)')


# ---------- 读写：保持原行尾 ----------
def read_norm(path):
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8")
    return text.replace("\r\n", "\n"), ("\r\n" if "\r\n" in text else "\n")


def write_norm(path, norm, nl):
    Path(path).write_bytes(norm.replace("\n", nl).encode("utf-8"))


# ---------- 事实：代码与磁盘 ----------
def discover_assertions():
    """assemble_issue.py 里所有 errs.append("Axx" 的编号与触发点数。"""
    src = (HERE / "assemble_issue.py").read_text(encoding="utf-8")
    return Counter(ASSERT_RE.findall(src))


def max_assert_no(assertions):
    nums = [int(re.match(r"A(\d+)", a).group(1)) for a in assertions] or [0]
    return max(nums)


def discover_scripts():
    """tools/ 下一切可执行脚本（.py / .js）；.cmd 只是包装，单独算。"""
    return sorted(p.name for p in HERE.iterdir()
                  if p.is_file() and p.suffix in (".py", ".js"))


# ---------- 解析：规则文档 ----------
def parse_rules(text):
    levels = {}
    for m in LEVEL_RE.finditer(text):
        levels[m.group(1)] = {"declared": int(m.group(2)), "rows": []}
    cur = None
    for line in text.split("\n"):
        lm = LEVEL_RE.match(line)
        if lm:
            cur = lm.group(1)
            continue
        rm = RULE_RE.match(line)
        if rm and cur:
            cells = [c.strip() for c in rm.group(2).split("|")]
            levels[cur]["rows"].append({
                "id": rm.group(1),
                "text": cells[0] if cells else "",
                # L0 有 4 列（规则/靠什么拦/后果），L1-L3 是 3 列；靠什么拦都在 [1]
                "enforce": " ".join(cells[1:]) if len(cells) > 1 else "",
            })
    return levels


def rule_refs(levels):
    """断言 → 引用它的规则 id 列表。"""
    refs = {}
    for lv in levels.values():
        for row in lv["rows"]:
            for a in re.findall(r"\bA\d{1,2}[a-z]?\b", row["enforce"]):
                refs.setdefault(a, [])
                if row["id"] not in refs[a]:
                    refs[a].append(row["id"])
    return refs


# ---------- 解析：产物清单 ----------
def parse_products(text):
    rows = re.findall(r"^\|\s*(\d{2})\s*\|\s*([^|]+)\|", text, re.M)
    locs, cats = [], []
    for no, name in rows:
        line = next(l for l in text.split("\n")
                    if l.startswith("| %s |" % no))
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        locs.append((no, name.strip(), cells[3] if len(cells) > 3 else ""))
        cats.append((no, cells[2] if len(cells) > 2 else ""))
    return {
        "total": [int(m.group(1)) for m in P_TOTAL_RE.finditer(text)],
        "head": [int(m.group(1)) for m in P_HEAD_RE.finditer(text)],
        "sum": [int(m.group(1)) for m in P_SUM_RE.finditer(text)],
        "rows": rows,
        "locs": locs,
        "cats": cats,
    }


def resolve_token(tok):
    tok = tok.strip().rstrip("，、；。")
    if not tok or tok.startswith(("http://", "https://", "C:\\", "file:", ".")):
        return None
    if "*" in tok or "…" in tok or "〔" in tok or " " in tok:
        return None
    if tok.startswith(("ai-daily/", "learn-agent/")):
        return WS / tok
    if tok.startswith("site/"):
        return ROOT / tok
    if tok in ROOT_FILES:
        return WS / tok
    return None


# ---------- 生成：断言索引块 ----------
def render_assertions(assertions, refs):
    ids = sorted(assertions, key=lambda a: (int(re.match(r"A(\d+)", a).group(1)), a))
    out = [BEGIN,
           "| 断言 | 触发点 | 对应规则 |",
           "|---|---|---|"]
    for a in ids:
        out.append("| %s | %d | %s |" % (a, assertions[a], "、".join(refs.get(a, [])) or "—"))
    gap = [a for a in ids if not refs.get(a)]
    out.append("")
    out.append("共 %d 个断言编号、%d 个触发点%s"
               % (len(ids), sum(assertions.values()),
                  "；**没有规则引用**：%s（要么补规则，要么承认它只是实现细节）"
                  % "、".join(gap) if gap else "；每个断言都有规则引用"))
    out.append(END)
    return "\n".join(out)


# ---------- 机械修正 ----------
def _replace_span(text, m, new_value, changes, label):
    s, e = m.span(1)
    old = m.group(1)
    changes.append("%s %s→%s" % (label, old, new_value))
    return text[:s] + str(new_value) + text[e:]


def body_of(text):
    """去掉 §八 变更记录：那是历史，里面写着的旧数字不该被当成现状。

    否则每修一次就多一行「A1–A13→A1–A16」，下一轮又把它当漂移抓出来，
    变成自己咬自己。
    """
    i = text.find(LOG_HDR)
    return text if i < 0 else text[:i]


def fix_rules(text, assertions, scripts):
    """返回 (新文本, 变更说明列表)。幂等：没漂就不动。"""
    cut = text.find(LOG_HDR)
    body, tail = (text, "") if cut < 0 else (text[:cut], text[cut:])
    text = body
    changes = []
    levels = parse_rules(text)
    refs = rule_refs(levels)

    # 1) 各级条数
    def _hdr(m):
        lv, n = m.group(1), int(m.group(2))
        real = len(levels.get(lv, {}).get("rows", []))
        if n == real:
            return m.group(0)
        changes.append("%s 条数 %d→%d" % (lv, n, real))
        s, e = m.span(2)
        return m.group(0)[:s - m.start(0)] + str(real) + m.group(0)[e - m.start(0):]

    text = LEVEL_RE.sub(_hdr, text)

    # 2) 总数行
    levels = parse_rules(text)
    counts = [(lv, len(levels[lv]["rows"])) for lv in ("L0", "L1", "L2", "L3")
              if lv in levels]
    total = sum(c for _, c in counts)
    m = TOTAL_RE.search(text)
    if m:
        want = "数一下：" + " + ".join("%s %d" % (lv, c) for lv, c in counts) \
               + " = **%d 条**" % total
        old = m.group(0).rstrip("。")
        if old.strip() != want.strip():
            changes.append("规则总数 → %d 条（%s）"
                           % (total, " + ".join("%s %d" % (lv, c) for lv, c in counts)))
            text = text[:m.start()] + want + "。" + text[m.end():]

    # 3) 断言范围 A1–Ax
    want_max = max_assert_no(assertions)

    def _rng(m2):
        if int(m2.group(2)) == want_max:
            return m2.group(0)
        changes.append("断言范围 %s→A1–A%d" % (m2.group(0), want_max))
        return "A1" + m2.group(1) + "A%d" % want_max

    text = RANGE_RE.sub(_rng, text)

    # 4) 脚本数量（"18 个脚本"）
    def _sn(m3):
        n = int(m3.group(1))
        if n == len(scripts):
            return m3.group(0)
        changes.append("脚本数量 %d→%d" % (n, len(scripts)))
        return "%d%s" % (len(scripts), m3.group(2))

    text = SCRIPT_N_RE.sub(_sn, text)

    # 5) 断言索引块
    block = render_assertions(assertions, refs)
    if BEGIN in text and END in text:
        i = text.index(BEGIN)
        j = text.index(END) + len(END)
        if text[i:j] != block:
            changes.append("断言索引表重生成")
            text = text[:i] + block + text[j:]
    else:
        m4 = TOTAL_RE.search(text)
        if m4:
            ins = "\n\n%s\n\n%s\n" % (APX_HDR, block)
            e = m4.end()
            # 跳过后面的句号与换行，插在空行之前
            while e < len(text) and text[e] in "。\n":
                e += 1
            text = text[:e] + ins.lstrip("\n") + "\n" + text[e:]
            changes.append("新增 §4.7 断言索引（自动生成）")

    return text + tail, changes


def sum_labels(line):
    """从小计行取出分类标签序列：`小计：报纸 5 · 入口 4 … = **28**。`"""
    labels = []
    for seg in line[len("小计："):].split("=")[0].split("·"):
        seg = seg.strip()
        if seg:
            labels.append(seg.rsplit(" ", 1)[0].strip())
    return labels


def render_sum_line(line, cats, total):
    """按表格「类别」列重算小计行。

    「工具与模板」这类合并段按「与」拆开分别累加；表格里出现了、小计行没列到的
    类别补一个「其他」，不让它静默消失。fix 与 check 共用这一份逻辑——否则
    「检查」和「修正」各写一遍，迟早跑出两种答案。
    """
    labels = sum_labels(line)
    if not labels:
        return line
    cnt = Counter(cats)

    def count(label):
        return sum(cnt.get(x.strip(), 0) for x in label.split("与"))

    vals = {lab: count(lab) for lab in labels}
    covered = {x.strip() for lab in labels for x in lab.split("与")}
    extra = {k: v for k, v in cnt.items() if k not in covered}
    if extra:
        vals["其他"] = sum(extra.values())
    return ("小计：" + " · ".join("%s %d" % (k, v) for k, v in vals.items())
            + " = **%d**。" % total)


def fix_products(text, scripts_ai):
    changes = []
    p = parse_products(text)
    n = len(p["rows"])

    for pat, label in ((P_TOTAL_RE, "共 N 项"), (P_HEAD_RE, "§二 标题项数")):
        def _sub(m, label=label):
            v = int(m.group(1))
            if v == n:
                return m.group(0)
            changes.append("%s %d→%d" % (label, v, n))
            s, e = m.span(1)
            return m.group(0)[:s - m.start(0)] + str(n) + m.group(0)[e - m.start(0):]
        text = pat.sub(_sub, text)

    # 小计行按「类别」列重算每一段，而不只是改末尾总数。
    # 踩过：新增第 28 项后总数自动变 28，但「文档 7」没动，
    # 5+4+2+7+5+3 = 26 ≠ 28，doc_sync 却报「对得上」——总数对、分项错，
    # 比整行不更新更难发现。
    cats = [c for _, c in p["cats"] if c]

    def _sum(m):
        new = render_sum_line(m.group(0), cats, n)
        if new != m.group(0):
            changes.append("小计分项（按类别重算）")
        return new

    text = P_SUM_LINE_RE.sub(_sum, text)

    def _grp(m):
        a, t, d = (int(m.group(i)) for i in (1, 2, 3))
        real = (scripts_ai, len(list((WS / "learn-agent" / "tools").glob("*.py"))),
                len(list((WS / "learn-agent" / "demo" / "tools").glob("*.py"))))
        if (a, t, d) == real:
            return m.group(0)
        changes.append("脚本分组 %d+%d+%d→%d+%d+%d" % (a, t, d, *real))
        return "晨报 %d + 教程 %d + 演示 %d" % real

    text = P_GROUP_RE.sub(_grp, text)

    def _sn(m):
        v = int(m.group(1))
        if v == scripts_ai:
            return m.group(0)
        changes.append("工具目录脚本数 %d→%d" % (v, scripts_ai))
        return "%d%s" % (scripts_ai, m.group(2))

    text = SCRIPT_N_RE.sub(_sn, text)

    # 清单里也会写「断言 A1–A13」，与规则文档共用同一个事实源。
    # 这条踩过：规则文档已改到 A16，清单第 77 行还写着 A1–A13，没人发现。
    nums = [int(a[1:]) for a in discover_assertions() if a[1:].isdigit()]
    if nums:
        maxa = str(max(nums))

        def _ar(m):
            if m.group(1) == maxa:
                return m.group(0)
            changes.append("断言范围 A1–A%s→A1–A%s" % (m.group(1), maxa))
            return m.group(0).replace("A" + m.group(1), "A" + maxa, 1)

        text = re.sub(r"A1[–-]A(\d+)", _ar, text)

    return text, changes


def append_log(text, rows, nl_norm="\n"):
    """在 §八 追加变更行；没有变化就不写。"""
    if not rows:
        return text, False
    if LOG_HDR not in text:
        head = ("\n---\n\n%s\n\n"
                "> 由 `tools/doc_sync.py --fix` 追加，只在真的改了东西时写一行。\n"
                "> 语义修改（加规则、删产物）仍然走人工，这里只记机械对齐。\n\n"
                "| 时间 | 变更 |\n|---|---|\n" % LOG_HDR)
        text = text.rstrip("\n") + "\n" + head
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    text = text.rstrip("\n") + "\n| %s | %s |\n" % (stamp, "；".join(rows))
    return text, True


# ---------- 检查 ----------
def check(doc_path=None, products_path=None):
    doc_path = Path(doc_path or RULES)
    products_path = Path(products_path or PRODUCTS)
    out = []

    def add(sev, code, msg):
        out.append({"sev": sev, "code": code, "msg": msg})

    if not doc_path.exists():
        add(WARN, "doc.missing", "找不到 %s，跳过规则对账" % doc_path.name)
        return out, {}

    text, _ = read_norm(doc_path)
    text = body_of(text)          # §八 是历史记录，不参与对账
    assertions = discover_assertions()
    scripts = discover_scripts()
    levels = parse_rules(text)
    refs = rule_refs(levels)

    # 条数
    for lv, info in levels.items():
        if info["declared"] != len(info["rows"]):
            add(FAIL, "count.%s" % lv,
                "%s 标题写 %d 条，表里实际 %d 行（跑 --fix 自动改）"
                % (lv, info["declared"], len(info["rows"])))
    m = TOTAL_RE.search(text)
    if m:
        real = sum(len(i["rows"]) for i in levels.values())
        nums = [int(x) for x in re.findall(r"L\d\s*(\d+)", m.group(0))]
        if sum(nums) != real or ("**%d 条**" % real) not in m.group(0):
            add(FAIL, "count.total",
                "总数行与各表不符：行显示 %s，实际 %d 条（跑 --fix）"
                % ("+".join(map(str, nums)) or "无", real))

    # 断言范围
    want = max_assert_no(assertions)
    for m2 in RANGE_RE.finditer(text):
        if int(m2.group(2)) != want:
            add(FAIL, "range.assertions",
                "文档写 %s，代码已到 A%d（跑 --fix）" % (m2.group(0), want))

    # 脚本数量
    for m3 in SCRIPT_N_RE.finditer(text):
        if int(m3.group(1)) != len(scripts):
            add(FAIL, "count.scripts",
                "文档写 %s 个脚本，tools/ 实存 %d 个（跑 --fix）"
                % (m3.group(1), len(scripts)))

    # 失效引用
    for a in sorted(refs):
        if a not in assertions:
            add(FAIL, "ref.dead",
                "规则 %s 引用了不存在的断言 %s" % ("、".join(refs[a]), a))
    for row_list in levels.values():
        for row in row_list["rows"]:
            for tok in re.findall(r"tools/([A-Za-z0-9_\-]+\.(?:py|js|cmd))", row["enforce"]):
                if not (HERE / tok).exists():
                    add(FAIL, "ref.script",
                        "规则 %s 引用了不存在的脚本 tools/%s" % (row["id"], tok))

    # 没有规则引用的断言（提示，不拦）
    gap = [a for a in assertions if a not in refs]
    if gap:
        add(WARN, "rule.gap",
            "代码里有 %d 个断言没有规则引用：%s" % (len(gap), "、".join(sorted(gap))))

    # 脚本没进文档
    for name in scripts:
        if name not in text:
            add(WARN, "script.unlisted", "tools/%s 没在规则文档里出现过" % name)

    # 断言索引块
    block = render_assertions(assertions, refs)
    if BEGIN not in text or END not in text:
        add(FAIL, "block.missing", "缺 §4.7 断言索引块（跑 --fix 生成）")
    else:
        i, j = text.index(BEGIN), text.index(END) + len(END)
        if text[i:j] != block:
            add(FAIL, "block.stale", "断言索引块与代码不一致（跑 --fix 重生成）")

    # 产物清单
    if products_path.exists():
        pt, _ = read_norm(products_path)
        p = parse_products(pt)
        n = len(p["rows"])
        for v in p["total"] + p["head"] + p["sum"]:
            if v != n:
                add(FAIL, "product.count",
                    "产物清单写 %d 项，表里实际 %d 行（跑 --fix）" % (v, n))
        nos = [int(no) for no, _, _ in p["locs"]]
        if nos != list(range(1, n + 1)):
            add(FAIL, "product.number",
                "产物编号不连续：%s" % "、".join("%02d" % x for x in nos))
        cats = [c for _, c in p["cats"] if c]
        for m6 in P_SUM_LINE_RE.finditer(pt):
            if render_sum_line(m6.group(0), cats, n) != m6.group(0):
                add(FAIL, "product.sum",
                    "产物清单小计分项与类别列不符：%s（跑 --fix）" % m6.group(0)[:46])
        for no, name, loc in p["locs"]:
            # 「仅本机」= 被 .gitignore 挡住的二进制（APK / 二维码）：本机有、公开导出里
            # 必然没有。不豁免的话，导出树跑自检会因为「列了不存在的文件」红一片。
            if "仅本机" in loc:
                continue
            for tok in re.findall(r"`([^`]+)`", loc):
                p2 = resolve_token(tok)
                if p2 is not None and not p2.exists():
                    add(FAIL, "product.path",
                        "第 %s 项「%s」列的 %s 不存在" % (no, name, tok))
        ai = len([s for s in scripts])
        for m5 in P_GROUP_RE.finditer(pt):
            got = tuple(int(x) for x in m5.groups())
            real = (ai, len(list((WS / "learn-agent" / "tools").glob("*.py"))),
                    len(list((WS / "learn-agent" / "demo" / "tools").glob("*.py"))))
            if got != real:
                add(FAIL, "product.group",
                    "脚本分组写 %d+%d+%d，实际 %d+%d+%d" % (got + real))
    else:
        add(WARN, "product.missing", "找不到 产物清单.md")

    meta = {"assertions": len(assertions), "triggers": sum(assertions.values()),
            "scripts": len(scripts), "rules": sum(len(i["rows"]) for i in levels.values())}
    return out, meta


# ---------- 提案 ----------
def write_proposal(pairs, changes, issues):
    if not changes and not any(i["sev"] == FAIL for i in issues):
        return ""
    PROPOSAL.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 文档对账提案 · %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
             "",
             "由 `tools/doc_sync.py --fix` 生成。**机械项已经改好了**，下面是改了什么、还差什么。",
             ""]
    if changes:
        lines += ["## 一、已自动修正", "", "| # | 变更 |", "|---|---|"]
        for i, c in enumerate(changes, 1):
            lines.append("| %d | %s |" % (i, c))
        lines.append("")
    hard = [i for i in issues if i["sev"] == FAIL]
    soft = [i for i in issues if i["sev"] == WARN]
    if hard or soft:
        lines += ["## 二、还要人处理", ""]
        for i in hard + soft:
            lines.append("- **%s** %s" % (i["sev"], i["msg"]))
        lines.append("")
    for name, before, after in pairs:
        if before == after:
            continue
        d = list(difflib.unified_diff(before.split("\n"), after.split("\n"),
                                      fromfile=name + "（旧）", tofile=name + "（新）",
                                      n=2, lineterm=""))
        lines += ["## 三、差异 · %s" % name, "", "```diff"] + d + ["```", ""]
    PROPOSAL.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return str(PROPOSAL)


# ---------- 入口 ----------
def fix(quiet=True, propose=True):
    result = {"fixed": [], "issues": [], "proposal": ""}
    pairs = []
    rules_changed = False
    for path, fn in ((RULES, lambda t: fix_rules(t, discover_assertions(),
                                                 discover_scripts())),
                     (PRODUCTS, lambda t: fix_products(t, len(discover_scripts())))):
        if not path.exists():
            continue
        before, nl = read_norm(path)
        after, changes = fn(before)
        if path is RULES:
            after, logged = append_log(after, changes)
            if logged:
                changes = changes + ["§八 记一行变更"]
            rules_changed = bool(changes)
        if after != before:
            write_norm(path, after, nl)
        pairs.append((path.name, before, after))
        result["fixed"] += changes

    if rules_changed and RULES.exists():
        # 只在规则文档真的改过时刷新「更新」时间；只改清单不该动这个戳
        before, nl = read_norm(RULES)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        new = re.sub(r"(> 更新：)(\d{4}-\d{2}-\d{2} \d{2}:\d{2})",
                     lambda m: m.group(1) + stamp, before, count=1)
        if new != before:
            write_norm(RULES, new, nl)
            pairs[0] = (pairs[0][0], pairs[0][1], new)

    issues, meta = check()
    result["issues"] = issues
    result["meta"] = meta
    if propose:
        result["proposal"] = write_proposal(pairs, result["fixed"], issues)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="机械项自动修正（幂等）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-proposal", action="store_true")
    a = ap.parse_args()

    if a.fix:
        res = fix(quiet=a.quiet, propose=not a.no_proposal)
    else:
        issues, meta = check()
        res = {"fixed": [], "issues": issues, "proposal": "",
               "meta": meta}

    hard = [i for i in res["issues"] if i["sev"] == FAIL]

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1 if hard else 0

    if not a.quiet:
        for c in res["fixed"]:
            print("  修正  %s" % c)
        for i in res["issues"]:
            print("[%s] %s  %s" % (i["sev"], i["code"], i["msg"]))
        meta = res.get("meta") or {}
        if meta:
            print("规则 %d 条 · 断言 %d 个 / %d 个触发点 · 脚本 %d 个"
                  % (meta["rules"], meta["assertions"], meta["triggers"], meta["scripts"]))
        if res["proposal"]:
            print("提案：%s" % res["proposal"])
        print("结论：%s" % ("对得上" if not hard and not res["issues"]
                          else "%d 个 FAIL / %d 个 WARN"
                          % (len(hard), len(res["issues"]) - len(hard))))
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
