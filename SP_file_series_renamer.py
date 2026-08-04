import os
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess

class FileRenamer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bulk File Renamer for Series")
        self.geometry("500x650")

        self.selected_folder = ""
        self.files = []
        self.file_order = []  # List to track the order of selected files

        self.create_widgets()

    def create_widgets(self):
        # Select folder button
        self.select_folder_button = tk.Button(self, text="Select Folder", command=self.select_folder)
        self.select_folder_button.pack(pady=10)

        # Listbox to display files
        self.file_listbox = tk.Listbox(self, selectmode=tk.SINGLE, width=100, height=15)
        self.file_listbox.pack(pady=10)
        self.file_listbox.bind('<<ListboxSelect>>', self.on_select_file)  # Bind selection event

        # Scrollbar for the listbox
        self.scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL, command=self.file_listbox.yview)
        self.file_listbox.config(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Entry fields for series name and season number
        self.series_name_label = tk.Label(self, text="Series Name:")
        self.series_name_label.pack(pady=5)
        self.series_name_entry = tk.Entry(self, width=50)
        self.series_name_entry.pack(pady=5)

        self.season_number_label = tk.Label(self, text="Season Number:")
        self.season_number_label.pack(pady=5)
        self.season_number_entry = tk.Entry(self, width=50)
        self.season_number_entry.pack(pady=5)

        self.extra_label = tk.Label(self, text="Extra:")
        self.extra_label.pack(pady=5)
        self.extra_entry = tk.Entry(self, width=50)
        self.extra_entry.pack(pady=5)

        # Start button
        self.start_button = tk.Button(self, text="Start Renaming", command=self.start_renaming)
        self.start_button.pack(pady=20)

        # Open folder button
        self.open_folder_button = tk.Button(self, text="Open Selected Directory", command=self.open_selected_directory)
        self.open_folder_button.pack(pady=10)

    def select_folder(self):
        self.selected_folder = filedialog.askdirectory()
        if self.selected_folder:
            self.files = os.listdir(self.selected_folder)
            self.files.sort()  # Sort files alphabetically
            self.update_file_listbox()

    def update_file_listbox(self):
        self.file_listbox.delete(0, tk.END)
        for file in self.files:
            display_name = file
            if file in self.file_order:
                display_name = f"{self.file_order.index(file) + 1}. {file}"
            self.file_listbox.insert(tk.END, display_name)

    def on_select_file(self, event):
        selected_index = self.file_listbox.curselection()
        if selected_index:
            selected_file = self.files[selected_index[0]]
            if selected_file in self.file_order:
                self.file_order.remove(selected_file)
            else:
                self.file_order.append(selected_file)
            self.update_file_listbox()

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

        for index, file in enumerate(self.file_order):
            episode_number = index + 1
            new_name = f"{series_name} - Season {season_number} Episode {episode_number}"
            if extra_text:
                new_name += f" {extra_text}"
            new_name += os.path.splitext(file)[1]
            old_path = os.path.join(self.selected_folder, file)
            new_path = os.path.join(self.selected_folder, new_name)
            os.rename(old_path, new_path)

        messagebox.showinfo("Success", "Files have been renamed successfully!")
        self.file_order = []  # Clear the order list after renaming
        self.update_file_listbox()

    def open_selected_directory(self):
        if self.selected_folder:
            if os.name == 'nt':  # Windows
                os.startfile(self.selected_folder)
            elif os.name == 'posix':  # macOS, Linux
                subprocess.Popen(['open', self.selected_folder])

if __name__ == "__main__":
    app = FileRenamer()
    app.mainloop()
