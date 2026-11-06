<p align="center">
  <img src="assets/logo.png" width="92" alt="FocusForge logo">
</p>

<h1 align="center">FocusForge</h1>

<p align="center">
  A deep-work challenge timer for Windows, built for long study sessions —
  from a 25 minute pomodoro to a full 24 hour marathon.
  <br>
  Dark, neon, distraction free. Pause anytime, track your streak, keep your PC awake.
</p>

<p align="center">
  <img alt="Windows 10/11" src="https://img.shields.io/badge/platform-Windows%2010%2F11-4C8DFF?style=flat-square">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-22D3EE?style=flat-square">
  <img alt="MIT License" src="https://img.shields.io/badge/license-MIT-34D399?style=flat-square">
</p>

![FocusForge screenshot](docs/screenshot.png)

## Features

- **Challenge presets** — 25m, 1h, 2h, 4h, 6h, 12h, 24h, plus any custom duration from 1 minute to 168 hours.
- **Pause / resume / reset** — pause with one click or the space bar; your elapsed time is preserved exactly.
- **+5 minute top-up** — extend the challenge without losing progress.
- **Animated progress ring** — crisp, anti-aliased gradient ring with a soft glow and rounded end caps.
- **Session goal** — type what you are working on (e.g. *Study math — 24h challenge*) and it is shown inside the ring.
- **Live stats** — today's focus time, day streak and completed sessions, saved between launches.
- **Keep awake** — prevents Windows from sleeping or blanking the screen while the timer runs.
- **Always on top** — keep the timer visible above your study material.
- **Fullscreen focus mode** — `F11` hides everything but the timer.
- **Milestone nudges** — quiet chimes at 25%, 50%, 75% and 90%.
- **Finish celebration** — confetti, a chime and a taskbar flash when the challenge is complete.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Space` | Start / pause / resume |
| `R` | Reset the timer |
| `F11` | Toggle fullscreen focus mode |
| `Esc` | Leave focus mode |

## Install

### From the prebuilt executable

1. Download `FocusForge.exe` from the releases page (or build it yourself, below).
2. Run it. No installer, no dependencies — it is a single self-contained file.

### Build from source

Requires [Python 3.10+](https://www.python.org/) on Windows.

```powershell
git clone https://github.com/<your-user>/FocusForge.git
cd FocusForge

python -m pip install pillow pyinstaller

# build dist\FocusForge.exe
powershell -ExecutionPolicy Bypass -File .\build.ps1

# install to %LOCALAPPDATA%\Programs\FocusForge,
# add Desktop + Start Menu shortcuts and launch it
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Run from source while developing:

```powershell
python src\app.py
```

## Publish this repository to GitHub

```powershell
winget install --id GitHub.cli
powershell -ExecutionPolicy Bypass -File .\publish.ps1
```

The script signs you in, creates the repository and pushes `main`.
Pass `-Visibility private` (or a different `-Repo` name) if you want.

Every push runs `.github/workflows/build.yml` on GitHub Actions, which tests the app
and uploads a freshly built `FocusForge.exe` artifact.

## Where is my data stored?

Everything is local and human readable:

```
%APPDATA%\FocusForge\stats.json
```

It holds your per-day focus seconds, completed sessions, goal text and last used duration.
Deleting the file simply starts you from zero.

## Uninstall

Use **Settings → Apps → FocusForge → Uninstall**, or run:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Programs\FocusForge\Uninstall.ps1"
```

That removes the app, the shortcuts, the registry entry and your local stats.

## Project layout

```
FocusForge/
├── src/app.py              # the whole application (tkinter + Pillow)
├── assets/                 # icon, logo, Windows version resource
├── tools/make_icon.py      # regenerates assets/icon.ico + logo.png
├── tests/smoke_test.py     # UI + state machine smoke test
├── build.ps1               # test + package into one .exe
└── install.ps1             # per-user install + shortcuts
```

## Tech notes

The entire UI is drawn with `tkinter` canvases and custom Pillow-rendered images
(rounded panels, gradient ring, buttons), so there are no third-party UI frameworks
and the executable stays small and portable. Rendering is cached per size, which keeps
the 1-second ring refresh around a few dozen milliseconds even in fullscreen.

## License

[MIT](LICENSE)
