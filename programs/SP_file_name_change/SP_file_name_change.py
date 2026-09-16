import os
import re
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkFont
from tkinter import filedialog, messagebox
from pathlib import Path

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


def build_new_name(name, target_word, replacement, case_sensitive=False, whole_word=False):
    if not target_word:
        return None
    flags = 0 if case_sensitive else re.IGNORECASE
    escaped = re.escape(target_word)
    if whole_word:
        not_a_letter = r"[^\W\d_]"  # a letter: word char that is not a digit/underscore
        escaped = rf"(?<!{not_a_letter}){escaped}(?!{not_a_letter})"
    pattern = re.compile(escaped, flags)
    if not pattern.search(name):
        return None
    return pattern.sub(replacement, name)


# --- Application ---
class FilenameChangerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Bulk File Name Changer")
        self.root.geometry("860x480")
        self.root.minsize(860, 480)
        add_footer(root, image_path="assets/footer.png")
        if WINDOW_BACKGROUND_COLOR:
            root.configure(bg=WINDOW_BACKGROUND_COLOR)
        center_window(root)

        self.files = []            # currently selected/tracked file paths
        self.last_rename_map = []  # (new_path, old_path) pairs from the last run, for reverting

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

        # --- Rename Settings Box ---
        settings_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        settings_box.pack(fill="x", anchor="nw")

        entry_width = BUTTON_WIDTH + 5

        tk.Label(settings_box, text="Text to delete/change:", bg=WINDOW_BACKGROUND_COLOR).pack(
            padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 2), anchor="w"
        )
        self.word_entry = tk.Entry(settings_box, width=entry_width)
        self.word_entry.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 5))

        tk.Label(settings_box, text="Replace with (blank = delete):", bg=WINDOW_BACKGROUND_COLOR).pack(
            padx=BOX_INTERNAL_PADDING, pady=(0, 2), anchor="w"
        )
        self.replace_entry = tk.Entry(settings_box, width=entry_width)
        self.replace_entry.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 5))

         # --- Matching Options ---
        self.case_sensitive_var = tk.BooleanVar(value=False)
        self.case_sensitive_check = tk.Checkbutton(
            settings_box, text="Case sensitive", variable=self.case_sensitive_var,
            bg=WINDOW_BACKGROUND_COLOR, activebackground=WINDOW_BACKGROUND_COLOR, anchor="w",
        )
        self.case_sensitive_check.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 2), anchor="w")

        self.whole_word_var = tk.BooleanVar(value=False)
        self.whole_word_check = tk.Checkbutton(
            settings_box, text="Whole word only", variable=self.whole_word_var,
            bg=WINDOW_BACKGROUND_COLOR, activebackground=WINDOW_BACKGROUND_COLOR, anchor="w",
        )
        self.whole_word_check.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING), anchor="w")

        tk.Frame(left_panel, bg=GROUP_BORDER_COLOR, height=2).pack(fill="x", pady=10)

        # --- Actions Box ---
        action_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        action_box.pack(fill="x", anchor="nw")

        self.preview_button = tk.Button(
            action_box, text="Show Preview", width=BUTTON_WIDTH, command=self.show_preview
        )
        self.preview_button.pack(padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 5))

        self.execute_button = tk.Button(
            action_box, text="Execute", font=button_font, fg=GO_COLOR, width=BUTTON_WIDTH,
            command=self.rename_files,
        )
        self.execute_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 5))

        self.revert_button = tk.Button(
            action_box, text="Revert Last Rename", font=button_font, fg=DANGER_COLOR, width=BUTTON_WIDTH,
            command=self.revert_last_rename, state=tk.DISABLED,
        )
        self.revert_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

    def _build_right_panel(self, parent):
        right_panel = tk.Frame(parent, bg=WINDOW_BACKGROUND_COLOR)
        right_panel.pack(side="left", fill="both", expand=True)

        self.count_label = tk.Label(right_panel, text="0 file(s) selected", bg=WINDOW_BACKGROUND_COLOR)
        self.count_label.pack(fill="x", anchor="w")

        tk.Label(
            right_panel,
            text="Select files or a folder, enter the text to change, then click \u201cShow Preview\u201d and or \u201cExecute\u201d.",
            bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=("Segoe UI", 8), justify="left", wraplength=560,
        ).pack(fill="x", anchor="w", pady=(2, 6))

        header_frame = tk.Frame(right_panel, bg=WINDOW_BACKGROUND_COLOR)
        header_frame.pack(fill="x")
        header_frame.grid_columnconfigure(0, weight=1)
        header_frame.grid_columnconfigure(1, weight=1)

        tk.Label(
            header_frame, text="Current Names", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header_frame, text="Preview (New Names)", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=1, sticky="w")

        lists_frame = tk.Frame(right_panel, bg=WINDOW_BACKGROUND_COLOR)
        lists_frame.pack(fill="both", expand=True, pady=(2, 0))

        # --- Current Names List ---
        current_frame = tk.Frame(lists_frame, bg=WINDOW_BACKGROUND_COLOR)
        current_frame.pack(side="left", fill="both", expand=True)

        self.file_listbox = tk.Listbox(current_frame, exportselection=False)
        self.file_listbox.pack(side="left", fill="both", expand=True)

        current_scrollbar = tk.Scrollbar(current_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        current_scrollbar.pack(side="right", fill="y")
        self.file_listbox.config(yscrollcommand=current_scrollbar.set)

        tk.Frame(lists_frame, bg=GROUP_BORDER_COLOR, width=2).pack(side="left", fill="y", padx=8)

        # --- Preview List ---
        preview_frame = tk.Frame(lists_frame, bg=WINDOW_BACKGROUND_COLOR)
        preview_frame.pack(side="left", fill="both", expand=True)

        self.preview_listbox = tk.Listbox(preview_frame, fg=HINT_COLOR, exportselection=False)
        self.preview_listbox.pack(side="left", fill="both", expand=True)

        preview_scrollbar = tk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_listbox.yview)
        preview_scrollbar.pack(side="right", fill="y")
        self.preview_listbox.config(yscrollcommand=preview_scrollbar.set)

    # --- File Selection ---
    def select_files(self):
        selected_files = filedialog.askopenfilenames(title="Select Files")
        if not selected_files:
            return
        self.files = list(selected_files)
        self._on_files_changed()

    def select_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        self.files = sorted(
            os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, f))
        )
        self._on_files_changed()

    def open_directory(self):
        if self.files:
            open_folder(os.path.dirname(self.files[0]))

    def _on_files_changed(self):
        self.count_label.config(text=f"{len(self.files)} file(s) selected")
        self.open_dir_button.config(state=tk.NORMAL if self.files else tk.DISABLED)
        self.refresh_listboxes()

    def refresh_listboxes(self):
        self.file_listbox.delete(0, tk.END)
        for file_path in self.files:
            self.file_listbox.insert(tk.END, os.path.basename(file_path))
        # The preview no longer matches the current names once the file list
        # changes, so it is cleared until "Show Preview" is run again.
        self.preview_listbox.delete(0, tk.END)

    # --- Preview ---
    def show_preview(self):
        if not self.files:
            messagebox.showerror("Error", "No files selected.")
            return
        target_word = self.word_entry.get()
        if not target_word:
            messagebox.showerror("Error", "Please enter the text to delete/change.")
            return
        replacement = self.replace_entry.get()
        case_sensitive = self.case_sensitive_var.get()
        whole_word = self.whole_word_var.get()

        self.preview_listbox.delete(0, tk.END)
        for file_path in self.files:
            name, ext = os.path.splitext(os.path.basename(file_path))
            new_name = build_new_name(name, target_word, replacement, case_sensitive, whole_word)
            if new_name is None:
                self.preview_listbox.insert(tk.END, "(no match)")
            elif not new_name.strip():
                self.preview_listbox.insert(tk.END, "(would be empty - skipped)")
            else:
                self.preview_listbox.insert(tk.END, new_name + ext)

    # --- Renaming ---
    def rename_files(self):
        if not self.files:
            messagebox.showerror("Error", "No files selected.")
            return
        target_word = self.word_entry.get()
        if not target_word:
            messagebox.showerror("Error", "Please enter the text to delete/change.")
            return
        replacement = self.replace_entry.get()
        case_sensitive = self.case_sensitive_var.get()
        whole_word = self.whole_word_var.get()

        rename_map = []
        skipped_files = []
        updated_files = []

        for file_path in self.files:
            dir_name, full_name = os.path.split(file_path)
            name, ext = os.path.splitext(full_name)

            new_name = build_new_name(name, target_word, replacement, case_sensitive, whole_word)
            if new_name is None:
                skipped_files.append(f"{full_name} (no match)")
                updated_files.append(file_path)
                continue
            if not new_name.strip():
                skipped_files.append(f"{full_name} (result would be empty)")
                updated_files.append(file_path)
                continue

            new_path = os.path.join(dir_name, new_name + ext)

            if os.path.normcase(new_path) != os.path.normcase(file_path) and os.path.exists(new_path):
                skipped_files.append(f"{full_name} (a file with the new name already exists)")
                updated_files.append(file_path)
                continue

            try:
                os.rename(file_path, new_path)
                rename_map.append((new_path, file_path))
                updated_files.append(new_path)
            except OSError as error:
                skipped_files.append(f"{full_name} ({error})")
                updated_files.append(file_path)

        self.files = updated_files
        self._on_files_changed()

        if rename_map:
            self.last_rename_map = rename_map
            self.revert_button.config(state=tk.NORMAL)

        message = f"Successfully renamed {len(rename_map)} file(s)."
        if skipped_files:
            message += "\n\nSkipped:\n" + "\n".join(skipped_files)
        messagebox.showinfo("Result", message)

    def revert_last_rename(self):
        if not self.last_rename_map:
            return

        if not messagebox.askyesno(
            "Revert Renaming",
            f"This will rename {len(self.last_rename_map)} file(s) back to their original names. Continue?",
        ):
            return

        failures = []
        for new_path, old_path in reversed(self.last_rename_map):
            try:
                os.rename(new_path, old_path)
                if new_path in self.files:
                    self.files[self.files.index(new_path)] = old_path
            except OSError as error:
                failures.append((os.path.basename(new_path), str(error)))

        self.last_rename_map = []
        self.revert_button.config(state=tk.DISABLED)
        self._on_files_changed()

        if failures:
            details = "\n".join(f"- {name}: {reason}" for name, reason in failures)
            messagebox.showwarning("Completed with errors", f"Some files could not be reverted:\n{details}")
        else:
            messagebox.showinfo("Reverted", "All files have been renamed back to their original names.")


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    app = FilenameChangerApp(root)
    root.deiconify()
    root.mainloop()