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
from tkinter import colorchooser, font as tkfont, messagebox, ttk
from datetime import datetime, timedelta, date
import calendar as _calendar
from pathlib import Path

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

DEFAULT_TIMER = {
    "id": "",  # filled in at create time
    "target": "",  # ISO timestamp, filled in at create time
    "font_family": DIGITAL_FONT_FAMILY,
    "font_size": 36,
    "font_color": "#FFAD46",
    "bg_color": "#1a1a1a",
    "always_on_top": True,
    "geometry": "420x180+200+200",
    "label": "Countdown",
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

        # Display
        self.display = tk.Label(
            self.frame, text="--", bg=bg, fg=cfg["font_color"],
            font=(cfg["font_family"], cfg["font_size"], "bold"),
        )
        self.display.pack(expand=True, fill="both", padx=10, pady=(0, 4))

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

        # Drag bindings
        for widget in (self.topbar, self.label, self.display, self.sub, self.frame):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

        self.grip.bind("<ButtonPress-1>", self._start_resize)
        self.grip.bind("<B1-Motion>", self._on_resize)

        top.bind("<Button-3>", self.open_menu)
        top.protocol("WM_DELETE_WINDOW", lambda: self.manager.hide_timer(self))

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
        size = max(14, int(h * 0.28))
        self.cfg["font_size"] = size
        self.display.configure(font=(self.cfg["font_family"], size, "bold"))

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
            self.display.configure(text="00d 00h 00m 00s")
            self.sub.configure(text=f"Target reached: {target.strftime('%Y-%m-%d %I:%M %p')}")
        else:
            total_sec = int(remaining.total_seconds())
            days, rem = divmod(total_sec, 86400)
            hours, rem = divmod(rem, 3600)
            mins, secs = divmod(rem, 60)
            self.display.configure(
                text=f"{days:02d}d {hours:02d}h {mins:02d}m {secs:02d}s"
            )
            self.sub.configure(text=f"Target: {target.strftime('%Y-%m-%d %I:%M %p')}")
        self.top.after(1000, self._tick)

    # ---------- menu ----------

    def open_menu(self, event=None):
        menu = tk.Menu(self.top, tearoff=0)
        menu.add_command(label="Set Target Date/Time...", command=self.set_target)
        menu.add_command(label="Set Label...", command=self.set_label)
        menu.add_separator()
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
            self.display.configure(font=(self.cfg["font_family"],
                                         self.cfg["font_size"], "bold"))
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
            self.display.configure(fg=hexval)
            self.manager.save()

    def set_bg_color(self):
        _, hexval = colorchooser.askcolor(
            color=self.cfg.get("bg_color", "#1a1a1a"),
            title="Pick background color", parent=self.top,
        )
        if hexval:
            self.cfg["bg_color"] = hexval
            for widget in (self.top, self.frame, self.topbar, self.label,
                           self.display, self.sub, self.menu_btn, self.close_btn,
                           self.grip):
                try:
                    widget.configure(bg=hexval)
                except tk.TclError:
                    pass
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
