<p align="center">
  <a href="https://github.com/real-pakdragon/FocusForge/releases/latest">
    <img src="docs/banner.png" alt="FocusForge — a deep work timer for Windows, macOS and Linux" width="100%">
  </a>
</p>

<h3 align="center">A dark, distraction-free timer for long study challenges.</h3>

<p align="center">
  From a 25 minute pomodoro to a full 24 hour marathon — pause anytime,<br>
  keep your computer awake, and watch your streak grow.
</p>

<p align="center">
  <img alt="Windows 10 / 11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-4C8DFF?style=for-the-badge&logo=windows11&logoColor=white">
  <img alt="Linux" src="https://img.shields.io/badge/Linux-supported-34D399?style=for-the-badge&logo=linux&logoColor=white">
  <img alt="macOS" src="https://img.shields.io/badge/macOS-supported-34D399?style=for-the-badge&logo=apple&logoColor=white">
  <a href="https://github.com/real-pakdragon/FocusForge/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/real-pakdragon/FocusForge?style=for-the-badge&color=22D3EE"></a>
  <a href="https://github.com/real-pakdragon/FocusForge/releases"><img alt="Downloads" src="https://img.shields.io/github/downloads/real-pakdragon/FocusForge/total?style=for-the-badge&color=34D399"></a>
  <img alt="MIT License" src="https://img.shields.io/badge/license-MIT-A78BFA?style=for-the-badge">
</p>

<p align="center">
  <a href="#download"><b>Download</b></a> &nbsp;·&nbsp;
  <a href="#features">Features</a> &nbsp;·&nbsp;
  <a href="#screenshots">Screenshots</a> &nbsp;·&nbsp;
  <a href="#build-from-source">Build</a> &nbsp;·&nbsp;
  <a href="#faq">FAQ</a>
</p>

---

## Download

| | |
| :--- | :--- |
| **Installer** &nbsp;·&nbsp; recommended | **Portable** |
| [**`FocusForge-Setup-1.0.0.exe`**](https://github.com/real-pakdragon/FocusForge/releases/latest/download/FocusForge-Setup-1.0.0.exe) | [**`FocusForge.exe`**](https://github.com/real-pakdragon/FocusForge/releases/latest/download/FocusForge.exe) |
| 32 MB — installs per-user, **no admin rights**, adds Desktop + Start Menu shortcuts and a real uninstaller. | 30 MB — a single self-contained file. Double-click and go, no installation. |

> **Windows SmartScreen:** the builds are not code-signed yet, so Windows may show
> *"Windows protected your PC"* on first run. Click **More info → Run anyway**.
> You can verify what you downloaded against the SHA-256 checksums in the release notes.

**Requirements:** Windows 10 or 11 (64-bit). No Python, no .NET, no runtime to install.

### Linux and macOS

There are no pre-built installers for these platforms yet, but FocusForge runs
natively and every push is built and smoke-tested on Linux and macOS by CI. To
build it yourself, see [Build from source](#build-from-source):

```bash
git clone https://github.com/real-pakdragon/FocusForge.git
cd FocusForge
./build.sh          # dist/FocusForge on Linux, dist/FocusForge.app on macOS
./install.sh        # optional: add it to your applications menu / ~/Applications
```

Requirements: Python 3.10+ with tkinter and Pillow. On Debian/Ubuntu install
`sudo apt install python3-tk` (Fedora: `sudo dnf install python3-tkinter`).
Keep-awake uses `systemd-inhibit` on Linux and `caffeinate` on macOS; chimes use
`paplay`, `aplay` or `ffplay` when available and fall back silently otherwise.

## Features

| | |
| :--- | :--- |
| ⏱️ **Any challenge length** — presets for 25m, 1h, 2h, 4h, 6h, 12h and 24h, plus any custom duration from 1 minute to 168 hours. | ⏸️ **Pause, resume, reset** — one click or the space bar. Elapsed time is preserved exactly, even after hours. |
| ➕ **+5 minute top-up** — extend a running challenge without losing progress. | 🎯 **Session goal** — type what you're working on and it is shown inside the ring. |
| 🌀 **Animated progress ring** — anti-aliased gradient ring with a soft glow and rounded end caps. | 📊 **Live stats** — today's focus time, day streak and completed sessions, saved between launches. |
| 💡 **Keep awake** — stops your computer from sleeping or blanking the screen while the timer runs. | 📌 **Always on top** — keeps the timer above your notes and textbooks. |
| 🖥️ **Focus mode** — `F11` turns the app into a fullscreen clock with everything else hidden. | 🎉 **Finish celebration** — confetti, a chime and a taskbar flash or desktop notification when the challenge completes. |

**Milestone nudges** at 25%, 50%, 75% and 90% give you a quiet chime and a status line —
enough to notice, not enough to break concentration.

## Screenshots

<p align="center">
  <img src="docs/screenshot.png" width="378" alt="FocusForge main window during a 24 hour challenge">
  &nbsp;&nbsp;
  <img src="docs/screenshot-complete.png" width="378" alt="Completed challenge with confetti">
  <br>
  <em>Mid-challenge &nbsp;·&nbsp; Challenge complete</em>
</p>

<p align="center">
  <img src="docs/screenshot-focus.png" width="520" alt="Fullscreen focus mode">
  <br>
  <em>Focus mode — press F11</em>
</p>

## Keyboard shortcuts

| Key | Action |
| :---: | :--- |
| `Space` | Start / pause / resume |
| `R` | Reset the timer |
| `F11` | Toggle fullscreen focus mode |
| `Esc` | Leave focus mode |

## Install

### Windows installer (recommended)

1. Download [`FocusForge-Setup-1.0.0.exe`](https://github.com/real-pakdragon/FocusForge/releases/latest).
2. Double-click it and follow the wizard — it needs **no administrator rights**.

It installs to `%LOCALAPPDATA%\Programs\FocusForge`, creates Desktop and Start Menu
shortcuts, registers FocusForge in **Settings → Apps**, and ships a real uninstaller.
A running copy is closed automatically before files are replaced, so upgrades are safe.

Unattended install:

```powershell
.\FocusForge-Setup-1.0.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

### Windows portable

Grab [`FocusForge.exe`](https://github.com/real-pakdragon/FocusForge/releases/latest/download/FocusForge.exe)
and run it from anywhere — USB stick, OneDrive folder, whatever. Settings live in
`%APPDATA%\FocusForge`, so your stats follow you even if the exe moves.

## Build from source

Requires [Python 3.10+](https://www.python.org/). Inno Setup 6 is only needed for
the Windows installer step and can be installed without admin rights.

### Windows

```powershell
git clone https://github.com/real-pakdragon/FocusForge.git
cd FocusForge

python -m pip install pillow pyinstaller
winget install --id JRSoftware.InnoSetup --scope user

# runs the smoke test, builds dist\FocusForge.exe and release\FocusForge-Setup-1.0.0.exe
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

`build.ps1` skips the installer when Inno Setup is missing, so the portable `.exe`
always builds. To compile only the installer:

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

### Linux and macOS

The app needs Python 3.10+ with tkinter and Pillow. PyInstaller is installed by the
build script if it is missing.

```bash
git clone https://github.com/real-pakdragon/FocusForge.git
cd FocusForge

# Debian/Ubuntu: sudo apt install python3-tk
# Fedora:        sudo dnf install python3-tkinter
python3 -m pip install pillow pyinstaller

./build.sh     # smoke test + dist/FocusForge (Linux) or dist/FocusForge.app (macOS)
./install.sh   # optional: ~/.local/bin + applications menu entry on Linux,
               #           ~/Applications on macOS
```

On a headless Linux machine `build.sh` uses `xvfb-run` for the smoke test when it
is available.

Run straight from source while developing:

```bash
python3 src/app.py          # normal app
python3 src/app.py --demo   # posed demo state, never writes stats
```

Regenerate the artwork and docs images (the screenshot tool uses Windows APIs and
must run on Windows):

```bash
python3 tools/make_icon.py
python3 tools/make_banner.py
python3 tools/make_screenshots.py   # Windows only
```

## Where is my data stored?

Everything is local and human readable, in a per-user directory:

| Platform | Path |
| :--- | :--- |
| Windows | `%APPDATA%\FocusForge\stats.json` |
| macOS | `~/Library/Application Support/FocusForge/stats.json` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/FocusForge/stats.json` |

Set `FOCUSFORGE_DATA_DIR` to point at a different directory (useful for portable
installs); `stats.json` is written inside it.

It holds your per-day focus seconds, completed sessions, goal text and last used
duration. Delete the file and you start from zero — nothing leaves your computer.

## Uninstall

Use **Settings → Apps → FocusForge → Uninstall**, or run:

```powershell
& "$env:LOCALAPPDATA\Programs\FocusForge\unins000.exe"
```

This removes the app, shortcuts and registry entry. Your stats in
`%APPDATA%\FocusForge` are deliberately kept, so reinstalling preserves your history;
delete that folder by hand for a clean slate.

On Linux/macOS, delete the binary/app and its launcher:

```bash
# Linux
rm -f ~/.local/bin/focusforge ~/.local/share/applications/focusforge.desktop

# macOS
rm -rf ~/Applications/FocusForge.app
```

Your stats are kept in the platform data directory shown above.

## FAQ

**Does it need administrator rights?**
No. Both the installer and the app run entirely in your user profile.

**Will my computer go to sleep during a 24 hour challenge?**
Not while the timer is running and *AWAKE* is on. The app holds
`SetThreadExecutionState` on Windows, `systemd-inhibit` on Linux and `caffeinate`
on macOS to keep the system and display awake, and releases it on pause or exit.

**Does the timer keep counting if the computer sleeps anyway?**
Elapsed time is computed from a monotonic clock, not by counting ticks, so a pause,
a hitch or a slow frame never makes the timer drift.

**Can I use it on several PCs?**
Yes. The app is a per-user install, so run it on as many machines as you like.
Stats are per-machine.

**Does it run on macOS and Linux?**
Yes. The timer logic is pure Python and the Windows-only integrations have native
fallbacks: `systemd-inhibit`/`caffeinate` for keep-awake, `paplay`/`aplay`/`afplay`
for chimes, a desktop notification on macOS and a normal window title elsewhere.
Build it with `./build.sh`; see [Build from source](#build-from-source).

## Project layout

```text
FocusForge/
├── src/app.py                  # the whole application (tkinter + Pillow)
├── installer.iss               # Inno Setup script -> release\FocusForge-Setup-*.exe
├── assets/                     # icon, logo, version resource, wizard artwork
├── tools/
│   ├── make_icon.py            # icon + logo
│   ├── make_banner.py          # README hero banner
│   ├── make_screenshots.py     # docs screenshots from the real UI
│   └── make_installer_art.py   # Inno Setup wizard bitmaps
├── tests/smoke_test.py         # UI + state machine smoke test
├── build.ps1                   # test, package the exe, compile the installer
├── build.sh                    # test + package on Linux / macOS
├── install.ps1                 # script based per-user install (portable builds)
├── install.sh                  # per-user install on Linux / macOS
└── publish.ps1                 # create the GitHub repo and push
```

Build outputs:

```text
dist\FocusForge.exe                 Windows portable single file   (~30 MB)
release\FocusForge-Setup-1.0.0.exe  Windows installer              (~32 MB)
dist/FocusForge                     Linux single file
dist/FocusForge.app                 macOS app bundle
```

## Tech notes

The interface is drawn with `tkinter` canvases and custom Pillow-rendered images —
rounded panels, buttons and a gradient progress ring with a glow — so there are no
third-party UI frameworks and the executable stays small. Bitmaps and gradients are
cached per size, which keeps the once-a-second ring refresh in the low tens of
milliseconds even at fullscreen sizes. Platform-specific behaviour is isolated in
small helpers (`keep_awake`, `play_tones`, `flash_taskbar`, `_set_window_icon`)
with native implementations for Windows, macOS and Linux.

## License

[MIT](LICENSE) — free to use, modify and share.

---

<p align="center"><sub>Built for people who sit down to study math for 24 hours straight.</sub></p>
