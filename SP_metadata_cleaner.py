import os
import shutil
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import piexif

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv")

class MetadataRemoverApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Photo & Video Metadata Remover")
        self.root.geometry("360x380")
        
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
        
        self.select_button = tk.Button(root, text="Select File(s)", command=self.select_files)
        self.select_button.pack(pady=5)
        
        self.open_dir_button = tk.Button(root, text="Open Directory", command=self.open_directory, state=tk.DISABLED)
        self.open_dir_button.pack(pady=5)
        
        self.grid_frame = tk.Frame(root)
        self.grid_frame.pack()
        
        self.delete_button = tk.Button(root, text="Delete Metadata", command=self.confirm_delete, state=tk.DISABLED)
        self.delete_button.pack(pady=5)

    def find_ffmpeg(self):
        # 1. Try PATH
        try:
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "ffmpeg"
        except FileNotFoundError:
            pass

        # 2. Common Windows locations
        common_paths = [
            r"C:\\ffmpeg\\bin\\ffmpeg.exe",
            r"C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
            r"C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe",
            os.path.expanduser(r"~\\Downloads\\ffmpeg\\bin\\ffmpeg.exe"),
        ]

        for path in common_paths:
            if os.path.exists(path):
                return path

        return None

    def select_files(self):
        self.file_paths = list(filedialog.askopenfilenames())
        if not self.file_paths:
            return
        
        self.display_images()
        self.open_dir_button.config(state=tk.NORMAL)
        self.delete_button.config(state=tk.NORMAL)

    def open_directory(self):
        if self.file_paths:
            folder = os.path.dirname(self.file_paths[0])
            os.startfile(folder)

    def display_images(self):
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        max_columns = 3
        for idx, file_path in enumerate(self.file_paths):
            ext = os.path.splitext(file_path)[1].lower()
            filename = os.path.basename(file_path)

            container = tk.Frame(self.grid_frame)

            if ext in IMAGE_EXTENSIONS:
                try:
                    img = Image.open(file_path)
                    img.thumbnail((100, 100))
                    img = ImageTk.PhotoImage(img)
                    img_label = tk.Label(container, image=img)
                    img_label.image = img
                except:
                    img_label = tk.Label(container, text="Image Error")
            else:
                img_label = tk.Label(container, text="VIDEO", width=12, height=6, bg="gray")

            name_label = tk.Label(container, text=filename, wraplength=100)

            img_label.pack()
            name_label.pack()

            container.grid(row=idx // max_columns, column=idx % max_columns, padx=5, pady=5)

    def confirm_delete(self):
        if messagebox.askyesno("Confirm", "Delete ALL metadata from selected files?"):
            self.delete_metadata()

    def delete_metadata(self):
        for file_path in self.file_paths:
            ext = os.path.splitext(file_path)[1].lower()
            try:
                if ext in IMAGE_EXTENSIONS:
                    self.clean_image(file_path)
                elif ext in VIDEO_EXTENSIONS:
                    if self.ffmpeg_available:
                        self.clean_video(file_path)
                    else:
                        messagebox.showwarning("Skipped", f"Skipping video (FFmpeg missing):\n{file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed: {file_path}\n{e}")

        messagebox.showinfo("Success", "Metadata removed from all possible files!")

    def clean_image(self, file_path):
        img = Image.open(file_path)
        data = list(img.getdata())
        clean_img = Image.new(img.mode, img.size)
        clean_img.putdata(data)

        temp_file = file_path + "_clean.jpg"
        clean_img.save(temp_file)
        img.close()

        os.remove(file_path)
        shutil.move(temp_file, file_path)

    def clean_video(self, file_path):
        temp_file = file_path + "_clean.mp4"

        command = [
            self.ffmpeg_path,
            "-i", file_path,
            "-map_metadata", "-1",
            "-c:v", "copy",
            "-c:a", "copy",
            temp_file
        ]

        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        os.remove(file_path)
        os.rename(temp_file, file_path)

if __name__ == "__main__":
    root = tk.Tk()
    app = MetadataRemoverApp(root)
    root.mainloop()
