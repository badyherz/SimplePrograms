import os
import shutil
import subprocess
import tkinter as tk
import tkinter.font as tkFont
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
class FileRenamer:
    def __init__(self, root):
        self.root = root
        self.root.title("Bulk File Renamer for Series")
        self.root.geometry("860x480")
        self.root.minsize(860, 480)
        add_footer(root, image_path="assets/footer.png")
        if WINDOW_BACKGROUND_COLOR:
            root.configure(bg=WINDOW_BACKGROUND_COLOR)
        center_window(root)

        self.selected_folder = ""
        self.available_files = []   # files not yet placed into the episode order
        self.episode_order = []     # files in their chosen episode order
        self.last_rename_map = []   # (new_path, old_path) pairs from the last run, for reverting

        self.create_widgets()

    # --- Widget Setup ---
    def create_widgets(self):
        self._build_progress_bar()

        main_frame = tk.Frame(self.root, bg=WINDOW_BACKGROUND_COLOR)
        main_frame.pack(fill="both", expand=True, padx=BOX_EXTERNAL_PADDING, pady=BOX_EXTERNAL_PADDING)

        self._build_left_panel(main_frame)

        tk.Frame(main_frame, bg=GROUP_BORDER_COLOR, width=2).pack(side="left", fill="y", padx=10)

        self._build_right_panel(main_frame)

    def _build_progress_bar(self):
        # Packed before the main content area so it reliably reserves its
        # strip at the bottom of the window
        bottom_frame = tk.Frame(self.root, bg=WINDOW_BACKGROUND_COLOR)
        bottom_frame.pack(side="bottom", fill="x", padx=BOX_EXTERNAL_PADDING, pady=(0, BOX_EXTERNAL_PADDING))

        progress_style = ttk.Style(self.root)
        progress_style.theme_use("clam")
        progress_style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor="#929292",
            background=GO_COLOR,
            bordercolor="#929292",
            lightcolor=GO_COLOR,
            darkcolor=GO_COLOR,
        )

        self.progress_bar = ttk.Progressbar(
            bottom_frame, style="Custom.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate",
        )
        self.progress_bar.pack(side="left", fill="x", expand=True)

        self.progress_label = tk.Label(bottom_frame, text="", bg=WINDOW_BACKGROUND_COLOR, width=8)
        self.progress_label.pack(side="left", padx=(8, 0))

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

        self.select_folder_button = tk.Button(
            source_box, text="Select Folder", width=BUTTON_WIDTH, command=self.select_folder
        )
        self.select_folder_button.pack(padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 5))

        self.open_folder_button = tk.Button(
            source_box, text="Open Selected Directory", width=BUTTON_WIDTH,
            command=self.open_selected_directory, state=tk.DISABLED,
        )
        self.open_folder_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        tk.Frame(left_panel, bg=GROUP_BORDER_COLOR, height=2).pack(fill="x", pady=10)

        # --- Naming Box ---
        naming_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        naming_box.pack(fill="x", anchor="nw")

        entry_width = BUTTON_WIDTH + 5

        tk.Label(naming_box, text="Series Name:", bg=WINDOW_BACKGROUND_COLOR).pack(
            padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 2), anchor="w"
        )
        self.series_name_entry = tk.Entry(naming_box, width=entry_width)
        self.series_name_entry.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 5))

        tk.Label(naming_box, text="Season Number:", bg=WINDOW_BACKGROUND_COLOR).pack(
            padx=BOX_INTERNAL_PADDING, pady=(0, 2), anchor="w"
        )
        self.season_number_entry = tk.Entry(naming_box, width=entry_width)
        self.season_number_entry.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 5))

        tk.Label(naming_box, text="Extra (optional):", bg=WINDOW_BACKGROUND_COLOR).pack(
            padx=BOX_INTERNAL_PADDING, pady=(0, 2), anchor="w"
        )
        self.extra_entry = tk.Entry(naming_box, width=entry_width)
        self.extra_entry.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        tk.Frame(left_panel, bg=GROUP_BORDER_COLOR, height=2).pack(fill="x", pady=10)

        # --- Actions Box ---
        action_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        action_box.pack(fill="x", anchor="nw")

        self.start_button = tk.Button(
            action_box, text="Start Renaming", font=button_font, fg=GO_COLOR, width=BUTTON_WIDTH,
            command=self.start_renaming, state=tk.DISABLED,
        )
        self.start_button.pack(padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 5))

        self.revert_button = tk.Button(
            action_box, text="Revert Last Rename", font=button_font, fg=DANGER_COLOR, width=BUTTON_WIDTH,
            command=self.revert_last_rename, state=tk.DISABLED,
        )
        self.revert_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

    def _build_right_panel(self, parent):
        right_panel = tk.Frame(parent, bg=WINDOW_BACKGROUND_COLOR)
        right_panel.pack(side="left", fill="both", expand=True)

        tk.Label(
            right_panel,
            text="Select file(s) on the left and click \u201cAdd\u201d. Files are added in "
                 "the order shown; \nuse \u201cMove Up\u201d / \u201cMove Down\u201d to fine-tune the result.",
            bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=("Segoe UI", 8), justify="left", wraplength=620,
        ).pack(fill="x", anchor="w", pady=(0, 6))

        header_frame = tk.Frame(right_panel, bg=WINDOW_BACKGROUND_COLOR)
        header_frame.pack(fill="x")
        header_frame.grid_columnconfigure(0, weight=1)
        header_frame.grid_columnconfigure(1, minsize=112)
        header_frame.grid_columnconfigure(2, weight=1)

        tk.Label(
            header_frame, text="Available Files", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header_frame, text="Episode Order", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=2, sticky="w")

        lists_frame = tk.Frame(right_panel, bg=WINDOW_BACKGROUND_COLOR)
        lists_frame.pack(fill="both", expand=True, pady=(2, 0))

        # --- Available Files List ---
        available_frame = tk.Frame(lists_frame, bg=WINDOW_BACKGROUND_COLOR)
        available_frame.pack(side="left", fill="both", expand=True)

        self.available_listbox = tk.Listbox(available_frame, selectmode=tk.EXTENDED, exportselection=False)
        self.available_listbox.pack(side="left", fill="both", expand=True)
        self.available_listbox.bind("<Double-Button-1>", lambda event: self.add_to_order())

        available_scrollbar = tk.Scrollbar(available_frame, orient=tk.VERTICAL, command=self.available_listbox.yview)
        available_scrollbar.pack(side="right", fill="y")
        self.available_listbox.config(yscrollcommand=available_scrollbar.set)

        # --- Reorder Controls ---
        controls_frame = tk.Frame(lists_frame, bg=WINDOW_BACKGROUND_COLOR, width=112)
        controls_frame.pack(side="left", fill="y", padx=8)

        tk.Button(controls_frame,text="➡ Add",width=14,command=self.add_to_order).pack(pady=(30, 4))
        tk.Button(controls_frame,text="⬅ Remove",width=14,command=self.remove_from_order).pack(pady=(4, 20))
        tk.Button(controls_frame,text="⬆ Move Up",width=14,command=self.move_up).pack(pady=4)
        tk.Button(controls_frame,text="⬇ Move Down",width=14,command=self.move_down).pack(pady=4)

        # --- Episode Order List ---
        order_frame = tk.Frame(lists_frame, bg=WINDOW_BACKGROUND_COLOR)
        order_frame.pack(side="left", fill="both", expand=True)

        self.order_listbox = tk.Listbox(order_frame, selectmode=tk.SINGLE, exportselection=False)
        self.order_listbox.pack(side="left", fill="both", expand=True)
        self.order_listbox.bind("<Double-Button-1>", lambda event: self.remove_from_order())

        order_scrollbar = tk.Scrollbar(order_frame, orient=tk.VERTICAL, command=self.order_listbox.yview)
        order_scrollbar.pack(side="right", fill="y")
        self.order_listbox.config(yscrollcommand=order_scrollbar.set)

    # --- Folder Selection ---
    def select_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return

        self.selected_folder = folder
        self.episode_order = []
        self.refresh_available_files()
        self.open_folder_button.config(state=tk.NORMAL)
        self.update_start_button_state()

    def open_selected_directory(self):
        if self.selected_folder:
            open_folder(self.selected_folder)

    def refresh_available_files(self):
        if not self.selected_folder:
            self.available_files = []
        else:
            all_files = sorted(
                f for f in os.listdir(self.selected_folder)
                if os.path.isfile(os.path.join(self.selected_folder, f))
            )
            self.available_files = [f for f in all_files if f not in self.episode_order]
        self.refresh_listboxes()

    # --- Order Building ---
    def add_to_order(self):
        selected_indices = self.available_listbox.curselection()
        if not selected_indices:
            return

        selected_files = [self.available_listbox.get(i) for i in selected_indices]
        self.episode_order.extend(selected_files)
        self.available_files = [f for f in self.available_files if f not in selected_files]

        self.refresh_listboxes()
        self.update_start_button_state()

    def remove_from_order(self):
        selected_indices = self.order_listbox.curselection()
        if not selected_indices:
            return

        removed_files = {self.episode_order[i] for i in selected_indices}
        self.episode_order = [f for i, f in enumerate(self.episode_order) if i not in selected_indices]
        self.available_files = sorted(self.available_files + list(removed_files))

        self.refresh_listboxes()
        self.update_start_button_state()

    def move_up(self):
        selected = self.order_listbox.curselection()
        if not selected or selected[0] == 0:
            return
        index = selected[0]
        self.episode_order[index - 1], self.episode_order[index] = (
            self.episode_order[index], self.episode_order[index - 1],
        )
        self.refresh_listboxes()
        self.order_listbox.selection_set(index - 1)

    def move_down(self):
        selected = self.order_listbox.curselection()
        if not selected or selected[0] == len(self.episode_order) - 1:
            return
        index = selected[0]
        self.episode_order[index + 1], self.episode_order[index] = (
            self.episode_order[index], self.episode_order[index + 1],
        )
        self.refresh_listboxes()
        self.order_listbox.selection_set(index + 1)

    def refresh_listboxes(self):
        self.available_listbox.delete(0, tk.END)
        for filename in self.available_files:
            self.available_listbox.insert(tk.END, filename)

        self.order_listbox.delete(0, tk.END)
        for position, filename in enumerate(self.episode_order, start=1):
            self.order_listbox.insert(tk.END, f"{position}. {filename}")

    def update_start_button_state(self):
        state = tk.NORMAL if self.episode_order else tk.DISABLED
        self.start_button.config(state=state)

    # --- Renaming ---
    def start_renaming(self):
        series_name = self.series_name_entry.get().strip()
        season_number = self.season_number_entry.get().strip()
        extra_text = self.extra_entry.get().strip()

        if not series_name or not season_number:
            messagebox.showwarning("Input Error", "Please enter both series name and season number.")
            return

        try:
            season_number = int(season_number)
        except ValueError:
            messagebox.showwarning("Input Error", "Season number must be an integer.")
            return

        if not self.episode_order:
            messagebox.showwarning("Input Error", "Please add at least one file to the episode order.")
            return

        total_files = len(self.episode_order)
        self.progress_bar.configure(maximum=total_files, value=0)
        self.progress_label.configure(text=f"0 / {total_files}")
        self.start_button.config(state=tk.DISABLED)

        rename_map = []
        for index, filename in enumerate(self.episode_order, start=1):
            new_name = f"{series_name} - Season {season_number} Episode {index}"
            if extra_text:
                new_name += f" {extra_text}"
            new_name += os.path.splitext(filename)[1]

            old_path = os.path.join(self.selected_folder, filename)
            new_path = os.path.join(self.selected_folder, new_name)

            try:
                os.rename(old_path, new_path)
                rename_map.append((new_path, old_path))
            except OSError as error:
                messagebox.showerror(
                    "Rename Failed",
                    f"Could not rename '{filename}':\n{error}\n\nRenaming has been stopped. "
                    "Files already renamed can be undone with \"Revert Last Rename\".",
                )
                break

            self.progress_bar.configure(value=index)
            self.progress_label.configure(text=f"{index} / {total_files}")
            self.root.update_idletasks()

        if rename_map:
            self.last_rename_map = rename_map
            self.revert_button.config(state=tk.NORMAL)
            messagebox.showinfo("Success", f"{len(rename_map)} file(s) have been renamed successfully!")

        self.episode_order = []
        self.refresh_available_files()
        self.update_start_button_state()

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
            except OSError as error:
                failures.append((os.path.basename(new_path), str(error)))

        self.last_rename_map = []
        self.revert_button.config(state=tk.DISABLED)

        if failures:
            details = "\n".join(f"- {name}: {reason}" for name, reason in failures)
            messagebox.showwarning("Completed with errors", f"Some files could not be reverted:\n{details}")
        else:
            messagebox.showinfo("Reverted", "All files have been renamed back to their original names.")

        self.refresh_available_files()


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    app = FileRenamer(root)
    root.deiconify()
    root.mainloop()