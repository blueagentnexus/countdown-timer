"""Re-point existing Countdown Clock shortcuts at the custom .ico icon.

Run after make_icon.py. Safe to re-run.
"""
import os
import subprocess
from pathlib import Path

APP_NAME = "CountdownClock"
SCRIPT_DIR = Path(__file__).resolve().parent
ICON = SCRIPT_DIR / "stopwatch_smiley.ico"

DESKTOP = Path(os.environ["USERPROFILE"]) / "Desktop"
STARTUP = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup"

TARGETS = [
    DESKTOP / f"{APP_NAME}.lnk",
    STARTUP / f"{APP_NAME}.lnk",
]


def retarget(lnk: Path, icon_path: Path) -> bool:
    if not lnk.exists():
        return False
    ps = (
        f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut('
        f'"{lnk}"); '
        f'$s.IconLocation = "{icon_path},0"; '
        f'$s.Save()'
    )
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        print(res.stderr)
    return res.returncode == 0


def main():
    if not ICON.exists():
        print(f"Missing icon: {ICON}")
        print("Run make_icon.py first.")
        return
    for lnk in TARGETS:
        ok = retarget(lnk, ICON)
        if ok:
            print(f"Updated: {lnk}")
        else:
            print(f"Not found or failed: {lnk}")
    # Nudge Explorer to refresh the desktop icon cache.
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "ie4uinit.exe -show; Start-Sleep -Milliseconds 300"],
        capture_output=True, text=True,
    )


if __name__ == "__main__":
    main()
