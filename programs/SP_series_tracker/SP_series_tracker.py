import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import sys
import shutil
import uuid
import colorsys

from SP_footer_picture import add_footer
from SP_window_utils import center_window

OLD_DOCUMENTS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "Series Tracker")
OLD_DATA_FILENAME = os.path.join(OLD_DOCUMENTS_DIR, "series_tracker_data.json")

DOCUMENTS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "SimplePrograms", "Series Tracker")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
DATA_FILENAME = os.path.join(DOCUMENTS_DIR, "series_tracker_data.json")

WINDOW_BACKGROUND_COLOR = "#E6E6E6"

# One-time migration: bring existing data over from the old folder, if any.
if not os.path.exists(DATA_FILENAME) and os.path.exists(OLD_DATA_FILENAME):
    try:
        shutil.copy2(OLD_DATA_FILENAME, DATA_FILENAME)
    except OSError:
        pass

class SeriesTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Series Tracker")
        self.root.geometry("550x400")
        self.root.minsize(550,400)
        self.series_data = []
        self.archive_data = []
        self.filtered_data = []
        self.archive_window = None
        self.archive_list_frame = None
        self.completed_labels = []
        self.rainbow_enabled = False  #Effect starts OFF by default
        self._default_label_fg = "black"
        center_window(self.root)

        #Adds footer, needs footer.png
        add_footer(root, image_path="footer.png")

        self.setup_ui()
        self.load_data()
        self._start_rainbow_animation()

    def _create_child_window(self, title, width, height, x_offset=60, y_offset=60):
        """Toplevel with a fixed starting size/position, placed near the main window."""
        self.root.update_idletasks()
        x = self.root.winfo_x() + x_offset
        y = self.root.winfo_y() + y_offset

        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.minsize(width, height)
       
        return window

    def _bind_mousewheel(self, canvas):
        """Let the mouse wheel scroll this canvas while the pointer is over it."""
        def on_wheel(event):
            if sys.platform == "darwin":
                canvas.yview_scroll(int(-1 * event.delta), "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def on_wheel_up(event):
            canvas.yview_scroll(-1, "units")

        def on_wheel_down(event):
            canvas.yview_scroll(1, "units")

        def bind_wheel(event):
            canvas.bind_all("<MouseWheel>", on_wheel)      # Windows / macOS
            canvas.bind_all("<Button-4>", on_wheel_up)      # Linux scroll up
            canvas.bind_all("<Button-5>", on_wheel_down)    # Linux scroll down

        def unbind_wheel(event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", bind_wheel)
        canvas.bind("<Leave>", unbind_wheel)

    def _make_scrollable_frame(self, parent):
        """Canvas+Scrollbar pair inside parent; returns the scrollable inner frame."""
        canvas = tk.Canvas(parent, bg=WINDOW_BACKGROUND_COLOR)
        scroll_y = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner_frame = tk.Frame(canvas, bg=WINDOW_BACKGROUND_COLOR)

        inner_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll_y.set)

        canvas.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        self._bind_mousewheel(canvas)

        return inner_frame

    def setup_ui(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        toolbar = tk.Frame(top_frame)
        toolbar.pack(fill=tk.X)
        tk.Button(toolbar, text="Add Series", command=self.add_series).pack(side=tk.LEFT)
        tk.Button(toolbar, text="View Archive", command=self.view_archive).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="Export", command=self.save_as).pack(side=tk.LEFT)
        tk.Button(toolbar, text="Import", command=self.load_from_file).pack(side=tk.LEFT, padx=5)

        tk.Label(toolbar, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.search_series)
        tk.Entry(toolbar, textvariable=self.search_var, width=30).pack(side=tk.LEFT, padx=5)
        
        self._toggle_bg_hex = toolbar.cget("bg")
        self.rainbow_toggle_canvas = tk.Canvas(
            toolbar, width=20, height=20, highlightthickness=0, bg=self._toggle_bg_hex, cursor="hand2"
        )
        self.rainbow_toggle_canvas.pack(side=tk.LEFT, padx=(5, 0))
        self.rainbow_toggle_canvas.bind("<Button-1>", lambda e: self.toggle_rainbow_effect())
        self._draw_rainbow_toggle()

        separator = ttk.Separator(top_frame, orient="horizontal")
        separator.pack(fill=tk.X, pady=(8, 0))

        self.frame = self._make_scrollable_frame(self.root)
        

    def add_series(self):
        add_window = self._create_child_window("Add Series", 425, 400)
        add_window.transient(self.root)
        add_window.grab_set()

        # --- Series name ---
        name_frame = tk.Frame(add_window, padx=10, pady=10)
        name_frame.pack(fill=tk.X)
        tk.Label(name_frame, text="Series Name:").pack(side=tk.LEFT)
        name_entry = tk.Entry(name_frame)
        name_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        name_entry.focus_set()

        # --- Season count ---
        season_frame = tk.Frame(add_window, padx=10, pady=10)
        season_frame.pack(fill=tk.X)
        tk.Label(season_frame, text="Number of Seasons:").pack(side=tk.LEFT)
        season_var = tk.StringVar(value="1")
        season_spin = tk.Spinbox(season_frame, from_=1, to=100, width=5, textvariable=season_var)
        season_spin.pack(side=tk.LEFT, padx=5)
        tk.Button(season_frame, text="Set Seasons", command=lambda: build_season_fields()).pack(side=tk.LEFT, padx=5)

        ttk.Separator(add_window, orient="horizontal").pack(fill=tk.X, padx=10)

        button_frame = tk.Frame(add_window, padx=10, pady=10)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # --- Scrollable area for per-season episode counts ---
        list_container = tk.Frame(add_window)
        list_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        episodes_frame = self._make_scrollable_frame(list_container)

        episode_entries = []

        def build_season_fields():
            for widget in episodes_frame.winfo_children():
                widget.destroy()
            episode_entries.clear()

            try:
                count = int(season_var.get())
                if count <= 0 or count > 57:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid input", "Please enter a valid number of seasons (1-57).")
                return

            for i in range(count):
                row = tk.Frame(episodes_frame)
                row.pack(fill=tk.X, pady=2, anchor='w')
                tk.Label(row, text=f"Season {i + 1} Episodes:", width=18, anchor='w').pack(side=tk.LEFT)
                entry = tk.Entry(row, width=8)
                entry.pack(side=tk.LEFT, padx=5)
                episode_entries.append(entry)

        # --- Save / Cancel ---

        def save_series():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Invalid input", "Please enter a series name.")
                return
            if not episode_entries:
                messagebox.showerror("Invalid input", "Please set the number of seasons first.")
                return

            episodes = []
            for i, entry in enumerate(episode_entries):
                try:
                    value = int(entry.get())
                    if value <= 0:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("Invalid input", f"Please enter a valid episode count for season {i + 1}.")
                    return
                episodes.append(value)

            series = {
                "id": uuid.uuid4().hex,
                "name": name,
                "episodes": episodes,
                "current_season": 0,
                "current_episode": 0,
            }
            # Insert at the beginning to make newest at top
            self.series_data.insert(0, series)
            self.refresh_display()
            add_window.destroy()

        tk.Button(button_frame, text="Cancel", command=add_window.destroy).pack(side=tk.RIGHT)
        tk.Button(button_frame, text="Add Series", command=save_series).pack(side=tk.RIGHT, padx=5)

        # Build the initial season fields (matches the default Spinbox value)
        build_season_fields()

    def _index_by_id(self, data_list, series_id):
        for i, s in enumerate(data_list):
            if s.get("id") == series_id:
                return i
        return -1

    def _remove_by_id(self, data_list, series_id):
        index = self._index_by_id(data_list, series_id)
        if index != -1:
            return data_list.pop(index)
        return None

    def _ensure_ids(self):
        """Backfill an id for entries loaded from older data files that predate it."""
        for series in self.series_data + self.archive_data:
            series.setdefault("id", uuid.uuid4().hex)

    def next_episode(self, index):
        series = self.filtered_data[index]
        real_index = self._index_by_id(self.series_data, series["id"])
        if real_index == -1:
            return
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
        real_index = self._index_by_id(self.series_data, series["id"])
        if real_index == -1:
            return
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
            self._remove_by_id(self.series_data, series["id"])
            self.refresh_display()

    def archive_series(self, index):
        series = self.filtered_data[index]
        self._remove_by_id(self.series_data, series["id"])
        self.archive_data.insert(0, series)  # newest archived on top
        self.refresh_display()
        self.refresh_archive_display()

    def view_archive(self):
        if self.archive_window is not None and self.archive_window.winfo_exists():
            self.archive_window.lift()
            return

        self.archive_window = self._create_child_window("Archived Series", 425, 400)
        self.archive_list_frame = self._make_scrollable_frame(self.archive_window)

        def on_close():
            self.archive_window.destroy()
            self.archive_window = None
            self.archive_list_frame = None

        self.archive_window.protocol("WM_DELETE_WINDOW", on_close)
        self.refresh_archive_display()

    def refresh_archive_display(self):
        # No-op if the archive window isn't currently open.
        if self.archive_list_frame is None or not self.archive_list_frame.winfo_exists():
            return

        for widget in self.archive_list_frame.winfo_children():
            widget.destroy()

        for series in self.archive_data:
            container = tk.Frame(self.archive_list_frame, relief=tk.RIDGE, bd=2, padx=5, pady=5)
            container.pack(fill=tk.X, padx=5, pady=5)

            tk.Label(container, text=series['name'], font=("Arial", 12)).pack(side=tk.LEFT)
            tk.Button(container, text="Retrieve", command=lambda s=series: self.retrieve_series(s)).pack(side=tk.RIGHT)
            tk.Button(container, text="Delete", command=lambda s=series: self.delete_archive_series(s)).pack(side=tk.RIGHT, padx=5)

    def retrieve_series(self, series):
        self._remove_by_id(self.archive_data, series["id"])
        self.series_data.append(series)
        self.refresh_display()
        self.refresh_archive_display()

    def delete_archive_series(self, series):
        if messagebox.askyesno("Delete Archive", f"Delete '{series['name']}'?"):
            self._remove_by_id(self.archive_data, series["id"])
            self.refresh_archive_display()

    def refresh_display(self):
        for widget in self.frame.winfo_children():
            widget.destroy()

        self.completed_labels = []
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
            title_row = tk.Frame(container)
            title_row.pack(side=tk.TOP, anchor='w')

            tk.Label(title_row, text=f"{name} - ", font=("Arial", 12, "bold")).pack(side=tk.LEFT)

            if progress_text == "Completed":
                status_holder = tk.Frame(title_row)
                status_holder.pack(side=tk.LEFT)

                status_label = tk.Label(status_holder, text=progress_text, font=("Arial", 12, "bold"))
                status_label.place(x=0, y=0)

                status_holder.update_idletasks()
                status_holder.config(
                    width=status_label.winfo_reqwidth() + 2,
                    height=status_label.winfo_reqheight() + 2,
                )

                self.completed_labels.append(status_label)
            else:
                tk.Label(title_row, text=progress_text, font=("Arial", 12, "bold")).pack(side=tk.LEFT)

            progress_bar = tk.Canvas(container, width=225, height=12, bg="#929292")
            progress_bar.pack(anchor='w', pady=5)
            progress_bar.create_rectangle(0, 0, 225 * progress, 12, fill="#3A8B63")

            button_frame = tk.Frame(container)
            button_frame.pack(anchor='w')
            tk.Button(button_frame, text="➖", command=lambda i=i: self.previous_episode(i)).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="➕", command=lambda i=i: self.next_episode(i)).pack(side=tk.LEFT)
            tk.Button(button_frame, text="Delete", command=lambda i=i: self.delete_series(i)).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="Archive", command=lambda i=i: self.archive_series(i)).pack(side=tk.LEFT)

    def search_series(self, *args):
        self.refresh_display()

    def _start_rainbow_animation(self):
        self._rainbow_hue = 0.0
        self._animate_rainbow()

    def _animate_rainbow(self):
        self._rainbow_hue = (self._rainbow_hue + 0.01) % 1.0 #Speed
        # Drop references to labels that got destroyed by a refresh in the meantime.
        self.completed_labels = [lbl for lbl in self.completed_labels if lbl.winfo_exists()]

        if self.rainbow_enabled:
            for i, label in enumerate(self.completed_labels):
                hue = (self._rainbow_hue + i * 0.08) % 1.0      
                r, g, b = colorsys.hsv_to_rgb(hue, 0.60, 0.85)  #Saturation, Brightness
                label.config(fg=f'#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}')

        self.root.after(50, self._animate_rainbow)

    def _make_rainbow_colors(self, n, alpha=1.0):
        """n evenly-spaced rainbow colors, faded toward the toolbar background by alpha (0-1)."""
        bg_r, bg_g, bg_b = (c / 256 for c in self.root.winfo_rgb(self._toggle_bg_hex))
        colors = []
        for i in range(n):
            r, g, b = colorsys.hsv_to_rgb(i / n, 0.75, 0.9)
            r, g, b = r * 255, g * 255, b * 255
            r = alpha * r + (1 - alpha) * bg_r
            g = alpha * g + (1 - alpha) * bg_g
            b = alpha * b + (1 - alpha) * bg_b
            colors.append(f'#{int(r):02x}{int(g):02x}{int(b):02x}')
        return colors

    def _draw_rainbow_toggle(self):
        canvas = self.rainbow_toggle_canvas
        canvas.delete("all")
        n = 12
        alpha = 1.0 if self.rainbow_enabled else 0.35  # faded = "slightly transparent" look
        colors = self._make_rainbow_colors(n, alpha=alpha)
        cx, cy, r = 10, 10, 9
        for i, color in enumerate(colors):
            canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=i * (360 / n), extent=360 / n,
                fill=color, outline=color,
            )

    def toggle_rainbow_effect(self):
        self.rainbow_enabled = not self.rainbow_enabled
        self._draw_rainbow_toggle()
        if not self.rainbow_enabled:
            # Immediately reset any currently rainbow-colored labels back to normal.
            for label in self.completed_labels:
                if label.winfo_exists():
                    label.config(fg=self._default_label_fg)

    def _write_to_path(self, path, include_settings=False):
        payload = {"series": self.series_data, "archive": self.archive_data}
        if include_settings:
            payload["settings"] = {"rainbow_enabled": self.rainbow_enabled}
        with open(path, 'w') as f:
            json.dump(payload, f, indent=4)

    def _load_from_path(self, path, load_settings=False):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            messagebox.showerror("Load Error", f"Could not load '{path}':\n{e}")
            return False

        self.series_data = data.get("series", [])
        self.archive_data = data.get("archive", [])
        self._ensure_ids()

        if load_settings:
            self.rainbow_enabled = data.get("settings", {}).get("rainbow_enabled", False)
            self._draw_rainbow_toggle()

        self.refresh_display()
        self.refresh_archive_display()
        return True

    def load_data(self):
        if os.path.exists(DATA_FILENAME):
            self._load_from_path(DATA_FILENAME, load_settings=True)

    def save_data(self):
        self._write_to_path(DATA_FILENAME, include_settings=True)

    def save_as(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if file_path:
            self._write_to_path(file_path) 

    def load_from_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if file_path and messagebox.askyesno("Load Data", "This will overwrite current data. Continue?"):
            self._load_from_path(file_path)

    def on_close(self):
        self.save_data()
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()
    app = SeriesTrackerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.deiconify()
    root.mainloop()