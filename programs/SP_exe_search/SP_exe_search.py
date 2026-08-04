import os
import tkinter as tk
from tkinter import filedialog, ttk

def browse_folder():
    global folder_path
    folder_path = filedialog.askdirectory()
    if folder_path:
        selected_directory_label.config(text="Selected directory: " + folder_path)
        search_button.config(state='normal')

def search_exe():
    results.delete(0, tk.END)
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".exe"):
                results.insert(tk.END, os.path.join(root, file))

def open_directory(event):
    selected_item = results.get(results.curselection())
    directory = os.path.dirname(selected_item)
    os.startfile(directory)

def sort_results():
    sort_type = sort_combobox.get()
    if sort_type == "Name (A-Z)":
        results_list = sorted(results.get(0, tk.END))
    elif sort_type == "Name (Z-A)":
        results_list = sorted(results.get(0, tk.END), reverse=True)
    elif sort_type == "Date (Newest)":
        results_list = sorted(results.get(0, tk.END), key=lambda x: os.path.getctime(x), reverse=True)
    elif sort_type == "Date (Oldest)":
        results_list = sorted(results.get(0, tk.END), key=lambda x: os.path.getctime(x))
    elif sort_type == "Size (Smallest)":
        results_list = sorted(results.get(0, tk.END), key=lambda x: os.path.getsize(x))
    elif sort_type == "Size (Largest)":
        results_list = sorted(results.get(0, tk.END), key=lambda x: os.path.getsize(x), reverse=True)
    else:
        return
    results.delete(0, tk.END)
    for result in results_list:
        results.insert(tk.END, result)

# ------------------- GUI Setup -------------------
root = tk.Tk()
root.title(".EXE File Search")
root.geometry("800x500")
root.minsize(600, 400)

# Frames
left_frame = tk.Frame(root)
left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)  # Only vertical stretch, buttons stay left

right_frame = tk.Frame(root)
right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)  # Listbox stretches

# Left Frame Widgets (anchored top-left)
folder_label = tk.Label(left_frame, text="Select a folder to search for .exe files:")
folder_label.pack(pady=10, anchor="nw")

folder_button = tk.Button(left_frame, text="Browse", command=browse_folder)
folder_button.pack(pady=10, anchor="nw")

search_button = tk.Button(left_frame, text="Search", command=search_exe, state='disabled')
search_button.pack(pady=10, anchor="nw")

sort_options = ["Name (A-Z)", "Name (Z-A)", "Date (Newest)", "Date (Oldest)", "Size (Smallest)", "Size (Largest)"]
sort_combobox = ttk.Combobox(left_frame, values=sort_options, state="readonly")
sort_combobox.pack(pady=10, anchor="nw")
sort_combobox.current(0)

sort_button = tk.Button(left_frame, text="Sort", command=sort_results)
sort_button.pack(pady=10, anchor="nw")

# Right Frame Widgets
selected_directory_label = tk.Label(right_frame, text="")
selected_directory_label.pack(padx=10, pady=10, anchor="w")

# Scrollbars
v_scrollbar = tk.Scrollbar(right_frame, orient=tk.VERTICAL)
v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

h_scrollbar = tk.Scrollbar(right_frame, orient=tk.HORIZONTAL)
h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

# Listbox
results = tk.Listbox(
    right_frame,
    yscrollcommand=v_scrollbar.set,
    xscrollcommand=h_scrollbar.set,
    width=70,
    height=20
)
results.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

v_scrollbar.config(command=results.yview)
h_scrollbar.config(command=results.xview)

# Open folder on double-click
results.bind("<Double-Button-1>", open_directory)

# Horizontal scrolling with Shift + Mouse Wheel
def on_mouse_wheel(event):
    if event.state & 0x1:  # Shift key held
        results.xview_scroll(int(-1*(event.delta/120)), "units")
    else:
        results.yview_scroll(int(-1*(event.delta/120)), "units")

results.bind("<MouseWheel>", on_mouse_wheel)

root.mainloop()
