"""Regenerate the README screenshots from the real UI.

Runs the app in demo mode against a throwaway profile, poses a few states and
captures each window with PrintWindow, so the docs always match the app.

    python tools/make_screenshots.py
"""

import ctypes
import os
import sys
import tempfile
import time
from ctypes import wintypes

from PIL import Image, ImageDraw, ImageFilter, ImageGrab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

# keep demo runs away from the real profile
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="focusforge-shots-")

import app as ff  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
os.makedirs(DOCS, exist_ok=True)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def capture(hwnd: int) -> Image.Image:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc_win = user32.GetWindowDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    gdi32.SelectObject(hdc_mem, hbmp)
    ok = user32.PrintWindow(hwnd, hdc_mem, 2)
    if not ok:
        # overrideredirect windows do not always respond to PrintWindow
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_win, 0, 0, 0x00CC0020)

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_win)

    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
    return img.convert("RGB")


def window_handle(widget) -> int:
    hwnd = user32.GetParent(widget.winfo_id())
    return hwnd or widget.winfo_id()


def grab_window(hwnd: int) -> Image.Image:
    """Screen-grab the window rectangle (reliable for borderless windows)."""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))


def make_widget_shot(pill: Image.Image) -> Image.Image:
    """Mock a study desktop with the floating mini timer in the corner."""
    W, H = 1000, 340
    bg = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    d = ImageDraw.Draw(bg)
    top, bottom = (8, 12, 18), (11, 20, 30)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=ff.mix(top, bottom, y / (H - 1)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((W - 420, -150, W + 90, 250), fill=(40, 120, 255, 80))
    gd.ellipse((-160, 180, 360, 520), fill=(34, 211, 238, 32))
    bg = Image.alpha_composite(bg, glow.filter(ImageFilter.GaussianBlur(70)))
    d = ImageDraw.Draw(bg)

    # faint dot grid, like a desktop wallpaper
    for y in range(16, H, 28):
        for x in range(16, W, 28):
            d.ellipse((x, y, x + 2, y + 2), fill=(70, 110, 160, 45))

    # two study documents sitting behind the floating timer
    def page(box, title_w):
        d.rounded_rectangle(box, radius=16, fill=(15, 22, 31, 255),
                            outline=(29, 41, 57, 255), width=1)
        x0, y0, x1, y1 = box
        d.rounded_rectangle((x0 + 26, y0 + 26, x0 + 26 + title_w, y0 + 36),
                            radius=5, fill=(73, 134, 226, 255))
        y = y0 + 58
        while y < y1 - 24:
            w = int((x1 - x0 - 52) * (0.62 if y % 3 == 0 else 0.92))
            d.rounded_rectangle((x0 + 26, y, x0 + 26 + w, y + 6),
                                radius=3, fill=(33, 46, 63, 255))
            y += 18

    page((38, 52, 566, 312), 168)
    page((606, 118, 962, 326), 120)

    # drop shadow + rounded mask so the widget melts into the wallpaper
    w, h = pill.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1),
                                           radius=max(8, int(min(w, h) * 0.26)), fill=255)
    pill = pill.convert("RGBA")
    pill.putalpha(mask)
    x, y = W - w - 38, 28
    shadow = Image.new("RGBA", (w + 80, h + 80), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((40, 40, 40 + w, 40 + h),
                                             radius=18, fill=(0, 0, 0, 150))
    bg.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)), (x - 40, y - 34))
    bg.alpha_composite(pill, (x, y))
    return bg.convert("RGB")


def pump(root, seconds=0.6):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def clean_edges(img: Image.Image, band: int = 14) -> Image.Image:
    """Replace the black DWM shadow fringe with the app background."""
    px = img.load()
    bg = ff.hex_rgb(ff.BG)
    w, h = img.size
    for y in range(h):
        for x in range(w):
            if (x < band or x >= w - band or y < band or y >= h - band) and px[x, y] == (0, 0, 0):
                px[x, y] = bg
    # scrub a light DWM title bar (it should be dark, but Windows can reset it)
    for y in range(min(40, h)):
        row = [px[x, y] for x in range(0, w, 4)]
        if sum(1 for c in row if min(c) > 200) > len(row) * 0.5:
            for x in range(w):
                px[x, y] = bg
    return img


def trim_square(img: Image.Image, out_size: int = 900) -> Image.Image:
    """Crop a fullscreen capture to a centred square around the ring."""
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    box = (left, 0, left + side, side)
    return img.crop(box).resize((out_size, out_size), Image.LANCZOS)


ff._enable_dpi_awareness()
root = ff.tk.Tk()
app = ff.FocusForge(root, demo=True)
app._beep = lambda notes: None  # keep the docs run quiet
pump(root, 1.4)

# 1) main window, mid challenge ------------------------------------------------
clean_edges(capture(window_handle(root))).save(
    os.path.join(DOCS, "screenshot.png"), optimize=True)
print("saved screenshot.png")

# 2) fullscreen focus mode ------------------------------------------------------
app._toggle_focus_mode()
pump(root, 1.6)
shot = capture(window_handle(root))
trim_square(shot).save(os.path.join(DOCS, "screenshot-focus.png"), optimize=True)
print("saved screenshot-focus.png", shot.size)
app._toggle_focus_mode()
pump(root, 1.2)

# 3) finished challenge with confetti -------------------------------------------
app.target = 24 * 3600
app.elapsed = float(app.target)
app._complete()
pump(root, 0.45)
ff.set_dark_title_bar(root)
pump(root, 0.2)
clean_edges(capture(window_handle(root))).save(
    os.path.join(DOCS, "screenshot-complete.png"), optimize=True)
print("saved screenshot-complete.png")

# 4) automatic five minute rest timer -------------------------------------------
app.start_break()
app.break_elapsed = 2 * 60          # pose it mid-break for the docs image
app.break_started_at = time.monotonic() - app.break_elapsed
app._last_render_key = None
pump(root, 1.0)
clean_edges(capture(window_handle(root))).save(
    os.path.join(DOCS, "screenshot-break.png"), optimize=True)
print("saved screenshot-break.png")

# 5) mini widget floating over a mock study desktop ------------------------------
app._enter_widget_mode()
pump(root, 0.9)
pill = grab_window(window_handle(app._widget))
app._exit_widget_mode()
pump(root, 0.6)
make_widget_shot(pill).save(os.path.join(DOCS, "screenshot-widget.png"), optimize=True)
print("saved screenshot-widget.png", pill.size)

root.destroy()
print("done")
