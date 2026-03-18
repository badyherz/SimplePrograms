import tkinter as tk
import tkinter.font as tkFont
from tkinter import messagebox
from difflib import SequenceMatcher
    
def compare_texts():
    text1 = text_field1.get("1.0", tk.END).strip()
    text2 = text_field2.get("1.0", tk.END).strip()
    
    # Clear existing highlights
    text_field1.tag_remove("diff", "1.0", tk.END)
    text_field2.tag_remove("diff", "1.0", tk.END)
    
    if text1 == text2:
        messagebox.showinfo("Result", "No difference found")
        return

    matcher = SequenceMatcher(None, text1, text2)
    match_blocks = matcher.get_matching_blocks()

    last_end1 = 0
    last_end2 = 0

    for match in match_blocks:
        start1, start2, length = match
        
        if start1 > last_end1:
            text_field1.tag_add("diff", f"1.0 + {last_end1} chars", f"1.0 + {start1} chars")
        
        if start2 > last_end2:
            text_field2.tag_add("diff", f"1.0 + {last_end2} chars", f"1.0 + {start2} chars")
        
        last_end1 = start1 + length
        last_end2 = start2 + length

    if last_end1 < len(text1):
        text_field1.tag_add("diff", f"1.0 + {last_end1} chars", tk.END)
    if last_end2 < len(text2):
        text_field2.tag_add("diff", f"1.0 + {last_end2} chars", tk.END)

def clear_texts():
    text_field1.delete("1.0", tk.END)
    text_field2.delete("1.0", tk.END)
    text_field1.tag_remove("diff", "1.0", tk.END)
    text_field2.tag_remove("diff", "1.0", tk.END)

def create_gui():
    window = tk.Tk()
    window.title("Text Comparator")
    window.geometry("400x450")  # Optional starting size

    # Make grid expandable
    window.grid_rowconfigure(1, weight=1)
    window.grid_rowconfigure(3, weight=1)
    window.grid_columnconfigure(0, weight=1)

    # Font Definition
    bold_font = tkFont.Font(family="Arial", size=10, weight="bold")

    # Section 1 Label
    tk.Label(window, text="Section 1:", font=bold_font).grid(row=0, column=0, sticky="w", padx=5, pady=5)

    global text_field1
    text_field1 = tk.Text(window)
    text_field1.grid(row=1, column=0, sticky="nsew", padx=5)

    # Section 2 Label
    tk.Label(window, text="Section 2:", font=bold_font).grid(row=2, column=0, sticky="w", padx=5, pady=5)


    global text_field2
    text_field2 = tk.Text(window)
    text_field2.grid(row=3, column=0, sticky="nsew", padx=5)

    # Button frame
    button_frame = tk.Frame(window)
    button_frame.grid(row=4, column=0, pady=10)

    compare_button = tk.Button(button_frame, text="Compare", command=compare_texts)
    compare_button.pack(side=tk.LEFT, padx=5)

    clear_button = tk.Button(button_frame, text="Clear", command=clear_texts)
    clear_button.pack(side=tk.LEFT, padx=5)

    # Highlight style
    text_field1.tag_config("diff", background="yellow", foreground="red")
    text_field2.tag_config("diff", background="yellow", foreground="red")

    window.mainloop()

create_gui()
