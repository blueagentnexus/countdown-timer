# Countdown Clock

A simple always-on-top countdown widget for Windows. Days / hours / minutes to any target date.

## Features

- **Countdown** in days + hours + minutes to a configurable target.
- **Persistent state** — closes and reopens on the same countdown, same window position, same colors, same font.
- **Borderless, draggable** — click and drag anywhere on the clock to move it.
- **Resizable** — drag the small handle in the bottom-right corner. Font scales with height.
- **Always on top** — toggle from the settings menu.
- **Three-dot settings menu** in the top-right (or right-click anywhere on the clock).
- **Font color + family + size** — all configurable.
- **Background color** configurable too.
- **Label** — optional small caption above the numbers.
- **Run at Windows startup** — toggle from the settings menu.
- **Desktop shortcut** — run `install_shortcuts.py` to create one.

## Run It

```
python countdown_clock.py
```

First run sets a default target 30 days from now. Open the three-dot menu to change it.

## Shortcuts

From this folder:

- **Desktop icon only:**
  ```
  python install_shortcuts.py
  ```
- **Desktop + launch at Windows startup:**
  ```
  python install_shortcuts.py --startup
  ```
- **Remove shortcuts:**
  ```
  python install_shortcuts.py --remove
  ```

You can also toggle "Run at Windows Startup" directly from the app's settings menu.

## Settings File

Settings live here:

```
%APPDATA%\CountdownClock\settings.json
```

Delete that file to reset to defaults.

## Tips

- **Stuck borderless window?** The three-dot menu is in the top-right. The small × next to it closes the app.
- **Lost the grip?** Resize the window from the bottom-right corner (a small ◢ marker).
- **Right-click anywhere** on the clock also opens the settings menu.
