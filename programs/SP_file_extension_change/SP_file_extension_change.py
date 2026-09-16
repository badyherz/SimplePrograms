import os
import shutil
import subprocess
import tkinter as tk
import tkinter.font as tkFont
from tkinter import filedialog, messagebox
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

HINT_COLOR = "#1B5FA8"
DANGER_COLOR = "#C55E5E"
GO_COLOR = "#3A8B63"


# --- Helper Functions ---
def open_folder(path):
    try:
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform.startswith("darwin"):
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
    except Exception as error:
        messagebox.showerror("Error", f"Cannot open folder:\n{error}")


# --- Application ---
class ExtensionChangerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Bulk File Extension Changer")
        self.root.geometry("860x480")
        self.root.minsize(860, 480)
        add_footer(root, image_path="assets/footer.png")
        if WINDOW_BACKGROUND_COLOR:
            root.configure(bg=WINDOW_BACKGROUND_COLOR)
        center_window(root)

        self.files = []            # absolute paths of the currently selected files
        self.common_path = ""      # highest common folder shared by all selected files
        self.last_rename_map = []  # (new_path, old_path) pairs from the last conversion, for reverting

        self.create_widgets()

    # --- Widget Setup ---
    def create_widgets(self):
        main_frame = tk.Frame(self.root, bg=WINDOW_BACKGROUND_COLOR)
        main_frame.pack(fill="both", expand=True, padx=BOX_EXTERNAL_PADDING, pady=BOX_EXTERNAL_PADDING)

        self._build_left_panel(main_frame)

        tk.Frame(main_frame, bg=GROUP_BORDER_COLOR, width=2).pack(side="left", fill="y", padx=10)

        self._build_right_panel(main_frame)

    def _build_left_panel(self, parent):
        left_panel = tk.Frame(parent, bg=WINDOW_BACKGROUND_COLOR)
        left_panel.pack(side="left", fill="y", anchor="n")

        button_font = tkFont.Font(family="Arial", size=9, weight="bold")

        # --- Source Box ---
        source_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        source_box.pack(fill="x", anchor="nw")

        self.select_files_button = tk.Button(
            source_box, text="Select Files", width=BUTTON_WIDTH, command=self.select_files
        )
        self.select_files_button.pack(padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 5))

        self.select_folder_button = tk.Button(
            source_box, text="Select Folder", width=BUTTON_WIDTH, command=self.select_folder
        )
        self.select_folder_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 5))

        self.open_dir_button = tk.Button(
            source_box, text="Open Directory", width=BUTTON_WIDTH,
            command=self.open_directory, state=tk.DISABLED,
        )
        self.open_dir_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        tk.Frame(left_panel, bg=GROUP_BORDER_COLOR, height=2).pack(fill="x", pady=10)

        # --- Options Box ---
        options_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        options_box.pack(fill="x", anchor="nw")

        entry_width = BUTTON_WIDTH + 5

        tk.Label(options_box, text="New Extension (e.g. jpg):", bg=WINDOW_BACKGROUND_COLOR).pack(
            padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 2), anchor="w"
        )
        self.extension_entry = tk.Entry(options_box, width=entry_width)
        self.extension_entry.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        tk.Frame(left_panel, bg=GROUP_BORDER_COLOR, height=2).pack(fill="x", pady=10)

        # --- Actions Box ---
        action_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        action_box.pack(fill="x", anchor="nw")

        self.convert_button = tk.Button(
            action_box, text="Execute", font=button_font, fg=GO_COLOR, width=BUTTON_WIDTH,
            command=self.convert_extensions,
        )
        self.convert_button.pack(padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 5))

        self.revert_button = tk.Button(
            action_box, text="Revert Last Change", font=button_font, fg=DANGER_COLOR, width=BUTTON_WIDTH,
            command=self.revert_last_change, state=tk.DISABLED,
        )
        self.revert_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

    def _build_right_panel(self, parent):
        right_panel = tk.Frame(parent, bg=WINDOW_BACKGROUND_COLOR)
        right_panel.pack(side="left", fill="both", expand=True)

        tk.Label(
            right_panel,
            text="Select individual files or a whole folder on the left, enter the new extension, "
                 "and click \u201cExecute\u201d.\nUse \u201cRevert Last Change\u201d to undo the most recent conversion.",
            bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=("Segoe UI", 8), justify="left", wraplength=620,
        ).pack(fill="x", anchor="w", pady=(0, 6))

        tk.Label(
            right_panel, text="Selected Files", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 9, "bold"),
        ).pack(fill="x", anchor="w")

        # --- Common Path Display ---
        self.common_path_label = tk.Label(
            right_panel, text="Common Path: \u2013", bg=WINDOW_BACKGROUND_COLOR,
            fg=HINT_COLOR, font=("Segoe UI", 8, "italic"), justify="left", wraplength=620, anchor="w",
        )
        self.common_path_label.pack(fill="x", anchor="w", pady=(0, 4))

        # --- Selected Files List ---
        list_frame = tk.Frame(right_panel, bg=WINDOW_BACKGROUND_COLOR)
        list_frame.pack(fill="both", expand=True, pady=(2, 0))

        self.file_listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, exportselection=False)
        self.file_listbox.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.file_listbox.config(yscrollcommand=scrollbar.set)

        self.count_label = tk.Label(right_panel, text="0 file(s) selected", bg=WINDOW_BACKGROUND_COLOR)
        self.count_label.pack(fill="x", anchor="w", pady=(6, 0))

    # --- File Selection ---
    def select_files(self):
        selected = filedialog.askopenfilenames(title="Select Files")
        if not selected:
            return
        self.files = list(selected)
        self._on_selection_changed()

    def select_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        self.files = sorted(
            os.path.join(folder, name) for name in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, name))
        )
        self._on_selection_changed()

    def _on_selection_changed(self):
        # A fresh selection invalidates any previous revert history.
        self.last_rename_map = []
        self.revert_button.config(state=tk.DISABLED)
        self.open_dir_button.config(state=tk.NORMAL if self.files else tk.DISABLED)
        self.refresh_listbox()

    def open_directory(self):
        if self.files:
            open_folder(os.path.dirname(self.files[0]))

    # --- Common Path Handling ---
    def _compute_common_path(self):
        if not self.files:
            return ""
        if len(self.files) == 1:
            return os.path.dirname(self.files[0])
        try:
            return os.path.commonpath(self.files)
        except ValueError:
            # Raised e.g. when paths live on different drives; no common path exists then.
            return ""

    def refresh_listbox(self):
        self.common_path = self._compute_common_path()
        self.common_path_label.config(
            text=f"Common Path: {self.common_path}" if self.common_path else "Common Path: \u2013"
        )

        self.file_listbox.delete(0, tk.END)
        for path in self.files:
            display_path = os.path.relpath(path, self.common_path) if self.common_path else path
            self.file_listbox.insert(tk.END, display_path)
        self.count_label.config(text=f"{len(self.files)} file(s) selected")

    # --- Conversion ---
    def convert_extensions(self):
        new_ext = self.extension_entry.get().strip().lstrip(".")
        if not new_ext:
            messagebox.showerror("Input Error", "Please enter a new file extension.")
            return
        if not self.files:
            messagebox.showerror("Input Error", "No files selected.")
            return

        converted = {}
        for old_path in self.files:
            base, _ = os.path.splitext(old_path)
            new_path = f"{base}.{new_ext}"
            if new_path == old_path:
                continue
            try:
                os.rename(old_path, new_path)
                converted[old_path] = new_path
            except OSError as error:
                messagebox.showerror(
                    "Rename Failed",
                    f"Could not rename:\n{old_path}\n{error}\n\nConversion has been stopped. "
                    "Files already converted can be undone with \"Revert Last Change\".",
                )
                break

        if converted:
            self.files = [converted.get(path, path) for path in self.files]
            self.last_rename_map = [(new_path, old_path) for old_path, new_path in converted.items()]
            self.revert_button.config(state=tk.NORMAL)
            self.refresh_listbox()
            messagebox.showinfo("Success", f"Converted {len(converted)} file(s) to .{new_ext}")

    # --- Revert ---
    def revert_last_change(self):
        if not self.last_rename_map:
            return

        if not messagebox.askyesno(
            "Revert Conversion",
            f"This will rename {len(self.last_rename_map)} file(s) back to their original extension. Continue?",
        ):
            return

        reverted = {}
        failures = []
        for new_path, old_path in reversed(self.last_rename_map):
            try:
                os.rename(new_path, old_path)
                reverted[new_path] = old_path
            except OSError as error:
                failures.append((os.path.basename(new_path), str(error)))

        self.files = [reverted.get(path, path) for path in self.files]
        self.last_rename_map = []
        self.revert_button.config(state=tk.DISABLED)
        self.refresh_listbox()

        if failures:
            details = "\n".join(f"- {name}: {reason}" for name, reason in failures)
            messagebox.showwarning("Completed with errors", f"Some files could not be reverted:\n{details}")
        else:
            messagebox.showinfo("Reverted", "All files have been renamed back to their original extension.")


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    app = ExtensionChangerApp(root)
    root.deiconify()
    root.mainloop()