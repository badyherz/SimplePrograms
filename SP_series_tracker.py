import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import json
import os
import sys

DOCUMENTS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "SeriesTracker")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

DATA_FILENAME = os.path.join(DOCUMENTS_DIR, "series_tracker_data.json")
ARCHIVE_DIR = os.path.join(DOCUMENTS_DIR, "archive")

class SeriesTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Series Tracker")
        self.series_data = []
        self.archive_data = []
        self.filtered_data = []

        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Button(top_frame, text="Add Series", command=self.add_series).pack(side=tk.LEFT)
        tk.Button(top_frame, text="View Archive", command=self.view_archive).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Export", command=self.save_as).pack(side=tk.LEFT)
        tk.Button(top_frame, text="Import", command=self.load_from_file).pack(side=tk.LEFT, padx=5)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.search_series)
        tk.Entry(top_frame, textvariable=self.search_var, width=30).pack(side=tk.RIGHT, padx=5)
        tk.Label(top_frame, text="Search:").pack(side=tk.RIGHT)

        self.canvas = tk.Canvas(self.root)
        self.scroll_y = tk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.frame = tk.Frame(self.canvas)

        self.frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll_y.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll_y.pack(side="right", fill="y")

    def add_series(self):
        name = simpledialog.askstring("Series Name", "Enter series name:")
        if not name:
            return
        try:
            seasons = int(simpledialog.askstring("Seasons", f"How many seasons in '{name}'?"))
            episodes = [int(simpledialog.askstring("Episodes", f"Episodes in season {i+1}?")) for i in range(seasons)]
        except (TypeError, ValueError):
            messagebox.showerror("Invalid input", "Please enter valid numbers.")
            return

        series = {"name": name, "episodes": episodes, "current_season": 0, "current_episode": 0}
        # Insert at the beginning to make newest at top
        self.series_data.insert(0, series)
        self.refresh_display()

    def next_episode(self, index):
        series = self.filtered_data[index]
        real_index = self.series_data.index(series)
        if series["current_season"] < len(series["episodes"]):
            series["current_episode"] += 1
            if series["current_episode"] >= series["episodes"][series["current_season"]]:
                series["current_season"] += 1
                series["current_episode"] = 0
        # Move updated series to top
        self.series_data.pop(real_index)
        self.series_data.insert(0, series)
        self.refresh_display()

    def previous_episode(self, index):
        series = self.filtered_data[index]
        real_index = self.series_data.index(series)
        if series["current_episode"] > 0:
            series["current_episode"] -= 1
        elif series["current_season"] > 0:
            series["current_season"] -= 1
            series["current_episode"] = series["episodes"][series["current_season"]] - 1
        # Move updated series to top
        self.series_data.pop(real_index)
        self.series_data.insert(0, series)
        self.refresh_display()

    def delete_series(self, index):
        series = self.filtered_data[index]
        if messagebox.askyesno("Delete Series", f"Delete '{series['name']}'?"):
            self.series_data.remove(series)
            self.refresh_display()

    def archive_series(self, index):
        series = self.filtered_data[index]
        self.archive_data.insert(0, series)  # newest archived on top
        self.series_data.remove(series)
        self.refresh_display()

    def view_archive(self):
        archive_window = tk.Toplevel(self.root)
        archive_window.title("Archived Series")
        canvas = tk.Canvas(archive_window)
        scroll_y = tk.Scrollbar(archive_window, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas)

        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll_y.set)

        canvas.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        for series in self.archive_data:
            container = tk.Frame(frame, relief=tk.RIDGE, bd=2, padx=5, pady=5)
            container.pack(fill=tk.X, padx=5, pady=5)

            tk.Label(container, text=series['name'], font=("Arial", 12)).pack(side=tk.LEFT)
            tk.Button(container, text="Retrieve", command=lambda s=series: self.retrieve_series(s, archive_window)).pack(side=tk.RIGHT)
            tk.Button(container, text="Delete", command=lambda s=series, c=container: self.delete_archive_series(s, c)).pack(side=tk.RIGHT, padx=5)

    def retrieve_series(self, series, window):
        self.series_data.append(series)
        self.archive_data.remove(series)
        self.refresh_display()
        window.destroy()

    def delete_archive_series(self, series, container):
        if messagebox.askyesno("Delete Archive", f"Delete '{series['name']}'?"):
            self.archive_data.remove(series)
            container.destroy()

    def refresh_display(self):
        for widget in self.frame.winfo_children():
            widget.destroy()

        self.filtered_data = [s for s in self.series_data if self.search_var.get().lower() in s['name'].lower()]

        for i, series in enumerate(self.filtered_data):
            container = tk.Frame(self.frame, relief=tk.RIDGE, bd=2, padx=5, pady=5)
            container.pack(fill=tk.X, padx=5, pady=5)

            name = series['name']
            season = series['current_season'] + 1
            episode = series['current_episode'] + 1
            total_episodes = sum(series['episodes'])
            watched = sum(series['episodes'][:series['current_season']]) + series['current_episode']
            progress = watched / total_episodes if total_episodes > 0 else 0

            progress_text = "Completed" if watched >= total_episodes else f"S{season}E{episode}"
            title_label = tk.Label(container, text=f"{name} - {progress_text}", font=("Arial", 12))
            title_label.pack(side=tk.TOP, anchor='w')

            progress_bar = tk.Canvas(container, width=200, height=10, bg='lightgray')
            progress_bar.pack(pady=2)
            progress_bar.create_rectangle(0, 0, 200 * progress, 10, fill='green')

            button_frame = tk.Frame(container)
            button_frame.pack(anchor='w')
            tk.Button(button_frame, text="-", font=("Arial", 12, "bold"), command=lambda i=i: self.previous_episode(i)).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="+", font=("Arial", 12, "bold"), command=lambda i=i: self.next_episode(i)).pack(side=tk.LEFT)
            tk.Button(button_frame, text="Delete", command=lambda i=i: self.delete_series(i)).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="Archive", command=lambda i=i: self.archive_series(i)).pack(side=tk.LEFT)

    def search_series(self, *args):
        self.refresh_display()

    def load_data(self):
        if os.path.exists(DATA_FILENAME):
            with open(DATA_FILENAME, 'r') as f:
                data = json.load(f)
                self.series_data = data.get("series", [])
                self.archive_data = data.get("archive", [])
                self.refresh_display()

    def save_data(self):
        with open(DATA_FILENAME, 'w') as f:
            json.dump({"series": self.series_data, "archive": self.archive_data}, f, indent=4)

    def save_as(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if file_path:
            with open(file_path, 'w') as f:
                json.dump({"series": self.series_data, "archive": self.archive_data}, f, indent=4)

    def load_from_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if file_path:
            if messagebox.askyesno("Load Data", "This will overwrite current data. Continue?"):
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    self.series_data = data.get("series", [])
                    self.archive_data = data.get("archive", [])
                    self.refresh_display()

    def on_close(self):
        self.save_data()
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = SeriesTrackerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
