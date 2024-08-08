import tkinter as tk
from tkinter import messagebox
from difflib import SequenceMatcher

def compare_texts():
    # Get the text from both sections
    text1 = text_field1.get("1.0", tk.END).strip()
    text2 = text_field2.get("1.0", tk.END).strip()
    
    # Clear existing highlights
    text_field1.tag_remove("diff", "1.0", tk.END)
    text_field2.tag_remove("diff", "1.0", tk.END)
    
    if text1 == text2:
        messagebox.showinfo("Result", "No difference found")
        return

    # Use SequenceMatcher to find matching blocks
    matcher = SequenceMatcher(None, text1, text2)
    match_blocks = matcher.get_matching_blocks()

    # Highlight differences in Section 1 and Section 2
    last_end1 = 0
    last_end2 = 0
    for match in match_blocks:
        start1, start2, length = match
        
        # Highlight the non-matching part in Section 1
        if start1 > last_end1:
            text_field1.tag_add("diff", f"1.0 + {last_end1} chars", f"1.0 + {start1} chars")
        
        # Highlight the non-matching part in Section 2
        if start2 > last_end2:
            text_field2.tag_add("diff", f"1.0 + {last_end2} chars", f"1.0 + {start2} chars")
        
        last_end1 = start1 + length
        last_end2 = start2 + length

    # Handle any trailing non-matching text after the last match
    if last_end1 < len(text1):
        text_field1.tag_add("diff", f"1.0 + {last_end1} chars", tk.END)
    if last_end2 < len(text2):
        text_field2.tag_add("diff", f"1.0 + {last_end2} chars", tk.END)

def clear_texts():
    # Clear the text fields and remove highlights
    text_field1.delete("1.0", tk.END)
    text_field2.delete("1.0", tk.END)
    text_field1.tag_remove("diff", "1.0", tk.END)
    text_field2.tag_remove("diff", "1.0", tk.END)

def create_gui():
    # Create the main window
    window = tk.Tk()
    window.title("Text Comparator")

    # Section 1
    tk.Label(window, text="Section 1:").pack()
    global text_field1
    text_field1 = tk.Text(window, height=10, width=50)
    text_field1.pack()

    # Section 2
    tk.Label(window, text="Section 2:").pack()
    global text_field2
    text_field2 = tk.Text(window, height=10, width=50)
    text_field2.pack()

    # Frame for buttons
    button_frame = tk.Frame(window)
    button_frame.pack(pady=10)

    # Compare button
    compare_button = tk.Button(button_frame, text="Compare", command=compare_texts)
    compare_button.pack(side=tk.LEFT, padx=5)

    # Clear button
    clear_button = tk.Button(button_frame, text="Clear", command=clear_texts)
    clear_button.pack(side=tk.LEFT, padx=5)

    # Define a tag for highlighting differences
    text_field1.tag_config("diff", background="yellow", foreground="red")
    text_field2.tag_config("diff", background="yellow", foreground="red")

    # Start the GUI loop
    window.mainloop()

# Run the program
create_gui()
