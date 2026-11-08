#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SessionStart hook：WorkBuddy 启动（新会话）时检查今天这期晨报的状态。

三种状态：
  ok        今天这期已出、已同步 site/、已收录索引 -> 完全静默
  missing   今天这期还没出                          -> 注入「自动补报」任务
  drift     出了但没同步 site/ 或没进索引           -> 注入「自动收尾」任务

设计要点：
1. 只在 ai-daily 本项目的会话里生效，其他项目的会话静默退出；
2. 任何异常都以 exit 0 + 静默结束，绝不阻塞 WorkBuddy 启动；
3. 同一会话只注入一次，避免 resume/clear 反复出报；
4. 2026-11-06 23:40 起，注入的是**完整自动任务**而不是提醒：
   不等用户消息、不询问确认，按 AGENTS.md §4 顺序走完闸门 → 发布 → 线上验证，
   任一 FAIL / BLOCK 立即停止。REQUIRED_CONTEXT 锁住不可删的片段。

手动查看：python tools/boot_check.py --status
文案体检：python tools/boot_check.py --check
"""

import datetime
import glob
import hashlib
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
NEWS_DIR = os.path.dirname(HERE)                       # .../ai-daily
PROJECT_DIR = os.path.dirname(NEWS_DIR)                # .../2026-11-03-20-15-44
PROJECT_KEY = "2026-11-03-20-15-44"                    # C 盘与 D 盘是同一份，用目录名识别
SITE_DIR = os.path.join(NEWS_DIR, "site")
STATUS_PATH = os.path.join(NEWS_DIR, "status.json")   # 与 tools/status.py 的 STATUS 同一位置
LOG_PATH = os.path.join(HERE, "boot_check.log")

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 注入文案的必需片段：锁住 AGENTS.md §4 里不可跳过的一步和几条红线。
# 防止以后被悄悄改回「只提醒、不自动执行」。用 `--check` 体检，两种状态都验。
REQUIRED_CONTEXT = (
    "不要等待用户消息",
    "不要询问确认",
    "00-thread.json",
    "00-facts.json",
    "00-blocks.json",
    "00-sources.json",
    "selfcheck.py --pre",
    "status.py --gate",
    "直接发布 site/",
    "selfcheck.py --online",
    "status.py --mark deploy=OK verify=OK",
    "不得发布",
    "不得说完成",
    "status.py --ticket",
)

# missing / drift 两种状态共用的闸门段：只写一份，避免两处漂移。
AUTO_TAIL = (
    "\n3) 发布前闸门：python ai-daily/tools/selfcheck.py --pre 必须全 PASS；"
    "python ai-daily/tools/status.py --gate 必须 ALLOW。任何 FAIL 或 BLOCK 立即停止："
    "不得发布、不得说完成，原样贴出失败项，"
    "并运行 python ai-daily/tools/status.py --ticket 出工单；\n"
    "4) 直接发布 site/（2026-11-06 起长期授权，不再征询；域名、访问码、domainPrefix 都不变）；\n"
    "5) 线上验证：python ai-daily/tools/selfcheck.py --online 必须全 PASS；"
    "再运行 python ai-daily/tools/status.py --mark deploy=OK verify=OK 记录结果；\n"
    "6) 完成后一句话汇报期号与两端可见；有 FAIL 就如实报失败，不许只报通过项。\n"
    "红线：报纸日期必须是出报当天（R07）；issues.js 禁手改；"
    "未点名采纳的提案一律不实施（沉默即否决）；自检有 FAIL 不许说完成（R06）。"
)


def validate_context(ctx: str) -> list:
    """返回缺失的必需片段；空列表表示文案完整。"""
    return [t for t in REQUIRED_CONTEXT if t not in ctx]


def log(line: str) -> None:
    try:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (stamp, line))
    except Exception:
        pass


def sync_docs() -> str:
    """会话开始把规则文档 / 产物清单的机械漂移改掉，返回一行摘要。

    「改完自动同步文档」靠这一步落地：新加断言、删了脚本、换了条数，
    下次开会话时数字自己就对了，不用人记。语义修改（加规则正文、删产物）
    doc_sync 只写提案，不动正文——它没有权力替人做判断。
    整段包在 try 里：文档同步失败绝不能影响出报。
    """
    try:
        import doc_sync
        res = doc_sync.fix(quiet=True)
    except Exception as exc:
        log("warn  doc_sync 跳过：%r" % (exc,))
        return ""
    if not res.get("fixed"):
        return ""
    line = "文档已自动对齐：%s。" % "；".join(res["fixed"][:4])
    if res.get("proposal"):
        line += "提案见 ai-daily/_process/doc-sync-proposal.md。"
    log("sync  " + line)
    return line


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()
    sys.exit(0)


def silent() -> None:
    emit({"continue": True, "suppressOutput": True})


def current_date() -> datetime.date:
    """默认取本机日期；测试时可用 AI_DAILY_TODAY=YYYY-MM-DD 覆盖。"""
    override = os.environ.get("AI_DAILY_TODAY", "").strip()
    if override:
        try:
            return datetime.date.fromisoformat(override)
        except Exception:
            pass
    return datetime.date.today()


def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def issue_no_of(path: str) -> int:
    m = re.search(r"第\s*(\d{3})\s*期", os.path.basename(path))
    if m:
        return int(m.group(1))
    try:
        head = open(path, encoding="utf-8", errors="ignore").read(4000)
        m = re.search(r"第\s*(\d{3})\s*期", head)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0


def issues() -> list:
    out = []
    for p in glob.glob(os.path.join(NEWS_DIR, "AI晨报-*.html")):
        m = re.search(r"AI晨报-(\d{4}-\d{2}-\d{2})\.html$", os.path.basename(p))
        if m:
            out.append((m.group(1), p))
    out.sort()
    return out


def today_file(today: datetime.date) -> str:
    return os.path.join(NEWS_DIR, "AI晨报-%s.html" % today.isoformat())


def index_has(today: datetime.date) -> bool:
    idx = os.path.join(SITE_DIR, "issues.js")
    try:
        return today.isoformat() in open(idx, encoding="utf-8", errors="ignore").read()
    except Exception:
        return False


def status_snapshot() -> dict:
    """读 status.json。读不到就返回空字典——状态机是辅助，不能拖垮启动检查。"""
    try:
        data = json.load(open(STATUS_PATH, encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def state_of(today: datetime.date):
    """返回 (状态, 问题列表)。"""
    src = today_file(today)
    if not os.path.exists(src):
        return "missing", []

    problems = []
    site_copy = os.path.join(SITE_DIR, os.path.basename(src))
    if not os.path.exists(site_copy):
        problems.append("site/ 里没有这一期，桌面与手机入口打不开")
    elif md5(src) != md5(site_copy):
        problems.append("site/ 那份与源文件不一致（大小或内容不同）")

    if not index_has(today):
        problems.append("issues.js 索引里还没有这一期，阅读器翻不到")

    # 状态机只在「记录的就是今天」时参与判定，历史期次不受影响
    st = status_snapshot()
    if st.get("date") == today.isoformat():
        steps = st.get("steps") or {}
        err = str(st.get("error") or "")
        if err.startswith("CIRCUIT_OPEN"):
            problems.append("status.json 已熔断：%s" % err)
        # 其它错误由下面的阶段状态表达，不重复报同一件事
        deploy = steps.get("deploy") or ""
        verify = steps.get("verify") or ""
        if not deploy.startswith("OK"):
            problems.append("还没发布到线上（status: deploy %s）" %
                            (deploy or "未开始"))
        elif not verify.startswith("OK"):
            problems.append("线上三处还没验证（status: verify %s）" %
                            (verify or "未开始"))

    return ("ok" if not problems else "drift"), problems


def in_this_project(cwd: str, event: dict | None = None) -> bool:
    """判断这次会话是不是本项目的。

    2026-11-06 19:39 之后 SessionStart 事件里的 cwd 一直是空字符串，
    旧实现 ``if not cwd: return False`` 让 hook 连指令都没注入过（log 里全是
    skip）。事件里还可能带 transcript_path / workspace 等路径，先都拿来正向
    命中；只有「明确给了路径、且都不指向本项目」时才静默，避免污染其它会话。
    完全拿不到路径时按安装位置兜底：这条 hook 就装在本项目 tools/ 下，
    脚本自身路径已经能证明它是为谁服务的。
    """
    ev = event or {}
    keys = ("transcript_path", "workspace", "project_dir",
            "session_cwd", "working_dir")
    explicit = [str(v) for v in [cwd] + [ev.get(k) for k in keys] if v]
    env_paths = [os.environ.get(k) for k in
                 ("CODEBUDDY_PROJECT_DIR", "CODEBUDDY_CWD", "WORKSPACE_DIR")]

    def hit(p):
        return PROJECT_KEY in os.path.normcase(os.path.abspath(p)).replace("\\", "/")

    for p in explicit:
        if hit(p):
            return True
    if explicit:
        return False                  # 明确指向别处：保持静默，环境变量也不许覆盖
    for p in env_paths:               # 事件没给路径时，环境变量可作正向证据
        if p and hit(p):
            return True
    return os.path.isfile(os.path.join(PROJECT_DIR, "ai-daily", "AGENTS.md"))


def build_context(today: datetime.date, latest, state: str, problems: list,
                  sync_note: str = "") -> str:
    if latest:
        last_date, last_path = latest
        last_no = issue_no_of(last_path)
        next_no = last_no + 1
        last_line = "最近一期是 %s 第 %03d 期。" % (last_date, last_no)
    else:
        next_no = 1
        last_line = "目前一期都没有。"

    wd = WEEKDAY_CN[today.weekday()]
    head = ("[启动检查·自动任务] 今天是 %s（%s）。%s\n"
            % (today.isoformat(), wd, last_line))
    if sync_note:
        head += sync_note + "\n"

    if state == "missing":
        task = (
            "这是系统自动任务，不是提醒：请立即执行下面完整链路，"
            "不要等待用户消息、不要询问确认、不要只回答不做事；"
            "无论用户本轮是否另有请求，都先完成本任务。\n"
            "今天这期还没出，应生成 AI晨报-%s.html（第 %03d 期）。\n"
            "1) 结算上期提案（到期转否决、登记本期四条、更新 ai-daily/提案台账.md）；"
            "沿用最近一期的版式与 CSS 写 ai-daily/parts/<MMDD>/p01…p16；"
            "先写同目录 00-thread.json（本期主线一句话 + 跑偏词）、00-facts.json（每处外部数字一行）、"
            "00-blocks.json（每版信息来源：官方 / 第三方信息网 / 本报实测 / AI 生成，AI 生成版不得超过 4 版）"
            "与 00-sources.json（逐条信源归属：谁给的、给了什么、哪一类）；"
            "正文引用外部数字就地加 src-tag 标记；"
            "内容必须是当期真实信息，禁止编造事实与数字，不确定的就不写；\n"
            "2) 落盘前先确认 AI晨报-%s.html 不存在（避免与其它进程互相覆盖）；"
            "运行 python ai-daily/tools/assemble_issue.py --parts ... --date %s --issue %03d"
            "（A1–A16 断言必须全过；缺主线、事实卡、版级来源或信源表，主线与报头不符，"
            "跑偏超阈值，AI 生成版超上限，都会直接拒拼），"
            "再运行 python ai-daily/tools/build_index.py 同步 site/、重建 issues.js 与各期 json；"
        ) % (today.isoformat(), next_no, today.isoformat(),
             today.isoformat(), next_no)
    else:
        task = (
            "这是系统自动任务，不是提醒：请立即补齐收尾，"
            "不要等待用户消息、不要询问确认、不要只回答不做事；不要重新生成正文。\n"
            "当前缺口：\n- " + "\n- ".join(problems) + "\n"
            "1) 源文件在 ai-daily/AI晨报-%s.html，site/ 缺失或不一致就重新同步过去；\n"
            "2) 若 parts/<MMDD>/ 缺 00-thread.json、00-facts.json、00-blocks.json 或 "
            "00-sources.json，补写后重跑 assemble_issue.py"
            "（A1–A16 全过再继续）；\n"
            "3) 运行 python ai-daily/tools/build_index.py 重建索引，一并同步 site/ 与各期 json；"
        ) % today.isoformat()

    return head + task + AUTO_TAIL


def main() -> None:
    argv = sys.argv[1:]

    if "--status" in argv:
        today = current_date()
        latest = issues()[-1] if issues() else None
        state, problems = state_of(today)
        print("项目：     ", PROJECT_DIR)
        print("今天：     ", today.isoformat(), WEEKDAY_CN[today.weekday()])
        print("状态：     ", state)
        if problems:
            for p in problems:
                print("           -", p)
        print("已有期数： ", ", ".join(d for d, _ in issues()) or "无")
        print("最近一期： ", latest[0] if latest else "无")
        st = status_snapshot()
        if st:
            print("状态机：   ", "%s · %s · 尝试 %s 次%s" % (
                st.get("date", "?"), st.get("state", "?"), st.get("attempt", 0),
                (" · 续跑点 " + st["resume_from"]) if st.get("resume_from") else ""))
            if st.get("error"):
                print("           ", st["error"])
        else:
            print("状态机：    尚无 status.json")
        return

    if "--check" in argv:
        today = current_date()
        latest = issues()[-1] if issues() else None
        samples = {
            "missing": build_context(today, latest, "missing", []),
            "drift": build_context(today, latest, "drift", ["还没发布到线上"]),
        }
        bad = []
        for token in REQUIRED_CONTEXT:
            miss = [k for k, ctx in samples.items() if token not in ctx]
            print("%-42s %s" % (token, "OK" if not miss else "MISSING in " + ",".join(miss)))
            if miss:
                bad.append(token)
        print("注入文案完整性：%s（两种状态都验）"
              % ("OK" if not bad else "FAIL · " + ", ".join(bad)))
        sys.exit(0 if not bad else 1)

    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw and raw.strip() else {}
    except Exception:
        event = {}

    cwd = str(event.get("cwd") or "")
    source = str(event.get("source") or "startup")
    session = str(event.get("session_id") or "")

    if not in_this_project(cwd, event):
        log("skip  source=%s  cwd=%s  不在本项目" % (source, cwd))
        silent()
    if not cwd:
        log("guard=installed  source=%s  事件未给 cwd，按 hook 安装位置判定" % source)

    today = current_date()
    state, problems = state_of(today)

    if state == "ok":
        log("ok    source=%s  %s" % (source, os.path.basename(today_file(today))))
        silent()

    if session:
        state_dir = os.path.join(HERE, ".boot-state")
        flag = os.path.join(state_dir, "%s.flag" % re.sub(r"[^0-9A-Za-z_.-]", "_", session))
        try:
            os.makedirs(state_dir, exist_ok=True)
            if os.path.exists(flag):
                log("skip  source=%s  session=%s 已提示过" % (source, session))
                silent()
            open(flag, "w", encoding="utf-8").write(today.isoformat())
        except Exception:
            pass

    ctx = build_context(today, issues()[-1] if issues() else None, state, problems,
                        sync_docs())
    broken = validate_context(ctx)
    if broken:
        # 宁可注入一份不完整的指令，也不能漏报；但把异常写进日志等人发现。
        log("error 注入文案缺必需片段：%s" % ", ".join(broken))
    log("inject source=%s  state=%s  %s" % (source, state, "; ".join(problems) or "缺报"))
    emit({
        "continue": True,
        "suppressOutput": True,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ctx,
        },
    })


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        log("error %r" % (exc,))
        sys.stdout.write(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)
