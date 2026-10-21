import hashlib
import os
import queue
import sys
import threading
import tkinter as tk
import tkinter.font as tkFont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import blake3
from tkinterdnd2 import DND_FILES, TkinterDnD

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from helper.SP_footer_picture import add_footer
from helper.SP_window_utils import center_window


# --- Constants ---
WINDOW_BACKGROUND_COLOR = "#E6E6E6"
GROUP_BORDER_COLOR = "#A7A7A7"
BOX_BORDER_THICKNESS = 0.5
BOX_INTERNAL_PADDING = 4
BOX_EXTERNAL_PADDING = 10
BUTTON_WIDTH = 20

SUCCESS_COLOR = "#3A8B63"
ERROR_COLOR = "#C55E5E"
HINT_COLOR = "#1B5FA8"
NEUTRAL_COLOR = "#333333"
MUTED_TEXT_COLOR = "#666666"
DROP_ZONE_COLOR = "#F2F2F2"
DROP_ZONE_ACTIVE_COLOR = "#D5E8DD"
RESULT_FIELD_COLOR = "#F7F7F7"

CHUNK_SIZE = 1024 * 1024        # bytes read per step while hashing files
POLL_INTERVAL_MS = 40           # how often the UI checks the worker thread
HEX_DIGITS = set("0123456789abcdef")

MODE_FILE_FILE = "file_file"
MODE_FILE_TEXT = "file_text"
MODE_TEXT_TEXT = "text_text"
MODE_OPTIONS = [
    (MODE_FILE_FILE, "File vs. File"),
    (MODE_FILE_TEXT, "File vs. Text"),
    (MODE_TEXT_TEXT, "Text vs. Text"),
]
MODE_SLOT_KINDS = {
    MODE_FILE_FILE: ("file", "file"),
    MODE_FILE_TEXT: ("file", "text"),
    MODE_TEXT_TEXT: ("text", "text"),
}

TEXT_TYPE_CHECKSUM = "checksum"
TEXT_TYPE_PLAIN = "plain"
TEXT_TYPE_OPTIONS = [
    (TEXT_TYPE_CHECKSUM, "Checksum"),
    (TEXT_TYPE_PLAIN, "Plain text (hashed)"),
]

DROP_PROMPT = "Drop a file here"
DEFAULT_ALGORITHM = "SHA-256"


# --- Hash algorithms ---
class Algorithm:
    def __init__(self, name, factory):
        self.name = name
        self.factory = factory
        self.hex_length = len(factory().hexdigest())

def _hashlib_factory(hashlib_name, **kwargs):
    """Return a factory for a hashlib algorithm, or None if this Python build lacks it."""
    for options in (kwargs, {}):
        try:
            hashlib.new(hashlib_name, **options)
        except TypeError:
            continue  # "usedforsecurity" is not supported on older Python versions
        except ValueError:
            return None
        return lambda options=options: hashlib.new(hashlib_name, **options)
    return None

def build_algorithms():
    """Build the ordered algorithm registry. Add new algorithms to this list."""
    definitions = [
        ("SHA-224", "sha224", {}),
        ("SHA-256", "sha256", {}),
        ("SHA-384", "sha384", {}),
        ("SHA-512", "sha512", {}),
        ("SHA-512/224", "sha512_224", {}),
        ("SHA-512/256", "sha512_256", {}),
        ("MD5", "md5", {"usedforsecurity": False}),
        ("BLAKE2b", "blake2b", {}),
        ("BLAKE2s", "blake2s", {}),
    ]

    algorithms = {}
    for display_name, hashlib_name, options in definitions:
        factory = _hashlib_factory(hashlib_name, **options)
        if factory is not None:  # silently skip algorithms missing in this Python build
            algorithms[display_name] = Algorithm(display_name, factory)

    algorithms["BLAKE3"] = Algorithm("BLAKE3", lambda: blake3.blake3())
    return algorithms

ALGORITHMS = build_algorithms()


# --- Helper functions ---
def hash_file(path, factory, progress_callback=None):
    """Return the hex digest of a file, reading it in chunks."""
    hasher = factory()
    with open(path, "rb") as file:
        while True:
            chunk = file.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
            if progress_callback:
                progress_callback(len(chunk))
    return hasher.hexdigest()

def hash_text(text, factory):
    """Return the hex digest of a text, encoded as UTF-8 exactly as typed."""
    hasher = factory()
    hasher.update(text.encode("utf-8"))
    return hasher.hexdigest()

def normalize_checksum(raw_text):
    """Remove all whitespace and lowercase, so pasted checksums compare reliably."""
    return "".join(raw_text.split()).lower()

def describe_checksum_issue(checksum, expected_length, algorithm_name):
    """Explain why an entered checksum cannot belong to the selected algorithm."""
    problems = []
    if not set(checksum) <= HEX_DIGITS:
        problems.append("contains characters that are not hexadecimal")
    if len(checksum) != expected_length:
        problems.append(
            f"has {len(checksum)} characters, but {algorithm_name} produces {expected_length}"
        )
    if not problems:
        return ""
    return " and ".join(problems)

def format_size(size_in_bytes):
    size = float(size_in_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


# --- Input slot ---
class InputSlot:
    """One comparison input. It is either a file (drop zone + button) or a text box."""

    def __init__(self, app, parent, name):
        self.app = app
        self.name = name
        self.kind = "file"
        self.file_path = None

        self.frame = tk.Frame(
            parent, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )

        self.title_label = tk.Label(
            self.frame, bg=WINDOW_BACKGROUND_COLOR, anchor="w", font=("Segoe UI", 9, "bold"),
        )
        self.title_label.pack(fill="x", padx=BOX_INTERNAL_PADDING + 2, pady=(BOX_INTERNAL_PADDING, 2))

        # --- File input ---
        self.file_frame = tk.Frame(self.frame, bg=WINDOW_BACKGROUND_COLOR)

        self.drop_label = tk.Label(
            self.file_frame, text=DROP_PROMPT, bg=DROP_ZONE_COLOR, fg=MUTED_TEXT_COLOR,
            relief="groove", bd=2, height=3, wraplength=520, justify="center",
        )
        self.drop_label.pack(fill="x", padx=BOX_INTERNAL_PADDING + 2)

        self.select_button = tk.Button(
            self.file_frame, text="Select File...", width=BUTTON_WIDTH, command=self.select_file,
        )
        self.select_button.pack(anchor="w", padx=BOX_INTERNAL_PADDING + 2, pady=(5, BOX_INTERNAL_PADDING + 2))

        # --- Text input ---
        self.text_frame = tk.Frame(self.frame, bg=WINDOW_BACKGROUND_COLOR)

        self.text_hint_label = tk.Label(
            self.text_frame, bg=WINDOW_BACKGROUND_COLOR, fg=MUTED_TEXT_COLOR, anchor="w",
            font=("Segoe UI", 8),
        )
        self.text_hint_label.pack(fill="x", padx=BOX_INTERNAL_PADDING + 2)

        text_container = tk.Frame(self.text_frame, bg=WINDOW_BACKGROUND_COLOR)
        text_container.pack(fill="x", padx=BOX_INTERNAL_PADDING + 2, pady=(2, BOX_INTERNAL_PADDING + 2))

        self.text_box = tk.Text(
            text_container, height=3, wrap="char", font=("Consolas", 9),
            relief="solid", bd=1, undo=True,
        )
        text_scrollbar = tk.Scrollbar(text_container, orient="vertical", command=self.text_box.yview)
        self.text_box.configure(yscrollcommand=text_scrollbar.set)
        self.text_box.pack(side="left", fill="x", expand=True)
        text_scrollbar.pack(side="right", fill="y")
        self.text_box.bind("<<Modified>>", self._on_text_modified)

        # --- Drag & drop ---
        drop_widgets = [
            self.frame, self.title_label, self.file_frame, self.drop_label, self.select_button,
        ]
        for widget in drop_widgets:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            widget.dnd_bind("<<DropEnter>>", self._on_drop_enter)
            widget.dnd_bind("<<DropLeave>>", self._on_drop_leave)

        self.configure_kind("file", TEXT_TYPE_CHECKSUM)

    # --- Slot configuration ---
    def configure_kind(self, kind, text_type):
        """Switch between file input and text input and update the captions."""
        self.kind = kind
        if kind == "file":
            self.title_label.configure(text=f"Input {self.name} - File")
            self.text_frame.pack_forget()
            self.file_frame.pack(fill="x")
        else:
            caption = "Checksum" if text_type == TEXT_TYPE_CHECKSUM else "Text"
            hint = (
                "Paste or type the checksum (hexadecimal):"
                if text_type == TEXT_TYPE_CHECKSUM
                else "Type or paste the text to hash (used exactly as typed):"
            )
            self.title_label.configure(text=f"Input {self.name} - {caption}")
            self.text_hint_label.configure(text=hint)
            self.file_frame.pack_forget()
            self.text_frame.pack(fill="x")

    def set_enabled(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.select_button.configure(state=state)
        self.text_box.configure(state=state)

    def clear(self):
        self.file_path = None
        self._show_file(None)
        self.text_box.delete("1.0", "end")
        self.text_box.edit_modified(False)

    # --- Value access ---
    def get_text(self):
        return self.text_box.get("1.0", "end-1c")

    # --- File handling ---
    def select_file(self):
        selected = filedialog.askopenfilename(
            title=f"Select file for input {self.name}",
            filetypes=[("All files", "*.*")],
        )
        if selected:
            self.set_file(selected)

    def set_file(self, path):
        if not os.path.isfile(path):
            messagebox.showwarning("Not a File", f"This is not a file and cannot be used:\n{path}")
            return
        self.file_path = path
        self._show_file(path)
        self.app.on_input_changed()

    def _show_file(self, path):
        if path is None:
            self.drop_label.configure(text=DROP_PROMPT)
            return
        try:
            size_text = format_size(os.path.getsize(path))
        except OSError:
            size_text = "size unknown"
        self.drop_label.configure(
            text=f"{os.path.basename(path)}\n{size_text}  -  {os.path.dirname(path)}",
        )

    # --- Event handlers ---
    def _on_text_modified(self, event):
        if self.text_box.edit_modified():
            self.text_box.edit_modified(False)
            self.app.on_input_changed()

    def _on_drop(self, event):
        self.drop_label.configure(bg=DROP_ZONE_COLOR)
        if self.kind != "file" or self.app.busy:
            return event.action
        paths = self.app.root.tk.splitlist(event.data)
        if paths:
            self.set_file(paths[0])
            if len(paths) > 1:
                self.app.show_info("Only one file per input is supported - the first dropped file was used.")
        return event.action

    def _on_drop_enter(self, event):
        if self.kind == "file" and not self.app.busy:
            self.drop_label.configure(bg=DROP_ZONE_ACTIVE_COLOR)
        return event.action

    def _on_drop_leave(self, event):
        self.drop_label.configure(bg=DROP_ZONE_COLOR)
        return event.action


# --- Main application ---
class ChecksumApp:

    def __init__(self, root):
        # --- Window setup ---
        self.root = root
        self.root.title("Checksums")
        self.root.geometry("900x600")
        self.root.minsize(900, 600)
        add_footer(root, image_path="assets/footer.png")
        if WINDOW_BACKGROUND_COLOR:
            root.configure(bg=WINDOW_BACKGROUND_COLOR)
        center_window(self.root)

        self.busy = False
        self.worker_queue = queue.Queue()
        self.current_job = None
        self.interactive_widgets = []

        self.algorithm_var = tk.StringVar(value=DEFAULT_ALGORITHM)
        self.mode_var = tk.StringVar(value=MODE_FILE_FILE)
        self.text_type_var = tk.StringVar(value=TEXT_TYPE_CHECKSUM)

        # --- Bottom progress bar ---
        # Packed before the main content area so it reliably reserves its
        # strip at the bottom of the window
        bottom_frame = tk.Frame(root, bg=WINDOW_BACKGROUND_COLOR)
        bottom_frame.pack(side="bottom", fill="x", padx=BOX_EXTERNAL_PADDING, pady=(0, BOX_EXTERNAL_PADDING))

        progress_style = ttk.Style(root)
        progress_style.theme_use("clam")
        progress_style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor="#929292",
            background="#3A8B63",
            bordercolor="#929292",
            lightcolor="#3A8B63",
            darkcolor="#3A8B63",
        )

        self.progress_bar = ttk.Progressbar(
            bottom_frame, style="Custom.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate",
        )
        self.progress_bar.pack(side="left", fill="x", expand=True)

        self.progress_label = tk.Label(bottom_frame, text="", bg=WINDOW_BACKGROUND_COLOR, width=8)
        self.progress_label.pack(side="left", padx=(8, 0))

        # --- Main content ---
        main_frame = tk.Frame(root, bg=WINDOW_BACKGROUND_COLOR)
        main_frame.pack(fill="both", expand=True, padx=BOX_EXTERNAL_PADDING, pady=BOX_EXTERNAL_PADDING)

        left_panel = tk.Frame(main_frame, bg=WINDOW_BACKGROUND_COLOR)
        left_panel.pack(side="left", fill="y", anchor="n")

        button_font = tkFont.Font(family="Arial", size=9, weight="bold")
        box_title_font = tkFont.Font(family="Segoe UI", size=9, weight="bold")

        # --- Left panel: algorithm ---
        algorithm_box = self._create_box(left_panel)
        algorithm_box.pack(fill="x", anchor="nw")
        self._create_box_title(algorithm_box, "Algorithm", box_title_font)

        self.algorithm_combobox = ttk.Combobox(
            algorithm_box, textvariable=self.algorithm_var, values=list(ALGORITHMS),
            state="readonly", width=BUTTON_WIDTH - 3,
        )
        self.algorithm_combobox.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 2))
        self.algorithm_combobox.bind("<<ComboboxSelected>>", self.on_algorithm_changed)
        self.interactive_widgets.append(self.algorithm_combobox)

        self.algorithm_info_label = tk.Label(
            algorithm_box, bg=WINDOW_BACKGROUND_COLOR, fg=MUTED_TEXT_COLOR, font=("Segoe UI", 8),
        )
        self.algorithm_info_label.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        tk.Frame(left_panel, bg=GROUP_BORDER_COLOR, height=2).pack(fill="x", pady=10)

        # --- Left panel: comparison mode ---
        mode_box = self._create_box(left_panel)
        mode_box.pack(fill="x", anchor="nw")
        self._create_box_title(mode_box, "Comparison Mode", box_title_font)

        self._create_option_group(mode_box, MODE_OPTIONS, self.mode_var, self.on_mode_changed)

        tk.Frame(left_panel, bg=GROUP_BORDER_COLOR, height=2).pack(fill="x", pady=10)

        # --- Left panel: text input type ---
        text_type_box = self._create_box(left_panel)
        text_type_box.pack(fill="x", anchor="nw")
        self._create_box_title(text_type_box, "Text Input Is", box_title_font)

        self._create_option_group(text_type_box, TEXT_TYPE_OPTIONS, self.text_type_var, self.on_text_type_changed)

        tk.Frame(left_panel, bg=GROUP_BORDER_COLOR, height=2).pack(fill="x", pady=10)

        # --- Left panel: actions ---
        action_box = self._create_box(left_panel)
        action_box.pack(fill="x", anchor="nw")

        self.compare_button = tk.Button(
            action_box, text="Compare", font=button_font, fg=SUCCESS_COLOR, width=BUTTON_WIDTH,
            command=self.start_compare,
        )
        self.compare_button.pack(padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 5))

        self.generate_button = tk.Button(
            action_box, text="Generate Checksum(s)", width=BUTTON_WIDTH, command=self.start_generate,
        )
        self.generate_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 5))

        self.clear_button = tk.Button(
            action_box, text="Clear All", width=BUTTON_WIDTH, command=self.clear_all,
        )
        self.clear_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        self.interactive_widgets.extend([self.compare_button, self.generate_button, self.clear_button])

        # Vertical divider between the control panel and the input panel
        tk.Frame(main_frame, bg=GROUP_BORDER_COLOR, width=2).pack(side="left", fill="y", padx=10)

        # --- Right panel: inputs ---
        right_panel = tk.Frame(main_frame, bg=WINDOW_BACKGROUND_COLOR)
        right_panel.pack(side="left", fill="both", expand=True)

        self.slots = [InputSlot(self, right_panel, "A"), InputSlot(self, right_panel, "B")]
        for slot in self.slots:
            slot.frame.pack(fill="x", pady=(0, 10))

        # --- Right panel: result ---
        result_box = self._create_box(right_panel)
        result_box.pack(fill="both", expand=True)
        self._create_box_title(result_box, "Result", box_title_font)

        self.result_texts = []
        for index, slot in enumerate(self.slots):
            header = tk.Frame(result_box, bg=WINDOW_BACKGROUND_COLOR)
            header.pack(fill="x", padx=BOX_INTERNAL_PADDING + 2)
            tk.Label(
                header, text=f"Checksum {slot.name}", bg=WINDOW_BACKGROUND_COLOR, anchor="w",
                font=("Segoe UI", 8, "bold"),
            ).pack(side="left")
            copy_button = tk.Button(
                header, text="Copy", font=("Segoe UI", 7), command=lambda i=index: self.copy_checksum(i),
            )
            copy_button.pack(side="right", pady=1)

            result_text = tk.Text(
                result_box, height=2, wrap="char", font=("Consolas", 9), bg=RESULT_FIELD_COLOR,
                relief="solid", bd=1, state=tk.DISABLED,
            )
            result_text.pack(fill="x", padx=BOX_INTERNAL_PADDING + 2, pady=(0, 6))
            self.result_texts.append(result_text)

        self.status_label = tk.Label(
            result_box, text="", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 15, "bold"),
        )
        self.status_label.pack(pady=(4, 0))

        self.info_label = tk.Label(
            result_box, text="Choose your inputs, then click Compare or Generate.",
            bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=("Segoe UI", 8),
            wraplength=560, justify="center",
        )
        self.info_label.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING + 2))

        self._update_algorithm_info()
        self._apply_mode()

    # --- Widget factories ---
    def _create_box(self, parent):
        return tk.Frame(
            parent, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )

    def _create_box_title(self, box, text, font):
        tk.Label(box, text=text, bg=WINDOW_BACKGROUND_COLOR, font=font, anchor="w").pack(
            fill="x", padx=BOX_INTERNAL_PADDING + 2, pady=(BOX_INTERNAL_PADDING, 2),
        )

    def _create_option_group(self, box, options, variable, command):
        """Square checkboxes that behave like radio buttons: exactly one is always ticked."""
        checkbox_vars = {}

        def sync(*_):
            for value, checkbox_var in checkbox_vars.items():
                checkbox_var.set(variable.get() == value)

        def select(value):
            variable.set(value)
            sync()  # keeps the clicked box ticked even if it was already selected
            command()

        for value, label in options:
            checkbox_vars[value] = tk.BooleanVar(value=variable.get() == value)
            checkbox = tk.Checkbutton(
                box, text=label, variable=checkbox_vars[value],
                command=lambda v=value: select(v),
                bg=WINDOW_BACKGROUND_COLOR, activebackground=WINDOW_BACKGROUND_COLOR,
                highlightthickness=0, anchor="w",
            )
            checkbox.pack(fill="x", padx=BOX_INTERNAL_PADDING + 2, pady=(0, 2))
            self.interactive_widgets.append(checkbox)

        variable.trace_add("write", sync)

    # --- Settings handlers ---
    def on_algorithm_changed(self, event=None):
        self.algorithm_combobox.selection_clear()
        self._update_algorithm_info()
        self.on_input_changed()

    def on_mode_changed(self):
        self._apply_mode()
        self.on_input_changed()

    def on_text_type_changed(self):
        self._apply_mode()
        self.on_input_changed()

    def _apply_mode(self):
        kinds = MODE_SLOT_KINDS[self.mode_var.get()]
        for slot, kind in zip(self.slots, kinds):
            slot.configure_kind(kind, self.text_type_var.get())

    def _update_algorithm_info(self):
        algorithm = ALGORITHMS[self.algorithm_var.get()]
        self.algorithm_info_label.configure(
            text=f"{algorithm.hex_length * 4}-bit digest ({algorithm.hex_length} hex characters)",
        )

    def on_input_changed(self):
        """Any change to inputs or settings invalidates the displayed result."""
        if not self.busy:
            self._reset_result()

    # --- Result display ---
    def _reset_result(self):
        for index in range(len(self.slots)):
            self._set_result_text(index, "")
        self.status_label.configure(text="")
        self.info_label.configure(
            text="Choose your inputs, then click Compare or Generate.", fg=HINT_COLOR,
        )
        self.progress_bar.configure(value=0)
        self.progress_label.configure(text="")

    def _set_result_text(self, index, text):
        widget = self.result_texts[index]
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)

    def show_info(self, text, color=MUTED_TEXT_COLOR):
        self.info_label.configure(text=text, fg=color)

    def copy_checksum(self, index):
        text = self.result_texts[index].get("1.0", "end-1c")
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)

    def clear_all(self):
        if self.busy:
            return
        for slot in self.slots:
            slot.clear()
        self._reset_result()

    # --- Hashing logic ---
    def start_compare(self):
        self._start_job(compare=True)

    def start_generate(self):
        self._start_job(compare=False)

    def _collect_entries(self, compare):
        """Read both inputs. Returns a list of entries, or None if validation failed."""
        text_type = self.text_type_var.get()
        entries = []

        for slot in self.slots:
            if slot.kind == "file":
                value = slot.file_path
                if not value:
                    if compare:
                        messagebox.showwarning("Missing Input", f"Please select a file for input {slot.name}.")
                        return None
                    continue
                if not os.path.isfile(value):
                    messagebox.showerror("File Not Found", f"The file for input {slot.name} no longer exists:\n{value}")
                    return None
                entries.append({"label": slot.name, "type": "file", "value": value})
            else:
                value = slot.get_text()
                if text_type == TEXT_TYPE_CHECKSUM:
                    value = normalize_checksum(value)
                if not value.strip():
                    if compare:
                        messagebox.showwarning("Missing Input", f"Please enter a text for input {slot.name}.")
                        return None
                    continue
                entry_type = "checksum" if text_type == TEXT_TYPE_CHECKSUM else "plain"
                entries.append({"label": slot.name, "type": entry_type, "value": value})

        if not entries:
            messagebox.showwarning("Missing Input", "Please provide at least one file or text first.")
            return None
        return entries

    def _start_job(self, compare):
        if self.busy:
            return

        algorithm = ALGORITHMS[self.algorithm_var.get()]

        entries = self._collect_entries(compare)
        if entries is None:
            return

        total_bytes = 0
        for entry in entries:
            if entry["type"] == "file":
                try:
                    total_bytes += os.path.getsize(entry["value"])
                except OSError as error:
                    messagebox.showerror("Cannot Read File", f"Could not access the file:\n{error}")
                    return
            elif entry["type"] == "plain":
                total_bytes += len(entry["value"].encode("utf-8"))

        self.current_job = {"compare": compare, "entries": entries, "algorithm": algorithm}
        self._reset_result()
        self._set_busy(True)
        self.progress_bar.configure(maximum=max(total_bytes, 1), value=0)
        self.progress_label.configure(text="0%")
        self.show_info(f"Calculating {algorithm.name} ...")

        worker = threading.Thread(
            target=self._worker, args=(entries, algorithm.factory, total_bytes), daemon=True,
        )
        worker.start()
        self.root.after(POLL_INTERVAL_MS, self._poll_worker)

    def _worker(self, entries, factory, total_bytes):
        """Runs in a background thread so the window stays responsive."""
        digests = {}
        processed = 0

        def on_chunk(chunk_size):
            nonlocal processed
            processed += chunk_size
            self.worker_queue.put(("progress", processed, total_bytes))

        for entry in entries:
            label = entry["label"]
            try:
                if entry["type"] == "file":
                    digests[label] = hash_file(entry["value"], factory, on_chunk)
                elif entry["type"] == "plain":
                    digests[label] = hash_text(entry["value"], factory)
                    on_chunk(len(entry["value"].encode("utf-8")))
                else:
                    digests[label] = entry["value"]
            except Exception as error:
                name = os.path.basename(entry["value"]) if entry["type"] == "file" else f"input {label}"
                self.worker_queue.put(("error", f"Could not process {name}:\n{error}"))
                return

        self.worker_queue.put(("done", digests))

    def _poll_worker(self):
        finished = False
        while True:
            try:
                message = self.worker_queue.get_nowait()
            except queue.Empty:
                break

            kind = message[0]
            if kind == "progress":
                _, processed, total = message
                self.progress_bar.configure(value=processed)
                percent = int(processed * 100 / total) if total else 100
                self.progress_label.configure(text=f"{percent}%")
            elif kind == "done":
                self._finish_job(message[1])
                finished = True
            elif kind == "error":
                self._fail_job(message[1])
                finished = True

        if not finished:
            self.root.after(POLL_INTERVAL_MS, self._poll_worker)

    def _set_busy(self, busy):
        self.busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for widget in self.interactive_widgets:
            if widget is self.algorithm_combobox:
                widget.configure(state="disabled" if busy else "readonly")
            else:
                widget.configure(state=state)
        for slot in self.slots:
            slot.set_enabled(not busy)

    def _fail_job(self, message):
        self._set_busy(False)
        self._reset_result()
        messagebox.showerror("Error", message)

    def _finish_job(self, digests):
        job = self.current_job
        self._set_busy(False)
        self.progress_bar.configure(value=self.progress_bar["maximum"])
        self.progress_label.configure(text="100%")

        for index, slot in enumerate(self.slots):
            self._set_result_text(index, digests.get(slot.name, ""))

        algorithm = job["algorithm"]
        if not job["compare"]:
            self.status_label.configure(text="Checksum generated", fg=NEUTRAL_COLOR)
            self.show_info(f"Algorithm: {algorithm.name}")
            return

        first, second = (digests[slot.name] for slot in self.slots)
        if first == second:
            self.status_label.configure(text="\u2714 IDENTICAL", fg=SUCCESS_COLOR)
            self.show_info("Both checksums match - the content is exactly the same.")
        else:
            self.status_label.configure(text="\u2718 NOT IDENTICAL", fg=ERROR_COLOR)
            self.show_info(self._build_mismatch_info(job, digests), color=ERROR_COLOR)

    def _build_mismatch_info(self, job, digests):
        """Hint at a wrong algorithm when an entered checksum has the wrong shape."""
        entries = {entry["label"]: entry for entry in job["entries"]}
        algorithm = job["algorithm"]

        for label, entry in entries.items():
            if entry["type"] != "checksum":
                continue
            other_labels = [other for other in entries if other != label]
            other_entry = entries[other_labels[0]]
            if other_entry["type"] == "checksum":
                continue
            issue = describe_checksum_issue(
                digests[label], len(digests[other_labels[0]]), algorithm.name,
            )
            if issue:
                return (
                    f"The checksums differ. The entered checksum {label} {issue} - "
                    "check that the selected algorithm matches the one used to create it."
                )
        return "The checksums differ - the content is not exactly the same."


# --- Entry point ---
if __name__ == "__main__":
    root = TkinterDnD.Tk()
    root.withdraw()
    app = ChecksumApp(root)
    root.deiconify()
    root.mainloop()