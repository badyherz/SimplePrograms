import os
import re
import shutil
import subprocess
import math
import tkinter as tk
import tkinter.font as tkFont
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageSequence
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from helper.SP_footer_picture import add_footer
from helper.SP_window_utils import center_window

WINDOW_BACKGROUND_COLOR = "#E6E6E6"
GROUP_BORDER_COLOR = "#A7A7A7"
BOX_BORDER_THICKNESS = 0.5
BOX_INTERNAL_PADDING = 4
BOX_EXTERNAL_PADDING = 10
BUTTON_WIDTH = 20
LABEL_WRAP_LENGTH = 150

PREVIEW_THUMBNAIL_SIZE = (140, 140)   # actual thumbnail max width/height, in pixels
PREVIEW_PLACEHOLDER_SIZE = (18, 8)
PREVIEW_COLUMNS = 3

FRAME_NUMBER_PATTERN = re.compile(r"(\d+)")
DEFAULT_FRAME_DURATION_MS = 100
DEFAULT_LOOP_COUNT = 0  # 0 = loop forever
GIF_DELAY_STEP_MS = 10  # the GIF Graphic Control Extension stores each frame's
                        # delay in hundredths of a second - 10 ms is the smallest
                        # time step a GIF file can actually represent


# --- helpers ---
def open_folder(path):
    if os.name == "nt":
        os.startfile(path)
    elif shutil.which("open"):
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])

def get_unique_destination_path(directory, filename):
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{base}_{counter}{ext}")
        counter += 1
    return candidate

def get_unique_directory_path(parent_dir, folder_name):
    candidate = os.path.join(parent_dir, folder_name)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(parent_dir, f"{folder_name}_{counter}")
        counter += 1
    return candidate

def extract_frame_number(filename):
    """Return the last number found in a filename, e.g. 42 for
    'myclip_frame_42.png'. Used to sort frames in true ascending order so
    that 'frame_10' correctly sorts after 'frame_2' instead of before it."""
    matches = FRAME_NUMBER_PATTERN.findall(filename)
    return int(matches[-1]) if matches else None

def parse_duration_ms(raw_text):
    """Parse a frame-duration string into a positive float number of
    milliseconds. Accepts a comma or a dot as the decimal separator (e.g.
    "0,5", "0.444", "0.001"). The value returned here is not yet what ends
    up in a GIF file - see quantize_duration_to_gif_ms() for that. Raises
    ValueError if the text isn't a valid positive number."""
    normalized = raw_text.strip().replace(",", ".")
    value = float(normalized)
    if value <= 0:
        raise ValueError("Duration must be greater than zero.")
    return value

# --- GIF duration quantization ---
def quantize_duration_to_gif_ms(duration_ms):
    """Round a requested per-frame duration to the nearest multiple of
    GIF_DELAY_STEP_MS (10 ms), since that's the smallest unit a GIF file can
    actually store - any finer input (e.g. "0.5" or "0.001") cannot survive
    being written to the file. Any positive input is floored to at least one
    step, so a frame never collapses to an undefined 0ms delay, which
    different GIF viewers handle inconsistently.

    Both the live preview and the exported file are driven by this same
    function, so the preview always plays at the speed the exported GIF
    actually will."""
    steps = max(math.floor(duration_ms / GIF_DELAY_STEP_MS + 0.5), 1)
    return steps * GIF_DELAY_STEP_MS


class GIFtoPNGConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("GIF to PNG Converter")
        self.root.geometry("740x500")
        self.root.minsize(740, 500)
        add_footer(self.root, image_path="assets/footer.png")
        if WINDOW_BACKGROUND_COLOR:
            self.root.configure(bg=WINDOW_BACKGROUND_COLOR)
        center_window(self.root)

        self.gif_path = None
        self.png_dir = None
        self.last_export_dir = None

        self.frame_paths = []

        # --- Bottom progress bar ---
        # Packed before the main content area so it reliably reserves its
        # strip at the bottom of the window
        bottom_frame = tk.Frame(root, bg=WINDOW_BACKGROUND_COLOR)
        bottom_frame.pack(side="bottom", fill="x", padx=BOX_EXTERNAL_PADDING, pady=(0, BOX_EXTERNAL_PADDING))

        progress_style = ttk.Style(root)
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

        self.progress_label = tk.Label(bottom_frame, text="", bg=WINDOW_BACKGROUND_COLOR, width=8)
        self.progress_label.pack(side="left", padx=(8, 0))

        # --- Main content: left control panel + right preview panel ---
        main_frame = tk.Frame(root, bg=WINDOW_BACKGROUND_COLOR)
        main_frame.pack(fill="both", expand=True, padx=BOX_EXTERNAL_PADDING, pady=BOX_EXTERNAL_PADDING)

        left_panel = tk.Frame(main_frame, bg=WINDOW_BACKGROUND_COLOR)
        left_panel.pack(side="left", fill="y", anchor="n")

        button_font = tkFont.Font(family="Arial", size=9, weight="bold")

        # --- Selection box: choosing/opening the GIF, output folder and frame folder ---
        selection_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        selection_box.pack(fill="x", anchor="nw")

        self.gif_button = tk.Button(
            selection_box, text="Select GIF", width=BUTTON_WIDTH, command=self.select_gif
        )
        self.gif_button.pack(padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 2))

        self.gif_label = tk.Label(
            selection_box, text="No GIF selected", bg=WINDOW_BACKGROUND_COLOR,
            font=("Segoe UI", 8), wraplength=LABEL_WRAP_LENGTH,
        )
        self.gif_label.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 8))

        self.dir_button = tk.Button(
            selection_box, text="Select Directory", width=BUTTON_WIDTH, command=self.select_directory
        )
        self.dir_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 2))

        self.dir_label = tk.Label(
            selection_box, text="No directory selected", bg=WINDOW_BACKGROUND_COLOR,
            font=("Segoe UI", 8), wraplength=LABEL_WRAP_LENGTH,
        )
        self.dir_label.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 5))

        self.open_dir_button = tk.Button(
            selection_box, text="Open Directory", width=BUTTON_WIDTH,
            command=self.open_output_directory, state=tk.DISABLED,
        )
        self.open_dir_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

         # Thin inner divider: GIF-to-PNG selection above, PNG-to-GIF selection below
        tk.Frame(selection_box, bg=GROUP_BORDER_COLOR, height=1).pack(fill="x", padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        self.frames_button = tk.Button(
            selection_box, text="Select Frames Folder", width=BUTTON_WIDTH, command=self.select_frames_folder
        )
        self.frames_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, 2))

        self.frames_label = tk.Label(
            selection_box, text="No frames selected", bg=WINDOW_BACKGROUND_COLOR,
            font=("Segoe UI", 8), wraplength=LABEL_WRAP_LENGTH,
        )
        self.frames_label.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        # Spacer / divider between the two boxes
        tk.Frame(left_panel, bg=GROUP_BORDER_COLOR, height=2).pack(fill="x", pady=10)

        # --- Action box: run the GIF-to-PNG conversion or open the GIF creator ---
        action_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        action_box.pack(fill="x", anchor="nw")

        self.convert_button = tk.Button(
            action_box, text="Convert to PNG", font=button_font, fg="#3A8B63", width=BUTTON_WIDTH,
            command=self.convert_to_png, state=tk.DISABLED,
        )
        self.convert_button.pack(padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 5))

        tk.Frame(action_box, bg=GROUP_BORDER_COLOR, height=1).pack(fill="x", padx=BOX_INTERNAL_PADDING, pady=(0, 5))

        self.create_gif_button = tk.Button(
            action_box, text="Create GIF...", font=button_font, fg="#3A8B63", width=BUTTON_WIDTH,
            command=self.open_gif_creator, state=tk.DISABLED,
        )
        self.create_gif_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        # Vertical divider between the control panel and the preview panel
        tk.Frame(main_frame, bg=GROUP_BORDER_COLOR, width=2).pack(side="left", fill="y", padx=10)

        # --- Right panel: scrollable frame preview grid ---
        right_panel = tk.Frame(main_frame, bg=WINDOW_BACKGROUND_COLOR)
        right_panel.pack(side="left", fill="both", expand=True)

        self.preview_canvas = tk.Canvas(right_panel, bg=WINDOW_BACKGROUND_COLOR, highlightthickness=0)
        preview_scrollbar = tk.Scrollbar(right_panel, orient="vertical", command=self.preview_canvas.yview)
        self.preview_canvas.configure(yscrollcommand=preview_scrollbar.set)

        self.preview_canvas.pack(side="left", fill="both", expand=True)
        preview_scrollbar.pack(side="right", fill="y")

        self.preview_grid = tk.Frame(self.preview_canvas, bg=WINDOW_BACKGROUND_COLOR)
        self.preview_canvas.create_window((0, 0), window=self.preview_grid, anchor="nw")

        self.preview_grid.bind(
            "<Configure>",
            lambda e: self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all")),
        )
        self.preview_canvas.bind("<Enter>", lambda e: self.preview_canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.preview_canvas.bind("<Leave>", lambda e: self.preview_canvas.unbind_all("<MouseWheel>"))

    # --- selection handlers ---
    def select_gif(self):
        selected = filedialog.askopenfilename(filetypes=[("GIF files", "*.gif")])
        if not selected:
            return

        self.gif_path = selected
        self.gif_label.config(text=f"Selected GIF: {os.path.basename(self.gif_path)}")
        self.show_source_preview()
        self._update_convert_button_state()

    def select_directory(self):
        selected = filedialog.askdirectory()
        if not selected:
            return

        self.png_dir = selected
        self.last_export_dir = None  # a freshly picked directory has no export of its own yet
        self.dir_label.config(text=f"Selected directory: {self.png_dir}")
        self.open_dir_button.config(state=tk.NORMAL)
        self._update_convert_button_state()

    def select_frames_folder(self):
        selected = filedialog.askdirectory()
        if not selected:
            return

        numbered_files = []
        for filename in os.listdir(selected):
            if not filename.lower().endswith(".png"):
                continue
            number = extract_frame_number(filename)
            if number is not None:
                numbered_files.append((number, filename))

        if not numbered_files:
            messagebox.showwarning(
                "No numbered frames found",
                "This folder does not contain any PNG files with an ascending "
                "number in their filename (e.g. frame_1.png, frame_2.png, ...).",
            )
            return

        numbered_files.sort(key=lambda pair: pair[0])
        self.frame_paths = [os.path.join(selected, filename) for _, filename in numbered_files]

        self.frames_label.config(text=f"{len(self.frame_paths)} frame(s) found in:\n{selected}")
        self.create_gif_button.config(state=tk.NORMAL)
        self.display_frame_previews(self.frame_paths)

    def open_output_directory(self):
        target = self.last_export_dir or self.png_dir
        if target:
            open_folder(target)

    def _update_convert_button_state(self):
        state = tk.NORMAL if (self.gif_path and self.png_dir) else tk.DISABLED
        self.convert_button.config(state=state)

    def open_gif_creator(self):
        if self.frame_paths:
            GifCreatorWindow(self.root, self.frame_paths)

    # --- preview grid ---
    def show_source_preview(self):
        """Show the selected GIF itself in the preview grid before conversion."""
        for widget in self.preview_grid.winfo_children():
            widget.destroy()

        try:
            with Image.open(self.gif_path) as gif_img:
                thumb = gif_img.convert("RGBA")
                thumb.thumbnail(PREVIEW_THUMBNAIL_SIZE)
                photo = ImageTk.PhotoImage(thumb)
        except Exception:
            return

        item = tk.Frame(self.preview_grid, bg=WINDOW_BACKGROUND_COLOR, bd=1, relief="groove", padx=6, pady=6)

        preview_label = tk.Label(item, image=photo, bg=WINDOW_BACKGROUND_COLOR)
        preview_label.image = photo  # keep a reference so it isn't garbage collected
        preview_label.pack()

        name_label = tk.Label(
            item, text=os.path.basename(self.gif_path), wraplength=PREVIEW_THUMBNAIL_SIZE[0],
            bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 8, "bold"),
        )
        name_label.pack()

        item.grid(row=0, column=0, padx=6, pady=6, sticky="n")
        self.preview_canvas.update_idletasks()
        self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))

    def display_frame_previews(self, frame_paths):
        """Show every exported PNG frame in the preview grid after conversion."""
        for widget in self.preview_grid.winfo_children():
            widget.destroy()

        for idx, frame_path in enumerate(frame_paths):
            item = self._build_frame_preview_item(self.preview_grid, frame_path)
            row, col = divmod(idx, PREVIEW_COLUMNS)
            item.grid(row=row, column=col, padx=6, pady=6, sticky="n")

        self.preview_canvas.update_idletasks()
        self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))

    def _build_frame_preview_item(self, parent, frame_path):
        item = tk.Frame(parent, bg=WINDOW_BACKGROUND_COLOR, bd=1, relief="groove", padx=6, pady=6)

        try:
            with Image.open(frame_path) as img:
                thumb = img.copy()
                thumb.thumbnail(PREVIEW_THUMBNAIL_SIZE)
                photo = ImageTk.PhotoImage(thumb)
            preview_label = tk.Label(item, image=photo, bg=WINDOW_BACKGROUND_COLOR)
            preview_label.image = photo  # keep a reference so it isn't garbage collected
        except Exception:
            preview_label = tk.Label(
                item, text="Preview\nunavailable", bg="gray", fg="white",
                width=PREVIEW_PLACEHOLDER_SIZE[0], height=PREVIEW_PLACEHOLDER_SIZE[1],
                wraplength=PREVIEW_THUMBNAIL_SIZE[0] - 10,
            )

        name_label = tk.Label(
            item, text=os.path.basename(frame_path), wraplength=PREVIEW_THUMBNAIL_SIZE[0],
            bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 8, "bold"),
        )

        preview_label.pack()
        name_label.pack()

        return item

    def _on_mousewheel(self, event):
        self.preview_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # --- GIF-to-PNG conversion logic ---
    def convert_to_png(self):
        if not (self.gif_path and self.png_dir):
            messagebox.showwarning("Missing input", "Please select a GIF and a directory first.")
            return

        self.gif_button.config(state=tk.DISABLED)
        self.dir_button.config(state=tk.DISABLED)
        self.convert_button.config(state=tk.DISABLED)

        base_name = os.path.splitext(os.path.basename(self.gif_path))[0]
        saved_paths = []

        try:
            output_dir = get_unique_directory_path(self.png_dir, f"{base_name}_frames")
            os.makedirs(output_dir, exist_ok=True)

            with Image.open(self.gif_path) as gif_img:
                total_frames = getattr(gif_img, "n_frames", 1)
                self.progress_bar.configure(maximum=total_frames, value=0)
                self.progress_label.configure(text=f"0 / {total_frames}")

                for index, frame in enumerate(ImageSequence.Iterator(gif_img), start=1):
                    frame_path = get_unique_destination_path(output_dir, f"{base_name}_frame_{index}.png")
                    frame.convert("RGBA").save(frame_path, format="PNG")
                    saved_paths.append(frame_path)

                    self.progress_bar.configure(value=index)
                    self.progress_label.configure(text=f"{index} / {total_frames}")
                    self.root.update_idletasks()
        except Exception as e:
            messagebox.showerror("Error", f"Conversion failed:\n{e}")
        else:
            self.last_export_dir = output_dir
            self.display_frame_previews(saved_paths)
            messagebox.showinfo(
                "Success",
                f"Converted {len(saved_paths)} frame(s) to PNG.\nSaved to:\n{output_dir}",
            )
        finally:
            self.gif_button.config(state=tk.NORMAL)
            self.dir_button.config(state=tk.NORMAL)
            self.convert_button.config(state=tk.NORMAL)


class GifCreatorWindow(tk.Toplevel):

    def __init__(self, parent, frame_paths):
        super().__init__(parent)
        self.withdraw()
        self.title("Create GIF from Frames")
        self.geometry("520x520")
        self.minsize(520, 520)
        self.configure(bg=WINDOW_BACKGROUND_COLOR)
        self.transient(parent)
        self.grab_set()
        center_window(self)

        self.frame_paths = frame_paths
        self.preview_photos = []
        self.preview_index = 0
        self.preview_job = None
        self.output_dir = None

        # --- Settings ---
        settings_frame = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        settings_frame.pack(fill="x", padx=BOX_EXTERNAL_PADDING, pady=(BOX_EXTERNAL_PADDING, 5))

        tk.Label(settings_frame, text="Frame duration (ms):", bg=WINDOW_BACKGROUND_COLOR).grid(
            row=0, column=0, sticky="w"
        )
        self.duration_var = tk.StringVar(value=str(DEFAULT_FRAME_DURATION_MS))
        tk.Entry(settings_frame, textvariable=self.duration_var, width=8).grid(
            row=0, column=1, sticky="w", padx=(6, 0)
        )

        tk.Label(settings_frame, text="Loop count (0 = infinite):", bg=WINDOW_BACKGROUND_COLOR).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        self.loop_var = tk.StringVar(value=str(DEFAULT_LOOP_COUNT))
        tk.Entry(settings_frame, textvariable=self.loop_var, width=8).grid(
            row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0)
        )

        tk.Label(
            settings_frame, text=f"{len(frame_paths)} frame(s) found",
            bg=WINDOW_BACKGROUND_COLOR, fg="#666666",
        ).grid(row=0, column=2, rowspan=2, sticky="e", padx=(20, 0))
        settings_frame.grid_columnconfigure(2, weight=1)

        self.effective_duration_var = tk.StringVar()
        tk.Label(
            settings_frame, textvariable=self.effective_duration_var,
            bg=WINDOW_BACKGROUND_COLOR, fg="#666666", font=("Segoe UI", 8),
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # Keeps the hint in sync with every keystroke, so what the label
        # says always matches what the preview and export will actually do.
        self.duration_var.trace_add("write", self._update_effective_duration_label)
        self._update_effective_duration_label()

        button_font = tkFont.Font(family="Arial", size=9, weight="bold")

        # --- Preview ---
        preview_box = tk.Frame(
            self, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        preview_box.pack(fill="both", expand=True, padx=BOX_EXTERNAL_PADDING, pady=5)

        self.preview_label = tk.Label(preview_box, bg=WINDOW_BACKGROUND_COLOR, text="Loading preview...")
        self.preview_label.pack(expand=True, pady=10)

        # --- Progress ---
        progress_frame = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        progress_frame.pack(fill="x", padx=BOX_EXTERNAL_PADDING, pady=(5, 0))

        self.progress_bar = ttk.Progressbar(
            progress_frame, style="Custom.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate",
        )
        self.progress_bar.pack(fill="x")

        # --- Export controls ---
        button_row = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        button_row.pack(fill="x", padx=BOX_EXTERNAL_PADDING, pady=BOX_EXTERNAL_PADDING)

        self.export_button = tk.Button(
            button_row, text="Save GIF...", font=button_font, fg="#3A8B63", width=BUTTON_WIDTH, command=self.export_gif
        )
        self.export_button.pack(side="left")

        self.open_folder_button = tk.Button(
            button_row, text="Open Directory", width=BUTTON_WIDTH,
            command=self.open_output_folder, state=tk.DISABLED,
        )
        self.open_folder_button.pack(side="left", padx=(8, 0))

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._load_preview_frames()

        self.deiconify()

    # --- preview ---
    def _update_effective_duration_label(self, *_args):
        """Reflect the actual playback speed for the current entry text -
        the same value both the preview and the exported GIF will use."""
        try:
            duration_ms = parse_duration_ms(self.duration_var.get())
            effective_ms = quantize_duration_to_gif_ms(duration_ms)
            self.effective_duration_var.set(
                f"Decimals allowed (comma or dot) - plays back at {effective_ms} ms/frame "
                f"(GIF files only support 10ms steps)"
            )
        except ValueError:
            self.effective_duration_var.set(
                "Enter a duration greater than 0 - decimals allowed, e.g. 0.5 or 0,5"
            )

    def _load_preview_frames(self):
        for path in self.frame_paths:
            try:
                with Image.open(path) as img:
                    thumb = img.convert("RGBA")
                    thumb.thumbnail(PREVIEW_THUMBNAIL_SIZE)
                    self.preview_photos.append(ImageTk.PhotoImage(thumb))
            except Exception:
                continue

        if self.preview_photos:
            self._animate_preview()
        else:
            self.preview_label.config(text="No previewable frames", image="")

    def _animate_preview(self):
        photo = self.preview_photos[self.preview_index]
        self.preview_label.config(image=photo, text="")
        self.preview_label.image = photo  # keep a reference so it isn't garbage collected
        self.preview_index = (self.preview_index + 1) % len(self.preview_photos)

        try:
            duration_ms = parse_duration_ms(self.duration_var.get())
        except ValueError:
            duration_ms = DEFAULT_FRAME_DURATION_MS

        # Quantized to the GIF format's real 10ms resolution - the same
        # value export_gif() below will write to the file - so the preview
        # always plays at the speed the exported GIF actually will.
        preview_delay = quantize_duration_to_gif_ms(duration_ms)

        # Reading the duration fresh on every tick means a settings change
        # takes effect on the next frame without needing a manual refresh.
        self.preview_job = self.after(preview_delay, self._animate_preview)

    def _on_close(self):
        if self.preview_job is not None:
            self.after_cancel(self.preview_job)
        self.destroy()

    # --- export ---
    def export_gif(self):
        try:
            duration = parse_duration_ms(self.duration_var.get())
        except ValueError:
            messagebox.showwarning(
                "Invalid duration",
                "Please enter a duration greater than 0 (in milliseconds). "
                "Decimals are allowed, using either a comma or a dot as the "
                "separator, e.g. 0.5, 0,5 or 0.001.",
            )
            return
        # The GIF format itself can only store delays in 10ms steps, so this
        # is the value that actually ends up in the file - identical to what
        # the live preview just played and the label under the entry showed.
        effective_duration = quantize_duration_to_gif_ms(duration)

        try:
            loop_count = int(self.loop_var.get())
            if loop_count < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid loop count", "Please enter 0 (infinite) or a positive whole number.")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".gif",
            filetypes=[("GIF files", "*.gif")],
            initialfile="output.gif",
        )
        if not save_path:
            return

        self.export_button.config(state=tk.DISABLED)
        total = len(self.frame_paths)
        self.progress_bar.configure(maximum=total, value=0)

        loaded_frames = []
        try:
            for index, path in enumerate(self.frame_paths, start=1):
                with Image.open(path) as img:
                    loaded_frames.append(img.convert("RGBA"))
                self.progress_bar.configure(value=index)
                self.update_idletasks()

            loaded_frames[0].save(
                save_path,
                format="GIF",
                save_all=True,
                append_images=loaded_frames[1:],
                duration=effective_duration,
                loop=loop_count,
                disposal=2,  # restore to background between frames, avoids ghosting
            )
        except Exception as e:
            messagebox.showerror("Error", f"GIF export failed:\n{e}")
            self.export_button.config(state=tk.NORMAL)
            return

        self.output_dir = os.path.dirname(save_path)
        self.open_folder_button.config(state=tk.NORMAL)
        self.export_button.config(state=tk.NORMAL)
        messagebox.showinfo(
            "Success",
            f"GIF saved to:\n{save_path}\n\n"
            f"Frame delay: {effective_duration} ms (GIF files only support "
            f"10ms steps, so this is what your input rounds to).",
        )

    def open_output_folder(self):
        if self.output_dir:
            open_folder(self.output_dir)

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    app = GIFtoPNGConverter(root)
    root.deiconify()
    root.mainloop()