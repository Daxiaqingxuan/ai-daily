# -*- coding: utf-8 -*-
"""生成手机入口二维码卡片：python tools/make_qr.py <分享链接> [输出png]"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import qrcode

url = sys.argv[1]
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "AI晨报-手机入口.png"
title = sys.argv[3] if len(sys.argv) > 3 else "AI 晨报 · 手机入口"
line1 = sys.argv[4] if len(sys.argv) > 4 else "手机相机扫码打开 → 添加到主屏幕"
line2 = sys.argv[5] if len(sys.argv) > 5 else "以后点图标，直接看今天的晨报与全部往期"

qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=11, border=2)
qr.add_data(url)
qr.make(fit=True)
code = qr.make_image(fill_color="#1b1a17", back_color="#fbf8f0").convert("RGB")

PAPER, INK, RED, MUTED = "#fbf8f0", "#1b1a17", "#8c1d18", "#6d6a60"
W = code.width + 76
H = code.height + 250
card = Image.new("RGB", (W, H), PAPER)
d = ImageDraw.Draw(card)
d.rectangle([22, 22, W - 23, H - 23], outline=INK, width=3)

f_big = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 32)
f_mid = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 17)
f_sml = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)
d.text((W / 2, 70), title, font=f_big, fill=INK, anchor="mm")
d.rectangle([W / 2 - 46, 100, W / 2 + 46, 104], fill=RED)
card.paste(code, (38, 122))
y = 122 + code.height
d.text((W / 2, y + 40), line1, font=f_mid, fill=INK, anchor="mm")
d.text((W / 2, y + 74), line2, font=f_sml, fill=MUTED, anchor="mm")

card.save(out)
print("[make_qr] 二维码卡片 ->", out, "|", url)
