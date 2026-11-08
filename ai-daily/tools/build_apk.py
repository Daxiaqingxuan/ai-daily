"""把 ai-daily/site 打成一个可安装的 Android APK。

不需要 Gradle / Android Studio：只用 JDK + Android build-tools 自带的
javac / aapt2 / d8 / zipalign / apksigner，命令行串起来即可。

产物：
  ai-daily/AI晨报.apk      —— 交付给用户安装
  ai-daily/site/ai-daily.apk —— 放到线上，手机浏览器可直接下载安装
  ai-daily/site/version.json —— 更新清单，App 启动时拿它比版本号
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
APK_SRC = ROOT / "apk"
SITE = ROOT / "site"
WORK = APK_SRC / ".build"
LOCAL = ROOT / ".local"                  # 本机私有值（口令等），已被 .gitignore 忽略
BUILD_STATE = LOCAL / "apk-build.json"   # 上一版版本号与指纹：自动更新靠它判重

TOOLS = Path(os.environ.get("AI_DAILY_ANDROID_HOME")
             or (Path(os.environ.get("LOCALAPPDATA") or Path.home())
                 / "ai-daily-build"))
OUT_NAME = "AI晨报.apk"

# 更新清单：App 启动时拉这一份，比 versionCode 决定弹不弹「有新版本」。
# 必须由打包脚本写——只有它知道最终 versionCode 和 sha256，别处再抄一份就是假绿源。
MANIFEST_NAME = "version.json"

# 离线快照保留最近 N 期正刊（及同期特刊）。不裁剪的话每期 +130 KB，
# 一年就是十几 MB——「纯自动」意味着没人会中途发现这件事，所以必须设上界。
OFFLINE_KEEP = int(os.environ.get("AI_DAILY_OFFLINE_KEEP") or 8)
MAX_MB = float(os.environ.get("AI_DAILY_APK_MAX_MB") or 4.0)

# versionCode 由打包日期派生：YYMMDD*100 + 当日序号。Android 只比 versionCode，
# 写死常量会让「新包」被系统当成同一个版本，覆盖安装静默失败。
VERSION_BASE = "1.3"


def load_state():
    try:
        d = json.loads(BUILD_STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_state(d):
    BUILD_STATE.parent.mkdir(parents=True, exist_ok=True)
    BUILD_STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")


def manifest_payload(st):
    """更新清单的字段。App 只认 code（单调递增）与 name（给人看）。"""
    return {
        "schema": 1,
        "code": st.get("code"),
        "name": st.get("name"),
        "file": "ai-daily.apk",
        "bytes": st.get("bytes"),
        "sha256": st.get("sha256"),
        "issue": st.get("issue"),
        "builtAt": st.get("at"),
    }


def write_manifest(st):
    """把清单写进 site/。字节级写：Windows 的 write_text 会翻成 CRLF。

    幂等：内容没变就不落盘，免得白改一次 mtime 让发布判定抖动。
    """
    raw = (json.dumps(manifest_payload(st), ensure_ascii=False, indent=2)
           + "\n").encode("utf-8")
    p = SITE / MANIFEST_NAME
    if p.exists() and p.read_bytes() == raw:
        return False
    p.write_bytes(raw)
    return True


def manifest_fresh(st):
    """清单是否已经和现有包对上。对不上就得重打，不能让 --auto 跳过。"""
    if not st.get("code") or not st.get("sha256"):
        return False
    try:
        d = json.loads((SITE / MANIFEST_NAME).read_text(encoding="utf-8"))
    except Exception:
        return False
    return (d.get("code") == st.get("code")
            and d.get("sha256") == st.get("sha256")
            and d.get("name") == st.get("name"))


def index_data():
    """读 site/issues.js。解析不了就拒绝打包——否则会做出一个离线点不开的包。"""
    t = (SITE / "issues.js").read_text(encoding="utf-8")
    m = re.search(r"window\.AI_DAILY_ISSUES\s*=\s*(\{.*\});?\s*$", t, re.S)
    if not m:
        raise SystemExit("issues.js 解析失败，拒绝打包（离线索引会与包内容对不上）")
    return json.loads(m.group(1))


def latest_issue():
    """站点索引里最新一期正刊的期号，用来拼 versionName。"""
    mains = [x for x in index_data().get("issues", []) if not x.get("isSpecial")]
    return str(mains[0]["issue"]) if mains else "0"


def snapshot_plan():
    """要进包的站点文件 + 中文名改名表。

    离线包 = 最近 OFFLINE_KEEP 期的快照：正文 HTML、每期 json、特刊目录、
    以及 index/config/sw 这些壳。更早的期只留线上，不进包。

    version.json 必须排除：它是打包**之后**才写的更新清单，留在快照里
    会让下一轮的指纹永远变，--auto 的判重就彻底失效（每次都重打、每次
    又改一次清单，自我激励）。
    """
    data = index_data()
    mains = [x["date"] for x in data["issues"] if not x.get("isSpecial")]
    keep = set(mains[:OFFLINE_KEEP])
    files, renames = [], {}
    for p in sorted(SITE.rglob("*")):
        if not p.is_file() or p.name in ("ai-daily.apk", MANIFEST_NAME):
            continue
        rel = p.relative_to(SITE).as_posix()
        m = re.match(r"^AI晨报-(\d{4}-\d{2}-\d{2})\.(html|json)$", p.name)
        if m:
            if m.group(1) not in keep:
                continue
            renames[p.name] = "issue-%s.%s" % (m.group(1), m.group(2))
            files.append(rel)
        elif rel.startswith("special/"):
            if Path(rel).stem not in keep:
                continue
            files.append(rel)
        else:
            files.append(rel)
    return files, renames, keep


def fingerprint(files, version_name):
    """内容指纹：站点快照 + Java 源码 + manifest + 版本名。

    不含 versionCode —— 它每次打包都会变，放进去就永远不会判重。
    """
    h = hashlib.sha256()
    h.update(b"apk-v2\0")
    h.update(version_name.encode("utf-8"))
    for rel in files:
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update((SITE / rel).read_bytes())
        h.update(b"\0")
    for extra in (APK_SRC / "src" / "cn" / "aidaily" / "app" / "MainActivity.java",
                  APK_SRC / "AndroidManifest.xml"):
        h.update(extra.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def next_code(st):
    """YYMMDD*100 + 当日序号。跨天必增，同日重打也增；时钟回退时退化为 last+1。"""
    today = dt.date.today().strftime("%y%m%d")
    base = int(today) * 100
    seq = int(st.get("seq", -1)) + 1 if st.get("day") == today else 0
    code = base + seq
    last = int(st.get("code") or 0)
    if last > base + 1000000:      # 状态被改坏或来自旧方案：以日期为准，别把版本号顶死
        last = 0
    if code <= last:
        code = last + 1
        seq = max(seq, code - base)
    return code, today, seq


def site_url():
    """入口地址的唯一事实源：site/config.js 的 siteUrl。"""
    s = (SITE / "config.js").read_text(encoding="utf-8")
    m = re.search(r'\bsiteUrl\s*:\s*"([^"]*)"', s)
    url = (m.group(1).strip() if m else "")
    if not url or "__SITE_URL__" in url:
        raise SystemExit("site/config.js 的 siteUrl 还是占位符，拒绝打包")
    return url


def apk_pass():
    """签名口令不进仓库：环境变量优先，其次 ai-daily/.local/apk.json。"""
    env = os.environ.get("AI_DAILY_APK_PASS", "").strip()
    if env:
        return env
    p = LOCAL / "apk.json"
    try:
        return str(json.loads(p.read_text(encoding="utf-8"))["keystorePass"])
    except Exception:
        raise SystemExit("缺少 APK 签名口令：设 AI_DAILY_APK_PASS，"
                         "或写 ai-daily/.local/apk.json 的 keystorePass")


def gen_java():
    """把源码里的占位符换成真实入口，产物写进 .build/gen，编译那一份。"""
    url = site_url()
    host = url.split("?", 1)[0].rstrip("/") + "/"
    src = (APK_SRC / "src" / "cn" / "aidaily" / "app" / "MainActivity.java"
           ).read_text(encoding="utf-8")
    out = src.replace("__SITE_URL__", url).replace("__SITE_HOST__", host)
    if "__SITE_" in out:
        raise SystemExit("注入后仍残留占位符，说明模板被改坏了")
    gen = WORK / "gen" / "cn" / "aidaily" / "app"
    gen.mkdir(parents=True, exist_ok=True)
    dst = gen / "MainActivity.java"
    dst.write_text(out, encoding="utf-8")
    print("[0/7] 注入入口地址：%s" % host)
    return dst


def find_tools():
    """找工具链。找不到不在这里炸——交给 missing_tools() 报，好让 --auto 走 SKIP。"""
    jdk_dir = TOOLS / "jdk"
    jdk = next(jdk_dir.glob("jdk-*"), None) if jdk_dir.exists() else None
    jdk = jdk or Path("__no_jdk__")
    bt = TOOLS / "sdk" / "build-tools" / "34.0.0"
    return {
        "java": jdk / "bin" / "java.exe",
        "javac": jdk / "bin" / "javac.exe",
        "keytool": jdk / "bin" / "keytool.exe",
        "android_jar": TOOLS / "sdk" / "platforms" / "android-34" / "android.jar",
        "aapt": bt / "aapt.exe",
        "aapt2": bt / "aapt2.exe",
        "zipalign": bt / "zipalign.exe",
        "d8": bt / "lib" / "d8.jar",
        "apksigner": bt / "lib" / "apksigner.jar",
    }


def missing_tools(t):
    return [k for k, v in t.items() if not Path(v).exists()]


def run(cmd, quiet=True, optional=False):
    # Windows 控制台是 GBK，不能用 text=True 强行按 UTF-8 解码
    p = subprocess.run([str(x) for x in cmd], capture_output=True)
    out = (p.stdout or b"").decode("utf-8", "replace")
    err = (p.stderr or b"").decode("utf-8", "replace")
    if p.returncode != 0 and not optional:
        print("FAILED:", " ".join(str(x) for x in cmd))
        print(out[-3000:])
        print(err[-3000:])
        raise SystemExit(1)
    if not quiet:
        print(out[-3000:])
    class Result:
        stdout, stderr, returncode = out, err, p.returncode
    return Result()


def make_icons(res):
    from PIL import Image
    im = Image.open(SITE / "icon-512.png").convert("RGBA")
    for density, px in [("mdpi", 48), ("hdpi", 72), ("xhdpi", 96),
                        ("xxhdpi", 144), ("xxxhdpi", 192)]:
        d = res / ("mipmap-" + density)
        d.mkdir(parents=True, exist_ok=True)
        im.resize((px, px), Image.LANCZOS).save(d / "ic_launcher.png")
    print("[1/7] 图标：5 档密度 OK")


def trim_index(text, keep):
    """包内 issues.js 只留包内真有的期。

    不裁的话，离线点开被裁掉的旧期就是 404——列表说有、文件没有。
    只动 assets 里的副本，site/issues.js 本身仍然由 build_index.py 独占。
    """
    m = re.search(r"(window\.AI_DAILY_ISSUES\s*=\s*)(\{.*\})(;?\s*)$", text, re.S)
    if not m:
        return text, 0, 0
    d = json.loads(m.group(2))
    before = len(d.get("issues", []))
    d["issues"] = [x for x in d.get("issues", []) if x.get("date") in keep]
    if isinstance(d.get("specials"), list):
        d["specials"] = [x for x in d["specials"] if x.get("date") in keep]
    body = json.dumps(d, ensure_ascii=False, indent=2)
    return text[:m.start(2)] + body + text[m.end(2):], before, len(d["issues"])


def make_assets(assets):
    """把站点快照复制进 assets：递归（含 special/）、裁到最近 N 期、中文名换 ASCII。"""
    assets.mkdir(parents=True, exist_ok=True)
    files, renames, keep = snapshot_plan()
    TEXT = {".html", ".js", ".json", ".webmanifest"}
    n = 0
    for rel in files:
        src = SITE / rel
        head, _, name = rel.rpartition("/")
        dst_rel = (head + "/" if head else "") + renames.get(name, name)
        dst = assets / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() in TEXT:
            # 必须走 bytes：read_text/write_text 在 Windows 上会把 \n 翻成 \r\n，
            # 包内 HTML 会平白胖出一千多字节，快照也就不再等于站点原文。
            raw = src.read_bytes()
            for old, new in renames.items():
                raw = raw.replace(old.encode("utf-8"), new.encode("utf-8"))
            if name == "issues.js":
                txt, before, after = trim_index(raw.decode("utf-8"), keep)
                raw = txt.encode("utf-8")
                print("[2/7] 离线索引：%d 期 → %d 期（包里只放了最近 %d 期）"
                      % (before, after, OFFLINE_KEEP))
            dst.write_bytes(raw)
        else:
            shutil.copy2(src, dst)
        n += 1
    print("[2/7] 内置站点：%d 个文件（含特刊 %d 个），重命名 %d 个"
          % (n, sum(1 for f in files if f.startswith("special/")), len(renames)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="打安卓包（--auto 供出报链路自动调用）")
    ap.add_argument("--auto", action="store_true",
                    help="自动更新：内容未变就跳过；缺工具链返回 2 而不是报错")
    ap.add_argument("--force", action="store_true", help="忽略指纹，强制重打")
    ap.add_argument("--code", type=int, default=0, help="覆盖 versionCode")
    ap.add_argument("--name", default="", help="覆盖 versionName")
    a = ap.parse_args(argv)

    t = find_tools()
    miss = missing_tools(t)
    if miss:
        msg = "Android 工具链缺失（%s），目录 %s" % ("/".join(miss), TOOLS)
        if a.auto:
            print("SKIP " + msg)
            print("     出报不阻塞：APK 停在上一个版本，装了的用户仍能看线上，"
                  "只是离线兜底不更新")
            return 2
        raise SystemExit(msg)

    st = load_state()
    files, _, _ = snapshot_plan()
    issue = latest_issue()
    vname_base = a.name or ("%s.%s" % (VERSION_BASE, issue))
    # 指纹用基础名：当日序号每次打包都变，放进去就永远不会判重
    fp = fingerprint(files, vname_base)
    built = ROOT / OUT_NAME
    if (a.auto and not a.force and st.get("fingerprint") == fp
            and built.exists() and (SITE / "ai-daily.apk").exists()
            and manifest_fresh(st)):
        print("SKIP 内容未变（%s / versionCode %s），不重打"
              % (st.get("name"), st.get("code")))
        return 0

    code, day, seq = next_code(st)
    if a.code:
        code = a.code
    # 同日重打时 versionName 也要跟着变。否则出报当天重打的包会弹「有新版本
    # 1.3.004」，而用户当前装的也是 1.3.004——看起来就是误报，点一次就再也不信了。
    # 后缀只影响显示名，不参与指纹（否则天天必重打）。
    vname = vname_base if (a.name or not seq) else "%s.%d" % (vname_base, seq)
    print("版本：%s（versionCode %d）· 内置 %d 个文件 · 第 %s 期"
          % (vname, code, len(files), issue))

    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    classes = WORK / "classes"
    dexout = WORK / "dex"
    res = WORK / "res"
    assets = WORK / "assets" / "site"
    classes.mkdir()
    dexout.mkdir()
    res.mkdir()

    make_icons(res)
    make_assets(assets)

    # 占位符注入：编译 .build/gen 下的副本，源码里的 __SITE_URL__ 不进成品
    java_src = gen_java()

    # Java -> class -> classes.jar -> classes.dex
    run([t["javac"], "-source", "8", "-target", "8", "-encoding", "UTF-8",
         "-cp", t["android_jar"], "-d", classes, java_src])
    jar = WORK / "classes.jar"
    with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as z:
        for f in classes.rglob("*.class"):
            z.write(f, f.relative_to(classes).as_posix())
    run([t["java"], "-cp", t["d8"], "com.android.tools.r8.D8",
         "--lib", t["android_jar"], "--min-api", "21",
         "--output", dexout, jar])
    print("[3/7] 编译 Java + d8 生成 classes.dex OK")

    # 资源 / manifest -> 基础 APK
    flat = WORK / "res.flata"
    run([t["aapt2"], "compile", "--dir", res, "-o", flat])
    base = WORK / "base.apk"
    run([t["aapt2"], "link", "-o", base, "-I", t["android_jar"],
         "--manifest", APK_SRC / "AndroidManifest.xml", "-R", flat,
         "--min-sdk-version", "21", "--target-sdk-version", "34",
         "--version-code", str(code), "--version-name", vname])
    print("[4/7] aapt2 编译资源与 manifest OK")

    with zipfile.ZipFile(base, "a", zipfile.ZIP_DEFLATED) as z:
        z.write(dexout / "classes.dex", "classes.dex")
        for f in sorted(assets.rglob("*")):
            if f.is_file():
                z.write(f, "assets/site/" + f.relative_to(assets).as_posix())
    aligned = WORK / "aligned.apk"
    run([t["zipalign"], "-f", "4", base, aligned])
    print("[5/7] 打包 dex + assets 并对齐 OK")

    ks = TOOLS / "aidaily.keystore"
    pw = apk_pass()
    if not ks.exists():
        run([t["keytool"], "-genkeypair", "-keystore", ks,
             "-alias", "aidaily", "-keyalg", "RSA", "-keysize", "2048",
             "-validity", "10000", "-storetype", "PKCS12",
             "-storepass", pw, "-keypass", pw,
             "-dname", "CN=AI Morning Post, OU=Personal, O=AI Daily, "
                       "L=Shenzhen, ST=Guangdong, C=CN"])
    final = ROOT / OUT_NAME
    run([t["java"], "-jar", t["apksigner"], "sign",
         "--ks", ks, "--ks-key-alias", "aidaily",
         "--ks-pass", "pass:" + pw, "--key-pass", "pass:" + pw,
         "--v1-signing-enabled", "true", "--v2-signing-enabled", "true",
         "--out", final, aligned])
    print("[6/7] 签名 OK")

    v = run([t["java"], "-jar", t["apksigner"], "verify", "--verbose", final])
    print("[7/7] 验签：")
    for line in v.stdout.splitlines():
        if "Verifies" in line or "signature" in line.lower():
            print("   ", line.strip())
    bad = run([t["aapt"], "dump", "badging", final], optional=True)
    for line in bad.stdout.splitlines():
        if line.startswith("package:") or "application-label" in line or "launchable-activity" in line:
            print("   ", line.strip())

    shutil.copy2(final, SITE / "ai-daily.apk")
    sha = hashlib.sha256(final.read_bytes()).hexdigest()
    size = final.stat().st_size
    mb = size / 1048576
    state = {
        "code": code, "name": vname, "day": day, "seq": seq,
        "fingerprint": fp, "sha256": sha, "bytes": size,
        "files": len(files), "issue": issue,
        "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_state(state)
    write_manifest(state)
    print("\n=== APK 就绪 ===")
    print("版本 :", "%s / versionCode %d" % (vname, code))
    print("文件 :", final)
    print("大小 :", "%.2f MB（内置 %d 个文件）" % (mb, len(files)))
    print("SHA256:", sha)
    print("更新清单:", SITE / MANIFEST_NAME)
    print("线上副本:", SITE / "ai-daily.apk")
    if mb > MAX_MB:
        print("⚠ 体积超过 %.1f MB：把 OFFLINE_KEEP（现为 %d）调小，"
              "或清理 site/ 里不再需要的静态资源" % (MAX_MB, OFFLINE_KEEP))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
