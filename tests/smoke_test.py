"""Headless-ish smoke test: builds the UI, pumps the event loop, checks layout."""

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

# keep the test away from the real profile
_TMP_PROFILE = tempfile.mkdtemp(prefix="focusforge-test-")
os.environ["APPDATA"] = _TMP_PROFILE

import app as ff  # noqa: E402

ff._enable_dpi_awareness()
root = app = None
failures = []


def check(name, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        failures.append(name)


def pump(seconds=1.0):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        time.sleep(0.02)
        if cond():
            return True
    return False


root = ff.tk.Tk()
a = ff.FocusForge(root)
a._muted = True          # keep the test quiet
a._beep = lambda notes: None
pump(0.8)

W, H = root.winfo_width(), root.winfo_height()
print(f"window {W}x{H}  scale={a.s}  ring={a._ring_size}px")
check("ring items built", a._ring_img_item is not None)
check("ring size sane", 200 <= a._ring_size <= W, f"{a._ring_size}")
check("time item present", a._ring_time_item is not None)
check("time text is 24:00:00", a.ring.itemcget(a._ring_time_item, "text") == "24:00:00",
      a.ring.itemcget(a._ring_time_item, "text"))

bottom = 0
for w, _ in a._children:
    if w.winfo_ismapped():
        bottom = max(bottom, w.winfo_y() + w.winfo_height())
check("layout fits window", bottom <= H, f"bottom={bottom} H={H}")
right = a.rest_pill.winfo_x() + a.rest_pill.winfo_width()
check("rest button present", a.rest_pill.itemcget(a.rest_pill._txt_item, "text").startswith("REST"))
check("controls fit width", right <= a.rest_pill.master.winfo_width(),
      f"{right} / {a.rest_pill.master.winfo_width()}")

# start / pause / resume
a.start()
pump(0.6)
check("running", a.running)
check("primary says PAUSE", a.primary_pill.itemcget(a.primary_pill._txt_item, "text") == "PAUSE")
check("elapsed advances", a.elapsed_now() > 0.3, f"{a.elapsed_now():.2f}")

a.pause()
pump(0.35)
check("paused", not a.running)
check("primary says RESUME", a.primary_pill.itemcget(a.primary_pill._txt_item, "text") == "RESUME")
frozen = a.elapsed_now()
pump(0.4)
check("elapsed frozen while paused", abs(a.elapsed_now() - frozen) < 0.01)

# presets
a.set_target(25 * 60)
pump(0.4)
check("target 25m", a.target == 1500)
check("preset chip highlighted", a.preset_pills[25].style_name == "chip_on")
check("display reset", a.ring.itemcget(a._ring_time_item, "text") == "00:25:00")

# add time
a.add_time(300)
pump(0.2)
check("add 5 min", a.target == 1800)

# custom duration
a.set_target(90 * 60, custom=True)
pump(0.2)
check("custom duration", a.target == 5400)
check("custom chip on", a.custom_pill.style_name == "chip_on")

# goal text
a.goal_var.set("Study math - 24h challenge")
pump(0.2)
check("goal mirrored in ring",
      a.ring.itemcget(a._ring_goal_item, "text") == "STUDY MATH - 24H CHALLENGE")

# completion path
a.set_target(2 * 60)
a.start()
a.elapsed = a.target - 0.15
pump(1.2)
check("completed", a.done)
check("primary says NEW SESSION",
      a.primary_pill.itemcget(a.primary_pill._txt_item, "text") == "NEW SESSION")
check("session logged", len(a.data["sessions"]) >= 1)
check("rest timer queued", a._break_job is not None)
# the finish firework + confetti always play before the rest timer takes over
check("firework plays before rest", a.done and not a.break_active)
a._arm_break_after_celebration()
check("auto rest starts", wait_for(lambda: a.break_active, 4.0))
pump(0.35)
check("rest is running", a.break_running and not a.break_done)
check("rest shows time", a.ring.itemcget(a._ring_time_item, "text").startswith("00:0"),
      a.ring.itemcget(a._ring_time_item, "text"))
check("rest status line", a.ring.itemcget(a._ring_status_item, "text") == "R E S T I N G",
      a.ring.itemcget(a._ring_status_item, "text"))
check("primary says SKIP BREAK",
      a.primary_pill.itemcget(a.primary_pill._txt_item, "text") == "SKIP BREAK")
check("skip button is mint", a.primary_pill.style_name == "break_btn")
check("rest uses break palette", a._last_render_key[1][0] == "break")

a.skip_break()
pump(0.35)
check("rest skipped", not a.break_active and not a.break_done)
check("back to ready", not a.done and a.primary_pill.itemcget(
    a.primary_pill._txt_item, "text") == "START")
check("skip message shown", "BREAK" in a._flash_msg)
check("ready status returns", wait_for(
    lambda: a.ring.itemcget(a._ring_status_item, "text") == "R E A D Y", 3.0))

# a full rest countdown plays out and returns to ready on its own
a.start_break()
a.break_target = 1
a.break_started_at -= 2.0
check("rest completes", wait_for(lambda: a.break_done and not a.break_running, 2.5))
check("rest complete status", a.ring.itemcget(a._ring_status_item, "text").replace(" ", "") == "RESTCOMPLETE",
      a.ring.itemcget(a._ring_status_item, "text"))
check("rest auto dismisses", wait_for(lambda: not a.break_active and not a.done, 5.0))
check("rest state cleared", a.break_elapsed == 0.0 and a.break_target == ff.BREAK_SECONDS)

# manual REST button: pauses the session, then hands back where it left off
a.set_target(25 * 60)
a.start()
pump(0.9)
before = a.elapsed_now()
a.start_rest(5)
pump(0.15)
check("manual break active", a.break_active and a.break_running and a.break_manual)
check("manual break is 5 min", a.break_target == 300)
check("session paused for break", not a.running)
check("session time frozen", abs(a.elapsed_now() - before) < 0.05, f"{a.elapsed_now():.2f}")
check("primary says BACK TO WORK",
      a.primary_pill.itemcget(a.primary_pill._txt_item, "text") == "BACK TO WORK")
check("rest pill says END REST",
      a.rest_pill.itemcget(a.rest_pill._txt_item, "text") == "END REST")
pump(1.1)
check("break clock counts", a.break_elapsed_now() >= 0.9, f"{a.break_elapsed_now():.2f}")
check("session still frozen", abs(a.elapsed_now() - before) < 0.05)
a.skip_break()
pump(0.35)
check("break skipped returns to focus", a.running and not a.break_active)
check("session kept its time", a.elapsed_now() >= before - 0.05, f"{a.elapsed_now():.2f}")
a.pause()
a.reset()
pump(0.2)

# a 10 minute break runs out and resumes the session on its own
a.set_target(25 * 60)
a.start()
pump(0.6)
kept = a.elapsed_now()
a.start_rest(10)
check("10 min break length", a.break_target == 600)
a.break_started_at -= 601.0
check("manual break completes",
      wait_for(lambda: a.break_done and not a.break_running, 2.5))
check("break complete status",
      a.ring.itemcget(a._ring_status_item, "text").replace(" ", "") == "BREAKCOMPLETE",
      a.ring.itemcget(a._ring_status_item, "text"))
check("manual break resumes", wait_for(lambda: not a.break_active and a.running, 5.0))
check("resumed at kept time", a.elapsed_now() >= kept - 0.05, f"{a.elapsed_now():.2f}")
a.pause()
a.reset()
pump(0.2)

# focus mode
a._toggle_focus_mode()
check("fullscreen focus mode", wait_for(lambda: a.focus_mode))
check("topbar hidden in focus", wait_for(lambda: not a._children[0][0].winfo_ismapped()))
a._toggle_focus_mode()
check("back from focus", wait_for(lambda: a._children[0][0].winfo_ismapped()))
pump(0.4)

# mini widget mode
class _E:
    def __init__(self, xr, yr):
        self.x_root, self.y_root = xr, yr

a._toggle_widget_mode()
check("widget created", a._widget is not None)
check("main window hidden", wait_for(lambda: root.state() == "withdrawn"))
check("widget mapped", wait_for(lambda: a._widget is not None and a._widget.winfo_ismapped()))
check("widget stays on top", bool(a._widget.attributes("-topmost")))
check("widget shows time", a._widget_c.itemcget(a._widget_time, "text") == ff.fmt_hms(a.remaining()))
check("mini chip lit", a.mini_pill.style_name == "toggle_blue")
wx, wy = a._widget.winfo_x(), a._widget.winfo_y()
a._widget_press(_E(wx + 20, wy + 20))
a._widget_motion(_E(wx + 120, wy + 90))
a._widget_release(_E(wx + 120, wy + 90))
pump(0.2)
check("widget dragged", a._widget_pos == (wx + 100, wy + 70), f"{a._widget_pos}")
a._widget_double_click()
check("widget closed", a._widget is None)
check("main window restored", wait_for(lambda: root.state() == "normal"))
check("mini chip reset", a.mini_pill.style_name == "toggle")
pump(0.4)

# always on top + awake toggles
a._toggle_pin()
check("pin toggled", a.aot)
a._toggle_pin()
a._toggle_awake()
check("awake toggled", not a.awake)
a._toggle_awake()

# finish sounds are synthesised as valid mono 16-bit PCM wav data
fw = ff.build_firework_wav()
ch = ff.build_chime_wav()
for name, data, min_len in (("firework", fw, 150000), ("chime", ch, 80000)):
    check(f"{name} wav header", data[:4] == b"RIFF" and data[8:12] == b"WAVE"
          and data[36:40] == b"data", f"{len(data)} bytes")
    check(f"{name} wav length", len(data) >= min_len, f"{len(data)} bytes")
ff.preload_sounds()
check("sounds preloaded", isinstance(ff._FIREWORK_WAV, bytes) and isinstance(ff._CHIME_WAV, bytes))

# the rest palette is visually distinct from the focus palette
focus_ring = ff.render_ring(320, 0.5, "focus")
break_ring = ff.render_ring(320, 0.5, "break")
check("break ring differs from focus", focus_ring.tobytes() != break_ring.tobytes())

# close
a._on_close()
shutil.rmtree(_TMP_PROFILE, ignore_errors=True)
print()
if failures:
    print("FAILURES:", ", ".join(failures))
    sys.exit(1)
print("ALL CHECKS PASSED")
