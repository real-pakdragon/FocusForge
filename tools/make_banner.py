"""Generate the README hero banner."""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import app as ff  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
os.makedirs(DOCS, exist_ok=True)

W, H = 1280, 420


def font(names, size):
    for name in names:
        path = os.path.join(FONTS, name)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def tracked(draw, xy, text, f, fill, tracking=0):
    widths = [draw.textlength(ch, font=f) for ch in text]
    total = sum(widths) + tracking * max(0, len(text) - 1)
    x = xy[0] - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, xy[1]), ch, font=f, fill=fill)
        x += w + tracking
    return total


def gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", (w, h), top)
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=ff.mix(top, bottom, y / max(1, h - 1)))
    return img


bg = gradient((W, H), (8, 12, 18), (11, 20, 30)).convert("RGBA")

# ambient glow behind the ring
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse((W - 470, -110, W + 170, 530), fill=(40, 120, 255, 90))
gd.ellipse((-220, 250, 380, 620), fill=(34, 211, 238, 40))
glow = glow.filter(ff.ImageFilter.GaussianBlur(70))
bg = Image.alpha_composite(bg, glow)

# faint grid dots
dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
dd = ImageDraw.Draw(dots)
for y in range(20, H, 34):
    for x in range(20, W, 34):
        dd.ellipse((x, y, x + 2, y + 2), fill=(70, 110, 160, 60))
bg = Image.alpha_composite(bg, dots)

# ring on the right
ring = ff.render_ring(330, 0.74)
bg.paste(ring, (W - 405, 46), ring)

d = ImageDraw.Draw(bg)

# logo badge
logo = ff.make_logo(74)
bg.paste(logo, (80, 78), logo)

f_name = font(["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"], 62)
f_tag = font(["segoeui.ttf", "arial.ttf"], 17)
f_small = font(["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"], 11)

# wordmark with a soft gradient fill
name = "FOCUSFORGE"
NAME_H = 100
name_mask = Image.new("L", (W, NAME_H), 0)
ImageDraw.Draw(name_mask).text((80, -4), name, font=f_name, fill=255)
grad = gradient((W, NAME_H), (255, 255, 255), (150, 205, 255))
bg.paste(grad, (0, 176), name_mask)

d = ImageDraw.Draw(bg)
tracked(d, (80 + 3, 258), "DEEP WORK TIMER", f_tag, (120, 175, 230), 6)

d.text((80, 300), "Pause & resume", font=f_small, fill=(150, 175, 205))
d.text((205, 300), "·", font=f_small, fill=(70, 90, 115))
d.text((220, 300), "24h challenges", font=f_small, fill=(150, 175, 205))
d.text((345, 300), "·", font=f_small, fill=(70, 90, 115))
d.text((360, 300), "streaks", font=f_small, fill=(150, 175, 205))
d.text((432, 300), "·", font=f_small, fill=(70, 90, 115))
d.text((447, 300), "keep awake", font=f_small, fill=(150, 175, 205))

d.text((80, 336), "Windows 10 / 11   ·   Free & open source   ·   MIT", font=f_small, fill=(92, 110, 134))

# hairline accents
d.line([(80, 372), (380, 372)], fill=(40, 70, 110), width=1)
d.line([(392, 372), (430, 372)], fill=(76, 141, 255), width=2)

out = os.path.join(DOCS, "banner.png")
bg.convert("RGB").save(out, optimize=True)
print("wrote", out, bg.size)
