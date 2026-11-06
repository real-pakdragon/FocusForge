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

### Installer (recommended)

1. Copy `FocusForge-Setup-1.0.0.exe` to any Windows 10/11 PC.
2. Double-click it and follow the wizard.

The installer is **per-user and needs no administrator rights**. It installs to
`%LOCALAPPDATA%\Programs\FocusForge`, adds a Desktop and Start Menu shortcut, creates a
real uninstaller and registers FocusForge in **Settings → Apps**. If an older copy is
running it is closed automatically before the files are replaced.

You can also run it unattended:

```powershell
.\FocusForge-Setup-1.0.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

### Portable executable

Prefer no installation? Run `FocusForge.exe` directly — it is a single self-contained
file with no dependencies and stores its data in `%APPDATA%\FocusForge`.

### Build from source

Requires [Python 3.10+](https://www.python.org/) on Windows, plus
[Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer step.

```powershell
git clone https://github.com/<your-user>/FocusForge.git
cd FocusForge

python -m pip install pillow pyinstaller
winget install --id JRSoftware.InnoSetup --scope user

# test, build dist\FocusForge.exe and release\FocusForge-Setup-1.0.0.exe
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

`build.ps1` skips the installer when Inno Setup is not installed, so the portable
`.exe` always builds. To compile only the installer, run:

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

The older script-based installer is still available for portable setups:

```powershell
# installs dist\FocusForge.exe per-user with shortcuts
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

Use **Settings → Apps → FocusForge → Uninstall**, or run the uninstaller directly:

```powershell
& "$env:LOCALAPPDATA\Programs\FocusForge\unins000.exe"
```

That removes the app, the shortcuts and the registry entry. Your stats in
`%APPDATA%\FocusForge` are deliberately left untouched, so reinstalling keeps your
history — delete that folder by hand if you want a clean slate.

## Project layout

```
FocusForge/
├── src/app.py                 # the whole application (tkinter + Pillow)
├── assets/                    # icon, logo, version resource, wizard artwork
├── installer.iss              # Inno Setup script -> release\FocusForge-Setup-*.exe
├── tools/make_icon.py         # regenerates assets/icon.ico + logo.png
├── tools/make_installer_art.py# regenerates the installer wizard bitmaps
├── tests/smoke_test.py        # UI + state machine smoke test
├── build.ps1                  # test + package .exe + compile the installer
├── install.ps1                # script based per-user install (portable builds)
└── publish.ps1                # create the GitHub repo and push
```

Build outputs:

```
dist\FocusForge.exe                 portable single file (~30 MB)
release\FocusForge-Setup-1.0.0.exe  installer for any Windows PC (~32 MB)
```

## Tech notes

The entire UI is drawn with `tkinter` canvases and custom Pillow-rendered images
(rounded panels, gradient ring, buttons), so there are no third-party UI frameworks
and the executable stays small and portable. Rendering is cached per size, which keeps
the 1-second ring refresh around a few dozen milliseconds even in fullscreen.

## License

[MIT](LICENSE)
