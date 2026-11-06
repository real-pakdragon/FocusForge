"""Generate the application icon (.ico) and a preview PNG from the same artwork."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import app  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
os.makedirs(ASSETS, exist_ok=True)

master = app.make_logo(512)
master.save(os.path.join(ASSETS, "logo.png"))
master.save(
    os.path.join(ASSETS, "icon.ico"),
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print("wrote", os.path.join(ASSETS, "icon.ico"))
print("wrote", os.path.join(ASSETS, "logo.png"))
