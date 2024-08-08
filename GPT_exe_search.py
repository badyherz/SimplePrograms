import os
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

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

root = tk.Tk()
root.title(".EXE File Search")
root.geometry("600x400")

left_frame = tk.Frame(root)
left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

folder_label = tk.Label(left_frame, text="Select a folder to search for .exe files:")
folder_label.pack(pady=10)

folder_button = tk.Button(left_frame, text="Browse", command=browse_folder)
folder_button.pack(pady=10)

search_button = tk.Button(left_frame, text="Search", command=search_exe, state='disabled')
search_button.pack(pady=10)

sort_options = ["Name (A-Z)", "Name (Z-A)", "Date (Newest)", "Date (Oldest)", "Size (Smallest)", "Size (Largest)"]
sort_combobox = ttk.Combobox(left_frame, values=sort_options)
sort_combobox.pack(pady=10)

sort_button = tk.Button(left_frame, text="Sort", command=sort_results)
sort_button.pack(pady=10)

right_frame = tk.Frame(root)
right_frame.pack(side=tk.RIGHT, fill=tk.BOTH)

selected_directory_label = tk.Label(right_frame, text="")
selected_directory_label.pack(padx=10, pady=10, anchor="w")
scrollbar = tk.Scrollbar(right_frame)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

results = tk.Listbox(right_frame, yscrollcommand=scrollbar.set, width=70, height=20)
results.pack(padx=10, pady=10)

scrollbar.config(command=results.yview)

results.bind("<Double-Button-1>", open_directory)

root.mainloop()
