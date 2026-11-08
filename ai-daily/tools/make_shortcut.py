"""生成 Windows 独立窗口快捷方式（.lnk），不需要 COM / WScript。

直接写 Shell Link 二进制。IDList / LinkInfo 借用系统自带的
「Microsoft Edge.lnk」原生文件（目标正是 msedge.exe），
再把命令行参数换成 --app=file:///...，双击即为无地址栏的独立窗口。
"""
import os
import shutil
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SITE = ROOT / "site"

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
if not EDGE.exists():
    EDGE = Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")

TEMPLATE = Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Microsoft Edge.lnk")


def wide(s):
    """StringData：字符数(2B) + UTF-16LE 文本"""
    raw = s.encode("utf-16-le")
    return struct.pack("<H", len(raw) // 2) + raw


def native_head():
    """取原生 .lnk 的 ShellLinkHeader + IDList + LinkInfo（目标 = msedge.exe）"""
    b = TEMPLATE.read_bytes()
    pos = 76
    n = struct.unpack_from("<H", b, pos)[0]
    pos += 2 + n                                   # LinkTargetIDList
    li_size = struct.unpack_from("<I", b, pos)[0]
    pos += li_size                                 # LinkInfo
    head = bytearray(b[:pos])

    # IDList | LinkInfo | Name | WorkingDir | Arguments | IconLocation | Unicode
    flags = 0x01 | 0x02 | 0x04 | 0x10 | 0x20 | 0x40 | 0x80
    struct.pack_into("<I", head, 20, flags)
    struct.pack_into("<i", head, 56, 0)            # IconIndex
    return bytes(head)


def main():
    site = SITE.resolve()
    icon = site / "favicon.ico"
    url = "file:///" + (site / "index.html").as_posix()
    args = (f"--app={url} --window-size=1180,880 "
            "--no-first-run --no-default-browser-check")

    data = native_head()
    data += wide("AI 晨报 · 今日报纸与往期")
    data += wide(str(site))
    data += wide(args)
    data += wide(str(icon))
    data += struct.pack("<I", 0)                   # ExtraData 终止块

    desktop = Path(os.environ["USERPROFILE"]) / "Desktop"
    lnk = desktop / "AI 晨报.lnk"
    lnk.write_bytes(data)
    print("created :", lnk, len(data), "bytes")
    print("target  :", EDGE)
    print("args    :", args)
    print("icon    :", icon)

    # 旧版浏览器式 .url 收进工程目录留档，桌面只留一个入口
    # 桌面(C:) 与工程(D:) 不同分区，os.replace 会报错，故先复制再移除
    old = desktop / "AI 晨报.url"
    if old.exists():
        backup = ROOT / "AI晨报-桌面入口-浏览器版备份.url"
        shutil.copy2(old, backup)
        old.unlink()
        print("archived:", backup)


if __name__ == "__main__":
    main()
