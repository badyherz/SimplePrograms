import configparser
import ctypes
import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import traceback
from ctypes import wintypes
from datetime import datetime

if sys.platform != "win32":
    sys.exit("This Overlay works only under Windows.")

VERSION = "2.1"
CONFIG_NAME = "mcd_clock_overlay.ini"
LOG_NAME = "mcd_clock_overlay.log"
MUTEX_NAME = "MCD_Clock_Overlay_Mutex"
TRANSPARENT = "#010101"
CORNERS = ["top_right", "top_left", "bottom_left", "bottom_right"]
TICK_MS = 150

# --- Settings: (Key, Default Value, Comment for the ini file) ---
SPEC = [
    ("scale", "4", "Size of a Pixel (1-20). 3 = small, 4 = medium, 6 = large."),
    ("show_seconds", "false", "Show seconds (true/false)."),
    ("use_24h", "true", "24-hour display (true) or 12-hour display (false)."),
    ("corner", "top_left", "Position: top_right, top_left, bottom_left or bottom_right."),
    ("margin", "30", "Distance from window edge in pixels (0-500)."),
    ("text_color", "#FFFFFF", "Text color as a hex value (Minecraft-White)."),
    ("shadow_color", "#3F3F3F", "Shadow color as a hex value (Minecraft-Shadow)."),
    ("trans_shadow", "false", "Shadows of the digits in the colors of the trans-flag! (true/false)."),
    ("hotkey_corner", "F8", "Key for switching the corner (F1-F12 or a single letter/number)."),
    ("hotkey_toggle", "F9", "Key for hiding and showing the clock."),
    ("game_title_part", "Dungeons", "Part of the window title where the game is recognized."),
    ("wait_for_game_seconds", "300", "How long to wait for the game start before the overlay exits (0 = unlimited)."),
    ("exit_grace_seconds", "3", "Only a fallback: how long the game window may be missing before the overlay exits (1-60)."),
]

def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def config_path():
    return os.path.join(app_dir(), CONFIG_NAME)

_log_file = None

def log(message):
    if _log_file:
        try:
            _log_file.write(time.strftime("%H:%M:%S ") + str(message) + "\n")
        except (OSError, ValueError):
            pass

def log_start():
    """Creates the log file next to the .exe (alternatively in the temp folder). It is rewritten on every start."""
    global _log_file
    for folder in (app_dir(), tempfile.gettempdir()):
        try:
            _log_file = open(os.path.join(folder, LOG_NAME), "w", encoding="utf-8", buffering=1)
            break
        except OSError:
            continue
    log(f"Minecraft Dungeons Clock-Overlay, Version {VERSION}")
    log(f"Program: {sys.executable}")
    log(f"Folder: {app_dir()}")
    log(f"Arguments: {sys.argv[1:]}")
    log(f"Working Directory: {os.getcwd()}")

def default_config_text():
    lines = [
        "; Configuration for the Minecraft-Dungeons-Clock-Overlay",
        "; Lines starting with ; or # are comments (please always in a separate line).",
        "; Missing or invalid values will be replaced by the default values.",
        "; Changes take effect from the next start of the overlay.",
        "",
        "[Overlay]",
    ]
    for key, value, comment in SPEC:
        lines += [f"; {comment}", f"{key} = {value}", ""]
    return "\n".join(lines)

def parse_int(text, lo, hi):
    try:
        return min(max(int(text.strip()), lo), hi)
    except (ValueError, AttributeError):
        return None

def parse_bool(text):
    value = str(text).strip().lower()
    if value in ("1", "true", "yes", "ja", "on", "an"):
        return True
    if value in ("0", "false", "no", "nein", "off", "aus"):
        return False
    return None

def parse_color(text):
    value = str(text).strip()
    if len(value) == 7 and value[0] == "#":
        try:
            int(value[1:], 16)
            return value
        except ValueError:
            pass
    return None

def parse_corner(text):
    value = str(text).strip().lower()
    return value if value in CORNERS else None

def parse_key(text):
    value = str(text).strip().upper()
    if value.startswith("F") and value[1:].isdigit() and 1 <= int(value[1:]) <= 12:
        return 0x70 + int(value[1:]) - 1
    if len(value) == 1 and value.isalnum():
        return ord(value)
    return None

def parse_str(text):
    return str(text).strip()

class Settings:
    """Reads the ini file; in case of errors, the default values apply."""

    def __init__(self, raw):
        defaults = {key: value for key, value, _ in SPEC}

        def pick(key, parser):
            value = parser(raw.get(key, defaults[key]))
            return value if value is not None else parser(defaults[key])

        self.scale = pick("scale", lambda s: parse_int(s, 1, 20))
        self.show_seconds = pick("show_seconds", parse_bool)
        self.use_24h = pick("use_24h", parse_bool)
        self.corner = pick("corner", parse_corner)
        self.margin = pick("margin", lambda s: parse_int(s, 0, 500))
        self.text_color = pick("text_color", parse_color)
        self.shadow_color = pick("shadow_color", parse_color)
        self.trans_shadow = pick("trans_shadow", parse_bool)
        self.hotkey_corner = pick("hotkey_corner", parse_key)
        self.hotkey_toggle = pick("hotkey_toggle", parse_key)
        self.game_title_part = pick("game_title_part", parse_str)
        self.wait_for_game = pick("wait_for_game_seconds", lambda s: parse_int(s, 0, 86400))
        self.exit_grace = pick("exit_grace_seconds", lambda s: parse_int(s, 1, 60))

def load_settings():
    """Loads the configuration. If it's missing, the default values are used and a template is created."""
    path = config_path()
    raw = {}
    if os.path.isfile(path):
        try:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(path, encoding="utf-8-sig")
            if parser.has_section("Overlay"):
                raw = dict(parser.items("Overlay"))
                log(f"Config loaded: {path}")
            else:
                log(f"Config without section [Overlay], default values apply: {path}")
        except (configparser.Error, OSError, UnicodeError) as exc:
            raw = {}
            log(f"Config not readable ({exc!r}), default values apply: {path}")
    else:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(default_config_text())
            log(f"No config found, template created: {path}")
        except OSError as exc:
            log(f"No config found, template could not be created ({exc!r}): {path}")
    try:
        return Settings(raw)
    except Exception:
        log("Error while evaluating the config, default values apply:\n" + traceback.format_exc())
        return Settings({})
# ---

# 5x7-Pixel font in a Minecraft-Look
FONT = {
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": [".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    ":": [".", ".", "#", ".", "#", ".", "."],
}
GLYPH_H = 7

# Colors of the trans-flag: blue, pink, white, pink, blue
STRIPES = ["#5BCEFA", "#F5A9B8", "#FFFFFF", "#F5A9B8", "#5BCEFA"]
SHADOW_OFFSET = 1   # Shadow: 1 pixel to the right and bottom

# Colon: gap = additional spacing left/right, rows = rows of the two dots.
COLON = dict(gap=0, rows=(2, 4))

def stripe_color(row, total_rows):
    """Flag color for a whole pixel row: the five stripes are distributed across the rows."""
    return STRIPES[min(4, int((row + 0.5) * 5 / total_rows))]

def layout_text(text, colon=COLON):
    """Sets the text together from pixels: (digit pixels, dot pixels, width in pixels)."""
    digits, dots, x = [], [], 0
    for ch in text:
        if ch == ":":
            x += colon["gap"]
            for top in colon["rows"]:
                dots.append((x, top))
            x += 1 + 1 + colon["gap"]
        else:
            glyph = FONT[ch]
            for row, line in enumerate(glyph):
                for col, cell in enumerate(line):
                    if cell == "#":
                        digits.append((x + col, row))
            x += len(glyph[0]) + 1
    return digits, dots, x - 1


# --- Windows-API-Access ---
user32 = ctypes.windll.user32
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # correct pixel coordinates
except Exception:
    pass

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]

kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

shell32 = ctypes.windll.shell32
shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                  wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
shell32.ShellExecuteW.restype = ctypes.c_void_p

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020   # Mouse clicks go through the overlay
WS_EX_TOOLWINDOW = 0x00000080    # no entry in the taskbar
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000    # never takes focus from the game
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0x00000000
WAIT_ABANDONED = 0x00000080

def _text_of(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value

def _class_of(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value

def find_game_window(title_part):
    """Searches for the Unreal Engine window of Minecraft Dungeons."""
    exact, fallback = [], []

    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and _class_of(hwnd) == "UnrealWindow":
            if title_part.lower() in _text_of(hwnd).lower():
                exact.append(hwnd)
            else:
                fallback.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    if exact:
        return exact[0]
    return fallback[0] if fallback else None

def client_area(hwnd):
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, rect.right, rect.bottom

def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)

def window_pid(hwnd):
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value

def acquire_single_instance(wait_ms=10000):
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True  # Mutex not creatable -> do not block
    result = kernel32.WaitForSingleObject(handle, wait_ms)
    if result in (WAIT_OBJECT_0, WAIT_ABANDONED):
        return handle
    kernel32.CloseHandle(handle)
    return None

def launch_game_from_args():
    args = sys.argv[1:]
    if not args:
        log("No start arguments: Overlay is waiting for an already running game.")
        return None
    log(f"Starting game: {args}")
    try:
        child = subprocess.Popen(args)
        log(f"Game started (Process {child.pid}).")
        return child
    except Exception as exc:
        log(f"Direct start failed: {exc!r}")
    # Fallback: start the Windows-Shell (works also for programs that require admin rights)
    try:
        params = subprocess.list2cmdline(args[1:]) or None
        result = shell32.ShellExecuteW(None, "open", args[0], params, os.getcwd(), 1)
        ok = (result or 0) > 32
        log(f"Start via Windows Shell: {'ok' if ok else 'failed (Code %s)' % result}")
    except Exception:
        log("Start via Windows Shell failed:\n" + traceback.format_exc())
    return None


# --- Presentation ---
class ClockOverlay:
    def __init__(self, cfg):
        self.cfg = cfg
        self.corner_index = CORNERS.index(cfg.corner)
        self.last_text = None
        self.last_pos = None
        self.shown = True
        self.hidden_by_user = False
        self.game_seen = False
        self.game_pid = None
        self.proc_handle = None
        self.missing_since = None
        self.start_time = time.monotonic()
        self.keys = [[cfg.hotkey_corner, "corner", False], [cfg.hotkey_toggle, "toggle", False]]

        self.root = tk.Tk()
        self.root.title("MCD Clock Overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT)
        self.root.attributes("-transparentcolor", TRANSPARENT)

        sample = "00:00:00" if cfg.show_seconds else "00:00"
        sample_width = layout_text(sample)[2]
        self.cw = (sample_width + SHADOW_OFFSET) * cfg.scale   # + Space for the shadow
        self.ch = (GLYPH_H + SHADOW_OFFSET) * cfg.scale
        self.canvas = tk.Canvas(self.root, width=self.cw, height=self.ch,
                                bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.root.update_idletasks()
        self.apply_window_style()
        self.root.withdraw()       # only show when the game is running and in the foreground
        self.shown = False
        log(f"Overlay ready, waiting for the game window. Trans-Shadows: {cfg.trans_shadow}")
        self.tick()

    # --- Window Style ---
    def apply_window_style(self):
        wid = self.root.winfo_id()
        hwnd = user32.GetParent(wid) or wid
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        self.root.attributes("-topmost", True)

    def draw(self, text):
        cfg = self.cfg
        sc = cfg.scale
        digits, dots, _ = layout_text(text)
        self.canvas.delete("all")

        def cell(col, row, color):
            x0, y0 = col * sc, row * sc
            self.canvas.create_rectangle(x0, y0, x0 + sc, y0 + sc, fill=color, outline="")

        total_rows = GLYPH_H + SHADOW_OFFSET
        for col, row in digits:
            color = (stripe_color(row + SHADOW_OFFSET, total_rows)
                     if cfg.trans_shadow else cfg.shadow_color)
            cell(col + SHADOW_OFFSET, row + SHADOW_OFFSET, color)
        for col, row in dots:
            cell(col + SHADOW_OFFSET, row + SHADOW_OFFSET, cfg.shadow_color)

        for col, row in digits + dots:
            cell(col, row, cfg.text_color)

    def place(self, area):
        ax, ay, aw, ah = area
        corner = CORNERS[self.corner_index]
        m = self.cfg.margin
        x = ax + (m if "left" in corner else aw - self.cw - m)
        y = ay + (m if "top" in corner else ah - self.ch - m)
        if (x, y) != self.last_pos:
            self.root.geometry(f"+{x}+{y}")
            self.last_pos = (x, y)

    # --- Game Tracking ---
    def track_game(self, hwnd):
        """Tracks the game process to detect when it exits."""
        pid = window_pid(hwnd)
        if pid == self.game_pid:
            return
        self.release_process()
        self.game_pid = pid
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        self.proc_handle = handle if handle else None
        log(f"Game window detected: '{_text_of(hwnd)}' (Process {pid}, "
            f"{'Process monitoring active' if self.proc_handle else 'window monitoring only'})")

    def release_process(self):
        if self.proc_handle:
            kernel32.CloseHandle(self.proc_handle)
        self.proc_handle = None

    def game_has_exited(self, game, now):
        if self.proc_handle:
            return kernel32.WaitForSingleObject(self.proc_handle, 0) == WAIT_OBJECT_0
        # Fallback with Process Handle: Window must be missing for a short time
        if game is None:
            if self.missing_since is None:
                self.missing_since = now
            return now - self.missing_since >= self.cfg.exit_grace
        self.missing_since = None
        return False

    def quit(self, reason):
        log(f"Overlay stopped: {reason}")
        self.release_process()
        self.root.destroy()

    # --- Hotkeys ---
    def handle_hotkeys(self):
        for entry in self.keys:
            vk, action, was_down = entry
            down = key_down(vk)
            if down and not was_down:
                if action == "corner":
                    self.corner_index = (self.corner_index + 1) % len(CORNERS)
                    self.last_pos = None
                elif action == "toggle":
                    self.hidden_by_user = not self.hidden_by_user
            entry[2] = down

    # --- Main Loop ---
    def tick(self):
        self.handle_hotkeys()

        game = find_game_window(self.cfg.game_title_part)
        now = time.monotonic()
        area = (0, 0, 0, 0)
        visible = False

        if game is not None:
            self.track_game(game)
            self.game_seen = True
            self.missing_since = None
            area = client_area(game)
            visible = user32.GetForegroundWindow() == game and not user32.IsIconic(game)

        if self.game_seen:
            if self.game_has_exited(game, now):
                self.quit("Game process has been terminated")
                return
        elif self.cfg.wait_for_game and now - self.start_time >= self.cfg.wait_for_game:
            self.quit("Game was not found within the wait time")
            return

        visible = visible and not self.hidden_by_user

        if visible and not self.shown:
            self.root.deiconify()
            self.apply_window_style()
            self.shown = True
        elif not visible and self.shown:
            self.root.withdraw()
            self.shown = False

        if self.shown:
            self.place(area)
            fmt = ("%H" if self.cfg.use_24h else "%I") + (":%M:%S" if self.cfg.show_seconds else ":%M")
            text = datetime.now().strftime(fmt)
            if text != self.last_text:
                self.draw(text)
                self.last_text = text

        self.root.after(TICK_MS, self.tick)

    def run(self):
        self.root.mainloop()

def main():
    child = None
    try:
        log_start()
        child = launch_game_from_args()
        cfg = load_settings()
        lock = acquire_single_instance()
        if lock is None:
            log("Another Overlay is already running - this one will close.")
            if child is not None:
                child.wait()
            return
        log("Single instance secured.")
        ClockOverlay(cfg).run()
    except Exception:
        log("Unexpected error:\n" + traceback.format_exc())
        if child is not None:
            child.wait()


if __name__ == "__main__":
    main()