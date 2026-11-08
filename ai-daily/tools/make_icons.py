# -*- coding: utf-8 -*-
"""生成 AI 晨报的桌面 / PWA 图标（报纸风：米黄纸 + 红色报头 + 墨线版面）"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SITE = Path(__file__).resolve().parent.parent / "site"
S = 512
PAPER = "#fbf8f0"
INK = "#1b1a17"
RED = "#8c1d18"
RULE = "#cfc8b6"

FONT_DIR = Path("C:/Windows/Fonts")
serif_b = FONT_DIR / "georgiab.ttf"
sans_b = FONT_DIR / "msyhbd.ttc"

def font(path, size):
    return ImageFont.truetype(str(path), size)

img = Image.new("RGB", (S, S), PAPER)
d = ImageDraw.Draw(img)

# 纸面卡片（maskable 安全区：内容收在中央 ~78%）
d.rounded_rectangle([46, 46, 466, 466], radius=26, fill=PAPER, outline=INK, width=7)
d.rectangle([60, 60, 452, 74], fill=RED)          # 报头红条
d.line([78, 92, 434, 92], fill=INK, width=3)      # 报头墨线

# 大号 AI
f_ai = font(serif_b, 176)
d.text((256, 196), "AI", font=f_ai, fill=RED, anchor="mm")

# 中文报名
f_cn = font(sans_b, 58)
d.text((256, 302), "晨  报", font=f_cn, fill=INK, anchor="mm")
d.line([132, 338, 380, 338], fill=RULE, width=2)

# 版面墨线
for y in (366, 392, 418):
    d.line([110, y, 402, y], fill=RULE, width=5)
d.rectangle([110, 366, 176, 370], fill=RED)

SITE.mkdir(parents=True, exist_ok=True)
img.save(SITE / "icon-512.png")
img.resize((192, 192), Image.LANCZOS).save(SITE / "icon-192.png")
img.resize((180, 180), Image.LANCZOS).save(SITE / "apple-touch-icon.png")
img.save(SITE / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])
print("[make_icons] 已生成 icon-512/192、apple-touch-icon、favicon.ico ->", SITE)
