"""
#Placing the code:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "helper"))

    import tkinter as tk
    from SP_footer_picture import add_footer

    root = tk.Tk()
    root.title("Hello World")
    root.geometry("600x400")

    add_footer(root, image_path="assets/footer.png")  

#Needs do be one of the first .pack calls

    root.mainloop()
"""
import sys
import os
import tkinter as tk
from pathlib import Path

def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def add_footer(root, image_path="assets/footer.png", background=None):
    resolved_path = resource_path(image_path)
    
    if not Path(resolved_path).exists():
        raise FileNotFoundError(
            f"Picture not found: {resolved_path}"
        )

    footer = tk.Frame(root, background=background)
    footer.pack(side='bottom', fill="x")

    photo = tk.PhotoImage(file=resolved_path)

    label = tk.Label(footer, image=photo, background=background)
    label.image = photo
    label.pack(side="left", padx=(10, 4), pady=4)

    return footer

#small test window
if __name__ == "__main__":

    test_root = tk.Tk()
    test_root.title("Footer_Test")
    test_root.geometry("420x260")

    add_footer(test_root)

    content = tk.Label(test_root, text="Main window content")
    content.pack(side="top", fill="both", expand=True)

    test_root.mainloop()