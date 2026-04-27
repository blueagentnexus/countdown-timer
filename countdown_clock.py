r"""
Countdown Clock - Windows desktop widget.

Features:
- Days / hours / minutes countdown to a target date.
- Settings menu (three-dot button, top-right).
- Always-on-top toggle.
- Borderless, drag-to-move, resize grip.
- Font color + family + size via settings.
- Persists target + preferences across restarts.
- Optional "run at Windows startup" toggle.

Settings file: %APPDATA%\CountdownClock\settings.json
"""
from __future__ import annotations

import json
import os
import sys
import time
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

DEFAULT_SETTINGS = {
    "target": (datetime.now() + timedelta(days=30)).replace(microsecond=0).isoformat(),
    "font_family": "Segoe UI",
    "font_size": 36,
    "font_color": "#FFAD46",        # orange by default, for old times' sake
    "bg_color": "#1a1a1a",
    "always_on_top": True,
    "geometry": "420x180+200+200",  # WxH+X+Y
    "label": "Countdown",
}


# ---------- settings helpers ----------

def load_settings() -> dict:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = DEFAULT_SETTINGS.copy()
            merged.update(data)
            return merged
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


# ---------- startup shortcut (pure stdlib via pythoncom/win32com if available,
# else fall back to a PowerShell one-liner) ----------

def _script_target() -> tuple[str, str]:
    """Return (target_exe, args) for a shortcut pointing at this script."""
    script = os.path.abspath(__file__)
    if getattr(sys, "frozen", False):  # e.g. PyInstaller
        return sys.executable, ""
    # Prefer pythonw.exe so no console window flashes.
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


# ---------- main app ----------

class CountdownApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = load_settings()

        # Window chrome: borderless + transparent look optional.
        root.overrideredirect(True)
        root.attributes("-topmost", self.settings.get("always_on_top", True))
        root.geometry(self.settings.get("geometry", "420x180+200+200"))
        root.configure(bg=self.settings.get("bg_color", "#1a1a1a"))
        root.minsize(260, 120)

        # Main frame
        self.frame = tk.Frame(root, bg=self.settings["bg_color"], bd=0, highlightthickness=0)
        self.frame.pack(fill="both", expand=True)

        # Top bar (drag area + label + three dots + close)
        self.topbar = tk.Frame(self.frame, bg=self.settings["bg_color"], height=24)
        self.topbar.pack(side="top", fill="x")

        self.label_var = tk.StringVar(value=self.settings.get("label", "Countdown"))
        self.label = tk.Label(
            self.topbar,
            textvariable=self.label_var,
            bg=self.settings["bg_color"],
            fg="#888",
            font=("Segoe UI", 9),
            anchor="w",
            padx=8,
        )
        self.label.pack(side="left", fill="x", expand=True)

        self.menu_btn = tk.Label(
            self.topbar, text="\u22EF", bg=self.settings["bg_color"], fg="#bbb",
            font=("Segoe UI", 14, "bold"), padx=8, cursor="hand2",
        )
        self.menu_btn.pack(side="right")
        self.menu_btn.bind("<Button-1>", self.open_menu)

        self.close_btn = tk.Label(
            self.topbar, text="\u2715", bg=self.settings["bg_color"], fg="#777",
            font=("Segoe UI", 10, "bold"), padx=8, cursor="hand2",
        )
        self.close_btn.pack(side="right")
        self.close_btn.bind("<Button-1>", lambda e: self.quit())

        # Countdown display
        self.display = tk.Label(
            self.frame,
            text="--",
            bg=self.settings["bg_color"],
            fg=self.settings["font_color"],
            font=(self.settings["font_family"], self.settings["font_size"], "bold"),
        )
        self.display.pack(expand=True, fill="both", padx=10, pady=(0, 4))

        # Sub-label (target date readout)
        self.sub = tk.Label(
            self.frame, text="", bg=self.settings["bg_color"], fg="#666",
            font=("Segoe UI", 9),
        )
        self.sub.pack(side="bottom", fill="x", pady=(0, 4))

        # Resize grip (bottom-right corner)
        self.grip = tk.Label(
            self.frame, text="\u25E2", bg=self.settings["bg_color"], fg="#444",
            font=("Segoe UI", 10), cursor="bottom_right_corner",
        )
        self.grip.place(relx=1.0, rely=1.0, anchor="se")

        # Drag bindings (whole window draggable via topbar + display)
        for widget in (self.topbar, self.label, self.display, self.sub, self.frame):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

        # Resize bindings on grip
        self.grip.bind("<ButtonPress-1>", self._start_resize)
        self.grip.bind("<B1-Motion>", self._on_resize)

        # Right-click anywhere = settings
        root.bind("<Button-3>", self.open_menu)

        # Tick
        self._tick()
        # Save geometry on close
        root.protocol("WM_DELETE_WINDOW", self.quit)

    # ---------- drag / resize ----------

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _start_resize(self, event):
        self._rs_x = event.x_root
        self._rs_y = event.y_root
        self._rs_w = self.root.winfo_width()
        self._rs_h = self.root.winfo_height()

    def _on_resize(self, event):
        dw = event.x_root - self._rs_x
        dh = event.y_root - self._rs_y
        w = max(260, self._rs_w + dw)
        h = max(120, self._rs_h + dh)
        self.root.geometry(f"{w}x{h}")
        # Scale font proportionally to height.
        size = max(14, int(h * 0.28))
        self.display.configure(font=(self.settings["font_family"], size, "bold"))

    # ---------- countdown ----------

    def _target_dt(self) -> datetime:
        try:
            return datetime.fromisoformat(self.settings["target"])
        except Exception:
            return datetime.now() + timedelta(days=30)

    def _tick(self):
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
        self.root.after(1000, self._tick)

    # ---------- settings menu ----------

    def open_menu(self, event=None):
        menu = tk.Menu(self.root, tearoff=0)
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
        menu.add_command(label="About", command=self.about)
        menu.add_command(label="Exit", command=self.quit)

        # Position near the three-dot button.
        if event and hasattr(event, "x_root"):
            menu.tk_popup(event.x_root, event.y_root)
        else:
            x = self.root.winfo_rootx() + self.root.winfo_width() - 10
            y = self.root.winfo_rooty() + 30
            menu.tk_popup(x, y)

    def _tk_bool(self, key):
        # Lazy-create tk.BooleanVar mirroring a settings key.
        attr = f"_var_{key}"
        if not hasattr(self, attr):
            var = tk.BooleanVar(value=bool(self.settings.get(key, False)))
            setattr(self, attr, var)
        return getattr(self, attr)

    @property
    def _tk_startup(self):
        if not hasattr(self, "_var_startup"):
            self._var_startup = tk.BooleanVar(value=startup_enabled())
        return self._var_startup

    # ---------- setting actions ----------

    def set_target(self):
        # Parse current target into components.
        try:
            cur = datetime.fromisoformat(self.settings["target"])
        except Exception:
            cur = datetime.now() + timedelta(days=30)

        picker = DateTimePicker(self.root, initial=cur)
        self.root.wait_window(picker.top)
        if picker.result is not None:
            self.settings["target"] = picker.result.replace(microsecond=0).isoformat()
            save_settings(self.settings)

    def set_label(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Set Label")
        dlg.transient(self.root)
        dlg.configure(padx=12, pady=12)
        ttk.Label(dlg, text="Label text:").pack(anchor="w")
        entry = ttk.Entry(dlg, width=28)
        entry.insert(0, self.settings.get("label", ""))
        entry.pack(pady=6)
        entry.focus_set()

        def save():
            self.settings["label"] = entry.get().strip()
            self.label_var.set(self.settings["label"])
            save_settings(self.settings)
            dlg.destroy()

        ttk.Button(dlg, text="Save", command=save).pack()
        dlg.bind("<Return>", lambda e: save())
        dlg.grab_set()

    def set_font(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Font Family & Size")
        dlg.transient(self.root)
        dlg.configure(padx=12, pady=12)

        ttk.Label(dlg, text="Font family:").pack(anchor="w")
        families = sorted(set(tkfont.families()))
        fam_var = tk.StringVar(value=self.settings.get("font_family", "Segoe UI"))
        combo = ttk.Combobox(dlg, textvariable=fam_var, values=families, width=32)
        combo.pack(pady=4)

        ttk.Label(dlg, text="Font size:").pack(anchor="w")
        size_var = tk.IntVar(value=self.settings.get("font_size", 36))
        spin = ttk.Spinbox(dlg, from_=10, to=200, textvariable=size_var, width=8)
        spin.pack(pady=4)

        def save():
            self.settings["font_family"] = fam_var.get()
            self.settings["font_size"] = int(size_var.get())
            self.display.configure(font=(self.settings["font_family"],
                                         self.settings["font_size"], "bold"))
            save_settings(self.settings)
            dlg.destroy()

        ttk.Button(dlg, text="Save", command=save).pack(pady=(6, 0))
        dlg.grab_set()

    def set_font_color(self):
        _, hexval = colorchooser.askcolor(
            color=self.settings.get("font_color", "#FFAD46"),
            title="Pick font color",
        )
        if hexval:
            self.settings["font_color"] = hexval
            self.display.configure(fg=hexval)
            save_settings(self.settings)

    def set_bg_color(self):
        _, hexval = colorchooser.askcolor(
            color=self.settings.get("bg_color", "#1a1a1a"),
            title="Pick background color",
        )
        if hexval:
            self.settings["bg_color"] = hexval
            for widget in (self.root, self.frame, self.topbar, self.label,
                           self.display, self.sub, self.menu_btn, self.close_btn,
                           self.grip):
                try:
                    widget.configure(bg=hexval)
                except tk.TclError:
                    pass
            save_settings(self.settings)

    def toggle_topmost(self):
        val = self._tk_bool("always_on_top").get()
        self.settings["always_on_top"] = val
        self.root.attributes("-topmost", val)
        save_settings(self.settings)

    def toggle_startup(self):
        want = self._tk_startup.get()
        if want:
            ok = make_shortcut(STARTUP_SHORTCUT)
            if not ok:
                messagebox.showerror(APP_NAME, "Failed to create startup shortcut.")
                self._tk_startup.set(False)
        else:
            remove_shortcut(STARTUP_SHORTCUT)

    def about(self):
        messagebox.showinfo(
            APP_NAME,
            f"{APP_NAME}\n\n"
            f"Settings: {SETTINGS_FILE}\n"
            f"Startup shortcut: {STARTUP_SHORTCUT if startup_enabled() else '(off)'}\n\n"
            "Right-click or click the three dots to open settings.",
        )

    # ---------- quit ----------

    def quit(self):
        self.settings["geometry"] = self.root.geometry()
        save_settings(self.settings)
        self.root.destroy()


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

        # --- Month/year header ---
        hdr = ttk.Frame(top)
        hdr.pack(fill="x", pady=(0, 6))
        ttk.Button(hdr, text="‹", width=3, command=self._prev_month).pack(side="left")
        self.title_lbl = ttk.Label(hdr, text="", font=("Segoe UI", 11, "bold"),
                                   anchor="center")
        self.title_lbl.pack(side="left", fill="x", expand=True)
        ttk.Button(hdr, text="›", width=3, command=self._next_month).pack(side="left")

        # --- Calendar grid ---
        self.grid_frame = ttk.Frame(top)
        self.grid_frame.pack()

        # --- Time row (12-hour with AM/PM) ---
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

        # --- Action buttons ---
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
        # Clear previous grid
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.title_lbl.configure(
            text=f"{self.MONTHS[self.view_month - 1]} {self.view_year}"
        )

        # Weekday headers
        for col, label in enumerate(self.WEEKDAY_HEADERS):
            ttk.Label(self.grid_frame, text=label, width=4, anchor="center",
                      font=("Segoe UI", 9, "bold")).grid(row=0, column=col, padx=1, pady=(0, 2))

        cal = _calendar.Calendar(firstweekday=6)  # Sunday
        weeks = cal.monthdatescalendar(self.view_year, self.view_month)
        today = date.today()
        for r, week in enumerate(weeks, start=1):
            for c, day in enumerate(week):
                btn = tk.Button(
                    self.grid_frame, text=str(day.day), width=3,
                    relief="flat", bd=0,
                    command=lambda d=day: self._select(d),
                )
                # Style: dim out-of-month, highlight selected, mark today.
                if day.month != self.view_month:
                    btn.configure(fg="#888")
                if day == self.selected:
                    btn.configure(bg="#FFAD46", fg="#000", activebackground="#FFAD46")
                elif day == today:
                    btn.configure(bg="#333", fg="#fff", activebackground="#555")
                btn.grid(row=r, column=c, padx=1, pady=1, sticky="nsew")

    def _select(self, d: date):
        self.selected = d
        # If the user clicked an adjacent-month date, follow it.
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
        # Convert 12-hour -> 24-hour.
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
    root = tk.Tk()
    root.title(APP_NAME)
    CountdownApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
