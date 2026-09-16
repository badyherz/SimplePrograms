import os
import json
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
from pynput.mouse import Button, Controller as MouseController, Listener as MouseListener
from pynput.keyboard import Controller as KeyboardController, Listener, Key, KeyCode
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from helper.SP_footer_picture import add_footer
from helper.SP_window_utils import center_window

# --- Configuration ---
WINDOW_BACKGROUND_COLOR = "#E6E6E6"
CARD_BACKGROUND_COLOR = "#F0F0F0"
BORDER_COLOR = "#C4C4C4"

TEXT_COLOR = "#1E1E1E"
MUTED_COLOR = "#6B6B6B"
HINT_COLOR = "#1B5FA8"
DANGER_COLOR = "#C55E5E"
GO_COLOR = "#3A8B63"
IDLE_COLOR = "#6B6B6B"
CHIP_BG_COLOR = "#D6E4F0"

CHIP_FLOW_WIDTH = 700  # approximate usable content width used to wrap chips
INFO_TEXT_WRAPLENGTH = 560  # fallback wrap width, recalculated on resize

DOCUMENTS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "SimplePrograms", "Simulated Button Pressing")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(DOCUMENTS_DIR, "settings.json")

mouse = MouseController()
keyboard = KeyboardController()

# Standard mouse buttons offered directly as checkable presets.
MOUSE_BUTTON_PRESETS = ["left", "right", "middle"]

# Friendlier display names for mouse buttons
MOUSE_DISPLAY_NAMES = {
    "left": "Left", "right": "Right", "middle": "Middle",
    "x1": "Mouse 4 (X1)", "x2": "Mouse 5 (X2)",
}

# Common keyboard keys offered directly as checkable presets.
# Any other key (letters, digits, punctuation, non-English keys like "Ö", ...)
# can still be added via "Add Custom Key...".
KEYBOARD_PRESETS = [
    "shift_l", "shift_r", "ctrl_l", "ctrl_r", "alt_l", "alt_gr",
    "space", "enter", "tab", "caps_lock",
]

# Friendlier display names for special keys
KEY_DISPLAY_NAMES = {
    "shift_l": "Left Shift", "shift_r": "Right Shift", "shift": "Shift",
    "ctrl_l": "Left Ctrl", "ctrl_r": "Right Ctrl", "ctrl": "Ctrl",
    "alt_l": "Left Alt", "alt_r": "Right Alt", "alt_gr": "Alt Gr",
    "cmd": "Cmd", "cmd_l": "Left Cmd", "cmd_r": "Right Cmd",
    "space": "Space", "enter": "Enter", "esc": "Esc", "tab": "Tab",
    "backspace": "Backspace", "caps_lock": "Caps Lock",
}

INFO_TEXT = (
    "Info: This program is intended for gaming and was build with that in mind.\nSome other software may not work properly with this program."
)


# --- Mouse Button Helpers ---
def available_mouse_buttons():
    """Return the names of every mouse button pynput can simulate on this
    platform. Windows adds x1/x2, X11 adds button8...button30, so the list
    is read from the Button enum instead of being hard coded."""
    names = []
    for member in Button:
        name = member.name
        if name == "unknown" or name.startswith("scroll"):
            continue
        names.append(name)
    return names


def mouse_button_from_name(name):
    """Return the pynput Button for a stored name, or None if this platform
    does not know it (e.g. settings copied from another operating system)."""
    try:
        return Button[name]
    except KeyError:
        return None


def mouse_button_to_display(name):
    """Return a short, human-readable label for a mouse button name."""
    if name in MOUSE_DISPLAY_NAMES:
        return MOUSE_DISPLAY_NAMES[name]
    if name.startswith("button") and name[6:].isdigit():
        return f"Mouse Button {name[6:]}"
    return name.replace("_", " ").title()


def mouse_button_sort_key(name):
    """Keep the standard buttons in their natural order and sort any extra
    buttons numerically afterwards (button8 before button10)."""
    if name in MOUSE_BUTTON_PRESETS:
        return (0, MOUSE_BUTTON_PRESETS.index(name), name)
    digits = "".join(ch for ch in name if ch.isdigit())
    return (1, int(digits) if digits else 0, name)


# --- Keyboard Key Helpers ---
def key_to_id(key):
    """Return a canonical, JSON-safe string id for a pynput key object."""
    if isinstance(key, KeyCode):
        return key.char if key.char is not None else f"vk_{key.vk}"
    if isinstance(key, Key):
        return key.name
    return str(key)


def key_to_display(key):
    """Return a short, human-readable label for a pynput key object."""
    if isinstance(key, KeyCode):
        return key.char.upper() if key.char else f"VK {key.vk}"
    if isinstance(key, Key):
        return KEY_DISPLAY_NAMES.get(key.name, key.name.replace("_", " ").title())
    return str(key)


def key_to_dict(key, vk=None):
    if isinstance(key, KeyCode):
        data = {"type": "char", "id": key_to_id(key), "display": key_to_display(key)}
        resolved_vk = vk if vk is not None else key.vk
        if resolved_vk is not None:
            data["vk"] = resolved_vk
        return data
    return {"type": "special", "id": key_to_id(key), "display": key_to_display(key)}


def key_from_dict(data):
    if data["type"] == "char":
        vk = data.get("vk")
        if vk is not None:
            return KeyCode.from_vk(vk)
        return KeyCode.from_char(data["id"])
    try:
        return Key[data["id"]]
    except KeyError:
        return None


# --- Application ---
class MouseSimulatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simulated Button Pressing")
        self.root.geometry("680x600")
        self.root.minsize(680, 600)
        add_footer(root, image_path="assets/footer.png")
        if WINDOW_BACKGROUND_COLOR:
            root.configure(bg=WINDOW_BACKGROUND_COLOR)
        center_window(root)

        # --- Simulation State ---
        self.simulating = False        # are the target buttons currently pressed down?
        self.combo_active = False      # is the activation combo currently fully held?
        self.hold_mode = True

        self.target_mouse_buttons = set()      # e.g. {"left", "x1"}
        self.target_keyboard_keys = []         # list of key dicts (see key_to_dict)
        self.activation_combo = []             # list of key dicts required to activate

        self.currently_pressed_keys = set()    # ids of keys currently held down

        # Remember what was actually pressed so the exact same targets are
        # released again, even if the selection changed in the meantime.
        self._pressed_mouse_buttons = []
        self._pressed_keyboard_keys = []

        # --- Capture State ---
        self.capturing_target_key = False
        self.capturing_mouse_button = False
        self.capturing_activation = False
        self._mouse_capture_listener = None
        self._activation_capture_keys = set()
        self._activation_capture_result = []

        # Widget variable placeholders, populated in create_widgets()
        self.mouse_button_vars = {}
        self.keyboard_preset_vars = {}

        self.load_settings()
        self.create_widgets()

        # Listener to monitor key presses
        self.listener = Listener(on_press=self.on_key_press, on_release=self.on_key_release)
        self.listener.start()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- GUI Construction ---
    def create_widgets(self):
        self._build_status_bar()
        self._build_mouse_button_section()
        self._build_keyboard_button_section()
        self._build_mode_section()
        self._build_activation_section()
        self._build_footer_row()

    def _create_section(self, title):
        frame = tk.LabelFrame(
            self.root, text=f" {title} ", bg=CARD_BACKGROUND_COLOR, fg=TEXT_COLOR,
            font=("Segoe UI", 9, "bold"), bd=1, relief="groove",
        )
        frame.pack(fill="x", padx=10, pady=5)
        return frame

    # --- Status Bar ---
    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg=CARD_BACKGROUND_COLOR, bd=1, relief="groove")
        bar.pack(fill="x", padx=10, pady=(10, 5))

        inner = tk.Frame(bar, bg=CARD_BACKGROUND_COLOR)
        inner.pack(fill="x", padx=10, pady=8)

        self.status_dot = tk.Canvas(
            inner, width=14, height=14, bg=CARD_BACKGROUND_COLOR,
            highlightthickness=0, bd=0,
        )
        self.status_dot_id = self.status_dot.create_oval(2, 2, 13, 13, fill=IDLE_COLOR, outline="")
        self.status_dot.pack(side="left")

        tk.Label(
            inner, text="Status:", bg=CARD_BACKGROUND_COLOR, font=("Segoe UI", 9),
        ).pack(side="left", padx=(8, 6))

        self.status_label = tk.Label(
            inner, text="Idle", bg=CARD_BACKGROUND_COLOR, fg=IDLE_COLOR, font=("Segoe UI", 11, "bold"),
        )
        self.status_label.pack(side="left")

        self.stop_button = tk.Button(
            inner, text="Stop", width=10, command=self.stop_simulation,
            bg=DANGER_COLOR, fg="white", activebackground="#C27A7A", activeforeground="white",
            font=("Segoe UI", 9, "bold"), relief="flat", bd=0, highlightthickness=0, cursor="hand2",
        )
        self.stop_button.pack(side="right")

        # Short reminder of what currently triggers the simulation.
        self.status_hint_label = tk.Label(
            inner, text="", bg=CARD_BACKGROUND_COLOR, fg=MUTED_COLOR, font=("Segoe UI", 9),
        )
        self.status_hint_label.pack(side="right", padx=(10, 12))

        self._refresh_status()
        self._refresh_status_hint()

    def _refresh_status(self):
        """Update the status text and the coloured indicator dot."""
        if self.simulating:
            self.status_label.config(text="Active", fg=GO_COLOR)
            self.status_dot.itemconfig(self.status_dot_id, fill=GO_COLOR)
        else:
            self.status_label.config(text="Idle", fg=IDLE_COLOR)
            self.status_dot.itemconfig(self.status_dot_id, fill=IDLE_COLOR)

    def _refresh_status_hint(self):
        mode = "Hold" if self.hold_mode else "Toggle"
        if self.activation_combo:
            combo = " + ".join(k["display"] for k in self.activation_combo)
            self.status_hint_label.config(text=f"{mode} \u00b7 {combo}", fg=MUTED_COLOR)
        else:
            self.status_hint_label.config(text=f"{mode} \u00b7 no activation key", fg=DANGER_COLOR)

    # --- Chip Display Helper ---
    def _render_chip_flow(self, container, chips, remove_callback):
        """Render `chips` (dicts with 'id' / 'display') as bold, clickable
        labels that flow left-to-right and wrap onto a new row once the
        current row would overflow. Clicking a chip removes it."""
        for child in container.winfo_children():
            child.destroy()

        background = container.cget("bg")

        if not chips:
            tk.Label(container, text="None selected", bg=background, fg="#777777").pack(anchor="w")
            return

        font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        row = tk.Frame(container, bg=background)
        row.pack(anchor="w", fill="x")
        used_width = 0

        for chip in chips:
            text = f"{chip['display']}  \u00d7"
            chip_width = font.measure(text) + 24
            if used_width + chip_width > CHIP_FLOW_WIDTH and used_width > 0:
                row = tk.Frame(container, bg=background)
                row.pack(anchor="w", fill="x")
                used_width = 0

            label = tk.Label(
                row, text=text, font=font, bg=CHIP_BG_COLOR, relief="solid", bd=1,
                padx=6, pady=2, cursor="hand2",
            )
            label.pack(side="left", padx=3, pady=3)
            label.bind("<Button-1>", lambda e, cid=chip["id"]: remove_callback(cid))
            used_width += chip_width + 6

    # --- Mouse Button Selection ---
    def _build_mouse_button_section(self):
        frame = self._create_section("Mouse Buttons (to press)")

        controls = tk.Frame(frame, bg=CARD_BACKGROUND_COLOR)
        controls.pack(anchor="w", padx=5, pady=5, fill="x")

        menubutton = tk.Menubutton(controls, text="Select Mouse Buttons \u25be", relief="raised")
        menu = tk.Menu(menubutton, tearoff=0)
        menubutton.config(menu=menu)

        available = available_mouse_buttons()
        presets = [name for name in MOUSE_BUTTON_PRESETS if name in available]
        extras = [name for name in available if name not in presets]

        for name in presets:
            menu.add_checkbutton(
                label=mouse_button_to_display(name),
                variable=self._create_mouse_button_var(name),
                command=lambda n=name: self._on_mouse_button_toggle(n),
            )

        # Any additional buttons this platform supports (x1/x2 on Windows,
        # button8+ on X11) live in a submenu to keep the main list short.
        if extras:
            extra_menu = tk.Menu(menu, tearoff=0)
            for name in extras:
                extra_menu.add_checkbutton(
                    label=mouse_button_to_display(name),
                    variable=self._create_mouse_button_var(name),
                    command=lambda n=name: self._on_mouse_button_toggle(n),
                )
            menu.add_separator()
            menu.add_cascade(label="More Mouse Buttons", menu=extra_menu)

        menubutton.pack(side="left")

        add_button = tk.Button(controls, text="Add Custom Key...", command=self.start_custom_mouse_capture)
        add_button.pack(side="left", padx=(6, 0))

        clear_mouse_button = tk.Button(controls, text="Clear", command=self.clear_target_mouse_buttons)
        clear_mouse_button.pack(side="left", padx=(6, 0))

        self.mouse_status_label = tk.Label(frame, text="", bg=CARD_BACKGROUND_COLOR)
        self.mouse_status_label.pack(anchor="w", padx=5, pady=(0, 2))

        self.mouse_chip_frame = tk.Frame(frame, bg=CARD_BACKGROUND_COLOR)
        self.mouse_chip_frame.pack(fill="x", padx=5, pady=(0, 8))
        self._refresh_mouse_chips()

    def _create_mouse_button_var(self, name):
        var = tk.BooleanVar(value=name in self.target_mouse_buttons)
        self.mouse_button_vars[name] = var
        return var

    def _on_mouse_button_toggle(self, name):
        if self.mouse_button_vars[name].get():
            self.target_mouse_buttons.add(name)
        else:
            self.target_mouse_buttons.discard(name)
        self._refresh_mouse_chips()
        self.save_settings()

    def _remove_mouse_button(self, name):
        self.target_mouse_buttons.discard(name)
        if name in self.mouse_button_vars:
            self.mouse_button_vars[name].set(False)
        self._refresh_mouse_chips()
        self.save_settings()

    def clear_target_mouse_buttons(self):
        self.target_mouse_buttons = set()
        for var in self.mouse_button_vars.values():
            var.set(False)
        self._refresh_mouse_chips()
        self.save_settings()

    def _refresh_mouse_chips(self):
        chips = [
            {"id": name, "display": mouse_button_to_display(name)}
            for name in sorted(self.target_mouse_buttons, key=mouse_button_sort_key)
        ]
        self._render_chip_flow(self.mouse_chip_frame, chips, self._remove_mouse_button)

    # --- Custom Mouse Button Capture ---
    def start_custom_mouse_capture(self):
        """Listen for the next physical mouse click and add that button.
        Useful for extra thumb buttons whose name is hard to guess."""
        if self.capturing_mouse_button:
            return
        self.capturing_mouse_button = True
        self.mouse_status_label.config(
            text="Press any mouse button to add it (Esc to cancel)...", fg=HINT_COLOR,
        )
        self._mouse_capture_listener = MouseListener(on_click=self._on_mouse_capture_click)
        self._mouse_capture_listener.start()

    def _on_mouse_capture_click(self, x, y, button, pressed):
        # Only react to the press, so the release of the click that started
        # the capture is ignored.
        if not pressed:
            return None
        self.root.after(0, lambda b=button: self._finish_mouse_capture(b))
        return False  # stop this listener

    def _finish_mouse_capture(self, button):
        self.capturing_mouse_button = False
        self._mouse_capture_listener = None

        name = getattr(button, "name", None)
        if not name or name == "unknown":
            self.mouse_status_label.config(text="That mouse button is not supported.", fg=DANGER_COLOR)
            return

        if name in self.target_mouse_buttons:
            self.mouse_status_label.config(
                text=f"{mouse_button_to_display(name)} is already selected.", fg=HINT_COLOR,
            )
            return

        self.target_mouse_buttons.add(name)
        if name in self.mouse_button_vars:
            self.mouse_button_vars[name].set(True)
        self.mouse_status_label.config(text=f"Added: {mouse_button_to_display(name)}", fg=GO_COLOR)
        self._refresh_mouse_chips()
        self.save_settings()

    def _cancel_mouse_capture(self):
        if not self.capturing_mouse_button:
            return
        self.capturing_mouse_button = False
        self._stop_mouse_capture_listener()
        self.mouse_status_label.config(text="")

    def _stop_mouse_capture_listener(self):
        if self._mouse_capture_listener is not None:
            try:
                self._mouse_capture_listener.stop()
            except Exception:
                pass
            self._mouse_capture_listener = None

    # --- Keyboard Button Selection ---
    def _build_keyboard_button_section(self):
        frame = self._create_section("Keyboard Buttons (to press)")

        controls = tk.Frame(frame, bg=CARD_BACKGROUND_COLOR)
        controls.pack(anchor="w", padx=5, pady=5, fill="x")

        menubutton = tk.Menubutton(controls, text="Select Keyboard Buttons \u25be", relief="raised")
        menu = tk.Menu(menubutton, tearoff=0)
        menubutton.config(menu=menu)
        for key_id in KEYBOARD_PRESETS:
            is_selected = any(k["id"] == key_id for k in self.target_keyboard_keys)
            var = tk.BooleanVar(value=is_selected)
            self.keyboard_preset_vars[key_id] = var
            menu.add_checkbutton(
                label=KEY_DISPLAY_NAMES.get(key_id, key_id.title()), variable=var,
                command=lambda k=key_id: self._on_keyboard_preset_toggle(k),
            )
        menubutton.pack(side="left")

        add_button = tk.Button(controls, text="Add Custom Key...", command=self.start_custom_key_capture)
        add_button.pack(side="left", padx=(6, 0))

        clear_keyboard_button = tk.Button(controls, text="Clear", command=self.clear_target_keyboard_keys)
        clear_keyboard_button.pack(side="left", padx=(6, 0))

        self.keyboard_status_label = tk.Label(frame, text="", bg=CARD_BACKGROUND_COLOR)
        self.keyboard_status_label.pack(anchor="w", padx=5, pady=(0, 2))

        self.keyboard_chip_frame = tk.Frame(frame, bg=CARD_BACKGROUND_COLOR)
        self.keyboard_chip_frame.pack(fill="x", padx=5, pady=(0, 8))
        self._refresh_keyboard_chips()

    def _on_keyboard_preset_toggle(self, key_id):
        if self.keyboard_preset_vars[key_id].get():
            self.add_target_keyboard_key(Key[key_id])
        else:
            self.remove_target_keyboard_key(key_id)

    def start_custom_key_capture(self):
        self.capturing_target_key = True
        self.keyboard_status_label.config(text="Press any key to add it...", fg=HINT_COLOR)

    def add_target_keyboard_key(self, key_obj, vk=None):
        key_id = key_to_id(key_obj)
        if any(k["id"] == key_id for k in self.target_keyboard_keys):
            return
        self.target_keyboard_keys.append(key_to_dict(key_obj, vk=vk))
        self._refresh_keyboard_chips()
        self.save_settings()

    def remove_target_keyboard_key(self, key_id):
        self.target_keyboard_keys = [k for k in self.target_keyboard_keys if k["id"] != key_id]
        if key_id in self.keyboard_preset_vars:
            self.keyboard_preset_vars[key_id].set(False)
        self._refresh_keyboard_chips()
        self.save_settings()

    def clear_target_keyboard_keys(self):
        self.target_keyboard_keys = []
        for var in self.keyboard_preset_vars.values():
            var.set(False)
        self._refresh_keyboard_chips()
        self.save_settings()

    def _refresh_keyboard_chips(self):
        self._render_chip_flow(self.keyboard_chip_frame, self.target_keyboard_keys, self.remove_target_keyboard_key)

    # --- Mode Selection ---
    def _build_mode_section(self):
        frame = self._create_section("Mode")

        self.hold_mode_var = tk.BooleanVar(value=self.hold_mode)
        radio_style = {
            "bg": CARD_BACKGROUND_COLOR, "activebackground": CARD_BACKGROUND_COLOR,
            "fg": TEXT_COLOR, "selectcolor": "white", "highlightthickness": 0,
        }
        tk.Radiobutton(
            frame, text="Hold (press only while activation key is held)",
            variable=self.hold_mode_var, value=True, command=self.on_mode_change, **radio_style,
        ).pack(anchor="w", padx=10, pady=2)
        tk.Radiobutton(
            frame, text="Toggle (press activation key once to start/stop)",
            variable=self.hold_mode_var, value=False, command=self.on_mode_change, **radio_style,
        ).pack(anchor="w", padx=10, pady=(2, 5))

    def on_mode_change(self):
        # Safety: release any held targets before switching modes so nothing
        # is left stuck pressed down.
        if self.simulating:
            self.release_all_targets()
        self.combo_active = False
        self.hold_mode = self.hold_mode_var.get()
        self._refresh_status_hint()
        self.save_settings()

    # --- Activation Key Capture ---
    def _build_activation_section(self):
        frame = self._create_section("Custom Key to Activate")

        tk.Label(
            frame, text="Combinations are supported, e.g. Ctrl + E.",
            bg=CARD_BACKGROUND_COLOR, fg=TEXT_COLOR,
        ).pack(anchor="w", padx=10, pady=(5, 0))

        button = tk.Button(frame, text="Set Activation Key(s)", command=self.start_activation_capture)
        button.pack(anchor="w", padx=10, pady=5)

        self.activation_label = tk.Label(frame, text="", bg=CARD_BACKGROUND_COLOR)
        self.activation_label.pack(anchor="w", padx=10, pady=(0, 5))
        self._refresh_activation_label()

    def start_activation_capture(self):
        self.capturing_activation = True
        self._activation_capture_keys = set()
        self._activation_capture_result = []
        self.activation_label.config(text="Press key combo...", fg=HINT_COLOR)

    def _refresh_activation_label(self):
        if self.activation_combo:
            display = " + ".join(k["display"] for k in self.activation_combo)
            self.activation_label.config(text=f"Activation: {display}", fg=GO_COLOR, font=("Arial", 9, "bold"))
        else:
            self.activation_label.config(text="No activation key set", fg=DANGER_COLOR)
        self._refresh_status_hint()

    # --- Footer Row ---
    def _build_footer_row(self):
        row = tk.Frame(self.root, bg=WINDOW_BACKGROUND_COLOR)
        row.pack(fill="x", padx=10, pady=10)

        self.clear_button = tk.Button(
            row, text="Clear All Settings", command=self.clear_all_settings,
            bg=HINT_COLOR, fg="white", activebackground="#547DA8", activeforeground="white",
        )
        self.clear_button.pack(side="right", padx=(10, 0))

        self.info_label = tk.Label(
            row, text=INFO_TEXT,
            bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=("Segoe UI", 8),
            justify="left", anchor="w", wraplength=INFO_TEXT_WRAPLENGTH,
        )
        self.info_label.pack(side="left", fill="x", expand=True)

        row.bind("<Configure>", self._on_footer_row_resize)

    def _on_footer_row_resize(self, event):
        """Keep the info text wrapping inside the space left of the button."""
        available = event.width - self.clear_button.winfo_reqwidth() - 20
        self.info_label.config(wraplength=max(200, available))

    # --- Settings Persistence ---
    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Could not load settings, using defaults: {e}")
            return

        # Drop buttons this platform cannot simulate (e.g. settings written
        # on a different operating system).
        self.target_mouse_buttons = {
            name for name in data.get("mouse_buttons", []) if mouse_button_from_name(name) is not None
        }
        self.target_keyboard_keys = data.get("keyboard_buttons", [])
        self.hold_mode = data.get("hold_mode", True)
        self.activation_combo = data.get("activation_combo", [])

    def save_settings(self):
        settings = {
            "mouse_buttons": sorted(self.target_mouse_buttons, key=mouse_button_sort_key),
            "keyboard_buttons": self.target_keyboard_keys,
            "hold_mode": self.hold_mode,
            "activation_combo": self.activation_combo,
        }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"Could not save settings: {e}")

    def clear_all_settings(self):
        if not messagebox.askyesno(
            "Clear All Settings", "Reset all settings to their defaults? This cannot be undone."
        ):
            return

        if self.simulating:
            self.release_all_targets()
        self.combo_active = False
        self._cancel_mouse_capture()
        self.capturing_target_key = False
        self.capturing_activation = False

        self.target_mouse_buttons = set()
        self.target_keyboard_keys = []
        self.hold_mode = True
        self.activation_combo = []

        for var in self.mouse_button_vars.values():
            var.set(False)
        for var in self.keyboard_preset_vars.values():
            var.set(False)
        self.hold_mode_var.set(True)

        self.mouse_status_label.config(text="")
        self.keyboard_status_label.config(text="")

        self._refresh_mouse_chips()
        self._refresh_keyboard_chips()
        self._refresh_activation_label()

        self.save_settings()

    # --- Input Event Handling ---
    def _canonical_key(self, key):
        """Normalise a raw key event so modifier keys (Ctrl in particular)
        don't turn it into a control character (e.g. Ctrl+A -> '\\x01').
        Without this, ids/labels for combos like "Ctrl + \u00dc" become garbled."""
        try:
            return self.listener.canonical(key)
        except Exception:
            return key

    def on_key_press(self, key):
        # Keep the raw virtual key code before canonicalising - it is needed
        # to later reproduce this key as a real, "held" key (see key_to_dict).
        raw_vk = getattr(key, "vk", None)
        key = self._canonical_key(key)

        # The listener runs on its own thread, so any code that touches Tk
        # widgets is scheduled onto the main thread via root.after(...).
        if self.capturing_mouse_button:
            if key == Key.esc:
                self.root.after(0, self._cancel_mouse_capture)
            return

        if self.capturing_target_key:
            self.root.after(0, lambda: self._finish_target_key_capture(key, raw_vk))
            return

        if self.capturing_activation:
            self.root.after(0, lambda: self._handle_activation_capture_press(key))
            return

        key_id = key_to_id(key)
        self.currently_pressed_keys.add(key_id)

        if not self.combo_active and self._activation_combo_satisfied():
            self.combo_active = True
            if self.hold_mode:
                self.press_all_targets()
            else:
                self.toggle_simulating()

    def on_key_release(self, key):
        key = self._canonical_key(key)

        if self.capturing_activation:
            self.root.after(0, lambda: self._handle_activation_capture_release(key))
            return

        key_id = key_to_id(key)
        self.currently_pressed_keys.discard(key_id)

        if self.combo_active and not self._activation_combo_satisfied():
            self.combo_active = False
            if self.hold_mode:
                self.release_all_targets()

    def _finish_target_key_capture(self, key, vk=None):
        self.capturing_target_key = False
        self.add_target_keyboard_key(key, vk=vk)
        self.keyboard_status_label.config(text="")

    def _handle_activation_capture_press(self, key):
        key_id = key_to_id(key)
        self._activation_capture_keys.add(key_id)
        if not any(k["id"] == key_id for k in self._activation_capture_result):
            self._activation_capture_result.append(key_to_dict(key))
        display = " + ".join(k["display"] for k in self._activation_capture_result)
        self.activation_label.config(text=f"Press key combo... ({display})", fg=HINT_COLOR)

    def _handle_activation_capture_release(self, key):
        key_id = key_to_id(key)
        self._activation_capture_keys.discard(key_id)
        if not self._activation_capture_keys and self._activation_capture_result:
            self.activation_combo = self._activation_capture_result
            self.capturing_activation = False
            self._refresh_activation_label()
            self.save_settings()

    def _activation_combo_satisfied(self):
        if not self.activation_combo:
            return False
        required_ids = {k["id"] for k in self.activation_combo}
        return required_ids.issubset(self.currently_pressed_keys)

    # --- Simulation Control ---
    def press_all_targets(self):
        self._pressed_mouse_buttons = []
        self._pressed_keyboard_keys = []

        for name in sorted(self.target_mouse_buttons, key=mouse_button_sort_key):
            button = mouse_button_from_name(name)
            if button is None:
                continue
            try:
                mouse.press(button)
            except Exception as e:
                print(f"Could not press mouse button '{name}': {e}")
                continue
            self._pressed_mouse_buttons.append(button)

        for k in self.target_keyboard_keys:
            key_obj = key_from_dict(k)
            if key_obj is None:
                continue
            try:
                keyboard.press(key_obj)
            except Exception as e:
                print(f"Could not press key '{k.get('id')}': {e}")
                continue
            self._pressed_keyboard_keys.append(key_obj)

        self.simulating = True
        self.root.after(0, self._refresh_status)

    def release_all_targets(self):
        for button in self._pressed_mouse_buttons:
            try:
                mouse.release(button)
            except Exception as e:
                print(f"Could not release mouse button '{button}': {e}")
        for key_obj in self._pressed_keyboard_keys:
            try:
                keyboard.release(key_obj)
            except Exception as e:
                print(f"Could not release key '{key_obj}': {e}")

        self._pressed_mouse_buttons = []
        self._pressed_keyboard_keys = []
        self.simulating = False
        self.root.after(0, self._refresh_status)

    def toggle_simulating(self):
        if self.simulating:
            self.release_all_targets()
        else:
            self.press_all_targets()

    def stop_simulation(self):
        """Immediately release everything and go back to idle, without
        touching any of the configured settings."""
        if self.simulating:
            self.release_all_targets()
        self.combo_active = False

    # --- Shutdown ---
    def on_close(self):
        if self.simulating:
            self.release_all_targets()
        self._stop_mouse_capture_listener()
        self.listener.stop()
        self.save_settings()
        self.root.destroy()


# --- Entry Point ---
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    app = MouseSimulatorApp(root)
    root.deiconify()
    root.mainloop()