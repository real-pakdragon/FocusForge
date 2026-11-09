"""Headless-ish smoke test: builds the UI, pumps the event loop, checks layout."""

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

# keep the test away from the real profile
_TMP_PROFILE = tempfile.mkdtemp(prefix="focusforge-test-")
os.environ["FOCUSFORGE_DATA_DIR"] = _TMP_PROFILE

import app as ff  # noqa: E402

ff._enable_dpi_awareness()
root = app = None
failures = []
DATA_DIR_OVERRIDE_OK = str(ff.DATA_DIR) == _TMP_PROFILE


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
pump(0.8)

W, H = root.winfo_width(), root.winfo_height()
print(f"window {W}x{H}  scale={a.s}  ring={a._ring_size}px")
check("data dir override honored", DATA_DIR_OVERRIDE_OK, str(ff.DATA_DIR))
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

# focus mode
a._toggle_focus_mode()
check("fullscreen focus mode", wait_for(lambda: a.focus_mode))
check("topbar hidden in focus", wait_for(lambda: not a._children[0][0].winfo_ismapped()))
a._toggle_focus_mode()
check("back from focus", wait_for(lambda: a._children[0][0].winfo_ismapped()))
pump(0.4)

# always on top + awake toggles
a._toggle_pin()
check("pin toggled", a.aot)
a._toggle_pin()
a._toggle_awake()
check("awake toggled", not a.awake)
a._toggle_awake()

# close
a._on_close()
shutil.rmtree(_TMP_PROFILE, ignore_errors=True)
print()
if failures:
    print("FAILURES:", ", ".join(failures))
    sys.exit(1)
print("ALL CHECKS PASSED")
