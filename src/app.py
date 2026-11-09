"""FocusForge - a deep work / study challenge timer for Windows, macOS and Linux.

A single-file tkinter application with a custom rendered UI:
  * circular progress ring with gradient + glow
  * pause / resume, reset, +5 min, custom durations (25m .. 24h)
  * live stats (today, streak, sessions), persisted to the per-user data dir
  * always-on-top and keep-awake toggles
  * fullscreen focus mode, keyboard shortcuts, completion confetti + chime
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import wave
from datetime import date, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

try:
    import winsound
except Exception:  # pragma: no cover - non Windows
    winsound = None

APP_NAME = "FocusForge"
VERSION = "1.0.0"

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"


def _default_data_dir() -> Path:
    """Return the per-user data directory for the current OS.

    ``FOCUSFORGE_DATA_DIR`` overrides the location (used by the tests and by
    people who want a portable install).
    """
    override = os.environ.get("FOCUSFORGE_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    elif IS_MACOS:
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / APP_NAME


DATA_DIR = _default_data_dir()
DATA_FILE = DATA_DIR / "stats.json"

# Font families differ per platform; Tk silently falls back if one is missing.
if IS_WINDOWS:
    UI_FONT = "Segoe UI"
    UI_FONT_SEMIBOLD = "Segoe UI Semibold"
    MONO_FONT = "Cascadia Mono SemiBold"
elif IS_MACOS:
    UI_FONT = "Helvetica Neue"
    UI_FONT_SEMIBOLD = "Helvetica Neue"
    MONO_FONT = "Menlo"
else:
    UI_FONT = "DejaVu Sans"
    UI_FONT_SEMIBOLD = "DejaVu Sans"
    MONO_FONT = "DejaVu Sans Mono"

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

RING_STOPS = [
    (0.0, (76, 141, 255)),
    (0.55, (34, 211, 238)),
    (1.0, (52, 211, 153)),
]

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


_GRAD_GRID: Image.Image | None = None
_GRAD_CACHE: dict[int, Image.Image] = {}
_RING_CACHE: dict[int, dict] = {}
_ALPHA_HALF = [int(v * 0.50) for v in range(256)]


def ring_gradient(size: int) -> Image.Image:
    """Cached blue -> cyan -> mint vertical gradient."""
    global _GRAD_GRID
    cached = _GRAD_CACHE.get(size)
    if cached is not None:
        return cached
    if _GRAD_GRID is None:
        base = Image.linear_gradient("L")
        luts = [
            [lerp_stops(RING_STOPS, v / 255.0)[ch] for v in range(256)] for ch in range(3)
        ]
        _GRAD_GRID = Image.merge("RGB", tuple(base.point(lut) for lut in luts))
    grad = _GRAD_GRID.resize((size, size), Image.BILINEAR)
    _GRAD_CACHE[size] = grad
    return grad


def _ring_assets(diameter: int) -> dict:
    assets = _RING_CACHE.get(diameter)
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

    assets = {
        "S": S,
        "pad": pad,
        "w": w,
        "box": box,
        "track": track,
        "annulus": annulus,
        "grad": ring_gradient(diameter),
        "glow_size": max(12, diameter // 2),
    }
    _RING_CACHE[diameter] = assets
    if len(_RING_CACHE) > 6:
        _RING_CACHE.pop(next(iter(_RING_CACHE)))
    return assets


def render_ring(diameter: int, frac: float) -> Image.Image:
    """Anti-aliased progress ring with a soft glow, drawn with Pillow."""
    diameter = max(48, int(diameter))
    a = _ring_assets(diameter)
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
    glow = Image.new("RGBA", (diameter, diameter), (34, 150, 255, 255))
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


def flash_taskbar(root: tk.Misc | None = None) -> None:
    """Get the user's attention when a challenge finishes (per platform)."""
    try:
        if IS_WINDOWS:
            hwnd = None
            if root is not None:
                hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            hwnd = hwnd or ctypes.windll.user32.GetForegroundWindow()

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
        elif IS_MACOS and shutil.which("osascript"):
            subprocess.Popen(
                ["osascript", "-e",
                 'display notification "Challenge complete" with title "FocusForge"'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
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


_AWAKE_PROC: subprocess.Popen | None = None
_AWAKE_LOCK = threading.Lock()


def _stop_awake_proc() -> None:
    global _AWAKE_PROC
    if _AWAKE_PROC is None:
        return
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(_AWAKE_PROC.pid), signal.SIGTERM)
        else:
            _AWAKE_PROC.terminate()
    except Exception:
        try:
            _AWAKE_PROC.terminate()
        except Exception:
            pass
    _AWAKE_PROC = None


def keep_awake(enabled: bool) -> None:
    """Stop the OS from sleeping/blanking the screen while a timer runs."""
    if IS_WINDOWS:
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ES_DISPLAY_REQUIRED = 0x00000002
        try:
            flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED if enabled else 0)
            ctypes.windll.kernel32.SetThreadExecutionState(flags)
        except Exception:
            pass
        return

    global _AWAKE_PROC
    with _AWAKE_LOCK:
        if enabled:
            if _AWAKE_PROC is not None and _AWAKE_PROC.poll() is None:
                return
            argv = None
            if IS_MACOS and shutil.which("caffeinate"):
                argv = ["caffeinate", "-dimsu"]
            elif shutil.which("systemd-inhibit"):
                argv = [
                    "systemd-inhibit",
                    "--what=idle:sleep",
                    "--who=FocusForge",
                    "--why=Focus timer running",
                    "sleep", "infinity",
                ]
            if not argv:
                return
            try:
                _AWAKE_PROC = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except Exception:
                _AWAKE_PROC = None
        else:
            _stop_awake_proc()


def _write_tone_wav(path: str, notes, rate: int = 44100) -> None:
    """Render a short sequence of (frequency, duration_ms) sine tones to a WAV."""
    frames = bytearray()
    for freq, dur_ms in notes:
        count = max(1, int(rate * dur_ms / 1000.0))
        fade = max(1, int(rate * 0.006))
        for i in range(count):
            env = min(1.0, i / fade, (count - i) / fade)
            sample = int(0.30 * 32767 * env * math.sin(2 * math.pi * freq * i / rate))
            frames += sample.to_bytes(2, "little", signed=True)
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(frames))


def play_tones(notes) -> None:
    """Play milestone/completion chimes on Windows, macOS and Linux."""
    if not notes:
        return

    def run():
        if IS_WINDOWS:
            if not winsound:
                return
            for freq, dur in notes:
                try:
                    winsound.Beep(int(freq), int(dur))
                except Exception:
                    pass
            return

        path = None
        try:
            fd, path = tempfile.mkstemp(prefix="focusforge-", suffix=".wav")
            os.close(fd)
            _write_tone_wav(path, notes)
            if IS_MACOS and shutil.which("afplay"):
                subprocess.run(["afplay", path], check=False, timeout=15)
                return
            players = (
                ["paplay"], ["aplay", "-q"],
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"],
            )
            for player in players:
                if shutil.which(player[0]):
                    subprocess.run(player + [path], check=False, timeout=15)
                    return
        except Exception:
            pass
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    threading.Thread(target=run, daemon=True).start()


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
    }

    def __init__(self, master, text, command=None, w=100, h=38, radius=12,
                 style="ghost", font=(UI_FONT_SEMIBOLD, -12), bg=None):
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
                 font=(UI_FONT_SEMIBOLD, -int(14 * s))).pack(anchor="w")
        tk.Label(wrap, text="How long is this challenge?", bg=BG, fg=MUTED,
                 font=(UI_FONT, -int(11 * s))).pack(anchor="w", pady=(2, int(16 * s)))

        row = tk.Frame(wrap, bg=BG)
        row.pack()
        self.hours = self._field(row, "HOURS", initial_minutes // 60, s)
        tk.Label(row, text=":", bg=BG, fg=DIM,
                 font=(UI_FONT_SEMIBOLD, -int(22 * s))).pack(side="left", padx=int(8 * s), pady=(int(14 * s), 0))
        self.minutes = self._field(row, "MINUTES", initial_minutes % 60, s)

        self.preview = tk.Label(wrap, text="", bg=BG, fg=ACCENT,
                                font=(MONO_FONT, -int(15 * s)))
        self.preview.pack(pady=(int(14 * s), int(4 * s)))
        self.error = tk.Label(wrap, text="", bg=BG, fg=ROSE,
                              font=(UI_FONT, -int(10 * s)))
        self.error.pack()

        btns = tk.Frame(wrap, bg=BG)
        btns.pack(pady=(int(14 * s), 0))
        Pill(btns, "CANCEL", command=self.destroy, w=int(104 * s), h=int(40 * s),
             radius=int(11 * s), style="ghost", font=(UI_FONT_SEMIBOLD, -int(11 * s)), bg=BG).pack(side="left", padx=(0, int(10 * s)))
        Pill(btns, "SET TIMER", command=self._ok, w=int(126 * s), h=int(40 * s),
             radius=int(11 * s), style="primary", font=(UI_FONT_SEMIBOLD, -int(11 * s)), bg=BG).pack(side="left")

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
                 font=(UI_FONT_SEMIBOLD, -int(8 * s))).pack(anchor="w", pady=(0, int(3 * s)))
        var = tk.StringVar(value=str(value))
        entry = tk.Entry(box, textvariable=var, width=4, justify="center", bg=CARD, fg=TEXT,
                         insertbackground=ACCENT, relief="flat", bd=0,
                         highlightthickness=1, highlightbackground=STROKE, highlightcolor=ACCENT,
                         font=(MONO_FONT, -int(24 * s)))
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
        self.aot = False
        self.awake = True
        self.focus_mode = False
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
        self._ring_size = 0
        self._resize_job = None
        self._closing = False
        self._btn_label = ""

        self.data = self._load_stats()
        self.goal = str(self.data.get("goal", "") or "")
        self.target = int(self.data.get("last_target", 1440 * 60) or 1440 * 60)
        self.target = max(60, min(self.target, 168 * 3600))

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
    def _set_window_icon(self, root: tk.Tk) -> None:
        try:
            if IS_WINDOWS:
                icon = resource_path(os.path.join("assets", "icon.ico"))
                if os.path.exists(icon):
                    root.iconbitmap(icon)
                return
            png = resource_path(os.path.join("assets", "logo.png"))
            if os.path.exists(png):
                photo = tk.PhotoImage(file=png)
                root.iconphoto(True, photo)
                root._icon_photo = photo  # type: ignore[attr-defined]
        except Exception:
            pass

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
        self._set_window_icon(r)
        r.protocol("WM_DELETE_WINDOW", self._on_close)

        self.f_title = (UI_FONT_SEMIBOLD, -self._px(17))
        self.f_tiny = (UI_FONT_SEMIBOLD, -self._px(7))
        self.f_btn = (UI_FONT_SEMIBOLD, -self._px(12))
        self.f_chip = (UI_FONT_SEMIBOLD, -self._px(10))
        self.f_small = (UI_FONT_SEMIBOLD, -self._px(9))
        self.f_label = (UI_FONT_SEMIBOLD, -self._px(8))
        self.f_time = (MONO_FONT, -self._px(44))
        self.f_goal = (UI_FONT_SEMIBOLD, -self._px(10))
        self.f_sub = (UI_FONT, -self._px(11))
        self.f_entry = (UI_FONT, -self._px(12))
        self.f_stat = (UI_FONT_SEMIBOLD, -self._px(19))
        self.f_foot = (UI_FONT, -self._px(9))

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
        self.reset_pill = Pill(inner, "RESET", command=self.reset, w=self._px(104), h=self._px(46),
                               radius=self._px(12), style="ghost", font=self.f_small, bg=BG)
        self.reset_pill.pack(side="left", pady=self._px(3))
        self.primary_pill = Pill(inner, "START", command=self._primary, w=self._px(168), h=self._px(52),
                                 radius=self._px(14), style="primary", font=self.f_btn, bg=BG)
        self.primary_pill.pack(side="left", padx=self._px(10))
        self.plus_pill = Pill(inner, "+5 MIN", command=self.add_time, w=self._px(104), h=self._px(46),
                              radius=self._px(12), style="ghost", font=self.f_small, bg=BG)
        self.plus_pill.pack(side="left", pady=self._px(3))

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
        tk.Label(footer, text="SPACE  pause    R  reset    F11  focus mode",
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

    def start(self):
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
        if self.done:
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
        self._soft_reset()
        self._flash("TIMER RESET", 1.6, MUTED)
        self._render_ring(force=True)
        self._refresh_buttons()
        self._save_stats()

    def add_time(self, seconds: int = 300):
        if self.done:
            self._soft_reset()
        self.target = max(60, min(self.target + seconds, 168 * 3600))
        self._last_render_key = None
        self._flash(f"+{seconds // 60} MIN ADDED", 1.8, MINT)
        self._render_ring(force=True)
        self._sync_preset_chips()
        self._save_stats()

    def set_target(self, seconds: int, custom: bool = False):
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
        keep_awake(self.awake and self.running)

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
        f_goal = (UI_FONT_SEMIBOLD, -max(7, int(self._px(10) * k)))
        f_small = (UI_FONT_SEMIBOLD, -max(7, int(self._px(9) * k)))
        f_time = (MONO_FONT, -max(18, int(self._px(44) * k)))
        f_sub = (UI_FONT, -max(8, int(self._px(11) * k)))

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
        frac = 1.0 if self.done else self.progress()
        key = (round(frac, 5), self.done, self._ring_size)
        if not force and key == self._last_render_key:
            return
        self._last_render_key = key
        img = render_ring(self._ring_size, frac)
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
        rem = self.remaining()
        self._render_ring()

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

        # status line (also used for flash messages)
        if self._ring_status_item is not None:
            now = time.monotonic()
            if self._flash_msg and now < self._flash_until:
                age = self._flash_until - now
                pulse = 0.60 + 0.40 * (0.5 + 0.5 * math.sin(now * 5.5))
                col = rgb_hex(mix(hex_rgb(self._flash_color), hex_rgb(BG), 0.15 + 0.35 * (1 - pulse)))
                self.ring.itemconfigure(self._ring_status_item, text=" ".join(self._flash_msg),
                                        fill=col)
            elif self.done:
                self.ring.itemconfigure(self._ring_status_item, text=" ".join("COMPLETE"), fill=MINT)
            elif self.running:
                self.ring.itemconfigure(self._ring_status_item, text=" ".join("FOCUSING"), fill=ACCENT)
            elif self.elapsed_now() > 0:
                self.ring.itemconfigure(self._ring_status_item, text=" ".join("PAUSED"), fill=AMBER)
            else:
                self.ring.itemconfigure(self._ring_status_item, text=" ".join("READY"), fill=MUTED)

        self._refresh_buttons()
        self._refresh_stats()
        self._update_title(rem)

    def _refresh_buttons(self):
        if self.done:
            label = "NEW SESSION"
        elif self.running:
            label = "PAUSE"
        elif self.elapsed_now() > 0:
            label = "RESUME"
        else:
            label = "START"
        if label != self._btn_label:
            self._btn_label = label
            self.primary_pill.set_text(label)
            self.primary_pill.set_style("primary")

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

    def _update_title(self, rem: float):
        if self.running:
            title = f"{fmt_hms(rem)}  -  {APP_NAME}"
        elif self.done:
            title = f"COMPLETE  -  {APP_NAME}"
        elif self.elapsed_now() > 0:
            title = f"{fmt_hms(rem)}  paused  -  {APP_NAME}"
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
        self._beep([(784, 130), (988, 130), (1175, 150), (1568, 420)])
        flash_taskbar(self.root)

    def _log_session(self):
        self.data["sessions"].append({
            "goal": self.goal or "Deep work",
            "minutes": round(self.target / 60),
            "finished": datetime.now().isoformat(timespec="seconds"),
        })
        self.data["sessions"] = self.data["sessions"][-100:]

    def _beep(self, notes):
        play_tones(notes)

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

    # -------------------------------------------------------------- dialog --
    def _open_custom(self):
        DurationDialog(self, max(1, int(round(self.target / 60))))

    # ---------------------------------------------------------------- keys --
    def _bind_keys(self):
        self.root.bind("<space>", self._key_space)
        self.root.bind("<Key-r>", self._key_reset)
        self.root.bind("<Key-R>", self._key_reset)
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
        self.toggle()
        return "break"

    def _key_reset(self, _e=None):
        if self._typing():
            return
        self.reset()
        return "break"

    def _key_focus(self, _e=None):
        self._toggle_focus_mode()
        return "break"

    def _key_escape(self, _e=None):
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
        self._save_stats()
        keep_awake(False)
        try:
            if self._after_job:
                self.root.after_cancel(self._after_job)
            if self._conf_job:
                self.root.after_cancel(self._conf_job)
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
