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

from PIL import Image

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
        raise RuntimeError("PrintWindow failed")

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
    return user32.GetParent(widget.winfo_id())


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
clean_edges(capture(window_handle(root))).save(
    os.path.join(DOCS, "screenshot-complete.png"), optimize=True)
print("saved screenshot-complete.png")

root.destroy()
print("done")
