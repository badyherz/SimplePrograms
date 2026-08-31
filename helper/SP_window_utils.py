"""
#Placing the code:

    import tkinter as tk
    from SP_window_utils import center_window

    window = tk.Tk()
    window.withdraw()
    # ... build widgets, set geometry ...
    center_window(window, width, height)
    window.deiconify()
    
    window.mainloop()
"""


def center_window(window, width=None, height=None):
    
    window.update_idletasks()

    width = width if width is not None else window.winfo_width()
    height = height if height is not None else window.winfo_height()

    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()

    x = (screen_width - width) // 2
    y = (screen_height - height) // 2

    window.geometry(f"{width}x{height}+{x}+{y}")
    