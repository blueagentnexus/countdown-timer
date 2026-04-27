# Countdown Clock

A simple always-on-top countdown widget for Windows. Days / hours / minutes / seconds to any target date. **Now supports multiple independent timers** — track as many countdowns as you want, each with its own settings and window.

## Install (Windows Desktop)

### Option A — Download the prebuilt EXE (easiest)

1. Go to the [Releases page](https://github.com/blueagentnexus/countdown-timer/releases).
2. Download `CountdownClock.exe` from the latest release.
3. Move it somewhere permanent (e.g. `C:\Users\<you>\Apps\CountdownClock\`).
4. Double-click `CountdownClock.exe` to run.
5. (Optional) Right-click the EXE → **Send to → Desktop (create shortcut)** to pin it to your desktop.
6. (Optional) To launch at Windows startup: open the app, click the three-dot menu (top-right), and toggle **Run at Windows Startup**.

> Windows SmartScreen may warn the first time you run an unsigned EXE. Click **More info → Run anyway**.

### Option B — Run from source (Python 3.10+)

```powershell
# 1. Clone the repo
git clone https://github.com/blueagentnexus/countdown-timer.git
cd countdown-timer

# 2. Run it (no third-party dependencies — pure stdlib + tkinter)
python countdown_clock.py

# 3. (Optional) Install desktop + startup shortcuts
python install_shortcuts.py --startup
```

### Option C — Build the EXE yourself

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name CountdownClock --icon stopwatch_smiley.ico countdown_clock.py
# Output: dist\CountdownClock.exe
```

## Features

- **Multiple timers** — add as many independent countdowns as you want from the **menu → New Timer**. Each has its own target, label, font, colors, and position.
- **Per-timer hide/show** — the **✕** button hides one timer (others keep ticking). Reopen it from any other timer's **menu → Show Hidden Timers**.
- **Permanent delete** — only via **menu → Delete This Timer** (with confirmation), so you can't lose a timer by accident.
- **Countdown** in days + hours + minutes + seconds to a configurable target date and time.
- **Calendar picker** runs **Sunday → Saturday** (US-style week).
- **12-hour time picker** with AM/PM.
- **Persistent state** — every timer reopens with the same target, position, colors, and font.
- **Borderless, draggable** — click and drag anywhere on the clock to move it.
- **Resizable** — drag the small handle in the bottom-right corner. Font scales with height.
- **Always on top** — toggle from the settings menu.
- **Three-dot settings menu** in the top-right (or right-click anywhere on the clock).
- **Font color + family + size** — all configurable.
- **Background color** configurable too.
- **Label** — optional small caption above the numbers.
- **Run at Windows startup** — toggle from the settings menu.

## Shortcuts (source install)

From the repo folder:

- **Desktop icon only:** `python install_shortcuts.py`
- **Desktop + launch at Windows startup:** `python install_shortcuts.py --startup`
- **Remove shortcuts:** `python install_shortcuts.py --remove`

You can also toggle "Run at Windows Startup" directly from the app's settings menu.

## Settings File

Settings live here:

```
%APPDATA%\CountdownClock\settings.json
```

Delete that file to reset to defaults.

## Tips

- **Stuck borderless window?** The three-dot menu is in the top-right. The small × next to it hides that timer (others stay open). The app exits gracefully if you hide your last visible timer; relaunch to bring everything back.
- **Lost the grip?** Resize the window from the bottom-right corner (a small ◢ marker).
- **Right-click anywhere** on the clock also opens the settings menu.
- **Want to permanently remove a timer?** Open its menu → **Delete This Timer**.
- **Want a new timer?** Open any timer's menu → **New Timer**.
