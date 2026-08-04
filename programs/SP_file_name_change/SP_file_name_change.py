import os
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import sys

class FilenameChangerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Bulk File Name Changer")
        self.files = []
        root.geometry("400x350")

        # Make window resizable
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self.create_widgets()

    def create_widgets(self):
        # --- Select files button ---
        self.select_button = tk.Button(self.root, text="Select Files", command=self.select_files)
        self.select_button.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        # --- Listbox with scrollbar ---
        list_frame = tk.Frame(self.root)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(list_frame)
        self.file_listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.file_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_listbox.config(yscrollcommand=scrollbar.set)

        # --- Count label ---
        self.count_label = tk.Label(self.root, text="0 files selected")
        self.count_label.grid(row=2, column=0, sticky="w", padx=5, pady=5)

       # --- Word entry frame ---
        word_frame = tk.Frame(self.root)
        word_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        word_frame.columnconfigure(1, weight=1)  # make entry expand

        # Word to delete/change
        tk.Label(word_frame, text="Text to delete/change:").grid(row=0, column=0, sticky="w")
        self.word_entry = tk.Entry(word_frame)
        self.word_entry.grid(row=0, column=1, sticky="ew")

        # Replace with (leave blank to delete)
        tk.Label(word_frame, text="Replace with (leave blank to delete):").grid(row=1, column=0, sticky="w", pady=(5,0))
        self.replace_entry = tk.Entry(word_frame)
        self.replace_entry.grid(row=1, column=1, sticky="ew", pady=(5,0))

        # --- Preview label ---
        self.preview_label = tk.Label(self.root, text="", fg="blue")
        self.preview_label.grid(row=4, column=0, sticky="w", padx=5, pady=5)

        # --- Buttons ---
        button_frame = tk.Frame(self.root)
        button_frame.grid(row=5, column=0, sticky="ew", padx=5, pady=10)
        self.preview_button = tk.Button(button_frame, text="Show Preview", command=self.show_preview)
        self.preview_button.pack(side=tk.LEFT, padx=5)
        self.execute_button = tk.Button(button_frame, text="Execute", command=self.rename_files)
        self.execute_button.pack(side=tk.LEFT, padx=5)
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
            self.open_dir_button.config(state=tk.NORMAL)
            self.preview_label.config(text="")  # clear preview

    # --- Show preview ---
    def show_preview(self):
        if not self.files:
            messagebox.showerror("Error", "No files selected.")
            return
        target_word = self.word_entry.get()
        replacement = self.replace_entry.get()
        if not target_word:
            messagebox.showerror("Error", "Please enter a word to delete/change.")
            return

        # Take the first file as example
        file_path = self.files[0]
        _, full_name = os.path.split(file_path)
        name, ext = os.path.splitext(full_name)

        if target_word in name:
            new_name = name.replace(target_word, replacement) + ext
            self.preview_label.config(
                text=f"Preview (first file):\nCurrent: {full_name}\nNew: {new_name}"
            )
        else:
            self.preview_label.config(
                text=f"Preview (first file):\nWord not found in {full_name}"
            )

    # --- Rename files ---
    def rename_files(self):
        target_word = self.word_entry.get()
        replacement = self.replace_entry.get()

        if not target_word:
            messagebox.showerror("Error", "Please enter a word to delete/change.")
            return
        if not self.files:
            messagebox.showerror("Error", "No files selected.")
            return

        failed_files = []
        renamed_count = 0

        for file_path in self.files:
            dir_name, full_name = os.path.split(file_path)
            name, ext = os.path.splitext(full_name)

            if target_word not in name:
                failed_files.append(full_name)
                continue

            new_name = name.replace(target_word, replacement)
            new_path = os.path.join(dir_name, new_name + ext)

            try:
                os.rename(file_path, new_path)
                renamed_count += 1
            except Exception:
                failed_files.append(full_name)

        message = f"Successfully renamed {renamed_count} file(s)."
        if failed_files:
            message += "\n\nFiles not changed (word not found or error):\n" + "\n".join(failed_files)
        messagebox.showinfo("Result", message)

        if self.files:
            self.open_folder(os.path.dirname(self.files[0]))

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
    app = FilenameChangerApp(root)
    root.mainloop()
