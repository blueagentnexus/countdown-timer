"""
Install desktop + Start Menu shortcuts for Countdown Clock.
Run once: python install_shortcuts.py [--startup]

Options:
  --desktop        Create a Desktop shortcut (default: on)
  --no-desktop     Skip the Desktop shortcut
  --startup        Also create a Windows Startup shortcut (default: off)
  --remove         Remove all shortcuts instead of creating
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "CountdownClock"
SCRIPT_DIR = Path(__file__).resolve().parent
MAIN_SCRIPT = SCRIPT_DIR / "countdown_clock.py"

DESKTOP = Path(os.path.join(os.environ["USERPROFILE"], "Desktop"))
APPDATA = Path(os.environ["APPDATA"])
STARTUP = APPDATA / r"Microsoft\Windows\Start Menu\Programs\Startup"


def python_exe() -> str:
    pyw = Path(sys.executable).with_name("pythonw.exe")
    return str(pyw if pyw.exists() else sys.executable)


def make_shortcut(lnk: Path) -> bool:
    exe = python_exe()
    args = f'"{MAIN_SCRIPT}"'
    lnk.parent.mkdir(parents=True, exist_ok=True)
    # Prefer the custom stopwatch-smiley icon if available, else fall back to python exe.
    custom_icon = SCRIPT_DIR / "stopwatch_smiley.ico"
    icon = str(custom_icon) if custom_icon.exists() else exe
    ps = (
        f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut('
        f'"{lnk}"); '
        f'$s.TargetPath = "{exe}"; '
        f'$s.Arguments = \'{args}\'; '
        f'$s.WorkingDirectory = "{SCRIPT_DIR}"; '
        f'$s.IconLocation = "{icon},0"; '
        f'$s.Save()'
    )
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        print(res.stderr)
    return res.returncode == 0


def remove(lnk: Path) -> None:
    if lnk.exists():
        lnk.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desktop", action="store_true", default=True)
    ap.add_argument("--no-desktop", dest="desktop", action="store_false")
    ap.add_argument("--startup", action="store_true", default=False)
    ap.add_argument("--remove", action="store_true", default=False)
    args = ap.parse_args()

    desktop_lnk = DESKTOP / f"{APP_NAME}.lnk"
    startup_lnk = STARTUP / f"{APP_NAME}.lnk"

    if args.remove:
        remove(desktop_lnk)
        remove(startup_lnk)
        print("Removed shortcuts (if present).")
        return

    created = []
    if args.desktop:
        if make_shortcut(desktop_lnk):
            created.append(str(desktop_lnk))
    if args.startup:
        if make_shortcut(startup_lnk):
            created.append(str(startup_lnk))

    print("Created:")
    for c in created:
        print(f"  {c}")


if __name__ == "__main__":
    main()
