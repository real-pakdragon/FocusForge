"""Generate the bitmaps used by the Inno Setup wizard (big + small images)."""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import app as ff  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")

BG_TOP = (9, 13, 19)
BG_BOTTOM = (13, 22, 33)


def load_font(names, size):
    for name in names:
        path = os.path.join(FONTS, name)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def spaced_text(draw, xy, text, font, fill, tracking=0):
    """Draw text with extra letter spacing, centered on x."""
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = xy[0] - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, xy[1]), ch, font=font, fill=fill)
        x += w + tracking


def gradient_canvas(w, h):
    img = Image.new("RGB", (w, h), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=ff.mix(BG_TOP, BG_BOTTOM, y / max(1, h - 1)))
    return img


def make_large():
    w, h = 164, 314
    img = gradient_canvas(w, h).convert("RGBA")

    # soft accent glow in the lower half
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((w / 2 - 90, 150, w / 2 + 90, 300), fill=(40, 120, 255, 60))
    glow = glow.filter(ff.ImageFilter.GaussianBlur(28))
    img = Image.alpha_composite(img, glow)

    d = ImageDraw.Draw(img)
    logo = ff.make_logo(56)
    img.paste(logo, (w // 2 - 28, 30), logo)

    f_title = load_font(["seguisb.ttf", "segoeui.ttf", "arialbd.ttf"], 15)
    f_sub = load_font(["seguisb.ttf", "segoeui.ttf", "arial.ttf"], 6)
    f_foot = load_font(["segoeui.ttf", "arial.ttf"], 7)

    spaced_text(d, (w / 2, 100), "FOCUSFORGE", f_title, (234, 242, 255), 0)
    spaced_text(d, (w / 2, 124), "DEEP WORK TIMER", f_sub, (110, 145, 190), 2)

    ring = ff.render_ring(104, 0.68)
    img.paste(ring, (w // 2 - 52, 152), ring)

    d = ImageDraw.Draw(img)
    spaced_text(d, (w / 2, 276), "24 HOUR CHALLENGES", f_sub, (90, 190, 220), 1)
    spaced_text(d, (w / 2, 294), "v1.0.0  ·  MIT", f_foot, (78, 92, 112), 1)

    return img.convert("RGB")


def make_small():
    size = 55
    img = Image.new("RGB", (size, size), BG_TOP)
    logo = ff.make_logo(43)
    img.paste(logo, ((size - 43) // 2, (size - 43) // 2), logo)
    return img


large = make_large()
large.save(os.path.join(ASSETS, "installer-large.bmp"), "BMP")

small = make_small()
small.save(os.path.join(ASSETS, "installer-small.bmp"), "BMP")

print("wrote", os.path.join(ASSETS, "installer-large.bmp"), large.size)
print("wrote", os.path.join(ASSETS, "installer-small.bmp"), small.size)
