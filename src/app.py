"""FocusForge - a deep work / study challenge timer for Windows.

A single-file tkinter application with a custom rendered UI:
  * circular progress ring with gradient + glow
  * pause / resume, reset, +5 min, custom durations (25m .. 24h)
  * automatic 5 minute rest timer after a finished challenge
  * manual 5 / 10 / 15 minute breaks that pause and resume the session
  * live stats (today, streak, sessions), persisted to %APPDATA%
  * always-on-top and keep-awake toggles
  * fullscreen focus mode, keyboard shortcuts, firework finish (sound + confetti)
"""

from __future__ import annotations

import array
import ctypes
import json
import math
import os
import random
import struct
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

try:
    import winsound
except Exception:  # pragma: no cover - non Windows
    winsound = None

APP_NAME = "FocusForge"
VERSION = "1.2.0"
DATA_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
DATA_FILE = DATA_DIR / "stats.json"

# ---------------------------------------------------------------- palette ---
BG = "#090D13"
BG_SOFT = "#0C1219"
CARD = "#111A24"
CARD_2 = "#16212E"
STROKE = "#1E2B3A"
TEXT = "#EAF2FF"
MUTED = "#7E90A8"
DIM = "#54657C"
ACCENT = "#4C8DFF"
ACCENT_HOVER = "#6BA3FF"
ACCENT_PRESS = "#3C74DB"
CYAN = "#22D3EE"
MINT = "#34D399"
AMBER = "#F5B54A"
ROSE = "#F2647C"
VIOLET = "#A78BFA"

PRESETS = [
    (25, "25m"),
    (60, "1h"),
    (120, "2h"),
    (240, "4h"),
    (360, "6h"),
    (720, "12h"),
    (1440, "24h"),
]

MILESTONES = [
    (25, "25%  -  WARMED UP"),
    (50, "HALFWAY THERE"),
    (75, "75%  -  HOME STRETCH"),
    (90, "ALMOST DONE"),
]

# default rest length; the REST button also offers the other choices
BREAK_SECONDS = 5 * 60
REST_CHOICES = (5, 10, 15)
# the finish firework always plays in full before the rest timer takes over
BREAK_SETTLE_MS = 1200      # quiet beat after the confetti has landed
BREAK_FALLBACK_MS = 9000    # safety net if the celebration cannot animate

RING_PALETTES = {
    "focus": [(0.0, (76, 141, 255)), (0.55, (34, 211, 238)), (1.0, (52, 211, 153))],
    "break": [(0.0, (52, 211, 153)), (0.50, (34, 211, 238)), (1.0, (167, 139, 250))],
}
RING_STOPS = RING_PALETTES["focus"]

S_BASE_W = 470
S_BASE_H = 792

_IMAGE_CACHE: dict[tuple, ImageTk.PhotoImage] = {}


# ---------------------------------------------------------------- helpers ---
def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), rel)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_hex(c: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % c


def mix(c1, c2, t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))  # type: ignore[return-value]


def lerp_stops(stops, t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if t <= p1:
            k = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            return mix(c0, c1, k)
    return stops[-1][1]


def fmt_hms(seconds: float) -> str:
    seconds = max(0, int(math.ceil(seconds - 1e-9)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def fmt_compact(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)}m"
    hours = seconds / 3600
    if hours < 10:
        return f"{hours:.1f}h"
    return f"{int(hours)}h"


def rounded_image(
    w: int,
    h: int,
    r: int,
    fill: str | None = None,
    outline: str | None = None,
    ow: int = 1,
    ss: int = 3,
) -> Image.Image:
    W, H, R = max(1, w * ss), max(1, h * ss), max(0, r * ss)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if outline:
        d.rounded_rectangle(
            (0, 0, W - 1, H - 1),
            radius=R,
            fill=fill,
            outline=outline,
            width=max(1, ow * ss),
        )
    else:
        d.rounded_rectangle((0, 0, W - 1, H - 1), radius=R, fill=fill)
    return img.resize((w, h), Image.LANCZOS)


def cached_rounded(w, h, r, fill, outline=None, ow=1) -> ImageTk.PhotoImage:
    key = (w, h, r, fill, outline, ow)
    img = _IMAGE_CACHE.get(key)
    if img is None:
        img = ImageTk.PhotoImage(rounded_image(w, h, r, fill, outline, ow))
        _IMAGE_CACHE[key] = img
    return img


_GRAD_GRID: dict[str, Image.Image] = {}
_GRAD_CACHE: dict[tuple[str, int], Image.Image] = {}
_RING_CACHE: dict[tuple[str, int], dict] = {}
_ALPHA_HALF = [int(v * 0.50) for v in range(256)]


def ring_gradient(size: int, palette: str = "focus") -> Image.Image:
    """Cached vertical gradient for the given ring palette."""
    key = (palette, size)
    cached = _GRAD_CACHE.get(key)
    if cached is not None:
        return cached
    grid = _GRAD_GRID.get(palette)
    if grid is None:
        stops = RING_PALETTES[palette]
        base = Image.linear_gradient("L")
        luts = [
            [lerp_stops(stops, v / 255.0)[ch] for v in range(256)] for ch in range(3)
        ]
        grid = Image.merge("RGB", tuple(base.point(lut) for lut in luts))
        _GRAD_GRID[palette] = grid
    grad = grid.resize((size, size), Image.BILINEAR)
    _GRAD_CACHE[key] = grad
    if len(_GRAD_CACHE) > 24:
        _GRAD_CACHE.pop(next(iter(_GRAD_CACHE)))
    return grad


def _ring_assets(diameter: int, palette: str = "focus") -> dict:
    key = (palette, diameter)
    assets = _RING_CACHE.get(key)
    if assets is not None:
        return assets
    ss = max(1.0, min(2.0, 900.0 / diameter))
    S = int(diameter * ss)
    pad = max(3, int(S * 0.042))
    w = max(4, int(S * 0.040))
    box = (pad, pad, S - pad - 1, S - pad - 1)

    track_hi = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(track_hi).ellipse(box, outline=hex_rgb(STROKE), width=w)
    track = track_hi.resize((diameter, diameter), Image.LANCZOS) if S != diameter else track_hi

    annulus = Image.new("L", (S, S), 0)
    ad = ImageDraw.Draw(annulus)
    ad.ellipse(box, fill=255)
    ad.ellipse((pad + w, pad + w, S - pad - 1 - w, S - pad - 1 - w), fill=0)

    stops = RING_PALETTES[palette]
    assets = {
        "S": S,
        "pad": pad,
        "w": w,
        "box": box,
        "track": track,
        "annulus": annulus,
        "grad": ring_gradient(diameter, palette),
        "glow_rgb": mix(stops[0][1], stops[-1][1], 0.45),
        "glow_size": max(12, diameter // 2),
    }
    _RING_CACHE[key] = assets
    if len(_RING_CACHE) > 8:
        _RING_CACHE.pop(next(iter(_RING_CACHE)))
    return assets


def render_ring(diameter: int, frac: float, palette: str = "focus") -> Image.Image:
    """Anti-aliased progress ring with a soft glow, drawn with Pillow."""
    diameter = max(48, int(diameter))
    a = _ring_assets(diameter, palette)
    S, pad, w, box = a["S"], a["pad"], a["w"], a["box"]
    out = a["track"].copy()

    frac = max(0.0, min(1.0, frac))
    if frac <= 0.0006:
        return out

    total = frac * 360.0
    wheel = Image.new("L", (S, S), 0)
    ImageDraw.Draw(wheel).pieslice(box, -90.0, -90.0 + total, fill=255)
    mask = ImageChops.multiply(wheel, a["annulus"])

    # rounded end caps (drawn on the supersampled mask)
    cx = cy = S / 2.0
    rad = (S - 2 * pad) / 2.0 - w / 2.0
    md = ImageDraw.Draw(mask)
    for ang in (-90.0, -90.0 + total):
        x = cx + rad * math.cos(math.radians(ang))
        y = cy + rad * math.sin(math.radians(ang))
        md.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=255)

    mask = mask.resize((diameter, diameter), Image.LANCZOS) if S != diameter else mask
    layer = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    layer.paste(a["grad"], (0, 0), mask)
    out = Image.alpha_composite(out, layer)

    # cheap glow: blur a small copy of the mask, upscale, composite underneath
    g = a["glow_size"]
    small = mask.resize((g, g), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3))
    glow_mask = small.point(_ALPHA_HALF).resize((diameter, diameter), Image.BILINEAR)
    glow = Image.new("RGBA", (diameter, diameter), (*a["glow_rgb"], 255))
    glow.putalpha(glow_mask)
    return Image.alpha_composite(glow, out)


def make_logo(size: int) -> Image.Image:
    ss = 4
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.30), fill=hex_rgb(ACCENT))
    # vertical gradient overlay
    grad = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    c0, c1 = hex_rgb(ACCENT), hex_rgb(CYAN)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=(*mix(c0, c1, y / max(1, S - 1)), 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.30), fill=255)
    img.paste(grad, (0, 0), mask)
    # lightning bolt
    pts = [(0.555, 0.10), (0.285, 0.555), (0.465, 0.555), (0.425, 0.90), (0.715, 0.435), (0.525, 0.435)]
    d.polygon([(x * S, y * S) for x, y in pts], fill=(255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


def flash_taskbar(hwnd: int) -> None:
    if sys.platform != "win32" or not hwnd:
        return
    try:
        class FLASHWINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("hwnd", ctypes.c_void_p),
                ("dwFlags", ctypes.c_uint),
                ("uCount", ctypes.c_uint),
                ("dwTimeout", ctypes.c_uint),
            ]

        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x00000003 | 0x0000000C, 6, 0)
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


def set_dark_title_bar(root: tk.Tk) -> None:
    if sys.platform != "win32":
        return
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
            )
            if res == 0:
                break
    except Exception:
        pass


def keep_awake(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002
    try:
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED if enabled else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass


# ----------------------------------------------------------------- sound ----
# The finish sound is synthesised here instead of shipping a .wav: a launch
# whistle, a low boom, a sprinkling of crackle and a long sparkle tail. It is
# built once in a background thread so the first completion never stutters.
_SR = 44100
_SND_LOCK = threading.Lock()
_FIREWORK_WAV: bytes | None = None
_CHIME_WAV: bytes | None = None


def _pcm_wav(samples, rate: int = _SR) -> bytes:
    pcm = array.array("h", (max(-32767, min(32767, int(v * 32767))) for v in samples))
    if sys.byteorder != "little":
        pcm.byteswap()
    data = pcm.tobytes()
    header = (
        b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data" + struct.pack("<I", len(data))
    )
    return header + data


def build_firework_wav() -> bytes:
    """A firework: rising whistle, deep boom, crackling sparks, fading shimmer."""
    rate = _SR
    dur = 3.0
    n = int(rate * dur)
    rnd = random.Random(20261108)
    out = [0.0] * n

    # rising launch whistle
    phase = 0.0
    launch = int(0.55 * rate)
    for i in range(launch):
        t = i / rate
        freq = 620.0 + 1250.0 * (t / 0.55) ** 0.7
        phase += 2.0 * math.pi * freq / rate
        env = min(1.0, t / 0.06) * max(0.0, 1.0 - (t / 0.55) ** 3)
        out[i] += 0.09 * env * math.sin(phase)

    # boom: low-passed noise burst + sub thump + sharp crack on impact
    start = int(0.50 * rate)
    lp = 0.0
    a = 0.16
    for i in range(start, n):
        t = (i - start) / rate
        if t > 2.0:
            break
        noise = rnd.uniform(-1.0, 1.0)
        lp += a * (noise - lp)
        body = lp * 1.35 * math.exp(-t / 0.32)
        thump = math.sin(2.0 * math.pi * 55.0 * t) * math.exp(-t / 0.45) * 0.55
        crack = noise * math.exp(-t / 0.012) * 0.35
        out[i] += body + thump + crack

    # crackle: sparse high-passed pops that thin out over time
    t0, t1 = 0.55, 2.75
    for _ in range(130):
        at = rnd.uniform(t0, t1)
        s = int(at * rate)
        if s >= n:
            continue
        length = int(rnd.uniform(0.003, 0.012) * rate)
        amp = rnd.uniform(0.05, 0.30) * (1.0 - (at - t0) / (t1 - t0)) ** 1.2
        prev = 0.0
        for j in range(length):
            if s + j >= n:
                break
            x = rnd.uniform(-1.0, 1.0)
            out[s + j] += (x - prev) * amp * (1.0 - j / length) ** 2
            prev = x

    # shimmering sparkle tail
    prev = 0.0
    base = int(0.45 * rate)
    for i in range(base, n):
        t = (i - base) / rate
        x = rnd.uniform(-1.0, 1.0)
        out[i] += (x - prev) * 0.14 * math.exp(-t / 0.85)
        prev = x

    peak = max(1e-9, max(abs(v) for v in out))
    gain = 0.92 / peak
    fade = int(0.008 * rate)
    tail = int(0.30 * rate)
    for i in range(n):
        v = out[i] * gain
        if i < fade:
            v *= i / fade
        if i >= n - tail:
            v *= (n - i) / tail
        out[i] = math.tanh(v * 1.2) * 0.95
    return _pcm_wav(out, rate)


def build_chime_wav() -> bytes:
    """Soft three note chime for the end of a rest break."""
    rate = _SR
    dur = 1.6
    n = int(rate * dur)
    out = [0.0] * n
    for freq, at, decay, amp in (
        (659.25, 0.00, 0.55, 0.30),
        (987.77, 0.16, 0.65, 0.24),
        (1318.51, 0.32, 0.85, 0.15),
    ):
        s = int(at * rate)
        for i in range(s, n):
            t = (i - s) / rate
            env = math.exp(-t / decay) * min(1.0, t / 0.004)
            out[i] += amp * env * (
                math.sin(2.0 * math.pi * freq * t)
                + 0.25 * math.sin(4.0 * math.pi * freq * t)
            )
    peak = max(1e-9, max(abs(v) for v in out))
    gain = 0.55 / peak
    tail = int(0.25 * rate)
    for i in range(n):
        v = out[i] * gain
        if i >= n - tail:
            v *= (n - i) / tail
        out[i] = v
    return _pcm_wav(out, rate)


def preload_sounds() -> None:
    global _FIREWORK_WAV, _CHIME_WAV
    if _FIREWORK_WAV is not None and _CHIME_WAV is not None:
        return
    with _SND_LOCK:
        if _FIREWORK_WAV is None:
            _FIREWORK_WAV = build_firework_wav()
        if _CHIME_WAV is None:
            _CHIME_WAV = build_chime_wav()


def _play_wav(data: bytes | None) -> None:
    if not winsound or not data:
        return
    try:
        winsound.PlaySound(
            data, winsound.SND_MEMORY | winsound.SND_ASYNC | winsound.SND_NODEFAULT
        )
    except Exception:
        pass


def play_firework() -> None:
    global _FIREWORK_WAV
    if not winsound:
        return
    if _FIREWORK_WAV is None:
        preload_sounds()
    _play_wav(_FIREWORK_WAV)


def play_chime() -> None:
    global _CHIME_WAV
    if not winsound:
        return
    if _CHIME_WAV is None:
        preload_sounds()
    _play_wav(_CHIME_WAV)


# ---------------------------------------------------------------- widgets ---
class Pill(tk.Canvas):
    """Flat, rounded, hover-aware button / chip drawn with Pillow images."""

    STYLES = {
        "primary": {"fill": ACCENT, "text": "#FFFFFF", "hover": ACCENT_HOVER, "press": ACCENT_PRESS, "outline": None, "ow": 0},
        "ghost": {"fill": CARD, "text": TEXT, "hover": CARD_2, "press": "#0D141D", "outline": STROKE, "ow": 1},
        "chip": {"fill": BG_SOFT, "text": MUTED, "hover": CARD, "press": CARD, "outline": STROKE, "ow": 1},
        "chip_on": {"fill": "#17324F", "text": "#CCE1FF", "hover": "#1B3A5B", "press": "#132A42", "outline": "#3E7BD4", "ow": 1},
        "toggle": {"fill": CARD, "text": MUTED, "hover": CARD_2, "press": CARD, "outline": STROKE, "ow": 1},
        "toggle_blue": {"fill": "#122A3D", "text": "#8FC4FF", "hover": "#16334A", "press": "#0F2434", "outline": "#2C5D8F", "ow": 1},
        "toggle_mint": {"fill": "#102B24", "text": "#8AF0C9", "hover": "#13342C", "press": "#0D241E", "outline": "#1F6B54", "ow": 1},
        "break_btn": {"fill": "#2FD399", "text": "#04231A", "hover": "#4BE0AC", "press": "#23BC86", "outline": None, "ow": 0},
    }

    def __init__(self, master, text, command=None, w=100, h=38, radius=12,
                 style="ghost", font=("Segoe UI Semibold", -12), bg=None):
        self._parent_bg = bg or master.cget("bg")
        super().__init__(master, width=w, height=h, bg=self._parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.w, self.h = w, h
        self.radius = radius
        self.font = font
        self.style_name = style
        self.command = command
        self._hover = False
        self._pressed = False
        self._disabled = False
        self._img_item = self.create_image(0, 0, anchor="nw")
        self._txt_item = self.create_text(w // 2, h // 2 + 1, text=text, font=font, fill=TEXT)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._render()

    def _render(self) -> None:
        st = self.STYLES[self.style_name]
        if self._disabled:
            fill, fg, outline, ow = CARD, DIM, STROKE, 1
        else:
            fill = st["press"] if self._pressed else (st["hover"] if self._hover else st["fill"])
            fg, outline, ow = st["text"], st["outline"], st["ow"]
        self.itemconfigure(self._img_item, image=cached_rounded(self.w, self.h, self.radius, fill, outline, ow))
        self.itemconfigure(self._txt_item, fill=fg)

    def _on_enter(self, _e=None):
        self._hover = True
        self._render()

    def _on_leave(self, _e=None):
        self._hover = False
        self._pressed = False
        self._render()

    def _on_press(self, _e=None):
        if self._disabled:
            return
        self._pressed = True
        self._render()

    def _on_release(self, e=None):
        was = self._pressed
        self._pressed = False
        self._render()
        if was and not self._disabled and e is not None:
            if 0 <= e.x <= self.w and 0 <= e.y <= self.h and self.command:
                try:
                    self.winfo_toplevel().focus_set()  # keep Space working after clicks
                except Exception:
                    pass
                self.command()

    def set_text(self, text: str) -> None:
        if self.itemcget(self._txt_item, "text") != text:
            self.itemconfigure(self._txt_item, text=text)

    def set_style(self, style: str) -> None:
        if style != self.style_name:
            self.style_name = style
            self._render()

    def set_disabled(self, flag: bool) -> None:
        self._disabled = flag
        self.configure(cursor="arrow" if flag else "hand2")
        self._render()


class StatCard(tk.Canvas):
    def __init__(self, master, label, w, h, radius, value_font, label_font, bg):
        super().__init__(master, width=w, height=h, bg=bg, highlightthickness=0, bd=0)
        self.w, self.h = w, h
        self._img = cached_rounded(w, h, radius, CARD, STROKE, 1)
        self.create_image(0, 0, anchor="nw", image=self._img)
        self._value = self.create_text(w // 2, h * 0.40, text="0", fill=TEXT, font=value_font)
        self.create_text(w // 2, h * 0.73, text=label, fill=DIM, font=label_font)
        self._value_font = value_font

    def set_value(self, text: str, color: str = TEXT) -> None:
        if self.itemcget(self._value, "text") != text:
            self.itemconfigure(self._value, text=text)
        if self.itemcget(self._value, "fill") != color:
            self.itemconfigure(self._value, fill=color)


# ------------------------------------------------------------------ dialog --
class DurationDialog(tk.Toplevel):
    def __init__(self, app: "FocusForge", initial_minutes: int):
        super().__init__(app.root)
        self.app = app
        s = app.s
        self.configure(bg=BG)
        self.title("Custom duration")
        self.resizable(False, False)
        self.transient(app.root)
        self.overrideredirect(False)

        wrap = tk.Frame(self, bg=BG, padx=int(24 * s), pady=int(22 * s))
        wrap.pack(fill="both", expand=True)

        tk.Label(wrap, text="CUSTOM DURATION", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", -int(14 * s))).pack(anchor="w")
        tk.Label(wrap, text="How long is this challenge?", bg=BG, fg=MUTED,
                 font=("Segoe UI", -int(11 * s))).pack(anchor="w", pady=(2, int(16 * s)))

        row = tk.Frame(wrap, bg=BG)
        row.pack()
        self.hours = self._field(row, "HOURS", initial_minutes // 60, s)
        tk.Label(row, text=":", bg=BG, fg=DIM,
                 font=("Segoe UI Semibold", -int(22 * s))).pack(side="left", padx=int(8 * s), pady=(int(14 * s), 0))
        self.minutes = self._field(row, "MINUTES", initial_minutes % 60, s)

        self.preview = tk.Label(wrap, text="", bg=BG, fg=ACCENT,
                                font=("Cascadia Mono SemiBold", -int(15 * s)))
        self.preview.pack(pady=(int(14 * s), int(4 * s)))
        self.error = tk.Label(wrap, text="", bg=BG, fg=ROSE,
                              font=("Segoe UI", -int(10 * s)))
        self.error.pack()

        btns = tk.Frame(wrap, bg=BG)
        btns.pack(pady=(int(14 * s), 0))
        Pill(btns, "CANCEL", command=self.destroy, w=int(104 * s), h=int(40 * s),
             radius=int(11 * s), style="ghost", font=("Segoe UI Semibold", -int(11 * s)), bg=BG).pack(side="left", padx=(0, int(10 * s)))
        Pill(btns, "SET TIMER", command=self._ok, w=int(126 * s), h=int(40 * s),
             radius=int(11 * s), style="primary", font=("Segoe UI Semibold", -int(11 * s)), bg=BG).pack(side="left")

        for e in (self.hours, self.minutes):
            e.bind("<KeyRelease>", lambda _e: self._update_preview())
            e.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())

        self._update_preview()
        self._center()
        self.after(60, self._activate)
        set_dark_title_bar(self)

    def _activate(self):
        if not self.winfo_exists():
            return
        self.grab_set()
        self.hours.focus_set()
        self.hours.select_range(0, "end")

    def _field(self, parent, label, value, s):
        box = tk.Frame(parent, bg=BG)
        box.pack(side="left")
        tk.Label(box, text=label, bg=BG, fg=DIM,
                 font=("Segoe UI Semibold", -int(8 * s))).pack(anchor="w", pady=(0, int(3 * s)))
        var = tk.StringVar(value=str(value))
        entry = tk.Entry(box, textvariable=var, width=4, justify="center", bg=CARD, fg=TEXT,
                         insertbackground=ACCENT, relief="flat", bd=0,
                         highlightthickness=1, highlightbackground=STROKE, highlightcolor=ACCENT,
                         font=("Cascadia Mono SemiBold", -int(24 * s)))
        entry.pack(ipady=int(6 * s))
        entry._var = var  # type: ignore[attr-defined]
        return entry

    def _minutes(self):
        try:
            h = int(self.hours._var.get() or 0)  # type: ignore[attr-defined]
            m = int(self.minutes._var.get() or 0)  # type: ignore[attr-defined]
        except ValueError:
            return None
        if h < 0 or m < 0 or m > 59 or h > 168:
            return None
        total = h * 60 + m
        return total if total > 0 else None

    def _update_preview(self):
        total = self._minutes()
        if total is None:
            self.preview.configure(text="--:--:--", fg=DIM)
            self.error.configure(text="Enter a duration between 1 minute and 168 hours.")
        else:
            self.preview.configure(text=fmt_hms(total * 60), fg=ACCENT)
            self.error.configure(text="")

    def _ok(self):
        total = self._minutes()
        if total is None:
            self._update_preview()
            return
        self.app.set_target(total * 60, custom=True)
        self.destroy()

    def _center(self):
        self.update_idletasks()
        root = self.app.root
        x = root.winfo_rootx() + (root.winfo_width() - self.winfo_width()) // 2
        y = root.winfo_rooty() + (root.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")


# --------------------------------------------------------------------- app --
class FocusForge:
    def __init__(self, root: tk.Tk, demo: bool = False):
        self.root = root
        self._demo = demo
        self.s = self._compute_scale()

        self.target = 1440 * 60
        self.elapsed = 0.0
        self.running = False
        self.started_at = 0.0
        self.done = False
        self.break_active = False
        self.break_running = False
        self.break_done = False
        self.break_manual = False
        self.break_target = BREAK_SECONDS
        self.break_elapsed = 0.0
        self.break_started_at = 0.0
        self._resume_after_break = False
        self.aot = False
        self.awake = True
        self.focus_mode = False
        self.widget_mode = False
        self._widget = None
        self._widget_c = None
        self._widget_time = None
        self._widget_fill = None
        self._widget_menu = None
        self._widget_pos: tuple[int, int] | None = None
        self._widget_drag = None
        self._widget_click_job = None
        self.milestones: set[int] = set()
        self._last_tick = time.monotonic()
        self._last_sec = -1
        self._last_render_key = None
        self._last_save = 0.0
        self._flash_msg = ""
        self._flash_until = 0.0
        self._flash_color = AMBER
        self._conf_parts: list[list] = []
        self._conf_job = None
        self._after_job = None
        self._break_job = None
        self._ring_size = 0
        self._resize_job = None
        self._closing = False
        self._btn_label = ""
        self._rest_label = ""
        self._rest_menu = None
        self._muted = demo

        self.data = self._load_stats()
        self.goal = str(self.data.get("goal", "") or "")
        self.target = int(self.data.get("last_target", 1440 * 60) or 1440 * 60)
        self.target = max(60, min(self.target, 168 * 3600))
        pos = self.data.get("widget_pos")
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                self._widget_pos = (int(pos[0]), int(pos[1]))
            except (TypeError, ValueError):
                self._widget_pos = None

        threading.Thread(target=preload_sounds, daemon=True).start()
        self._build_window()
        self._build_ui()
        self._bind_keys()
        self._sync_preset_chips()
        self._start_tick()
        self.root.after(120, lambda: set_dark_title_bar(self.root))
        if demo:
            self._apply_demo()

    def _apply_demo(self):
        """Pose the UI for documentation screenshots (never writes stats)."""
        self.goal = "Study math - 24h challenge"
        self.goal_var.set(self.goal)
        self.target = 24 * 3600
        self.elapsed = 9 * 3600 + 12 * 60
        self.running = False
        self.done = False
        today = date.today().isoformat()
        self.data["daily"][today] = 3 * 3600 + 42 * 60
        self.data["daily"][(date.today() - timedelta(days=1)).isoformat()] = 4 * 3600 + 10 * 60
        self.data["sessions"] = [{"goal": "Deep work", "minutes": 1440,
                                  "finished": datetime.now().isoformat(timespec="seconds")}] * 5
        self._sync_preset_chips(False)
        self._btn_label = ""
        self._refresh_buttons()
        self._refresh_stats()
        self._render_ring(force=True)
        self.milestones = {25, 50}
        self.running = True
        self.started_at = time.monotonic()
        self._last_tick = self.started_at

    # ------------------------------------------------------------- setup --
    def _compute_scale(self) -> float:
        try:
            dpi = float(self.root.winfo_fpixels("1i"))
        except Exception:
            dpi = 96.0
        s = dpi / 96.0
        max_h = self.root.winfo_screenheight() * 0.86
        if S_BASE_H * s > max_h:
            s = max_h / S_BASE_H
        return max(0.8, round(s, 3))

    def _px(self, v: float) -> int:
        return int(round(v * self.s))

    def _build_window(self) -> None:
        r = self.root
        W, H = self._px(S_BASE_W), self._px(S_BASE_H)
        r.title(f"{APP_NAME} - Deep Work Timer")
        r.configure(bg=BG)
        r.geometry(f"{W}x{H}")
        r.resizable(False, False)
        try:
            icon = resource_path(os.path.join("assets", "icon.ico"))
            if os.path.exists(icon):
                r.iconbitmap(icon)
        except Exception:
            pass
        r.protocol("WM_DELETE_WINDOW", self._on_close)

        self.f_title = ("Segoe UI Semibold", -self._px(17))
        self.f_tiny = ("Segoe UI Semibold", -self._px(7))
        self.f_btn = ("Segoe UI Semibold", -self._px(12))
        self.f_chip = ("Segoe UI Semibold", -self._px(10))
        self.f_small = ("Segoe UI Semibold", -self._px(9))
        self.f_label = ("Segoe UI Semibold", -self._px(8))
        self.f_time = ("Cascadia Mono SemiBold", -self._px(44))
        self.f_goal = ("Segoe UI Semibold", -self._px(10))
        self.f_sub = ("Segoe UI", -self._px(11))
        self.f_entry = ("Segoe UI", -self._px(12))
        self.f_stat = ("Segoe UI Semibold", -self._px(19))
        self.f_foot = ("Segoe UI", -self._px(9))

        self._children: list[tuple[tk.Widget, dict]] = []
        self._hidden_in_focus: set[tk.Widget] = set()

    def _add(self, widget, **kw):
        widget.pack(**kw)
        self._children.append((widget, kw))
        return widget

    def _apply_layout(self):
        for w, _ in self._children:
            w.pack_forget()
        for w, kw in self._children:
            if self.focus_mode and w in self._hidden_in_focus:
                continue
            w.pack(**kw)

    # --------------------------------------------------------------- ui ----
    def _build_ui(self):
        s, PAD = self.s, self._px(22)

        # top bar ---------------------------------------------------------
        bar = tk.Frame(self.root, bg=BG)
        self._hidden_in_focus.add(bar)
        self._add(bar, fill="x", padx=PAD, pady=(self._px(14), 0))

        logo = tk.Label(bar, bg=BG, bd=0)
        self._logo_img = ImageTk.PhotoImage(make_logo(self._px(32)))
        logo.configure(image=self._logo_img)
        logo.pack(side="left")

        titles = tk.Frame(bar, bg=BG)
        titles.pack(side="left", padx=(self._px(10), 0))
        tk.Label(titles, text=APP_NAME, bg=BG, fg=TEXT, font=self.f_title).pack(anchor="w")
        tk.Label(titles, text="D E E P   W O R K   T I M E R", bg=BG, fg=DIM,
                 font=self.f_tiny).pack(anchor="w")

        self.pin_pill = Pill(bar, "PIN", command=self._toggle_pin, w=self._px(56), h=self._px(30),
                             radius=self._px(9), style="toggle", font=self.f_small, bg=BG)
        self.pin_pill.pack(side="right", pady=self._px(2))
        self.mini_pill = Pill(bar, "MINI", command=self._toggle_widget_mode,
                              w=self._px(62), h=self._px(30), radius=self._px(9),
                              style="toggle", font=self.f_small, bg=BG)
        self.mini_pill.pack(side="right", padx=(0, self._px(8)), pady=self._px(2))
        self.awake_pill = Pill(bar, "AWAKE", command=self._toggle_awake, w=self._px(76), h=self._px(30),
                               radius=self._px(9), style="toggle_mint", font=self.f_small, bg=BG)
        self.awake_pill.pack(side="right", padx=(0, self._px(8)), pady=self._px(2))

        sep = tk.Frame(self.root, bg=STROKE, height=1)
        self._hidden_in_focus.add(sep)
        self._add(sep, fill="x", padx=PAD, pady=(self._px(12), 0))

        # ring ------------------------------------------------------------
        self.ring = tk.Canvas(self.root, bg=BG, highlightthickness=0, bd=0)
        self._add(self.ring, fill="both", expand=True, padx=PAD, pady=(self._px(4), 0))
        self.ring.bind("<Configure>", self._on_ring_configure)
        self._ring_img_item = None
        self._ring_photo = None
        self._ring_goal_item = None
        self._ring_status_item = None
        self._ring_time_item = None
        self._ring_sub_item = None

        # controls ---------------------------------------------------------
        controls = tk.Frame(self.root, bg=BG)
        self._add(controls, fill="x", padx=PAD, pady=(self._px(2), 0))
        inner = tk.Frame(controls, bg=BG)
        inner.pack()
        self.reset_pill = Pill(inner, "RESET", command=self.reset, w=self._px(82), h=self._px(46),
                               radius=self._px(12), style="ghost", font=self.f_small, bg=BG)
        self.reset_pill.pack(side="left", padx=self._px(2), pady=self._px(3))
        self.primary_pill = Pill(inner, "START", command=self._primary, w=self._px(152), h=self._px(52),
                                 radius=self._px(14), style="primary", font=self.f_btn, bg=BG)
        self.primary_pill.pack(side="left", padx=self._px(5))
        self.plus_pill = Pill(inner, "+5 MIN", command=self.add_time, w=self._px(82), h=self._px(46),
                              radius=self._px(12), style="ghost", font=self.f_small, bg=BG)
        self.plus_pill.pack(side="left", padx=self._px(2), pady=self._px(3))
        self.rest_pill = Pill(inner, "REST \u25be", command=self._open_rest_menu, w=self._px(82),
                              h=self._px(46), radius=self._px(12), style="toggle_mint",
                              font=self.f_small, bg=BG)
        self.rest_pill.pack(side="left", padx=(self._px(5), self._px(2)), pady=self._px(3))

        # presets ----------------------------------------------------------
        presets = tk.Frame(self.root, bg=BG)
        self._hidden_in_focus.add(presets)
        self._add(presets, fill="x", padx=PAD, pady=(self._px(12), 0))
        for i in range(len(PRESETS) + 1):
            presets.grid_columnconfigure(i, weight=1, uniform="preset")
        self.preset_pills: dict[int, Pill] = {}
        for i, (minutes, label) in enumerate(PRESETS):
            p = Pill(presets, label, command=lambda m=minutes: self.set_target(m * 60),
                     w=self._px(44), h=self._px(32), radius=self._px(9),
                     style="chip", font=self.f_chip, bg=BG)
            p.grid(row=0, column=i, sticky="ew", padx=self._px(2))
            self.preset_pills[minutes] = p
        self.custom_pill = Pill(presets, "SET", command=self._open_custom,
                                w=self._px(44), h=self._px(32), radius=self._px(9),
                                style="chip", font=self.f_chip, bg=BG)
        self.custom_pill.grid(row=0, column=len(PRESETS), sticky="ew", padx=self._px(2))

        # goal -------------------------------------------------------------
        goalbox = tk.Frame(self.root, bg=BG)
        self._hidden_in_focus.add(goalbox)
        self._add(goalbox, fill="x", padx=PAD, pady=(self._px(12), 0))
        tk.Label(goalbox, text="SESSION GOAL", bg=BG, fg=DIM, font=self.f_label).pack(anchor="w",
                                                                                      pady=(0, self._px(4)))
        self.goal_var = tk.StringVar(value=self.goal)
        self.goal_entry = tk.Entry(goalbox, textvariable=self.goal_var, bg=CARD, fg=TEXT,
                                   insertbackground=ACCENT, relief="flat", bd=0,
                                   highlightthickness=1, highlightbackground=STROKE,
                                   highlightcolor=ACCENT, font=self.f_entry)
        self.goal_entry.pack(fill="x", ipady=self._px(7))
        self.goal_var.trace_add("write", lambda *_: self._on_goal_change())

        # stats ------------------------------------------------------------
        stats = tk.Frame(self.root, bg=BG)
        self._hidden_in_focus.add(stats)
        self._add(stats, fill="x", padx=PAD, pady=(self._px(12), 0))
        gap = self._px(8)
        card_w = (self._px(S_BASE_W) - 2 * PAD - 2 * gap) // 3
        card_h = self._px(62)
        for i in range(3):
            stats.grid_columnconfigure(i, weight=1, uniform="stat")
        self.card_today = StatCard(stats, "T O D A Y", card_w, card_h, self._px(12),
                                   self.f_stat, self.f_label, BG)
        self.card_today.grid(row=0, column=0, sticky="ew", padx=(0, gap // 2))
        self.card_streak = StatCard(stats, "S T R E A K", card_w, card_h, self._px(12),
                                    self.f_stat, self.f_label, BG)
        self.card_streak.grid(row=0, column=1, sticky="ew", padx=gap // 2)
        self.card_sessions = StatCard(stats, "S E S S I O N S", card_w, card_h, self._px(12),
                                      self.f_stat, self.f_label, BG)
        self.card_sessions.grid(row=0, column=2, sticky="ew", padx=(gap // 2, 0))

        # footer -----------------------------------------------------------
        footer = tk.Frame(self.root, bg=BG)
        self._hidden_in_focus.add(footer)
        self._add(footer, fill="x", padx=PAD, pady=(self._px(10), self._px(12)))
        tk.Label(footer, text="SPACE  start / pause    R  reset    B  break    F10  mini    F11  focus",
                 bg=BG, fg=DIM, font=self.f_foot).pack(side="left")
        tk.Label(footer, text=f"v{VERSION}", bg=BG, fg=DIM, font=self.f_foot).pack(side="right")

        # focus-mode hint (only packed while in focus mode)
        self.hint = tk.Label(self.root, text="ESC  exit focus mode", bg=BG, fg=DIM, font=self.f_small)

    # ------------------------------------------------------------ helpers --
    def _load_stats(self) -> dict:
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError
        except Exception:
            data = {}
        data.setdefault("daily", {})
        data.setdefault("sessions", [])
        if not isinstance(data["daily"], dict):
            data["daily"] = {}
        if not isinstance(data["sessions"], list):
            data["sessions"] = []
        return data

    def _save_stats(self):
        if self._demo:
            return
        cutoff = (date.today() - timedelta(days=400)).isoformat()
        daily = {k: v for k, v in self.data["daily"].items() if k >= cutoff}
        out = {
            "daily": daily,
            "sessions": self.data["sessions"][-100:],
            "goal": self.goal,
            "last_target": int(self.target),
            "widget_pos": list(self._widget_pos) if self._widget_pos else None,
            "version": VERSION,
        }
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = DATA_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
            tmp.replace(DATA_FILE)
        except Exception:
            pass
        self._last_save = time.monotonic()

    # -------------------------------------------------------------- state --
    def elapsed_now(self) -> float:
        e = self.elapsed
        if self.running:
            e += time.monotonic() - self.started_at
        return min(e, float(self.target))

    def remaining(self) -> float:
        return max(0.0, self.target - self.elapsed_now())

    def progress(self) -> float:
        if self.target <= 0:
            return 0.0
        return max(0.0, min(1.0, self.elapsed_now() / self.target))

    # --------------------------------------------------------------- rest --
    def break_elapsed_now(self) -> float:
        e = self.break_elapsed
        if self.break_running:
            e += time.monotonic() - self.break_started_at
        return min(e, float(self.break_target))

    def break_remaining(self) -> float:
        return max(0.0, self.break_target - self.break_elapsed_now())

    def break_progress(self) -> float:
        if self.break_target <= 0:
            return 0.0
        return max(0.0, min(1.0, self.break_elapsed_now() / self.break_target))

    def _cancel_break_job(self) -> None:
        if self._break_job:
            try:
                self.root.after_cancel(self._break_job)
            except Exception:
                pass
            self._break_job = None

    def _clear_break(self, resume: bool = True) -> None:
        """Reset the rest state; a manual break can hand straight back to focus."""
        resume = bool(resume and self.break_manual and self._resume_after_break
                      and not self.done and self.elapsed_now() > 0)
        self._cancel_break_job()
        self.break_active = False
        self.break_running = False
        self.break_done = False
        self.break_manual = False
        self.break_target = BREAK_SECONDS
        self.break_elapsed = 0.0
        self.break_started_at = 0.0
        self._resume_after_break = False
        if resume and not self.running:
            self.start()

    def _schedule_break(self) -> None:
        """Safety net: rest starts even if the celebration cannot animate."""
        self._cancel_break_job()
        if self._demo or not self.done or self.break_active:
            return
        self._break_job = self.root.after(BREAK_FALLBACK_MS, self.start_break)

    def _arm_break_after_celebration(self) -> None:
        """The firework and confetti always play in full before the rest."""
        if self._demo or self._closing or not self.done or self.break_active:
            return
        self._cancel_break_job()
        self._break_job = self.root.after(BREAK_SETTLE_MS, self.start_break)

    def _begin_break(self, minutes: int, manual: bool = False, resume: bool = False) -> None:
        self.break_active = True
        self.break_running = True
        self.break_done = False
        self.break_manual = bool(manual)
        self.break_target = max(60, int(minutes) * 60)
        self.break_elapsed = 0.0
        self.break_started_at = time.monotonic()
        self._resume_after_break = bool(resume)
        self._last_tick = self.break_started_at
        self._last_render_key = None
        # a clean ring makes the rest state obvious
        try:
            if self._conf_job:
                self.root.after_cancel(self._conf_job)
        except Exception:
            pass
        self._conf_job = None
        self._conf_parts = []
        try:
            self.ring.delete("confetti")
        except Exception:
            pass
        self._flash_msg = ""
        self._flash_until = 0.0
        self._apply_awake()
        self._render_ring(force=True)
        self._refresh_buttons()

    def start_break(self) -> None:
        """Automatic rest that follows a completed challenge."""
        self._break_job = None
        if self._closing or self.break_active:
            return
        self._begin_break(max(1, int(round(BREAK_SECONDS / 60))), manual=False, resume=False)

    def start_rest(self, minutes: int = 5) -> None:
        """REST button / B key: pause the session and take a break."""
        if self._closing or self.break_active:
            return
        was_running = self.running
        if was_running:
            self.pause()
        self._cancel_break_job()
        self._clear_break(resume=False)
        self._begin_break(minutes, manual=not self.done, resume=was_running)
        if not self._muted:
            play_chime()
        self._flash(f"{int(minutes)} MIN BREAK", 2.0, MINT)

    def _finish_break(self) -> None:
        self.break_elapsed = float(self.break_target)
        self.break_running = False
        self.break_done = True
        self._apply_awake()
        self._last_render_key = None
        self._render_ring(force=True)
        self._refresh_buttons()
        if self.break_manual:
            self._flash("BREAK COMPLETE", 2.4, MINT)
        else:
            self._flash("REST COMPLETE", 3.2, MINT)
        if not self._muted:
            play_chime()
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            flash_taskbar(hwnd)
        except Exception:
            pass
        delay = 1800 if self.break_manual else 2800
        self._break_job = self.root.after(delay, self._dismiss_break)

    def skip_break(self) -> None:
        if not self.break_active:
            return
        self._dismiss_break("BREAK SKIPPED")

    def _dismiss_break(self, msg: str | None = None) -> None:
        manual = self.break_manual
        if manual:
            self._clear_break()
            resumed = self.running
        else:
            self._clear_break(resume=False)
            self._soft_reset()
            resumed = False
        self._last_render_key = None
        if msg:
            self._flash(msg, 2.0, MUTED)
        elif resumed:
            self._flash("BACK TO FOCUS", 2.4, ACCENT)
        self._render_ring(force=True)
        self._refresh_buttons()

    def start(self):
        if self.break_active:
            return
        if self.done:
            self._soft_reset()
        if self.running:
            return
        self.running = True
        self.done = False
        self.started_at = time.monotonic()
        self._last_tick = self.started_at
        p = self.progress() * 100
        self.milestones = {m for m, _ in MILESTONES if p >= m}
        self._apply_awake()
        self._refresh_buttons()
        self._save_stats()

    def pause(self):
        if not self.running:
            return
        self.elapsed = self.elapsed_now()
        self.running = False
        self._apply_awake()
        self._refresh_buttons()
        self._render_ring(force=True)
        self._save_stats()

    def toggle(self):
        if self.running:
            self.pause()
        else:
            self.start()

    def _primary(self):
        if self.break_active:
            if self.break_running:
                self.skip_break()
            else:
                self._dismiss_break()
            return
        if self.done:
            self._cancel_break_job()
            self._soft_reset()
            self.start()
        elif self.running:
            self.pause()
        else:
            self.start()

    def _soft_reset(self):
        self.running = False
        self.done = False
        self.elapsed = 0.0
        self.milestones.clear()
        self._apply_awake()

    def reset(self):
        self._clear_break(resume=False)
        self._soft_reset()
        self._flash("TIMER RESET", 1.6, MUTED)
        self._render_ring(force=True)
        self._refresh_buttons()
        self._save_stats()

    def add_time(self, seconds: int = 300):
        self._clear_break()
        if self.done:
            self._soft_reset()
        self.target = max(60, min(self.target + seconds, 168 * 3600))
        self._last_render_key = None
        self._flash(f"+{seconds // 60} MIN ADDED", 1.8, MINT)
        self._render_ring(force=True)
        self._sync_preset_chips()
        self._save_stats()

    def set_target(self, seconds: int, custom: bool = False):
        self._clear_break(resume=False)
        seconds = max(60, min(int(seconds), 168 * 3600))
        was_running = self.running
        self.running = False
        self.done = False
        self.elapsed = 0.0
        self.target = seconds
        self.milestones.clear()
        self._apply_awake()
        self._last_render_key = None
        self._flash(f"{fmt_compact(seconds).upper()} SET", 1.8, ACCENT)
        self._sync_preset_chips(custom)
        self._render_ring(force=True)
        self._refresh_buttons()
        self._save_stats()
        if was_running:
            self.start()

    def _sync_preset_chips(self, custom: bool | None = None):
        if custom is None:
            custom = self.target not in {m * 60 for m, _ in PRESETS}
        for minutes, pill in self.preset_pills.items():
            pill.set_style("chip_on" if minutes * 60 == self.target and not custom else "chip")
        self.custom_pill.set_style("chip_on" if custom else "chip")

    # ------------------------------------------------------------- toggles --
    def _toggle_pin(self):
        self.aot = not self.aot
        self.root.attributes("-topmost", self.aot)
        self.pin_pill.set_style("toggle_blue" if self.aot else "toggle")
        self._flash("ALWAYS ON TOP" if self.aot else "ON TOP OFF", 1.5, ACCENT)

    def _toggle_awake(self):
        self.awake = not self.awake
        self.awake_pill.set_style("toggle_mint" if self.awake else "toggle")
        self._apply_awake()
        self._flash("PC STAYS AWAKE" if self.awake else "SLEEP ALLOWED", 1.5, MINT if self.awake else MUTED)

    def _apply_awake(self):
        keep_awake(self.awake and (self.running or self.break_running))

    # -------------------------------------------------------------- layout --
    def _on_ring_configure(self, _e=None):
        if self._resize_job:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.root.after(60, self._redo_ring)

    def _redo_ring(self):
        self._resize_job = None
        w = self.ring.winfo_width()
        h = self.ring.winfo_height()
        size = max(120, min(w, h) - self._px(6))
        if abs(size - self._ring_size) >= 2:
            self._ring_size = size
            self._build_ring_items()
        self._render_ring(force=True)

    def _build_ring_items(self):
        cv = self.ring
        for tag in ("ring", "ringtext"):
            cv.delete(tag)
        w = cv.winfo_width()
        h = cv.winfo_height()
        size = self._ring_size
        cx, cy = w / 2.0, h / 2.0
        r = size / 2.0

        # keep the ring typography proportional when focus mode grows the ring
        k = max(0.72, min(2.9, size / float(self._px(420))))
        f_goal = ("Segoe UI Semibold", -max(7, int(self._px(10) * k)))
        f_small = ("Segoe UI Semibold", -max(7, int(self._px(9) * k)))
        f_time = ("Cascadia Mono SemiBold", -max(18, int(self._px(44) * k)))
        f_sub = ("Segoe UI", -max(8, int(self._px(11) * k)))

        self._ring_img_item = cv.create_image(cx, cy, anchor="center", tags="ring")
        cv.tag_lower("ring")

        self._ring_goal_item = cv.create_text(
            cx, cy - r * 0.44, text="", fill=DIM, font=f_goal, tags="ringtext")
        self._ring_status_item = cv.create_text(
            cx, cy - r * 0.19, text="", fill=MUTED, font=f_small, tags="ringtext")
        self._ring_time_item = cv.create_text(
            cx, cy + r * 0.05, text="00:00:00", fill=TEXT, font=f_time, tags="ringtext")
        self._ring_sub_item = cv.create_text(
            cx, cy + r * 0.31, text="", fill=MUTED, font=f_sub, tags="ringtext")

    def _render_ring(self, force: bool = False):
        if self._ring_img_item is None or self._ring_size <= 0:
            return
        if self.break_active:
            frac = 1.0 if self.break_done else self.break_progress()
            palette = "break"
            phase = ("break", self.break_done)
        else:
            frac = 1.0 if self.done else self.progress()
            palette = "focus"
            phase = ("focus", self.done)
        key = (round(frac, 5), phase, self._ring_size)
        if not force and key == self._last_render_key:
            return
        self._last_render_key = key
        img = render_ring(self._ring_size, frac, palette)
        self._ring_photo = ImageTk.PhotoImage(img)
        self.ring.itemconfigure(self._ring_img_item, image=self._ring_photo)

    # -------------------------------------------------------------- update --
    def _start_tick(self):
        self._after_job = self.root.after(200, self._tick)

    def _tick(self):
        if self._closing:
            return
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        if self.running:
            dt = min(max(dt, 0.0), 5.0)
            self._accumulate(dt)
            if self.awake and int(now) % 20 == 0:
                self._apply_awake()
            if self.elapsed_now() >= self.target - 1e-6:
                self._complete()
            else:
                self._check_milestones()
        elif self.break_running:
            if self.break_elapsed_now() >= self.break_target - 1e-6:
                self._finish_break()
        if now - self._last_save > 20:
            self._save_stats()

        self._refresh()
        self._after_job = self.root.after(200, self._tick)

    def _accumulate(self, dt: float):
        if self._demo:
            return
        self.data["daily"][date.today().isoformat()] = (
            self.data["daily"].get(date.today().isoformat(), 0.0) + dt
        )

    def _check_milestones(self):
        p = self.progress() * 100
        for m, msg in MILESTONES:
            if p >= m and m not in self.milestones:
                self.milestones.add(m)
                self._flash(msg, 3.4, AMBER)
                self._beep([(1046, 70)])

    def _refresh(self):
        self._render_ring()

        if self.break_active:
            self._draw_break()
        else:
            self._draw_session()

        self._refresh_buttons()
        self._refresh_stats()
        self._update_title()
        self._refresh_widget()

    def _draw_session(self):
        rem = self.remaining()
        text = "00:00:00" if self.done else fmt_hms(rem)
        if self._ring_time_item is not None:
            self.ring.itemconfigure(self._ring_time_item, text=text)

        if self._ring_goal_item is not None:
            goal = (self.goal or "DEEP WORK SESSION").strip().upper()
            if len(goal) > 30:
                goal = goal[:29].rstrip() + "\u2026"
            self.ring.itemconfigure(self._ring_goal_item, text=goal)

        if self._ring_sub_item is not None:
            pct = self.progress() * 100
            self.ring.itemconfigure(self._ring_sub_item,
                                    text=f"{pct:.1f}% of {fmt_compact(self.target)}")

        self._draw_status()

    def _draw_break(self):
        rem = self.break_remaining()
        text = "00:00:00" if self.break_done else fmt_hms(rem)
        if self._ring_time_item is not None:
            self.ring.itemconfigure(self._ring_time_item, text=text)

        if self._ring_goal_item is not None:
            goal = "R E S T   B R E A K" if self.break_manual else "R E S T   &   R E S E T"
            self.ring.itemconfigure(self._ring_goal_item, text=goal)

        if self._ring_sub_item is not None:
            minutes = max(1, int(round(self.break_target / 60)))
            if self.break_manual:
                sub = f"{minutes} min break  \u00b7  session is paused and resumes after"
            else:
                sub = f"{minutes} min break  \u00b7  stretch, breathe, drink water"
            self.ring.itemconfigure(self._ring_sub_item, text=sub)

        self._draw_status()

    def _draw_status(self):
        if self._ring_status_item is None:
            return
        now = time.monotonic()
        if self._flash_msg and now < self._flash_until:
            age = self._flash_until - now
            pulse = 0.60 + 0.40 * (0.5 + 0.5 * math.sin(now * 5.5))
            col = rgb_hex(mix(hex_rgb(self._flash_color), hex_rgb(BG), 0.15 + 0.35 * (1 - pulse)))
            self.ring.itemconfigure(self._ring_status_item, text=" ".join(self._flash_msg),
                                    fill=col)
        elif self.break_active:
            if self.break_done:
                msg = "BREAK COMPLETE" if self.break_manual else "REST COMPLETE"
                self.ring.itemconfigure(self._ring_status_item,
                                        text=" ".join(msg), fill=MINT)
            else:
                self.ring.itemconfigure(self._ring_status_item,
                                        text=" ".join("RESTING"), fill=CYAN)
        elif self.done:
            self.ring.itemconfigure(self._ring_status_item, text=" ".join("COMPLETE"), fill=MINT)
        elif self.running:
            self.ring.itemconfigure(self._ring_status_item, text=" ".join("FOCUSING"), fill=ACCENT)
        elif self.elapsed_now() > 0:
            self.ring.itemconfigure(self._ring_status_item, text=" ".join("PAUSED"), fill=AMBER)
        else:
            self.ring.itemconfigure(self._ring_status_item, text=" ".join("READY"), fill=MUTED)

    def _refresh_buttons(self):
        style = "primary"
        if self.break_active:
            if self.break_done:
                label = "BACK TO WORK" if self.break_manual else "NEW SESSION"
                style = "primary"
            else:
                label = "BACK TO WORK" if self.break_manual else "SKIP BREAK"
                style = "break_btn"
        elif self.done:
            label = "NEW SESSION"
        elif self.running:
            label = "PAUSE"
        elif self.elapsed_now() > 0:
            label = "RESUME"
        else:
            label = "START"
        key = (label, style)
        if key != self._btn_label:
            self._btn_label = key
            self.primary_pill.set_text(label)
            self.primary_pill.set_style(style)

        if self.break_active:
            rest_label, rest_style = "END REST", "toggle_mint"
        else:
            rest_label, rest_style = "REST \u25be", "toggle_mint"
        rest_key = (rest_label, rest_style)
        if rest_key != self._rest_label:
            self._rest_label = rest_key
            self.rest_pill.set_text(rest_label)
            self.rest_pill.set_style(rest_style)

    def _refresh_stats(self):
        today_sec = self.data["daily"].get(date.today().isoformat(), 0.0)
        self.card_today.set_value(fmt_compact(today_sec), ACCENT)
        self.card_streak.set_value(f"{self._streak()}d", AMBER if self._streak() > 0 else TEXT)
        self.card_sessions.set_value(str(len(self.data["sessions"])), MINT)

    def _streak(self) -> int:
        daily = self.data["daily"]
        d = date.today()
        if daily.get(d.isoformat(), 0.0) < 60:
            d -= timedelta(days=1)
        n = 0
        while daily.get(d.isoformat(), 0.0) >= 60:
            n += 1
            d -= timedelta(days=1)
        return n

    def _update_title(self):
        if self.break_active:
            word = "break" if self.break_manual else "rest"
            if self.break_done:
                title = f"{word.upper()} COMPLETE  -  {APP_NAME}"
            else:
                title = f"{fmt_hms(self.break_remaining())}  {word}  -  {APP_NAME}"
        elif self.running:
            title = f"{fmt_hms(self.remaining())}  -  {APP_NAME}"
        elif self.done:
            title = f"COMPLETE  -  {APP_NAME}"
        elif self.elapsed_now() > 0:
            title = f"{fmt_hms(self.remaining())}  paused  -  {APP_NAME}"
        else:
            title = f"{APP_NAME} - Deep Work Timer"
        try:
            if self.root.title() != title:
                self.root.title(title)
        except Exception:
            pass

    # ------------------------------------------------------------- effects --
    def _flash(self, msg: str, seconds: float = 2.4, color: str = AMBER):
        self._flash_msg = msg
        self._flash_until = time.monotonic() + seconds
        self._flash_color = color

    def _complete(self):
        self.elapsed = self.target
        self.running = False
        self.done = True
        self._apply_awake()
        self._log_session()
        self._refresh_buttons()
        self._last_render_key = None
        self._render_ring(force=True)
        self._save_stats()
        self._flash("CHALLENGE COMPLETE", 6.0, MINT)
        self._confetti()
        if not self._muted:
            if winsound:
                play_firework()
            else:
                self._beep([(784, 130), (988, 130), (1175, 150), (1568, 420)])
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            flash_taskbar(hwnd)
        except Exception:
            pass
        self._schedule_break()

    def _log_session(self):
        self.data["sessions"].append({
            "goal": self.goal or "Deep work",
            "minutes": round(self.target / 60),
            "finished": datetime.now().isoformat(timespec="seconds"),
        })
        self.data["sessions"] = self.data["sessions"][-100:]

    def _beep(self, notes):
        if not winsound:
            return

        def run():
            for freq, dur in notes:
                try:
                    winsound.Beep(int(freq), int(dur))
                except Exception:
                    pass

        threading.Thread(target=run, daemon=True).start()

    def _confetti(self):
        cv = self.ring
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 10:
            return
        cx, cy = w / 2.0, h / 2.0
        colors = [ACCENT, CYAN, MINT, AMBER, ROSE, VIOLET, "#FFFFFF"]
        self._conf_parts = []
        for _ in range(110):
            angle = random.uniform(-math.pi * 0.95, -math.pi * 0.05)
            speed = random.uniform(3.2, 11.5) * self.s
            size = random.uniform(2.5, 6.5) * self.s
            x = cx + random.uniform(-14, 14) * self.s
            y = cy + random.uniform(-8, 8) * self.s
            item = cv.create_oval(x, y, x + size, y + size,
                                  fill=random.choice(colors), outline="", tags="confetti")
            self._conf_parts.append([item, math.cos(angle) * speed, math.sin(angle) * speed, size])
        if self._conf_job:
            try:
                self.root.after_cancel(self._conf_job)
            except Exception:
                pass
        self._conf_ticks = 0
        self._animate_confetti()

    def _animate_confetti(self):
        if self._closing:
            return
        cv = self.ring
        h = cv.winfo_height()
        gravity = 0.34 * self.s
        alive = []
        for part in self._conf_parts:
            item, vx, vy, size = part
            vy += gravity
            vx *= 0.995
            try:
                cv.move(item, vx, vy)
                coords = cv.coords(item)
            except Exception:
                continue
            if coords and coords[1] < h + 30 * self.s:
                part[1], part[2] = vx, vy
                alive.append(part)
            else:
                cv.delete(item)
        self._conf_parts = alive
        self._conf_ticks += 1
        if alive and self._conf_ticks < 320:
            self._conf_job = self.root.after(24, self._animate_confetti)
        else:
            for part in alive:
                try:
                    cv.delete(part[0])
                except Exception:
                    pass
            self._conf_parts = []
            self._conf_job = None
            # the firework has landed - only now may the rest timer take over
            self._arm_break_after_celebration()

    # -------------------------------------------------------------- dialog --
    def _open_custom(self):
        DurationDialog(self, max(1, int(round(self.target / 60))))

    def _open_rest_menu(self):
        """REST pill: pick a 5 / 10 / 15 minute break, or end the current one."""
        if self.break_active:
            self.skip_break()
            return
        menu = tk.Menu(self.root, tearoff=0, bg=CARD, fg=TEXT, activebackground=ACCENT,
                       activeforeground="#FFFFFF", bd=0, relief="flat")
        for minutes in REST_CHOICES:
            menu.add_command(label=f"{minutes} minute break",
                             command=lambda m=minutes: self.start_rest(m))
        if self.elapsed_now() > 0 and not self.done:
            menu.add_separator()
            menu.add_command(label="Your session timer pauses", state="disabled")
        self._rest_menu = menu
        try:
            x = self.rest_pill.winfo_rootx()
            y = self.rest_pill.winfo_rooty() + self.rest_pill.winfo_height() + self._px(4)
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    # ---------------------------------------------------------------- keys --
    def _bind_keys(self):
        self.root.bind("<space>", self._key_space)
        self.root.bind("<Key-r>", self._key_reset)
        self.root.bind("<Key-R>", self._key_reset)
        self.root.bind("<Key-b>", self._key_break)
        self.root.bind("<Key-B>", self._key_break_long)
        self.root.bind("<F10>", self._key_widget)
        self.root.bind("<Key-w>", self._key_widget)
        self.root.bind("<Key-W>", self._key_widget)
        self.root.bind("<F11>", self._key_focus)
        self.root.bind("<Escape>", self._key_escape)

    def _typing(self) -> bool:
        try:
            w = self.root.focus_get()
            return isinstance(w, (tk.Entry, tk.Spinbox))
        except Exception:
            return False

    def _key_space(self, _e=None):
        if self._typing():
            return
        if self.break_active:
            if self.break_running:
                self.skip_break()
            else:
                self._dismiss_break()
        else:
            self.toggle()
        return "break"

    def _key_reset(self, _e=None):
        if self._typing():
            return
        self.reset()
        return "break"

    def _key_break(self, _e=None):
        if self._typing():
            return
        if self.break_active:
            self.skip_break()
        else:
            self.start_rest(5)
        return "break"

    def _key_break_long(self, _e=None):
        if self._typing():
            return
        if self.break_active:
            self.skip_break()
        else:
            self.start_rest(10)
        return "break"

    def _key_focus(self, _e=None):
        self._toggle_focus_mode()
        return "break"

    def _key_widget(self, _e=None):
        if self._typing():
            return
        self._toggle_widget_mode()
        return "break"

    def _key_escape(self, _e=None):
        if self.widget_mode:
            self._exit_widget_mode()
            return "break"
        if self.focus_mode:
            self._toggle_focus_mode()
            return "break"

    def _toggle_focus_mode(self):
        self.focus_mode = not self.focus_mode
        try:
            self.root.resizable(True, True)
            self.root.attributes("-fullscreen", self.focus_mode)
        except Exception:
            pass
        if self.focus_mode:
            self.hint.pack(side="bottom", pady=(0, self._px(8)))
        else:
            self.hint.pack_forget()
            self.root.resizable(False, False)
        self._apply_layout()
        self.root.after(120, lambda: (self._redo_ring(), self._render_ring(force=True)))
        if not self.focus_mode:
            # Windows can drop the dark title bar when leaving fullscreen
            self.root.after(180, lambda: set_dark_title_bar(self.root))

    # ---------------------------------------------------------- mini widget --
    def _widget_geometry(self) -> tuple[int, int]:
        return self._px(196), self._px(66)

    def _build_widget(self) -> None:
        if self._widget is not None:
            return
        w, h = self._widget_geometry()
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.configure(bg=BG)
        top.attributes("-topmost", True)
        try:
            top.attributes("-toolwindow", True)
        except Exception:
            pass

        cv = tk.Canvas(top, width=w, height=h, bg=BG, highlightthickness=0, bd=0,
                       cursor="hand2")
        cv.pack()
        self._widget_bg = cached_rounded(w, h, self._px(17), CARD, STROKE, 1)
        cv.create_image(0, 0, anchor="nw", image=self._widget_bg)

        pad = self._px(14)
        bar_y = h - self._px(10)
        cv.create_line(pad, bar_y, w - pad, bar_y, fill=STROKE, width=max(2, self._px(3)),
                       capstyle="round")
        self._widget_fill = cv.create_line(pad, bar_y, pad + 1, bar_y, fill=ACCENT,
                                           width=max(2, self._px(3)), capstyle="round")
        self._widget_time = cv.create_text(
            w // 2, h // 2 - self._px(3), text="00:00:00", fill=TEXT,
            font=("Cascadia Mono SemiBold", -self._px(25)),
        )
        self._widget_c = cv
        self._widget = top

        for seq in ("<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>"):
            cv.bind(seq, getattr(self, {
                "<ButtonPress-1>": "_widget_press",
                "<B1-Motion>": "_widget_motion",
                "<ButtonRelease-1>": "_widget_release",
            }[seq]))
        cv.bind("<Double-Button-1>", self._widget_double_click)
        top.bind("<Double-Button-1>", self._widget_double_click)
        top.bind("<Escape>", lambda _e: self._exit_widget_mode())
        top.bind("<Button-3>", self._widget_menu_popup)

        menu = tk.Menu(top, tearoff=0, bg=CARD, fg=TEXT, activebackground=ACCENT,
                       activeforeground="#FFFFFF", bd=0, relief="flat")
        menu.add_command(label="Open full window", command=self._exit_widget_mode)
        menu.add_command(label="Start / pause", command=self._primary)
        menu.add_command(label="Take a 5 min break", command=lambda: self.start_rest(5))
        menu.add_command(label="Take a 10 min break", command=lambda: self.start_rest(10))
        menu.add_command(label="Reset timer", command=self.reset)
        menu.add_separator()
        menu.add_command(label="Quit FocusForge", command=self._on_close)
        self._widget_menu = menu

        self._place_widget()

    def _place_widget(self) -> None:
        if self._widget is None:
            return
        w, h = self._widget_geometry()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if self._widget_pos:
            x, y = self._widget_pos
        else:
            x, y = sw - w - self._px(26), self._px(26)
        x = max(-w + self._px(48), min(int(x), sw - self._px(48)))
        y = max(0, min(int(y), sh - self._px(48)))
        self._widget.geometry(f"{w}x{h}+{x}+{y}")

    def _refresh_widget(self) -> None:
        if self._widget_c is None or self._widget_time is None:
            return
        if self.break_active:
            frac = self.break_progress()
            if self.break_done:
                text, color = "00:00:00", MINT
            else:
                text, color = fmt_hms(self.break_remaining()), CYAN
        elif self.done:
            text, color, frac = "00:00:00", MINT, 1.0
        elif self.running:
            text, color, frac = fmt_hms(self.remaining()), ACCENT, self.progress()
        elif self.elapsed_now() > 0:
            text, color, frac = fmt_hms(self.remaining()), AMBER, self.progress()
        else:
            text, color, frac = fmt_hms(self.target), TEXT, 0.0
        self._widget_c.itemconfigure(self._widget_time, text=text, fill=color)
        if self._widget_fill is not None:
            w, h = self._widget_geometry()
            pad = self._px(14)
            y = h - self._px(10)
            end = pad + max(1, int((w - 2 * pad) * frac))
            self._widget_c.coords(self._widget_fill, pad, y, end, y)
            self._widget_c.itemconfigure(self._widget_fill, fill=color)

    def _widget_press(self, e):
        if self._widget is None:
            return
        self._widget_drag = (e.x_root, e.y_root,
                             self._widget.winfo_x(), self._widget.winfo_y())
        self._widget_moved = False

    def _widget_motion(self, e):
        if self._widget is None or not self._widget_drag:
            return
        x0, y0, wx, wy = self._widget_drag
        dx, dy = e.x_root - x0, e.y_root - y0
        if abs(dx) + abs(dy) > self._px(3):
            self._widget_moved = True
        self._widget.geometry(f"+{wx + dx}+{wy + dy}")

    def _widget_release(self, _e=None):
        if self._widget is None:
            return
        if self._widget_drag:
            if not getattr(self, "_widget_moved", False):
                self._widget_schedule_click()
            else:
                self._widget.update_idletasks()
                self._widget_pos = (self._widget.winfo_x(), self._widget.winfo_y())
                self._save_stats()
        self._widget_drag = None

    def _widget_schedule_click(self) -> None:
        self._cancel_widget_click()
        self._widget_click_job = self.root.after(220, self._widget_click)

    def _cancel_widget_click(self) -> None:
        if self._widget_click_job:
            try:
                self.root.after_cancel(self._widget_click_job)
            except Exception:
                pass
            self._widget_click_job = None

    def _widget_click(self) -> None:
        self._widget_click_job = None
        self._primary()

    def _widget_double_click(self, _e=None):
        self._cancel_widget_click()
        self._exit_widget_mode()
        return "break"

    def _widget_menu_popup(self, e):
        if self._widget_menu is not None:
            try:
                self._widget_menu.tk_popup(e.x_root, e.y_root)
            finally:
                self._widget_menu.grab_release()
        return "break"

    def _toggle_widget_mode(self):
        if self.widget_mode:
            self._exit_widget_mode()
        else:
            self._enter_widget_mode()

    def _enter_widget_mode(self) -> None:
        if self.widget_mode:
            return
        if self.focus_mode:
            self._toggle_focus_mode()
        self.widget_mode = True
        self._build_widget()
        self._refresh_widget()
        self.mini_pill.set_style("toggle_blue")
        self.root.withdraw()
        self._widget.lift()
        try:
            self._widget.focus_force()
        except Exception:
            pass

    def _exit_widget_mode(self) -> None:
        if not self.widget_mode:
            return
        self.widget_mode = False
        self._cancel_widget_click()
        if self._widget is not None:
            try:
                self._widget.destroy()
            except Exception:
                pass
            self._widget = None
            self._widget_c = None
            self._widget_time = None
            self._widget_fill = None
            self._widget_menu = None
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass
        self.mini_pill.set_style("toggle")
        self._last_render_key = None
        self.root.after(80, lambda: (self._redo_ring(), self._render_ring(force=True)))

    # --------------------------------------------------------------- misc ---
    def _on_goal_change(self):
        self.goal = self.goal_var.get().strip()
        if self._ring_goal_item is not None:
            goal = (self.goal or "DEEP WORK SESSION").strip().upper()
            if len(goal) > 30:
                goal = goal[:29].rstrip() + "\u2026"
            self.ring.itemconfigure(self._ring_goal_item, text=goal)

    def _on_close(self):
        if self._closing:
            return
        self._closing = True
        if self.running:
            self.elapsed = self.elapsed_now()
        if self.break_running:
            self.break_elapsed = self.break_elapsed_now()
        self._save_stats()
        keep_awake(False)
        try:
            if self._after_job:
                self.root.after_cancel(self._after_job)
            if self._conf_job:
                self.root.after_cancel(self._conf_job)
            self._cancel_break_job()
            self._cancel_widget_click()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


def main() -> None:
    _enable_dpi_awareness()
    root = tk.Tk()
    FocusForge(root, demo="--demo" in sys.argv)
    root.mainloop()


if __name__ == "__main__":
    main()
