import hashlib
import json
import os
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkFont
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from helper.SP_footer_picture import add_footer
from helper.SP_window_utils import center_window

# --- Configuration ---
WINDOW_BACKGROUND_COLOR = "#E6E6E6"
GROUP_BORDER_COLOR = "#A7A7A7"
BOX_BORDER_THICKNESS = 0.5
BOX_INTERNAL_PADDING = 4
BOX_EXTERNAL_PADDING = 10
BUTTON_WIDTH = 20

SORT_OPTIONS = [
    "Name (A-Z)",
    "Name (Z-A)",
    "Date (Newest)",
    "Date (Oldest)",
    "Size (Smallest)",
    "Size (Largest)",
]

DOUBLE_OPEN_GUARD_SECONDS = 0.4  # avoids opening the same folder twice on a double-click

CACHE_HINT_COLOR = "#1B5FA8"
DANGER_COLOR = "#C55E5E"
GO_COLOR = "#3A8B63"

DOCUMENTS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "SimplePrograms", ".EXE File Search")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
CACHE_DIR = os.path.join(DOCUMENTS_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# --- Helper functions ---
def open_directory(path):
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        os.system(f'open "{path}"')
    else:
        os.system(f'xdg-open "{path}"')

def safe_getctime(path):
    try:
        return os.path.getctime(path)
    except OSError:
        return 0

def safe_getsize(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0

def to_relative_display_path(full_path, base_folder):
    relative = os.path.relpath(full_path, base_folder)
    return "/" + relative.replace(os.sep, "/")


# --- Cache helpers ---
def normalize_path_key(folder_path):
    return os.path.normcase(os.path.normpath(os.path.abspath(folder_path)))

def get_cache_file(folder_path):
    digest = hashlib.sha256(normalize_path_key(folder_path).encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{digest}.json")

def load_cache(folder_path):
    cache_file = get_cache_file(folder_path)
    if not os.path.isfile(cache_file):
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("path") != normalize_path_key(folder_path):
            return None  # hash collision safety check
        return data
    except (OSError, ValueError, KeyError):
        return None

def save_cache(folder_path, files):
    cache_file = get_cache_file(folder_path)
    data = {
        "path": normalize_path_key(folder_path),
        "display_path": folder_path,
        "created": datetime.now().isoformat(timespec="seconds"),
        "files": files,
    }
    try:
        with open(cache_file, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
    except OSError:
        pass  # caching is a convenience feature; a failed write shouldn't crash the app

def format_cache_timestamp(iso_timestamp):
    try:
        return datetime.fromisoformat(iso_timestamp).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_timestamp

def clear_all_caches():
    """Delete every cache file. Returns how many were removed."""
    removed = 0
    if not os.path.isdir(CACHE_DIR):
        return removed
    for name in os.listdir(CACHE_DIR):
        if name.endswith(".json"):
            try:
                os.remove(os.path.join(CACHE_DIR, name))
                removed += 1
            except OSError:
                pass
    return removed


# --- Application ---
class ExeSearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title(".EXE File Search")
        self.root.geometry("740x420")
        self.root.minsize(740, 420)
        add_footer(root, image_path="assets/footer.png")
        if WINDOW_BACKGROUND_COLOR:
            root.configure(bg=WINDOW_BACKGROUND_COLOR)
        center_window(root)

        # State
        self.selected_folder = None
        self.found_files = []        # every .exe found in the last/current search (absolute paths)
        self.displayed_paths = []    # absolute paths, in the same order as the currently listed rows
        self.result_queue = queue.Queue()
        self.search_thread = None
        self._last_open_index = None
        self._last_open_time = 0.0

        self._build_ui()

    # --- UI construction ---
    def _build_ui(self):
        button_font = tkFont.Font(family="Arial", size=9, weight="bold")

        # Progress bar (packed first so it reliably reserves its strip at the bottom)
        bottom_frame = tk.Frame(self.root, bg=WINDOW_BACKGROUND_COLOR)
        bottom_frame.pack(side="bottom", fill="x", padx=BOX_EXTERNAL_PADDING, pady=(0, BOX_EXTERNAL_PADDING))

        progress_style = ttk.Style(self.root)
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

        self.progress_label = tk.Label(bottom_frame, text="", bg=WINDOW_BACKGROUND_COLOR, anchor="w")
        self.progress_label.pack(fill="x", pady=(4, 0))

        # Main content: left control panel + right results panel
        main_frame = tk.Frame(self.root, bg=WINDOW_BACKGROUND_COLOR)
        main_frame.pack(fill="both", expand=True, padx=BOX_EXTERNAL_PADDING, pady=BOX_EXTERNAL_PADDING)

        left_panel = tk.Frame(main_frame, bg=WINDOW_BACKGROUND_COLOR)
        left_panel.pack(side="left", fill="y", anchor="n")

        # --- Folder selection ---
        source_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        source_box.pack(fill="x", anchor="nw")

        folder_label = tk.Label(source_box, text="Select a folder to search:", bg=WINDOW_BACKGROUND_COLOR)
        folder_label.pack(padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 5))

        self.browse_button = tk.Button(source_box, text="Browse", width=BUTTON_WIDTH, command=self.browse_folder)
        self.browse_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 5))

        self.search_button = tk.Button(
            source_box, text="Search", font=button_font,fg=GO_COLOR, width=BUTTON_WIDTH,
            command=self.start_search, state=tk.DISABLED,
        )
        self.search_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        # Divider between the two boxes
        tk.Frame(left_panel, bg=GROUP_BORDER_COLOR, height=2).pack(fill="x", pady=10)

        # --- Filter & sort ---
        filter_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        filter_box.pack(fill="x", anchor="nw")

        filter_label = tk.Label(filter_box, text="Filter by name:", bg=WINDOW_BACKGROUND_COLOR)
        filter_label.pack(padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 5))

        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_args: self.refresh_results())
        self.filter_entry = tk.Entry(filter_box, textvariable=self.filter_var, width=BUTTON_WIDTH)
        self.filter_entry.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        sort_label = tk.Label(filter_box, text="Sort by:", bg=WINDOW_BACKGROUND_COLOR)
        sort_label.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 5))

        self.sort_combobox = ttk.Combobox(
            filter_box, values=SORT_OPTIONS, state="readonly", width=BUTTON_WIDTH - 2,
        )
        self.sort_combobox.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))
        self.sort_combobox.current(0)
        self.sort_combobox.bind("<<ComboboxSelected>>", lambda _event: self.refresh_results())

        # --- Cache management ---
        self.clear_cache_button = tk.Button(
            left_panel, text="Clear Cache", font=button_font, fg=DANGER_COLOR, width=BUTTON_WIDTH,
            command=self.clear_cache,
        )
        self.clear_cache_button.pack(side="bottom", pady=(10, 0))

        # --- Results ---
        right_panel = tk.Frame(main_frame, bg=WINDOW_BACKGROUND_COLOR)
        right_panel.pack(side="left", fill="both", expand=True, padx=(10, 0))

        directory_row = tk.Frame(right_panel, bg=WINDOW_BACKGROUND_COLOR)
        directory_row.pack(fill="x", pady=(0, 10))

        self.selected_directory_label = tk.Label(
            directory_row, text="No folder selected", bg=WINDOW_BACKGROUND_COLOR, anchor="w",
        )
        self.selected_directory_label.pack(side="left")

        self.cache_hint_label = tk.Label(
            directory_row, text="", bg=WINDOW_BACKGROUND_COLOR, fg=CACHE_HINT_COLOR,
            font=button_font, anchor="w",
        )
        self.cache_hint_label.pack(side="left", padx=(10, 0))

        list_frame = tk.Frame(right_panel, bg=WINDOW_BACKGROUND_COLOR)
        list_frame.pack(fill="both", expand=True)

        v_scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        h_scrollbar = tk.Scrollbar(list_frame, orient=tk.HORIZONTAL)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.results_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=v_scrollbar.set,
            xscrollcommand=h_scrollbar.set,
        )
        self.results_listbox.pack(fill=tk.BOTH, expand=True)

        v_scrollbar.config(command=self.results_listbox.yview)
        h_scrollbar.config(command=self.results_listbox.xview)

        # Single click on an already-selected row opens it; double-click always opens.
        self.results_listbox.bind("<Button-1>", self.on_single_click)
        self.results_listbox.bind("<Double-Button-1>", self.on_double_click)
        self.results_listbox.bind("<MouseWheel>", self.on_mouse_wheel)

    # --- Folder selection ---
    def browse_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.selected_folder = folder
        self.selected_directory_label.config(text="Selected directory: " + folder)
        self.search_button.config(state=tk.NORMAL)
        self._load_cache_if_available()

    def _load_cache_if_available(self):
        cache = load_cache(self.selected_folder)
        if cache is not None:
            self.found_files = cache.get("files", [])
            self.refresh_results()
            created_display = format_cache_timestamp(cache.get("created", ""))
            self.cache_hint_label.config(text=f"Cache loaded \u2014 created {created_display}")
            self.progress_bar.config(mode="determinate", maximum=100, value=100)
            self.progress_label.config(text=f"Loaded {len(self.found_files)} file(s) from cache")
            self.search_button.config(text="New Search")
        else:
            self.found_files = []
            self.displayed_paths = []
            self.results_listbox.delete(0, tk.END)
            self.cache_hint_label.config(text="")
            self.progress_label.config(text="")
            self.search_button.config(text="Search")

    # --- Search (runs in a background thread so the UI stays responsive) ---
    def start_search(self):
        if not self.selected_folder or (self.search_thread and self.search_thread.is_alive()):
            return

        self.found_files = []
        self.displayed_paths = []
        self.results_listbox.delete(0, tk.END)
        self.cache_hint_label.config(text="")  # a live search replaces whatever was cached

        self.search_button.config(state=tk.DISABLED)
        self.browse_button.config(state=tk.DISABLED)
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(12)
        self.progress_label.config(text="Searching...")

        self.search_thread = threading.Thread(
            target=self._search_worker, args=(self.selected_folder,), daemon=True,
        )
        self.search_thread.start()
        self.root.after(100, self._poll_search_queue)

    def _search_worker(self, folder):
        """Runs off the main thread: walks the folder tree and pushes every
        .exe it finds onto the queue so the UI thread can pick it up."""
        for current_root, _dirs, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(".exe"):
                    self.result_queue.put(os.path.join(current_root, file))
        self.result_queue.put(None)  # sentinel: search finished

    def _poll_search_queue(self):
        found_new_items = False
        finished = False

        while True:
            try:
                item = self.result_queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                finished = True
                break
            self.found_files.append(item)
            found_new_items = True

        if found_new_items:
            self.progress_label.config(text=f"Found {len(self.found_files)} file(s)...")
            self.refresh_results()  # show results live as they come in

        if finished:
            self.progress_bar.stop()
            self.progress_bar.config(mode="determinate", maximum=100, value=100)
            self.progress_label.config(text=f"Found {len(self.found_files)} file(s)")
            self.search_button.config(state=tk.NORMAL, text="New Search")
            self.browse_button.config(state=tk.NORMAL)
            save_cache(self.selected_folder, self.found_files)
        else:
            self.root.after(100, self._poll_search_queue)

    # --- Filtering & sorting (both re-apply instantly, no extra button needed) ---
    def refresh_results(self):
        if not self.selected_folder:
            return

        filter_text = self.filter_var.get().strip().lower()
        if filter_text:
            matches = [
                path for path in self.found_files
                if filter_text in to_relative_display_path(path, self.selected_folder).lower()
            ]
        else:
            matches = list(self.found_files)

        sort_type = self.sort_combobox.get()
        if sort_type == "Name (A-Z)":
            matches.sort(key=lambda p: os.path.basename(p).lower())
        elif sort_type == "Name (Z-A)":
            matches.sort(key=lambda p: os.path.basename(p).lower(), reverse=True)
        elif sort_type == "Date (Newest)":
            matches.sort(key=safe_getctime, reverse=True)
        elif sort_type == "Date (Oldest)":
            matches.sort(key=safe_getctime)
        elif sort_type == "Size (Smallest)":
            matches.sort(key=safe_getsize)
        elif sort_type == "Size (Largest)":
            matches.sort(key=safe_getsize, reverse=True)

        self.displayed_paths = matches
        self.results_listbox.delete(0, tk.END)
        for full_path in matches:
            self.results_listbox.insert(tk.END, to_relative_display_path(full_path, self.selected_folder))

    # --- Result list interaction ---
    def on_single_click(self, event):
        index = self.results_listbox.nearest(event.y)
        if index < 0 or index >= self.results_listbox.size():
            return
        current_selection = self.results_listbox.curselection()
        already_selected = bool(current_selection) and current_selection[0] == index
        if already_selected:
            self.open_result(index)

    def on_double_click(self, event):
        index = self.results_listbox.nearest(event.y)
        self.open_result(index)

    def on_mouse_wheel(self, event):
        if event.state & 0x1:  # Shift held -> scroll horizontally
            self.results_listbox.xview_scroll(int(-1 * (event.delta / 120)), "units")
        else:
            self.results_listbox.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def open_result(self, index):
        if index < 0 or index >= len(self.displayed_paths):
            return

        # Guards against opening the same folder twice: a double-click fires
        # both a "second single click" and a "double click" event.
        now = time.time()
        if self._last_open_index == index and (now - self._last_open_time) < DOUBLE_OPEN_GUARD_SECONDS:
            return
        self._last_open_index = index
        self._last_open_time = now

        full_path = self.displayed_paths[index]
        open_directory(os.path.dirname(full_path))

    # --- Cache management ---
    def clear_cache(self):
        if not messagebox.askyesno(
            "Clear Cache",
            "This will delete the saved cache file for every\nfolder you've searched.\n\n"
            "Continue?",
        ):
            return
        if not messagebox.askyesno(
            "Clear Cache",
            "Are you sure? This cannot be undone.",
        ):
            return

        removed = clear_all_caches()
        messagebox.showinfo("Clear Cache", f"Removed {removed} cache file(s).")

        # If the currently selected folder had a cache, it's gone now too.
        if self.selected_folder:
            self.cache_hint_label.config(text="")
            self.search_button.config(text="Search")


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    app = ExeSearchApp(root)
    root.deiconify()
    root.mainloop()