r"""
Countdown Clock - Windows desktop widget (multi-timer edition).

Features:
- Multiple independent countdown timers, each in its own borderless window.
- Per-timer settings: target date/time, label, font, colors, geometry, topmost.
- Add/delete timers from the three-dot menu (right-click also opens menu).
- Drag-to-move, resize grip, always-on-top toggle, runs at Windows startup.
- All timers persist in one settings file; closing/deleting one timer never
  affects the others. App exits only when you choose "Exit App" or you delete
  the last remaining timer.

Settings file: %APPDATA%\CountdownClock\settings.json
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import uuid
import tkinter as tk
from tkinter import colorchooser, filedialog, font as tkfont, messagebox, ttk
from datetime import datetime, timedelta, date
import calendar as _calendar
from pathlib import Path

try:
    import winsound  # stdlib on Windows; only used for .wav playback
except ImportError:
    winsound = None

APP_NAME = "CountdownClock"
APPDATA = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
SETTINGS_DIR = APPDATA / APP_NAME
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
STARTUP_DIR = APPDATA / r"Microsoft\Windows\Start Menu\Programs\Startup"
STARTUP_SHORTCUT = STARTUP_DIR / f"{APP_NAME}.lnk"

SETTINGS_VERSION = 2

# Bundled digital-clock font (DSEG7 Classic Bold, SIL OFL).
DIGITAL_FONT_FAMILY = "DSEG7 Classic"
DIGITAL_FONT_FILE = "DSEG7Classic-Bold.ttf"


def _resource_path(rel: str) -> Path:
    """Return absolute path for a bundled resource (works in dev + PyInstaller)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent / rel


def load_bundled_fonts() -> None:
    """Register bundled .ttf files with the Windows GDI for this process only.

    Uses AddFontResourceExW with FR_PRIVATE so the font is usable by Tk in this
    process without permanently installing it on the system.
    """
    if sys.platform != "win32":
        return
    font_path = _resource_path(f"fonts/{DIGITAL_FONT_FILE}")
    if not font_path.exists():
        return
    try:
        FR_PRIVATE = 0x10
        gdi32 = ctypes.windll.gdi32
        gdi32.AddFontResourceExW(str(font_path), FR_PRIVATE, 0)
    except Exception:
        pass

MODERN_DEFAULT_FONT = "Segoe UI"
UNIT_LABELS = ("DAY(S)", "HOUR(S)", "MINUTE(S)", "SECOND(S)")

WINDOWS_MEDIA = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Media"

# Pretty names for the built-in Windows alarms so menus read better.
BUILTIN_PRETTY = {
    "Alarm01.wav": "Alarm 1 (Cyber)",
    "Alarm02.wav": "Alarm 2 (Pulse)",
    "Alarm03.wav": "Alarm 3 (Beep)",
    "Alarm04.wav": "Alarm 4 (Chord)",
    "Alarm05.wav": "Alarm 5 (Trill)",
    "Alarm06.wav": "Alarm 6 (Sonar)",
    "Alarm07.wav": "Alarm 7 (Ascend)",
    "Alarm08.wav": "Alarm 8 (Loud)",
    "Alarm09.wav": "Alarm 9 (Buzzer)",
    "Alarm10.wav": "Alarm 10 (Wake)",
    "Ring01.wav": "Ring 1", "Ring02.wav": "Ring 2", "Ring03.wav": "Ring 3",
    "Ring04.wav": "Ring 4", "Ring05.wav": "Ring 5", "Ring06.wav": "Ring 6",
    "Ring07.wav": "Ring 7", "Ring08.wav": "Ring 8", "Ring09.wav": "Ring 9",
    "Ring10.wav": "Ring 10",
    "chimes.wav": "Chimes", "chord.wav": "Chord", "ding.wav": "Ding",
    "notify.wav": "Notify", "tada.wav": "Tada", "ringout.wav": "Ring Out",
    "recycle.wav": "Recycle",
}


def list_builtin_sounds() -> dict[str, list[tuple[str, str]]]:
    """Return {category: [(pretty_name, filename), ...]} of available system sounds.

    Skips Windows housekeeping sounds (Critical Stop etc.) so the menu doesn't
    feel like Control Panel.
    """
    if not WINDOWS_MEDIA.exists():
        return {}
    files = sorted(p.name for p in WINDOWS_MEDIA.glob("*.wav"))
    cats: dict[str, list[tuple[str, str]]] = {
        "Alarms": [], "Rings": [], "Chimes & Tones": [],
    }
    for fname in files:
        if fname.startswith("Alarm") and fname.endswith(".wav"):
            cats["Alarms"].append((BUILTIN_PRETTY.get(fname, fname), fname))
        elif fname.startswith("Ring") and fname not in ("ringout.wav",):
            cats["Rings"].append((BUILTIN_PRETTY.get(fname, fname), fname))
        elif fname in ("chimes.wav", "chord.wav", "ding.wav", "notify.wav",
                       "tada.wav", "ringout.wav", "recycle.wav"):
            cats["Chimes & Tones"].append((BUILTIN_PRETTY.get(fname, fname), fname))
    return {k: v for k, v in cats.items() if v}


class _AlarmPlayer:
    """Plays the end-of-timer sound. Uses winsound for .wav, MCI for everything else."""

    _MCI_ALIAS = "cdclock_alarm"

    def __init__(self):
        self._mci_active = False

    def _mci(self, cmd: str) -> int:
        if sys.platform != "win32":
            return 0
        try:
            return ctypes.windll.winmm.mciSendStringW(cmd, None, 0, 0)
        except Exception:
            return -1

    def stop(self):
        if winsound is not None:
            try:
                winsound.PlaySound(None, 0)
            except Exception:
                pass
        if self._mci_active:
            self._mci(f"close {self._MCI_ALIAS}")
            self._mci_active = False

    def play(self, path: str) -> bool:
        """Fire-and-forget play of `path`. Returns True if launched."""
        self.stop()
        if not path or not os.path.exists(path):
            return False
        ext = os.path.splitext(path)[1].lower()
        if ext == ".wav" and winsound is not None:
            try:
                winsound.PlaySound(
                    path, winsound.SND_FILENAME | winsound.SND_ASYNC,
                )
                return True
            except Exception:
                pass
        # MCI handles mp3 / mp4 / m4a / aac / wma / wav.
        self._mci(f"close {self._MCI_ALIAS}")
        if self._mci(f'open "{path}" alias {self._MCI_ALIAS}') != 0:
            return False
        if self._mci(f"play {self._MCI_ALIAS}") != 0:
            return False
        self._mci_active = True
        return True


ALARM_PLAYER = _AlarmPlayer()


def resolve_alarm_path(alarm: dict) -> str | None:
    """Translate an alarm config dict to an absolute file path (or None)."""
    if not alarm:
        return None
    kind = alarm.get("kind", "none")
    if kind == "none":
        return None
    if kind == "builtin":
        name = alarm.get("name") or ""
        path = WINDOWS_MEDIA / name
        return str(path) if path.exists() else None
    if kind == "custom":
        path = alarm.get("path") or ""
        return path if path and os.path.exists(path) else None
    return None


DEFAULT_TIMER = {
    "id": "",  # filled in at create time
    "target": "",  # ISO timestamp, filled in at create time
    "style": "digital",  # "digital" or "modern"
    "font_family": DIGITAL_FONT_FAMILY,
    "font_size": 36,
    "font_color": "#FFAD46",
    "bg_color": "#1a1a1a",
    "always_on_top": True,
    "geometry": "420x180+200+200",
    "label": "Countdown",
    "alarm": {"kind": "builtin", "name": "Alarm03.wav", "path": ""},
}


# ---------- settings helpers ----------

def _new_timer(offset: int = 0) -> dict:
    t = DEFAULT_TIMER.copy()
    t["id"] = uuid.uuid4().hex[:12]
    t["target"] = (datetime.now() + timedelta(days=30)).replace(microsecond=0).isoformat()
    # Stagger geometry so multiple new timers don't stack perfectly.
    x = 200 + (offset * 30)
    y = 200 + (offset * 30)
    t["geometry"] = f"420x180+{x}+{y}"
    return t


def load_settings() -> dict:
    """Load settings, migrating older single-timer format if needed."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    else:
        data = {}

    # Migration: v1 had top-level "target" instead of "timers".
    if "timers" not in data:
        if "target" in data:
            migrated = DEFAULT_TIMER.copy()
            migrated.update({k: v for k, v in data.items() if k in DEFAULT_TIMER})
            migrated["id"] = uuid.uuid4().hex[:12]
            data = {"version": SETTINGS_VERSION, "timers": [migrated]}
        else:
            data = {"version": SETTINGS_VERSION, "timers": [_new_timer()]}

    # Ensure each timer has all expected fields + an id.
    cleaned = []
    for i, t in enumerate(data.get("timers", [])):
        merged = DEFAULT_TIMER.copy()
        merged.update(t)
        if not merged.get("id"):
            merged["id"] = uuid.uuid4().hex[:12]
        if not merged.get("target"):
            merged["target"] = (datetime.now() + timedelta(days=30)).replace(microsecond=0).isoformat()
        cleaned.append(merged)
    if not cleaned:
        cleaned = [_new_timer()]

    # One-shot migration: switch existing timers to the digital font once.
    out = {"version": SETTINGS_VERSION, "timers": cleaned}
    if not data.get("digital_font_default_applied"):
        for t in out["timers"]:
            t["font_family"] = DIGITAL_FONT_FAMILY
        out["digital_font_default_applied"] = True
    else:
        out["digital_font_default_applied"] = True
    return out


def save_settings(settings: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


# ---------- startup shortcut ----------

def _script_target() -> tuple[str, str]:
    script = os.path.abspath(__file__)
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pyw if pyw.exists() else sys.executable)
    return exe, f'"{script}"'


def make_shortcut(target_lnk: Path) -> bool:
    exe, args = _script_target()
    workdir = str(Path(__file__).resolve().parent)
    target_lnk.parent.mkdir(parents=True, exist_ok=True)

    ps = (
        f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut('
        f'"{target_lnk}"); '
        f'$s.TargetPath = "{exe}"; '
        f'$s.Arguments = \'{args}\'; '
        f'$s.WorkingDirectory = "{workdir}"; '
        f'$s.IconLocation = "{exe},0"; '
        f'$s.Save()'
    )
    import subprocess
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def remove_shortcut(target_lnk: Path) -> None:
    try:
        if target_lnk.exists():
            target_lnk.unlink()
    except Exception:
        pass


def startup_enabled() -> bool:
    return STARTUP_SHORTCUT.exists()


# ---------- timer manager (owns hidden root + all timer windows) ----------

class TimerManager:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # hidden root; only Toplevels are visible
        self.root.title(APP_NAME)
        self.settings = load_settings()
        self.timers: list[TimerWindow] = []
        for cfg in self.settings["timers"]:
            self._spawn_window(cfg)

    def _spawn_window(self, cfg: dict) -> "TimerWindow":
        win = TimerWindow(self, cfg)
        self.timers.append(win)
        return win

    def add_timer(self):
        cfg = _new_timer(offset=len(self.timers))
        self.settings["timers"].append(cfg)
        self._spawn_window(cfg)
        self.save()

    def visible_timers(self) -> list["TimerWindow"]:
        return [t for t in self.timers if not t.hidden]

    def hidden_timers(self) -> list["TimerWindow"]:
        return [t for t in self.timers if t.hidden]

    def hide_timer(self, win: "TimerWindow"):
        # If this is the last visible timer, exit the app instead.
        # Hidden state is in-memory only, so relaunching brings everything back.
        if len(self.visible_timers()) <= 1:
            self.exit_app()
            return
        win.hide()

    def delete_timer(self, win: "TimerWindow"):
        if not messagebox.askyesno(
            APP_NAME,
            f"Delete timer \"{win.cfg.get('label', 'Countdown')}\"?",
            parent=win.top,
        ):
            return
        self._remove(win)
        if not self.timers:
            self.exit_app()

    def _remove(self, win: "TimerWindow"):
        try:
            self.timers.remove(win)
        except ValueError:
            pass
        self.settings["timers"] = [t for t in self.settings["timers"] if t.get("id") != win.cfg.get("id")]
        try:
            win.top.destroy()
        except Exception:
            pass
        self.save()

    def save(self):
        # Snapshot live geometry from each window before persisting.
        for w in self.timers:
            try:
                w.cfg["geometry"] = w.top.geometry()
            except Exception:
                pass
        # Rebuild the timers list in window order (preserve config dicts).
        self.settings["timers"] = [w.cfg for w in self.timers]
        save_settings(self.settings)

    def exit_app(self):
        self.save()
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


# ---------- one timer window ----------

class TimerWindow:
    def __init__(self, manager: TimerManager, cfg: dict):
        self.manager = manager
        self.cfg = cfg
        top = tk.Toplevel(manager.root)
        self.top = top
        top.overrideredirect(True)
        top.attributes("-topmost", cfg.get("always_on_top", True))
        top.geometry(cfg.get("geometry", "420x180+200+200"))
        top.configure(bg=cfg.get("bg_color", "#1a1a1a"))
        top.minsize(260, 120)
        top.title(cfg.get("label", "Countdown"))

        bg = cfg["bg_color"]

        self.frame = tk.Frame(top, bg=bg, bd=0, highlightthickness=0)
        self.frame.pack(fill="both", expand=True)

        # Top bar
        self.topbar = tk.Frame(self.frame, bg=bg, height=24)
        self.topbar.pack(side="top", fill="x")

        self.label_var = tk.StringVar(value=cfg.get("label", "Countdown"))
        self.label = tk.Label(
            self.topbar, textvariable=self.label_var, bg=bg, fg="#888",
            font=("Segoe UI", 9), anchor="w", padx=8,
        )
        self.label.pack(side="left", fill="x", expand=True)

        self.menu_btn = tk.Label(
            self.topbar, text="\u22EF", bg=bg, fg="#bbb",
            font=("Segoe UI", 14, "bold"), padx=8, cursor="hand2",
        )
        self.menu_btn.pack(side="right")
        self.menu_btn.bind("<Button-1>", self.open_menu)

        # ✕ hides just this timer (other timers stay open). The timer is not
        # deleted - reopen it from any other timer's "Show Hidden Timers" menu.
        # If this is the only visible timer, the app exits and all timers will
        # return on next launch.
        self.close_btn = tk.Label(
            self.topbar, text="\u2715", bg=bg, fg="#777",
            font=("Segoe UI", 10, "bold"), padx=8, cursor="hand2",
        )
        self.close_btn.pack(side="right")
        self.close_btn.bind("<Button-1>", lambda e: self.manager.hide_timer(self))
        self.hidden = False

        # Display container - holds either the digital single-label layout or
        # the modern multi-column (numbers + colons + unit labels) layout.
        # Built empty here; populated at the end of __init__ once self.sub /
        # self.grip exist (so _apply_bg can walk every chrome widget).
        self.display = tk.Frame(self.frame, bg=bg, bd=0, highlightthickness=0)
        self.display.pack(expand=True, fill="both", padx=10, pady=(0, 4))
        self._digital_label = None
        self._modern_nums: list[tk.Label] = []
        self._modern_units: list[tk.Label] = []
        self._modern_colons: list[tk.Label] = []

        self.sub = tk.Label(
            self.frame, text="", bg=bg, fg="#666", font=("Segoe UI", 9),
        )
        self.sub.pack(side="bottom", fill="x", pady=(0, 4))

        # Resize grip
        self.grip = tk.Label(
            self.frame, text="\u25E2", bg=bg, fg="#444",
            font=("Segoe UI", 10), cursor="bottom_right_corner",
        )
        self.grip.place(relx=1.0, rely=1.0, anchor="se")

        # Drag bindings (display children get their bindings inside _rebuild_display)
        for widget in (self.topbar, self.label, self.display, self.sub, self.frame):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

        self.grip.bind("<ButtonPress-1>", self._start_resize)
        self.grip.bind("<B1-Motion>", self._on_resize)

        top.bind("<Button-3>", self.open_menu)
        top.protocol("WM_DELETE_WINDOW", lambda: self.manager.hide_timer(self))

        # All chrome widgets exist now - safe to populate the display container.
        self._rebuild_display()
        self._alarm_fired = False  # reset whenever target changes (see set_target)
        self._tick()

    # ---------- drag / resize ----------

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.top.winfo_x()
        self._drag_y = event.y_root - self.top.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.top.geometry(f"+{x}+{y}")

    def _start_resize(self, event):
        self._rs_x = event.x_root
        self._rs_y = event.y_root
        self._rs_w = self.top.winfo_width()
        self._rs_h = self.top.winfo_height()

    def _on_resize(self, event):
        dw = event.x_root - self._rs_x
        dh = event.y_root - self._rs_y
        w = max(260, self._rs_w + dw)
        h = max(120, self._rs_h + dh)
        self.top.geometry(f"{w}x{h}")
        if self.cfg.get("style") == "modern":
            size = max(14, int(h * 0.34))
        else:
            size = max(14, int(h * 0.28))
        self.cfg["font_size"] = size
        self._apply_font()

    # ---------- display layout (digital vs modern) ----------

    def _rebuild_display(self):
        for child in self.display.winfo_children():
            child.destroy()
        self._digital_label = None
        self._modern_nums = []
        self._modern_units = []
        self._modern_colons = []
        if self.cfg.get("style") == "modern":
            self._build_modern_inside()
        else:
            self._build_digital_inside()
        self._apply_bg(self.cfg["bg_color"])

    def _build_digital_inside(self):
        cfg = self.cfg
        lbl = tk.Label(
            self.display, text="--",
            bg=cfg["bg_color"], fg=cfg["font_color"],
            font=(cfg["font_family"], cfg["font_size"], "bold"),
        )
        lbl.pack(expand=True, fill="both")
        lbl.bind("<ButtonPress-1>", self._start_drag)
        lbl.bind("<B1-Motion>", self._on_drag)
        lbl.bind("<Button-3>", self.open_menu)
        self._digital_label = lbl

    def _build_modern_inside(self):
        cfg = self.cfg
        bg = cfg["bg_color"]
        fg = cfg["font_color"]
        fam = cfg["font_family"]
        size = cfg["font_size"]
        unit_size = max(7, int(size * 0.25))

        holder = tk.Frame(self.display, bg=bg)
        holder.pack(expand=True, fill="both")
        # 7 columns: num, colon, num, colon, num, colon, num
        num_cols = (0, 2, 4, 6)
        colon_cols = (1, 3, 5)
        for c in num_cols:
            holder.grid_columnconfigure(c, weight=1)
        for c in colon_cols:
            holder.grid_columnconfigure(c, weight=0)
        holder.grid_rowconfigure(0, weight=3)
        holder.grid_rowconfigure(1, weight=1)

        for i, unit in enumerate(UNIT_LABELS):
            col = num_cols[i]
            num = tk.Label(holder, text="00", bg=bg, fg=fg,
                           font=(fam, size, "bold"))
            num.grid(row=0, column=col, sticky="ew", padx=2)
            u = tk.Label(holder, text=unit, bg=bg, fg=fg,
                         font=("Segoe UI", unit_size, "bold"))
            u.grid(row=1, column=col, sticky="new", padx=2)
            self._modern_nums.append(num)
            self._modern_units.append(u)
        for ci in colon_cols:
            colon = tk.Label(holder, text=":", bg=bg, fg=fg,
                             font=(fam, size, "bold"))
            colon.grid(row=0, column=ci, sticky="ns")
            self._modern_colons.append(colon)

        for w in (holder, *self._modern_nums, *self._modern_units, *self._modern_colons):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<Button-3>", self.open_menu)

    def _apply_font(self):
        cfg = self.cfg
        fam = cfg["font_family"]
        size = cfg["font_size"]
        if cfg.get("style") == "modern":
            unit_size = max(7, int(size * 0.25))
            for w in self._modern_nums + self._modern_colons:
                w.configure(font=(fam, size, "bold"))
            for w in self._modern_units:
                w.configure(font=("Segoe UI", unit_size, "bold"))
        elif self._digital_label is not None:
            self._digital_label.configure(font=(fam, size, "bold"))

    def _apply_fg(self, color: str):
        if self.cfg.get("style") == "modern":
            for w in self._modern_nums + self._modern_units + self._modern_colons:
                w.configure(fg=color)
        elif self._digital_label is not None:
            self._digital_label.configure(fg=color)

    def _apply_bg(self, color: str):
        for w in (self.top, self.frame, self.topbar, self.label, self.display,
                  self.sub, self.menu_btn, self.close_btn, self.grip):
            try:
                w.configure(bg=color)
            except tk.TclError:
                pass
        # Walk display children for the modern layout's nested frames + labels.
        def _walk(parent):
            for child in parent.winfo_children():
                try:
                    child.configure(bg=color)
                except tk.TclError:
                    pass
                _walk(child)
        _walk(self.display)

    # ---------- countdown ----------

    def _target_dt(self) -> datetime:
        try:
            return datetime.fromisoformat(self.cfg["target"])
        except Exception:
            return datetime.now() + timedelta(days=30)

    def hide(self):
        self.hidden = True
        try:
            self.top.withdraw()
        except tk.TclError:
            pass

    def show(self):
        self.hidden = False
        try:
            self.top.deiconify()
            # Restore overrideredirect after deiconify (Windows may reset it).
            self.top.overrideredirect(True)
            self.top.attributes("-topmost", self.cfg.get("always_on_top", True))
            self.top.lift()
        except tk.TclError:
            pass

    def _tick(self):
        if not self.top.winfo_exists():
            return
        now = datetime.now()
        target = self._target_dt()
        remaining = target - now
        if remaining.total_seconds() <= 0:
            d = h = m = s = 0
            self.sub.configure(text=f"Target reached: {target.strftime('%Y-%m-%d %I:%M %p')}")
            if not self._alarm_fired:
                self._alarm_fired = True
                self._fire_alarm()
        else:
            total_sec = int(remaining.total_seconds())
            d, rem = divmod(total_sec, 86400)
            h, rem = divmod(rem, 3600)
            m, s = divmod(rem, 60)
            self.sub.configure(text=f"Target: {target.strftime('%Y-%m-%d %I:%M %p')}")
        self._render_numbers(d, h, m, s)
        self.top.after(1000, self._tick)

    def _fire_alarm(self):
        path = resolve_alarm_path(self.cfg.get("alarm") or {})
        if path:
            ALARM_PLAYER.play(path)
        # Pop a non-modal toast so the user can see which timer fired and stop the sound.
        try:
            label = self.cfg.get("label") or "Countdown"
            messagebox.showinfo(
                APP_NAME, f"\u23f0  {label}\n\nTarget reached.",
                parent=self.top,
            )
        finally:
            ALARM_PLAYER.stop()

    def _render_numbers(self, d: int, h: int, m: int, s: int):
        if self.cfg.get("style") == "modern":
            if len(self._modern_nums) == 4:
                self._modern_nums[0].configure(text=f"{d:03d}")
                self._modern_nums[1].configure(text=f"{h:02d}")
                self._modern_nums[2].configure(text=f"{m:02d}")
                self._modern_nums[3].configure(text=f"{s:02d}")
        elif self._digital_label is not None:
            self._digital_label.configure(
                text=f"{d:02d}d {h:02d}h {m:02d}m {s:02d}s"
            )

    # ---------- menu ----------

    def open_menu(self, event=None):
        menu = tk.Menu(self.top, tearoff=0)
        menu.add_command(label="Set Target Date/Time...", command=self.set_target)
        menu.add_command(label="Set Label...", command=self.set_label)
        menu.add_separator()
        style_menu = tk.Menu(menu, tearoff=0)
        style_menu.add_radiobutton(
            label="Digital (7-segment)", value="digital",
            variable=self._tk_style, command=lambda: self.set_style("digital"),
        )
        style_menu.add_radiobutton(
            label="Modern (numbers + labels)", value="modern",
            variable=self._tk_style, command=lambda: self.set_style("modern"),
        )
        menu.add_cascade(label="Style", menu=style_menu)
        menu.add_command(label="Font Family & Size...", command=self.set_font)
        menu.add_command(label="Font Color...", command=self.set_font_color)
        menu.add_command(label="Background Color...", command=self.set_bg_color)
        menu.add_separator()
        menu.add_checkbutton(
            label="Always on Top",
            onvalue=True, offvalue=False,
            variable=self._tk_bool("always_on_top"),
            command=self.toggle_topmost,
        )
        menu.add_checkbutton(
            label="Run at Windows Startup",
            onvalue=True, offvalue=False,
            variable=self._tk_startup,
            command=self.toggle_startup,
        )
        menu.add_separator()
        menu.add_cascade(label="End-of-Timer Sound", menu=self._build_alarm_menu(menu))
        menu.add_separator()
        menu.add_command(label="New Timer", command=self.manager.add_timer)
        hidden = self.manager.hidden_timers()
        if hidden:
            sub = tk.Menu(menu, tearoff=0)
            for h in hidden:
                lbl = h.cfg.get("label") or "Countdown"
                sub.add_command(label=lbl, command=h.show)
            menu.add_cascade(label="Show Hidden Timers", menu=sub)
        menu.add_command(label="Delete This Timer", command=lambda: self.manager.delete_timer(self))
        menu.add_separator()
        menu.add_command(label="About", command=self.about)
        menu.add_command(label="Exit App", command=self.manager.exit_app)

        if event and hasattr(event, "x_root"):
            menu.tk_popup(event.x_root, event.y_root)
        else:
            x = self.top.winfo_rootx() + self.top.winfo_width() - 10
            y = self.top.winfo_rooty() + 30
            menu.tk_popup(x, y)

    def _tk_bool(self, key):
        attr = f"_var_{key}"
        if not hasattr(self, attr):
            var = tk.BooleanVar(value=bool(self.cfg.get(key, False)))
            setattr(self, attr, var)
        return getattr(self, attr)

    @property
    def _tk_style(self):
        if not hasattr(self, "_var_style"):
            self._var_style = tk.StringVar(value=self.cfg.get("style", "digital"))
        return self._var_style

    def set_style(self, style: str):
        if style not in ("digital", "modern"):
            return
        prev = self.cfg.get("style", "digital")
        if style == prev:
            return
        # Auto-switch font to a sensible default for the new style if the user
        # hasn't actively chosen a custom one.
        if style == "modern" and self.cfg.get("font_family") == DIGITAL_FONT_FAMILY:
            self.cfg["font_family"] = MODERN_DEFAULT_FONT
        elif style == "digital" and self.cfg.get("font_family") == MODERN_DEFAULT_FONT:
            self.cfg["font_family"] = DIGITAL_FONT_FAMILY
        self.cfg["style"] = style
        self._tk_style.set(style)
        self._rebuild_display()
        self._render_numbers(0, 0, 0, 0)  # immediate refresh until next tick
        self.manager.save()

    @property
    def _tk_startup(self):
        if not hasattr(self, "_var_startup"):
            self._var_startup = tk.BooleanVar(value=startup_enabled())
        return self._var_startup

    # ---------- setting actions ----------

    def set_target(self):
        try:
            cur = datetime.fromisoformat(self.cfg["target"])
        except Exception:
            cur = datetime.now() + timedelta(days=30)

        picker = DateTimePicker(self.top, initial=cur)
        self.top.wait_window(picker.top)
        if picker.result is not None:
            self.cfg["target"] = picker.result.replace(microsecond=0).isoformat()
            self._alarm_fired = False  # arm alarm for the new target
            self.manager.save()

    def set_label(self):
        dlg = tk.Toplevel(self.top)
        dlg.title("Set Label")
        dlg.transient(self.top)
        dlg.configure(padx=12, pady=12)
        ttk.Label(dlg, text="Label text:").pack(anchor="w")
        entry = ttk.Entry(dlg, width=28)
        entry.insert(0, self.cfg.get("label", ""))
        entry.pack(pady=6)
        entry.focus_set()

        def save():
            self.cfg["label"] = entry.get().strip()
            self.label_var.set(self.cfg["label"])
            self.top.title(self.cfg["label"] or "Countdown")
            self.manager.save()
            dlg.destroy()

        ttk.Button(dlg, text="Save", command=save).pack()
        dlg.bind("<Return>", lambda e: save())
        dlg.grab_set()

    def set_font(self):
        dlg = tk.Toplevel(self.top)
        dlg.title("Font Family & Size")
        dlg.transient(self.top)
        dlg.configure(padx=12, pady=12)

        ttk.Label(dlg, text="Font family:").pack(anchor="w")
        families = sorted(set(tkfont.families()))
        fam_var = tk.StringVar(value=self.cfg.get("font_family", "Segoe UI"))
        ttk.Combobox(dlg, textvariable=fam_var, values=families, width=32).pack(pady=4)

        ttk.Label(dlg, text="Font size:").pack(anchor="w")
        size_var = tk.IntVar(value=self.cfg.get("font_size", 36))
        ttk.Spinbox(dlg, from_=10, to=200, textvariable=size_var, width=8).pack(pady=4)

        def save():
            self.cfg["font_family"] = fam_var.get()
            self.cfg["font_size"] = int(size_var.get())
            self._apply_font()
            self.manager.save()
            dlg.destroy()

        ttk.Button(dlg, text="Save", command=save).pack(pady=(6, 0))
        dlg.grab_set()

    def set_font_color(self):
        _, hexval = colorchooser.askcolor(
            color=self.cfg.get("font_color", "#FFAD46"),
            title="Pick font color", parent=self.top,
        )
        if hexval:
            self.cfg["font_color"] = hexval
            self._apply_fg(hexval)
            self.manager.save()

    def set_bg_color(self):
        _, hexval = colorchooser.askcolor(
            color=self.cfg.get("bg_color", "#1a1a1a"),
            title="Pick background color", parent=self.top,
        )
        if hexval:
            self.cfg["bg_color"] = hexval
            self._apply_bg(hexval)
            self.manager.save()

    def toggle_topmost(self):
        val = self._tk_bool("always_on_top").get()
        self.cfg["always_on_top"] = val
        self.top.attributes("-topmost", val)
        self.manager.save()

    def toggle_startup(self):
        want = self._tk_startup.get()
        if want:
            ok = make_shortcut(STARTUP_SHORTCUT)
            if not ok:
                messagebox.showerror(APP_NAME, "Failed to create startup shortcut.", parent=self.top)
                self._tk_startup.set(False)
        else:
            remove_shortcut(STARTUP_SHORTCUT)

    def _alarm_match(self, kind: str, name: str = "") -> bool:
        cur = self.cfg.get("alarm") or {}
        if cur.get("kind") != kind:
            return False
        if kind == "builtin":
            return cur.get("name") == name
        return True

    def _build_alarm_menu(self, parent_menu: tk.Menu) -> tk.Menu:
        m = tk.Menu(parent_menu, tearoff=0)
        # Active state in the label so users see what's selected at a glance.
        cur = self.cfg.get("alarm") or {}
        m.add_command(
            label=("• None" if cur.get("kind") == "none" else "  None"),
            command=lambda: self.set_alarm({"kind": "none", "name": "", "path": ""}),
        )
        m.add_command(label="  Test current sound", command=self.test_alarm)
        m.add_command(label="  Stop sound", command=lambda: ALARM_PLAYER.stop())
        m.add_separator()
        for cat, items in list_builtin_sounds().items():
            sub = tk.Menu(m, tearoff=0)
            for pretty, fname in items:
                marker = "• " if self._alarm_match("builtin", fname) else "  "
                sub.add_command(
                    label=marker + pretty,
                    command=lambda fn=fname: self.set_alarm({
                        "kind": "builtin", "name": fn, "path": "",
                    }),
                )
            m.add_cascade(label=cat, menu=sub)
        m.add_separator()
        custom_label = "  Custom file..."
        if cur.get("kind") == "custom" and cur.get("path"):
            custom_label = f"• Custom: {os.path.basename(cur['path'])}"
        m.add_command(label=custom_label, command=self.set_alarm_custom)
        return m

    def set_alarm(self, alarm: dict):
        self.cfg["alarm"] = alarm
        self.manager.save()

    def set_alarm_custom(self):
        path = filedialog.askopenfilename(
            parent=self.top,
            title="Pick alarm sound",
            filetypes=[
                ("Audio / video", "*.wav *.mp3 *.mp4 *.m4a *.aac *.wma *.flac *.ogg *.avi *.wmv *.mov"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.set_alarm({"kind": "custom", "name": "", "path": path})

    def test_alarm(self):
        path = resolve_alarm_path(self.cfg.get("alarm") or {})
        if not path:
            messagebox.showinfo(APP_NAME, "No sound selected (or file missing).", parent=self.top)
            return
        ALARM_PLAYER.play(path)

    def about(self):
        messagebox.showinfo(
            APP_NAME,
            f"{APP_NAME}\n\n"
            f"Settings: {SETTINGS_FILE}\n"
            f"Active timers: {len(self.manager.timers)}\n"
            f"Startup shortcut: {STARTUP_SHORTCUT if startup_enabled() else '(off)'}\n\n"
            "Right-click or click the three dots for menu.\n"
            "✕ hides just this timer (others stay open).\n"
            "Reopen from any other timer's \"Show Hidden Timers\" menu.\n"
            "Use \"Delete This Timer\" in the menu to remove one permanently.",
            parent=self.top,
        )


# ---------- calendar + time picker ----------

class DateTimePicker:
    """Pure-Tk month calendar + hour/minute spinboxes. No third-party deps."""

    WEEKDAY_HEADERS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
    MONTHS = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    def __init__(self, parent, initial: datetime):
        self.result: datetime | None = None
        self.view_year = initial.year
        self.view_month = initial.month
        self.selected: date = initial.date()

        top = tk.Toplevel(parent)
        self.top = top
        top.title("Pick Target Date & Time")
        top.transient(parent)
        top.resizable(False, False)
        top.configure(padx=12, pady=12)

        hdr = ttk.Frame(top)
        hdr.pack(fill="x", pady=(0, 6))
        ttk.Button(hdr, text="‹", width=3, command=self._prev_month).pack(side="left")
        self.title_lbl = ttk.Label(hdr, text="", font=("Segoe UI", 11, "bold"),
                                   anchor="center")
        self.title_lbl.pack(side="left", fill="x", expand=True)
        ttk.Button(hdr, text="›", width=3, command=self._next_month).pack(side="left")

        self.grid_frame = ttk.Frame(top)
        self.grid_frame.pack()

        time_row = ttk.Frame(top)
        time_row.pack(pady=(10, 0))
        ttk.Label(time_row, text="Time:").pack(side="left")

        hour24 = initial.hour
        is_pm = hour24 >= 12
        hour12 = hour24 % 12
        if hour12 == 0:
            hour12 = 12
        self.hour_var = tk.IntVar(value=hour12)
        self.min_var = tk.IntVar(value=initial.minute)
        self.ampm_var = tk.StringVar(value="PM" if is_pm else "AM")

        ttk.Spinbox(time_row, from_=1, to=12, width=4, textvariable=self.hour_var,
                    format="%02.0f").pack(side="left", padx=(6, 2))
        ttk.Label(time_row, text=":").pack(side="left")
        ttk.Spinbox(time_row, from_=0, to=59, width=4, textvariable=self.min_var,
                    format="%02.0f").pack(side="left", padx=(2, 6))
        ttk.Combobox(time_row, textvariable=self.ampm_var, values=("AM", "PM"),
                     width=4, state="readonly").pack(side="left")

        btns = ttk.Frame(top)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="Today", command=self._jump_today).pack(side="left")
        ttk.Button(btns, text="Cancel", command=self._cancel).pack(side="right")
        ttk.Button(btns, text="OK", command=self._ok).pack(side="right", padx=(0, 6))

        self._render_month()
        top.grab_set()
        top.bind("<Escape>", lambda e: self._cancel())
        top.bind("<Return>", lambda e: self._ok())

    def _render_month(self):
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.title_lbl.configure(
            text=f"{self.MONTHS[self.view_month - 1]} {self.view_year}"
        )

        for col, label in enumerate(self.WEEKDAY_HEADERS):
            ttk.Label(self.grid_frame, text=label, width=4, anchor="center",
                      font=("Segoe UI", 9, "bold")).grid(row=0, column=col, padx=1, pady=(0, 2))

        cal = _calendar.Calendar(firstweekday=6)
        weeks = cal.monthdatescalendar(self.view_year, self.view_month)
        today = date.today()
        for r, week in enumerate(weeks, start=1):
            for c, day in enumerate(week):
                btn = tk.Button(
                    self.grid_frame, text=str(day.day), width=3,
                    relief="flat", bd=0,
                    command=lambda d=day: self._select(d),
                )
                if day.month != self.view_month:
                    btn.configure(fg="#888")
                if day == self.selected:
                    btn.configure(bg="#FFAD46", fg="#000", activebackground="#FFAD46")
                elif day == today:
                    btn.configure(bg="#333", fg="#fff", activebackground="#555")
                btn.grid(row=r, column=c, padx=1, pady=1, sticky="nsew")

    def _select(self, d: date):
        self.selected = d
        if d.month != self.view_month or d.year != self.view_year:
            self.view_year, self.view_month = d.year, d.month
        self._render_month()

    def _prev_month(self):
        y, m = self.view_year, self.view_month - 1
        if m == 0:
            m = 12
            y -= 1
        self.view_year, self.view_month = y, m
        self._render_month()

    def _next_month(self):
        y, m = self.view_year, self.view_month + 1
        if m == 13:
            m = 1
            y += 1
        self.view_year, self.view_month = y, m
        self._render_month()

    def _jump_today(self):
        t = date.today()
        self.view_year, self.view_month = t.year, t.month
        self.selected = t
        self._render_month()

    def _ok(self):
        try:
            h12 = max(1, min(12, int(self.hour_var.get())))
            mi = max(0, min(59, int(self.min_var.get())))
        except (tk.TclError, ValueError):
            h12, mi = 12, 0
        is_pm = self.ampm_var.get().upper() == "PM"
        if h12 == 12:
            h24 = 12 if is_pm else 0
        else:
            h24 = h12 + 12 if is_pm else h12
        self.result = datetime(
            self.selected.year, self.selected.month, self.selected.day, h24, mi, 0,
        )
        self.top.destroy()

    def _cancel(self):
        self.result = None
        self.top.destroy()


def main():
    load_bundled_fonts()
    mgr = TimerManager()
    mgr.run()


if __name__ == "__main__":
    main()
