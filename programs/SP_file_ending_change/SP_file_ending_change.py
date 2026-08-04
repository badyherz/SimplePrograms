import os
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import sys

class ExtensionChangerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Bulk File Extension Renamer")
        self.files = []
        root.geometry("400x350")

        # Make window resizable
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)  # Listbox row grows

        self.create_widgets()

    def create_widgets(self):
        # --- Select files button ---
        self.select_button = tk.Button(self.root, text="Select Files", command=self.select_files)
        self.select_button.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        # --- Listbox with scrollbar ---
        self.file_listbox = tk.Listbox(self.root)
        self.file_listbox.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        scrollbar = tk.Scrollbar(self.file_listbox, orient="vertical", command=self.file_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.file_listbox.config(yscrollcommand=scrollbar.set)

        # --- Count label ---
        self.count_label = tk.Label(self.root, text="0 files selected")
        self.count_label.grid(row=2, column=0, sticky="w", padx=5, pady=5)

        # --- Extension entry ---
        ext_frame = tk.Frame(self.root)
        ext_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        tk.Label(ext_frame, text="New File Extension (e.g., jpg):").pack(side=tk.LEFT)
        self.extension_entry = tk.Entry(ext_frame)
        self.extension_entry.pack(side=tk.LEFT, fill="x", expand=True)

        # --- Buttons: Convert + Open Directory ---
        button_frame = tk.Frame(self.root)
        button_frame.grid(row=4, column=0, sticky="ew", padx=5, pady=10)
        self.convert_button = tk.Button(button_frame, text="Convert", command=self.convert_extensions)
        self.convert_button.pack(side=tk.LEFT, padx=5)
        self.open_dir_button = tk.Button(button_frame, text="Open Directory", command=self.open_directory, state=tk.DISABLED)
        self.open_dir_button.pack(side=tk.LEFT, padx=5)

    # --- File selection ---
    def select_files(self):
        selected_files = filedialog.askopenfilenames(title="Select Files")
        if selected_files:
            self.files = list(selected_files)
            self.file_listbox.delete(0, tk.END)
            for file in self.files:
                self.file_listbox.insert(tk.END, file)
            self.count_label.config(text=f"{len(self.files)} files selected")
            self.open_dir_button.config(state=tk.NORMAL)  # Enable "Open Directory"

    # --- Convert extensions ---
    def convert_extensions(self):
        new_ext = self.extension_entry.get().strip().lstrip(".")
        if not new_ext:
            messagebox.showerror("Error", "Please enter a new file extension.")
            return
        if not self.files:
            messagebox.showerror("Error", "No files selected.")
            return

        for file_path in self.files:
            base, _ = os.path.splitext(file_path)
            new_path = f"{base}.{new_ext}"
            try:
                os.rename(file_path, new_path)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to rename:\n{file_path}\n{e}")
                return

        messagebox.showinfo("Success", f"Renamed {len(self.files)} files to .{new_ext}")
        # Open the folder where files were renamed
        folder = os.path.dirname(self.files[0])
        self.open_folder(folder)

    # --- Open directory ---
    def open_directory(self):
        if self.files:
            folder = os.path.dirname(self.files[0])
            self.open_folder(folder)

    def open_folder(self, path):
        try:
            if sys.platform.startswith('darwin'):
                subprocess.run(['open', path])
            elif os.name == 'nt':
                os.startfile(path)
            elif os.name == 'posix':
                subprocess.run(['xdg-open', path])
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open folder:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ExtensionChangerApp(root)
    root.mainloop()
