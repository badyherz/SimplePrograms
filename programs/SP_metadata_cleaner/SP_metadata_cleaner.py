import os
import shutil
import subprocess
import tkinter as tk
import tkinter.font as tkFont
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageOps, ImageSequence

from SP_footer_picture import add_footer
from SP_window_utils import center_window

# Optional HEIC/HEIF support - only enabled if the "pillow-heif" package is
# installed, since Pillow does not support this format out of the box.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:
    HEIF_SUPPORTED = False

DOCUMENTS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "SimplePrograms", "Metadata Remover")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".jfif", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp")
if HEIF_SUPPORTED:
    IMAGE_EXTENSIONS += (".heic", ".heif")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv")
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS

WINDOW_BACKGROUND_COLOR = "#E6E6E6"
GROUP_BORDER_COLOR = "#A7A7A7"
BOX_BORDER_THICKNESS = 0.5
BOX_INTERNAL_PADDING = 4
BOX_EXTERNAL_PADDING = 10
BUTTON_WIDTH = 20

PREVIEW_THUMBNAIL_SIZE = (140, 140)   # actual image thumbnail max width/height, in pixels
PREVIEW_PLACEHOLDER_SIZE = (18, 8) 
PREVIEW_COLUMNS = 3

def open_folder(path):
    """Open a folder in the OS file explorer (Windows/macOS/Linux)."""
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
        candidate = os.path.join(directory, f"{base} ({counter}){ext}")
        counter += 1
    return candidate

class MetadataRemoverApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Photo & Video Metadata Remover")
        self.root.geometry("740x420")
        self.root.minsize(740, 420)
        add_footer(root, image_path="footer.png")
        if WINDOW_BACKGROUND_COLOR:
            root.configure(bg=WINDOW_BACKGROUND_COLOR)
        center_window(self.root)
        
        self.file_paths = []
        self.ffmpeg_path = self.find_ffmpeg()
        self.ffmpeg_available = self.ffmpeg_path is not None

        if not self.ffmpeg_available:
            messagebox.showwarning(
                "FFmpeg Not Found",
                "FFmpeg is not installed or not found.\n\n"
                "Video metadata removal will NOT work.\n\n"
                "Download FFmpeg from:\nhttps://ffmpeg.org/download.html\n\n"
                "After installing, restart this program."
            )

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

        button_font= tkFont.Font(family="Arial",size=9,weight="bold")

        # Box 1: source selection
        source_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        source_box.pack(fill="x", anchor="nw")

        self.select_button = tk.Button(
            source_box, text="Select File(s)", width=BUTTON_WIDTH, command=self.select_files
        )
        self.select_button.pack(padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 5))

        self.open_source_dir_button = tk.Button(
            source_box, text="Open Source Directory", width=BUTTON_WIDTH,
            command=self.open_source_directory, state=tk.DISABLED,
        )
        self.open_source_dir_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        # Spacer / divider between the two boxes
        tk.Frame(left_panel, bg=GROUP_BORDER_COLOR, height=2).pack(fill="x", pady=10)

        # Box 2: processing controls
        action_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        action_box.pack(fill="x", anchor="nw")

        self.delete_button = tk.Button(
            action_box, text="Delete Metadata",font=button_font, fg="#C55E5E", width=BUTTON_WIDTH,
            command=self.confirm_delete, state=tk.DISABLED,
        )
        self.delete_button.pack(padx=BOX_INTERNAL_PADDING, pady=(BOX_INTERNAL_PADDING, 5))

        self.open_output_dir_button = tk.Button(
            action_box, text="Open Output Directory", width=BUTTON_WIDTH,
            command=self.open_output_directory,
        )
        self.open_output_dir_button.pack(padx=BOX_INTERNAL_PADDING, pady=(0, BOX_INTERNAL_PADDING))

        # Vertical divider between the control panel and the preview panel
        tk.Frame(main_frame, bg=GROUP_BORDER_COLOR, width=2).pack(side="left", fill="y", padx=10)

        # --- Right panel: scrollable preview grid ---------------------------
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

    def find_ffmpeg(self):
        run_kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        # 1. Try PATH
        try:
            subprocess.run(["ffmpeg", "-version"], **run_kwargs)
            return "ffmpeg"
        except (FileNotFoundError, OSError):
            pass

        # 2. Common Windows locations
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            os.path.expanduser(r"~\Downloads\ffmpeg\bin\ffmpeg.exe"),
        ]

        for path in common_paths:
            if os.path.exists(path):
                return path

        return None

    def select_files(self):
        filetypes = [
            ("Supported files", " ".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)),
            ("Image files", " ".join(f"*{ext}" for ext in IMAGE_EXTENSIONS)),
            ("Video files", " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)),
            ("All files", "*.*"),
        ]
        selected = filedialog.askopenfilenames(filetypes=filetypes)
        if not selected:
            return

        self.file_paths = list(selected)
        self.display_previews()
        self.open_source_dir_button.config(state=tk.NORMAL)
        self.delete_button.config(state=tk.NORMAL)

    def open_source_directory(self):
        if self.file_paths:
            open_folder(os.path.dirname(self.file_paths[0]))

    def open_output_directory(self):
        open_folder(DOCUMENTS_DIR)

    def display_previews(self):
        for widget in self.preview_grid.winfo_children():
            widget.destroy()

        for idx, file_path in enumerate(self.file_paths):
            item = self._build_preview_item(self.preview_grid, file_path)
            row, col = divmod(idx, PREVIEW_COLUMNS)
            item.grid(row=row, column=col, padx=6, pady=6, sticky="n")

        self.preview_canvas.update_idletasks()
        self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))

    def _build_preview_item(self, parent, file_path):
        ext = os.path.splitext(file_path)[1].lower()
        name_without_ext = os.path.splitext(os.path.basename(file_path))[0]

        item = tk.Frame(parent, bg=WINDOW_BACKGROUND_COLOR, bd=1, relief="groove", padx=6, pady=6)

        if ext in IMAGE_EXTENSIONS:
            try:
                with Image.open(file_path) as img:
                    thumb = ImageOps.exif_transpose(img)
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
        else:
            preview_label = tk.Label(
                item, text="\u25b6 VIDEO", bg="#555555", fg="white",
                width=PREVIEW_PLACEHOLDER_SIZE[0], height=PREVIEW_PLACEHOLDER_SIZE[1],
            )

        name_label = tk.Label(
            item, text=name_without_ext, wraplength=PREVIEW_THUMBNAIL_SIZE[0],
            bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 8, "bold"),
        )
        ext_label = tk.Label(
            item, text=ext.upper().lstrip("."), bg=WINDOW_BACKGROUND_COLOR,
            fg="#666666", font=("Segoe UI", 7),
        )

        preview_label.pack()
        name_label.pack()
        ext_label.pack()

        return item

    def _on_mousewheel(self, event):
        self.preview_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def confirm_delete(self):
        if not self.file_paths:
            return
        if messagebox.askyesno(
            "Confirm",
            "This will create cleaned copies of the selected file(s), with all "
            "metadata removed, and save them to:\n"
            f"{DOCUMENTS_DIR}\n\n"
            "The original files will not be modified. Continue?",
        ):
            self.delete_metadata()

    def delete_metadata(self):
        total_files = len(self.file_paths)
        if total_files == 0:
            return

        self.progress_bar.configure(maximum=total_files, value=0)
        self.progress_label.configure(text=f"0 / {total_files}")
        self.select_button.configure(state=tk.DISABLED)
        self.delete_button.configure(state=tk.DISABLED)

        succeeded = []
        failed = []

        for index, file_path in enumerate(self.file_paths, start=1):
            filename = os.path.basename(file_path)
            ext = os.path.splitext(file_path)[1].lower()

            try:
                if ext in IMAGE_EXTENSIONS:
                    self.clean_image(file_path, DOCUMENTS_DIR)
                    succeeded.append(filename)
                elif ext in VIDEO_EXTENSIONS:
                    if self.ffmpeg_available:
                        self.clean_video(file_path, DOCUMENTS_DIR)
                        succeeded.append(filename)
                    else:
                        failed.append((filename, "FFmpeg is not available"))
                else:
                    failed.append((filename, "Unsupported file type"))
            except Exception as e:
                failed.append((filename, str(e)))

            self.progress_bar.configure(value=index)
            self.progress_label.configure(text=f"{index} / {total_files}")
            self.root.update_idletasks()

        self.select_button.configure(state=tk.NORMAL)
        self.delete_button.configure(state=tk.NORMAL)

        self.show_summary(succeeded, failed)

        if succeeded:
            self.open_output_directory()

    def show_summary(self, succeeded, failed):
        if not failed:
            messagebox.showinfo(
                "Success",
                f"Metadata removed successfully from all {len(succeeded)} file(s).\n"
                f"Clean copies were saved to:\n{DOCUMENTS_DIR}",
            )
            return

        details = "\n".join(f"- {name}: {reason}" for name, reason in failed)
        messagebox.showwarning(
            "Completed with errors",
            f"{len(succeeded)} of {len(succeeded) + len(failed)} file(s) were processed successfully.\n\n"
            f"The following file(s) could not be processed:\n{details}",
        )

    # --- image logic ---
    def clean_image(self, file_path, dest_dir):
        """Create a metadata-free copy of an image inside dest_dir."""
        filename = os.path.basename(file_path)
        dest_path = get_unique_destination_path(dest_dir, filename)

        with Image.open(file_path) as original:
            image_format = original.format
            if not image_format:
                ext_upper = os.path.splitext(filename)[1][1:].upper()
                image_format = "JPEG" if ext_upper in ("JPG", "JPEG") else ext_upper

            frame_count = getattr(original, "n_frames", 1)

            if frame_count > 1:
                # Multi-frame image (e.g. animated GIF/WEBP): rebuild every
                # frame individually so the animation is preserved while
                # metadata is stripped from each frame.
                clean_frames = []
                durations = []
                for frame in ImageSequence.Iterator(original):
                    clean_frames.append(self._strip_frame_metadata(frame))
                    durations.append(frame.info.get("duration", 100))

                clean_frames[0].save(
                    dest_path,
                    format=image_format,
                    save_all=True,
                    append_images=clean_frames[1:],
                    loop=original.info.get("loop", 0),
                    duration=durations,
                )
            else:
                # Single-frame image: bake in the EXIF orientation before
                # stripping metadata.
                oriented = ImageOps.exif_transpose(original)
                clean_frame = self._strip_frame_metadata(oriented)

                save_kwargs = {"format": image_format}
                if image_format == "JPEG":
                    save_kwargs["quality"] = 98
                clean_frame.save(dest_path, **save_kwargs)

        return dest_path

    @staticmethod
    def _strip_frame_metadata(frame):
        """Return a copy of a single frame with no metadata, preserving its
        palette so indexed-color images (GIF, some PNGs) keep the right
        colors instead of turning black/garbled."""
        clean_frame = Image.new(frame.mode, frame.size)
        if frame.mode == "P":
            palette = frame.getpalette()
            if palette:
                clean_frame.putpalette(palette)
        clean_frame.putdata(list(frame.getdata()))
        return clean_frame

    # --- video logic ---
    def clean_video(self, file_path, dest_dir):
        """Create a metadata-free copy of a video inside dest_dir."""
        filename = os.path.basename(file_path)
        dest_path = get_unique_destination_path(dest_dir, filename)

        command = [
            self.ffmpeg_path,
            "-y",
            "-i", file_path,
            "-map_metadata", "-1",
            "-c:v", "copy",
            "-c:a", "copy",
            dest_path,
        ]

        run_kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        if os.name == "nt":
            run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(command, **run_kwargs)

        if result.returncode != 0 or not os.path.exists(dest_path):
            if os.path.exists(dest_path):
                os.remove(dest_path)
            stderr_text = result.stderr.decode(errors="ignore").strip()
            last_line = stderr_text.splitlines()[-1] if stderr_text else "FFmpeg failed for an unknown reason"
            raise RuntimeError(last_line)

        return dest_path

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    app = MetadataRemoverApp(root)
    root.deiconify()
    root.mainloop()