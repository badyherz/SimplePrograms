import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk

class GIFtoPNGConverter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GIF to PNG Converter")
        self.geometry("310x200")

        self.gif_path = None
        self.png_dir = None

        self.gif_label = tk.Label(self, text="No GIF selected")
        self.gif_label.pack()

        self.gif_button = tk.Button(self, text="Select GIF", command=self.select_gif)
        self.gif_button.pack()

        self.dir_label = tk.Label(self, text="No directory selected")
        self.dir_label.pack()

        self.dir_button = tk.Button(self, text="Select Directory", command=self.select_directory)
        self.dir_button.pack()

        self.convert_button = tk.Button(self, text="Convert to PNG", command=self.convert_to_png)
        self.convert_button.pack()

    def select_gif(self):
        self.gif_path = filedialog.askopenfilename(filetypes=[("GIF files", "*.gif")])
        if self.gif_path:
            self.gif_label.config(text=f"Selected GIF: {self.gif_path}")
            self.show_gif_preview()

    def show_gif_preview(self):
        gif_img = Image.open(self.gif_path)
        gif_img.thumbnail((100, 100))  # Adjust the size as needed
        gif_preview = ImageTk.PhotoImage(gif_img)
        if hasattr(self, 'preview_label'):
            self.preview_label.config(image=gif_preview)
            self.preview_label.image = gif_preview
        else:
            self.preview_label = tk.Label(self, image=gif_preview)
            self.preview_label.image = gif_preview
            self.preview_label.pack()

    def select_directory(self):
        self.png_dir = filedialog.askdirectory()
        if self.png_dir:
            self.dir_label.config(text=f"Selected directory: {self.png_dir}")

    def convert_to_png(self):
        if self.gif_path and self.png_dir:
            gif_img = Image.open(self.gif_path)
            gif_img.seek(0)
            frame_num = 0
            while True:
                try:
                    gif_img.seek(frame_num)
                    frame_num += 1
                    gif_img.save(f"{self.png_dir}/frame_{frame_num}.png")
                except EOFError:
                    break
            print("Conversion completed!")
        else:
            print("Please select a GIF and a directory.")

if __name__ == "__main__":
    app = GIFtoPNGConverter()
    app.mainloop()
