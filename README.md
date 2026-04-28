# Countdown Clock

A polished, always-on-top countdown widget for Windows. Days / hours / minutes / seconds to any target date — with multiple independent timers, two visual styles, a bundled digital-clock font, and a built-in alarm library that keeps ringing until you stop it.

![status: stable](https://img.shields.io/badge/status-stable-brightgreen) ![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue) ![platform: Windows](https://img.shields.io/badge/platform-Windows-0078d6)

## Highlights

- **Multiple independent timers** — each in its own borderless window with its own target, label, font, colors, position, size, style, and end-of-timer alarm.
- **Two display styles per timer:**
  - **Digital** — classic 7-segment LED look (uses the bundled DSEG7 Classic font).
  - **Modern** — large numbers separated by colons with `DAY(S) / HOUR(S) / MINUTE(S) / SECOND(S)` labels underneath.
- **Bundled DSEG7 Classic font** — loaded at runtime as a private process font (no system install needed).
- **End-of-timer alarms with a large built-in library:**
  - 10 alarm tones, 10 ringtones, 7 chimes/tones (auto-detected from `C:\Windows\Media`).
  - Plus **None** (silent), **Test current sound** (one-shot preview), **Stop sound** (instant kill).
  - **Custom file** picker accepts `.wav .mp3 .mp4 .m4a .aac .wma .flac .ogg .avi .wmv .mov` (`.wav` plays via `winsound`, everything else via Windows MCI).
  - Alarm **loops continuously** when the timer hits zero. Dismiss the popup, click "Stop sound" in any menu, or pick None/Test to silence.
- **Pure stdlib** — no third-party Python packages required (Tk + ctypes + winsound + winmm).
- **Run at Windows Startup** toggle in the settings menu.
- **Persistent state** — every timer reopens with the same target, position, colors, font, style, and alarm.

## Install (Windows Desktop)

### Option A — Download the prebuilt EXE (easiest)

1. Go to the [Releases page](https://github.com/blueagentnexus/countdown-timer/releases) and grab the latest `CountdownClock.exe`.
2. Move it somewhere permanent (e.g. `C:\Users\<you>\Apps\CountdownClock\`).
3. Double-click `CountdownClock.exe` to run.
4. (Optional) Right-click the EXE → **Send to → Desktop (create shortcut)** to pin it to your desktop.
5. (Optional) To launch at Windows startup: open the app, click the three-dot menu (top-right), and toggle **Run at Windows Startup**.

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
pyinstaller --noconfirm CountdownClock.spec
# Output: dist\CountdownClock.exe   (font is bundled via the spec)
```

## Default Look (new timers)

- **Style:** Modern
- **Color:** Red (`#FF0000`)
- **Font:** DSEG7 Classic
- **Size:** 54
- **Alarm:** Alarm 3 (Beep)

You can change any of these from the settings menu.

## Settings Menu

Open the menu by clicking the three dots in the top-right of any timer (or right-click anywhere on it):

- **Set Target Date/Time…** — calendar picker (Sunday → Saturday, US-style) + 12-hour AM/PM time picker.
- **Set Label…** — optional caption above the numbers.
- **Style** ▶ Digital (7-segment) or Modern (numbers + labels).
- **Font Family & Size…** — pick any installed font + a custom size. Bundled `DSEG7 Classic` is always available.
- **Font Color…** / **Background Color…** — full color pickers.
- **Always on Top** — toggle.
- **Run at Windows Startup** — toggle.
- **End-of-Timer Sound** ▶
  - **None** — silent.
  - **Test current sound** — one-shot preview.
  - **Stop sound** — kill any currently-playing alarm.
  - **Alarms** ▶ Alarm 1–10.
  - **Rings** ▶ Ring 1–10.
  - **Chimes & Tones** ▶ Chimes / Chord / Ding / Notify / Tada / Ring Out / Recycle.
  - **Custom file…** — file picker for any `.wav .mp3 .mp4 .m4a .aac .wma .flac .ogg .avi .wmv .mov`.
- **New Timer** — spawn another independent timer.
- **Show Hidden Timers** ▶ list of timers you've hidden via ✕ (one click reopens).
- **Delete This Timer** — permanently remove (asks for confirmation).
- **About** / **Exit App**.

## Window Behavior

- **Borderless + draggable** — click and drag anywhere on the clock to move it.
- **Resizable** — drag the small ◢ in the bottom-right. The font scales with height.
- **✕ button** — hides this timer; other timers keep ticking. Reopen it from any other timer's **Show Hidden Timers** submenu. Hiding the last visible timer exits the app gracefully (everything reappears on next launch).

## Settings File

Settings live here:

```
%APPDATA%\CountdownClock\settings.json
```

The schema stores all timers in one file (with auto-migration from the old single-timer v1 format). Delete the file to reset to defaults.

## Build Notes

- The DSEG7 Classic Bold font ([keshikan/DSEG](https://github.com/keshikan/DSEG), SIL Open Font License) is bundled in `fonts/` and registered at runtime via Windows GDI `AddFontResourceExW` with the `FR_PRIVATE` flag — no permanent system install.
- The Windows alarm library is **not bundled**. The app reads sounds directly from `C:\Windows\Media`, which is present on every Windows install. This avoids redistribution issues with Microsoft's media files.
- Custom audio playback uses `winsound` for `.wav` and Windows MCI (`mciSendStringW`) for everything else. Looping for non-WAV formats is implemented with a `threading.Timer` that re-arms playback at the end of each pass.

## License

MIT for the application code. The bundled DSEG7 Classic Bold font is licensed under the [SIL Open Font License 1.1](https://scripts.sil.org/OFL); the original font files are unchanged.

## Tips

- **Want a new timer?** Any timer's menu → **New Timer**.
- **Want to permanently remove a timer?** Its menu → **Delete This Timer**.
- **Just hide it temporarily?** Click the **✕** in the top-right.
- **Right-click anywhere** on a timer also opens the settings menu.
- **Stop a runaway alarm?** Click **OK** on the popup, or pick **Stop sound** in any timer's End-of-Timer Sound submenu.
