import tkinter as tk
import tkinter.font as tkFont
from tkinter import messagebox
from difflib import SequenceMatcher
import os
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from helper.SP_footer_picture import add_footer
from helper.SP_window_utils import center_window

DOCUMENTS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "SimplePrograms", "Text Comparison")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
DATA_FILENAME = os.path.join(DOCUMENTS_DIR, "text_comparison_data.json")

WINDOW_TITLE = "Text Comparison"
WINDOW_WIDTH = 740
WINDOW_HEIGHT = 450
WINDOW_MIN_WIDTH = 740
WINDOW_MIN_HEIGHT = 450
WINDOW_BACKGROUND_COLOR = "#E6E6E6"

DIFF_BACKGROUND_COLOR = "#FCE7A8"
DIFF_TEXT_COLOR = "#411818"
MOVED_BACKGROUND_COLOR = "#CFE3F7"
MOVED_TEXT_COLOR = "#411818"

TITLE_PLACEHOLDER_TEXT = "Optional title..."
TITLE_PLACEHOLDER_COLOR = "gray"
TITLE_ACTIVE_COLOR = "black"

SECTION_PADDING_X = 4
SECTION_PADDING_Y = 5

GROUP_BORDER_COLOR = "#A7A7A7"
GROUP_BORDER_THICKNESS = 0.5
GROUP_INNER_PADDING_X = 4
GROUP_INNER_PADDING_Y = 4
GROUP_ITEM_SPACING = 2

TEXT_CONTENT_FONT_DEFAULT_SIZE = 10
TEXT_CONTENT_FONT_STEP = 2
TEXT_CONTENT_FONT_MIN_SIZE = 10
TEXT_CONTENT_FONT_MAX_SIZE = 40

SYNC_SCROLL_ACTIVE_COLOR = "black"
SYNC_SCROLL_INACTIVE_COLOR = "gray"

SCROLL_SPEED_STEP = 1
SCROLL_SPEED_MIN = 1
SCROLL_SPEED_MAX = 10
SCROLL_SPEED_DEFAULT = 3

class PlaceholderEntry(tk.Entry):
    def __init__(self, master, placeholder=TITLE_PLACEHOLDER_TEXT, **kwargs):
        super().__init__(master, **kwargs)
        self.placeholder = placeholder
        self._showing_placeholder = False

        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self._show_placeholder()

    def _show_placeholder(self):
        self.delete(0, tk.END)
        self.insert(0, self.placeholder)
        self.config(fg=TITLE_PLACEHOLDER_COLOR)
        self._showing_placeholder = True

    def _on_focus_in(self, _event=None):
        if self._showing_placeholder:
            self.delete(0, tk.END)
            self.config(fg=TITLE_ACTIVE_COLOR)
            self._showing_placeholder = False

    def _on_focus_out(self, _event=None):
        if not self.get().strip():
            self._show_placeholder()

    def get_value(self):
        """Returns the real title text, or '' while the placeholder is showing."""
        return "" if self._showing_placeholder else self.get().strip()

    def set_value(self, value):
        """Sets a real value, or shows the placeholder again if value is empty."""
        self.delete(0, tk.END)
        if value:
            self.insert(0, value)
            self.config(fg=TITLE_ACTIVE_COLOR)
            self._showing_placeholder = False
        else:
            self._show_placeholder()

def _find_moved_lines(lines1, lines2):
    opcodes = SequenceMatcher(None, lines1, lines2).get_opcodes()

    changed1, changed2 = set(), set()
    for tag, i1, i2, j1, j2 in opcodes:
        if tag != "equal":
            changed1.update(range(i1, i2))
            changed2.update(range(j1, j2))

    changed_lines2 = [lines2[j] for j in changed2]
    changed_lines1 = [lines1[i] for i in changed1]

    moved1 = {i for i in changed1 if lines1[i].strip() and lines1[i] in changed_lines2}
    moved2 = {j for j in changed2 if lines2[j].strip() and lines2[j] in changed_lines1}
    return moved1, moved2

def compare_texts():
    text1 = text_field1.get("1.0", "end-1c")
    text2 = text_field2.get("1.0", "end-1c")

    text_field1.tag_remove("diff", "1.0", tk.END)
    text_field2.tag_remove("diff", "1.0", tk.END)
    text_field1.tag_remove("moved", "1.0", tk.END)
    text_field2.tag_remove("moved", "1.0", tk.END)

    if text1 == text2:
        messagebox.showinfo("Result", "No meaningful difference found")
        return

    matcher = SequenceMatcher(None, text1, text2)

    last_end1 = 0
    last_end2 = 0

    for start1, start2, length in matcher.get_matching_blocks():
        if start1 > last_end1:
            text_field1.tag_add("diff", f"1.0 + {last_end1} chars", f"1.0 + {start1} chars")
        if start2 > last_end2:
            text_field2.tag_add("diff", f"1.0 + {last_end2} chars", f"1.0 + {start2} chars")

        last_end1 = start1 + length
        last_end2 = start2 + length

    moved1, moved2 = _find_moved_lines(text1.split("\n"), text2.split("\n"))
    for i in moved1:
        text_field1.tag_add("moved", f"{i + 1}.0", f"{i + 1}.end")
    for j in moved2:
        text_field2.tag_add("moved", f"{j + 1}.0", f"{j + 1}.end")

def clear_texts():
    text_field1.delete("1.0", tk.END)
    text_field2.delete("1.0", tk.END)
    text_field1.tag_remove("diff", "1.0", tk.END)
    text_field2.tag_remove("diff", "1.0", tk.END)
    text_field1.tag_remove("moved", "1.0", tk.END)
    text_field2.tag_remove("moved", "1.0", tk.END)
    title_field1.set_value("")
    title_field2.set_value("")

def _resize_font(step):
    new_size = text_content_font.cget("size") + step
    new_size = max(TEXT_CONTENT_FONT_MIN_SIZE, min(TEXT_CONTENT_FONT_MAX_SIZE, new_size))
    text_content_font.configure(size=new_size)
    font_size_display_var.set(f"[{new_size}]")

def increase_font_size(event=None):
    _resize_font(TEXT_CONTENT_FONT_STEP)

def decrease_font_size(event=None):
    _resize_font(-TEXT_CONTENT_FONT_STEP)

def _resize_scroll_speed(step):
    new_speed = scroll_speed_var.get() + step
    new_speed = max(SCROLL_SPEED_MIN, min(SCROLL_SPEED_MAX, new_speed))
    scroll_speed_var.set(new_speed)
    scroll_speed_display_var.set(f"[{new_speed}]")

def increase_scroll_speed():
    _resize_scroll_speed(SCROLL_SPEED_STEP)

def decrease_scroll_speed():
    _resize_scroll_speed(-SCROLL_SPEED_STEP)

def _on_mousewheel(event, widget):
    # Windows/Mac: event.delta's sign tells us the direction; its magnitude
    # varies by platform/device, so we ignore it and scroll by our own
    # configurable amount instead.
    widget.yview_scroll(-scroll_speed_var.get() if event.delta > 0 else scroll_speed_var.get(), "units")
    return "break"  # stop Tk's default wheel handling from also scrolling

def _on_mousewheel_linux(event, widget, direction):
    # Linux: <Button-4> (up) / <Button-5> (down) instead of <MouseWheel>
    widget.yview_scroll(direction * scroll_speed_var.get(), "units")
    return "break"

_syncing_scroll = False

def _sync_scroll(source, target):
    
    def _handler(first, last):
        global _syncing_scroll
        if dual_scroll_var.get() and not _syncing_scroll:
            _syncing_scroll = True
            try:
                target.yview_moveto(float(first))
            finally:
                _syncing_scroll = False
    return _handler

def toggle_dual_scroll():
    dual_scroll_var.set(not dual_scroll_var.get())
    sync_scroll_button.config(
        fg=SYNC_SCROLL_ACTIVE_COLOR if dual_scroll_var.get() else SYNC_SCROLL_INACTIVE_COLOR
    )

def load_saved_data():
    if not os.path.exists(DATA_FILENAME):
        return

    try:
        with open(DATA_FILENAME, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return

    text_field1.insert("1.0", data.get("text1", ""))
    text_field2.insert("1.0", data.get("text2", ""))
    title_field1.set_value(data.get("title1", ""))
    title_field2.set_value(data.get("title2", ""))

    saved_font_size = data.get("font_size")
    if isinstance(saved_font_size, (int, float)):
        clamped_size = max(TEXT_CONTENT_FONT_MIN_SIZE, min(TEXT_CONTENT_FONT_MAX_SIZE, int(saved_font_size)))
        text_content_font.configure(size=clamped_size)
        font_size_display_var.set(f"[{clamped_size}]")

    saved_scroll_speed = data.get("scroll_speed")
    if isinstance(saved_scroll_speed, (int, float)):
        clamped_speed = max(SCROLL_SPEED_MIN, min(SCROLL_SPEED_MAX, int(saved_scroll_speed)))
        scroll_speed_var.set(clamped_speed)
        scroll_speed_display_var.set(f"[{clamped_speed}]")

def save_data():
    data = {
        "text1": text_field1.get("1.0", "end-1c"),
        "text2": text_field2.get("1.0", "end-1c"),
        "title1": title_field1.get_value(),
        "title2": title_field2.get_value(),
        "font_size": text_content_font.cget("size"),
        "scroll_speed": scroll_speed_var.get(),
    }
    try:
        with open(DATA_FILENAME, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        messagebox.showwarning("Save failed", f"Could not save your content:\n{e}")

def on_close():
    save_data()
    window.destroy()

def _bg_kwargs():
    """Small helper so WINDOW_BACKGROUND_COLOR=None doesn't get passed as
    literal bg=None (which Tkinter would reject)."""
    return {"bg": WINDOW_BACKGROUND_COLOR} if WINDOW_BACKGROUND_COLOR else {}

def create_gui():
    global window, text_field1, text_field2, title_field1, title_field2, text_content_font, dual_scroll_var, sync_scroll_button, scroll_speed_var, font_size_display_var, scroll_speed_display_var

    window = tk.Tk()
    window.withdraw()
    window.title(WINDOW_TITLE)
    window.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
    window.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
    if WINDOW_BACKGROUND_COLOR:
        window.configure(bg=WINDOW_BACKGROUND_COLOR)
    center_window(window)

    window.grid_rowconfigure(0, weight=1)
    window.grid_rowconfigure(1, weight=0)
    window.grid_columnconfigure(0, weight=1)

    content = tk.Frame(window, **_bg_kwargs())
    content.grid(row=0, column=0, sticky="nsew")

    footer_frame = tk.Frame(window)
    footer_frame.grid(row=1, column=0, sticky="ew")
    add_footer(footer_frame, image_path="assets/footer.png") 

    content.grid_rowconfigure(1, weight=1)
    content.grid_columnconfigure(0, weight=1)
    content.grid_columnconfigure(1, weight=1)

    label_font = tkFont.Font(family="Arial", size=10, weight="bold",slant="italic")
    title_font = tkFont.Font(family="Arial", size=11, weight="bold")
    button_font= tkFont.Font(family="Arial",size=9,weight="bold")
    try:
        default_family = tkFont.nametofont("TkTextFont").actual("family")
    except tk.TclError:
        default_family = "TkDefaultFont"
    text_content_font = tkFont.Font(family=default_family, size=TEXT_CONTENT_FONT_DEFAULT_SIZE)
    font_size_display_var = tk.StringVar(value=f"[{TEXT_CONTENT_FONT_DEFAULT_SIZE}]")

    dual_scroll_var = tk.BooleanVar(value=True)
    scroll_speed_var = tk.IntVar(value=SCROLL_SPEED_DEFAULT)
    scroll_speed_display_var = tk.StringVar(value=f"[{SCROLL_SPEED_DEFAULT}]")

    # --- Section 1 ---
    header1 = tk.Frame(content, **_bg_kwargs())
    header1.grid(row=0, column=0, sticky="ew", padx=SECTION_PADDING_X, pady=SECTION_PADDING_Y)
    tk.Label(header1, text="Section 1:", font=label_font, **_bg_kwargs()).pack(side=tk.LEFT)
    title_field1 = PlaceholderEntry(header1, font=title_font)
    title_field1.pack(side=tk.LEFT, fill="x", expand=True, padx=(8, 0))

    text_field1 = tk.Text(content, wrap="word", font=text_content_font)
    text_field1.grid(row=1, column=0, sticky="nsew", padx=(SECTION_PADDING_X, 4))

    # --- Section 2 ---
    header2 = tk.Frame(content, **_bg_kwargs())
    header2.grid(row=0, column=1, sticky="ew", padx=SECTION_PADDING_X, pady=SECTION_PADDING_Y)
    tk.Label(header2, text="Section 2:", font=label_font, **_bg_kwargs()).pack(side=tk.LEFT)
    title_field2 = PlaceholderEntry(header2, font=title_font)
    title_field2.pack(side=tk.LEFT, fill="x", expand=True, padx=(8, 0))

    text_field2 = tk.Text(content, wrap="word", font=text_content_font)
    text_field2.grid(row=1, column=1, sticky="nsew", padx=(4, SECTION_PADDING_X))

    # --- Difference & Scrolling ---
    text_field1.tag_config("diff", background=DIFF_BACKGROUND_COLOR, foreground=DIFF_TEXT_COLOR)
    text_field2.tag_config("diff", background=DIFF_BACKGROUND_COLOR, foreground=DIFF_TEXT_COLOR)
    text_field1.tag_config("moved", background=MOVED_BACKGROUND_COLOR, foreground=MOVED_TEXT_COLOR)
    text_field2.tag_config("moved", background=MOVED_BACKGROUND_COLOR, foreground=MOVED_TEXT_COLOR)

    text_field1.config(yscrollcommand=_sync_scroll(text_field1, text_field2))
    text_field2.config(yscrollcommand=_sync_scroll(text_field2, text_field1))

    for widget in (text_field1, text_field2):
        widget.bind("<MouseWheel>", lambda e, w=widget: _on_mousewheel(e, w))
        widget.bind("<Button-4>", lambda e, w=widget: _on_mousewheel_linux(e, w, -1))
        widget.bind("<Button-5>", lambda e, w=widget: _on_mousewheel_linux(e, w, 1))

    # --- Buttons ---
    button_frame = tk.Frame(content, **_bg_kwargs())
    button_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky="ew")

    # --- Font size controls (bordered, left side) ---
    font_size_frame = tk.Frame(
        button_frame,
        highlightbackground=GROUP_BORDER_COLOR,
        highlightthickness=GROUP_BORDER_THICKNESS,
        **_bg_kwargs(),
    )
    font_size_frame.pack(side=tk.LEFT, padx=SECTION_PADDING_X)

    tk.Label(font_size_frame, text="Font-Size:", font=button_font, **_bg_kwargs()).pack(
        side=tk.LEFT, padx=(GROUP_INNER_PADDING_X, GROUP_ITEM_SPACING), pady=GROUP_INNER_PADDING_Y)
    tk.Label(font_size_frame, textvariable=font_size_display_var, font=button_font, width=2, **_bg_kwargs()).pack(
        side=tk.LEFT, padx=GROUP_ITEM_SPACING, pady=GROUP_INNER_PADDING_Y)
    tk.Button(font_size_frame, text="➖", command=decrease_font_size).pack(
        side=tk.LEFT, padx=GROUP_ITEM_SPACING, pady=GROUP_INNER_PADDING_Y)
    tk.Button(font_size_frame, text="➕", command=increase_font_size).pack(
        side=tk.LEFT, padx=(GROUP_ITEM_SPACING, GROUP_INNER_PADDING_X), pady=GROUP_INNER_PADDING_Y)

    scroll_speed_frame = tk.Frame(
        button_frame,
        highlightbackground=GROUP_BORDER_COLOR,
        highlightthickness=GROUP_BORDER_THICKNESS,
        **_bg_kwargs(),
    )
    scroll_speed_frame.pack(side=tk.LEFT, padx=SECTION_PADDING_X)

    tk.Label(scroll_speed_frame, text="Scroll-Speed:", font=button_font, **_bg_kwargs()).pack(
        side=tk.LEFT, padx=(GROUP_INNER_PADDING_X, GROUP_ITEM_SPACING), pady=GROUP_INNER_PADDING_Y)
    tk.Label(scroll_speed_frame, textvariable=scroll_speed_display_var, font=button_font, width=2, **_bg_kwargs()).pack(
        side=tk.LEFT, padx=GROUP_ITEM_SPACING, pady=GROUP_INNER_PADDING_Y)
    tk.Button(scroll_speed_frame, text="➖", command=decrease_scroll_speed).pack(
        side=tk.LEFT, padx=GROUP_ITEM_SPACING, pady=GROUP_INNER_PADDING_Y)
    tk.Button(scroll_speed_frame, text="➕", command=increase_scroll_speed).pack(
        side=tk.LEFT, padx=(GROUP_ITEM_SPACING, GROUP_INNER_PADDING_X), pady=GROUP_INNER_PADDING_Y)

    # --- Sync scroll toggle (bordered, its own box) ---
    sync_scroll_frame = tk.Frame(
        button_frame,
        highlightbackground=GROUP_BORDER_COLOR,
        highlightthickness=GROUP_BORDER_THICKNESS,
        **_bg_kwargs(),
    )
    sync_scroll_frame.pack(side=tk.LEFT, padx=SECTION_PADDING_X)

    sync_scroll_button = tk.Button(
        sync_scroll_frame, text="Sync scroll", font=button_font,
        fg=SYNC_SCROLL_ACTIVE_COLOR, command=toggle_dual_scroll,
    )
    sync_scroll_button.pack(side=tk.LEFT, padx=GROUP_INNER_PADDING_X, pady=GROUP_INNER_PADDING_Y)

    # --- Compare / Clear (bordered, right side) ---
    action_frame = tk.Frame(
        button_frame,
        highlightbackground=GROUP_BORDER_COLOR,
        highlightthickness=GROUP_BORDER_THICKNESS,
        **_bg_kwargs(),
    )
    action_frame.pack(side=tk.RIGHT, padx=SECTION_PADDING_X)

    tk.Button(action_frame, text="Compare", font=button_font, command=compare_texts).pack(
        side=tk.LEFT, padx=(GROUP_INNER_PADDING_X, GROUP_ITEM_SPACING), pady=GROUP_INNER_PADDING_Y)
    tk.Button(action_frame, text="Clear", font=button_font, fg="#C55E5E", command=clear_texts).pack(
        side=tk.LEFT, padx=(GROUP_ITEM_SPACING, GROUP_INNER_PADDING_X), pady=GROUP_INNER_PADDING_Y)

    window.bind_all("<Control-plus>", increase_font_size)
    window.bind_all("<Control-equal>", increase_font_size)
    window.bind_all("<Control-KP_Add>", increase_font_size)
    window.bind_all("<Control-minus>", decrease_font_size)
    window.bind_all("<Control-KP_Subtract>", decrease_font_size)

    load_saved_data()

    window.protocol("WM_DELETE_WINDOW", on_close)
    window.deiconify()
    window.mainloop()

create_gui()