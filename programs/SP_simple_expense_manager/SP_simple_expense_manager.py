import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
from pathlib import Path
from datetime import datetime
import re
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import csv
import shutil

from SP_footer_picture import add_footer
from SP_window_utils import center_window

# ====================================
# Main Data Naming
# ====================================
PROGRAM_NAME = "Simple Expense Manager"
DATA_FILE_NAME = "spendings_tracker_data.json"
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MONTH_TRANSLATION_KEYS = [
    "month.january",
    "month.february",
    "month.march",
    "month.april",
    "month.may",
    "month.june",
    "month.july",
    "month.august",
    "month.september",
    "month.october",
    "month.november",
    "month.december"
]
CURRENCIES = ["€", "$", "£", "CHF", "¥", "₩", "₹", "C$", "A$", "R$", "kr", "zł"]

# ====================================
# Global Standards
# ====================================
month_frames = {}
energy_entries = {}
grocery_entries = {}
year_energy_total_label = None
year_grocery_total_label = None
trend_labels = {}
statistics_window = None
month_chart_figure = None
year_chart_figure = None
WINDOW_BACKGROUND_COLOR = "#E6E6E6"

# ====================================
# Input Validation
# ====================================
def validate_money(value):
    if value == "":
        return True
    # allow comma or dot
    value=value.replace(",", ".")
    # only numbers and one decimal point
    if not re.match(r"^\d*\.?\d*$", value):
        return False
    return True

# ====================================
# Storage Handeling
# ====================================
def get_data_folder():
    documents = Path.home() / "Documents"
    folder = documents / "SimplePrograms" / PROGRAM_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def get_old_data_folder():
    documents = Path.home() / "Documents"
    return documents / PROGRAM_NAME
DATA_PATH = get_data_folder() / DATA_FILE_NAME
LANGUAGE_FOLDER = get_data_folder() / "languages"
LANGUAGE_FOLDER.mkdir(exist_ok=True)

# One-time migration: bring existing data over from the old folder, if any.
OLD_DATA_PATH = get_old_data_folder() / DATA_FILE_NAME
if not DATA_PATH.exists() and OLD_DATA_PATH.exists():
    try:
        shutil.copy2(OLD_DATA_PATH, DATA_PATH)
    except OSError:
        pass

# One-time migration: bring existing language files over from the old folder, if any.
OLD_LANGUAGE_FOLDER = get_old_data_folder() / "languages"
if OLD_LANGUAGE_FOLDER.exists():
    for old_file in OLD_LANGUAGE_FOLDER.glob("*.json"):
        new_file = LANGUAGE_FOLDER / old_file.name
        if not new_file.exists():
            try:
                shutil.copy2(old_file, new_file)
            except OSError:
                pass
DEFAULT_LANGUAGE = {
"english": {
    "language_name": "English",
    "window.statistics": "Statistics",
    "window.settings": "Settings",
    "menu.settings": "Settings",
    "menu.language": "Language",
    "menu.currency": "Currency",
    "menu.import_json": "Import JSON",
    "menu.export_json": "Export JSON",
    "menu.export_csv": "Export CSV",
    "menu.delete_all": "Delete All Data",
    "button.statistics": "Annual Statistics",
    "button.show_all_months": "Show All Months",
    "button.current_month": "Current Month",
    "button.save": "Save",
    "button.cancel": "Cancel",
    "button.close": "Close",
    "button.ok": "OK",
    "button.yes": "Yes",
    "button.no": "No",
    "button.export_charts": "Export Charts",
    "label.year": "Year",
    "label.month": "Month",
    "label.all_months": "All Months",
    "label.electricity": "Electricity",
    "label.groceries": "Groceries",
    "label.year_total": "Annual Total",
    "label.year_average": "Annual Average",
    "label.energy_total": "Total Electricity",
    "label.groceries_total": "Total Groceries",
    "label.comparison": "Comparison",
    "label.charts": "Charts",
    "trend.title": "Trends",
    "trend.last_month": "Compared to last month",
    "trend.same_month_last_year": "Compared to same month last year",
    "statistics.title": "Statistics for",
    "statistics.label_1": "Expenses in",
    "statistics.previous_years": "Comparison to previous years",
    "statistics.average": "Annual Average",
    "statistics.month_chart": "Monthly Spending",
    "statistics.year_chart": "10-Year Average Trend",
    "chart.month": "Month",
    "chart.cost": "Cost",
    "chart.average": "Average",
    "chart.year": "Year",
    "message.restart_language": "Restart the application to apply the new language.",
    "message.save_error": "Save Error",
    "message.import_success": "Import completed successfully.",
    "message.export_success": "Export completed successfully.",
    "message.delete_warning": "Are you sure you want to delete ALL data?",
    "message.delete_warning2": "This action cannot be undone!",
    "message.delete": "All data has been removed.",
    "message.no_previous_month": "No previous month available.",
    "message.charts_exported": "Charts exported successfully.",
    "message.csv_export_success": "CSV file exported successfully.",
    "message.no_chart": "No charts available.",
    "dialog.confirmation": "Confirmation",
    "dialog.confirm": "Continue",
    "dialog.deleted": "Deleted",
    "dialog.warning": "Warning",
    "dialog.warning_final": "FINAL WARNING",
    "dialog.error": "Error",
    "dialog.information": "Information",
    "file.json": "JSON file",
    "file.csv": "CSV file",
    "csv.year": "Year",
    "csv.month": "Month",
    "csv.electricity": "Electricity",
    "csv.groceries": "Groceries",
    "csv.currency": "Currency",
    "settings.language": "Language",
    "settings.currency": "Currency",
    "month.january": "January",
    "month.february": "February",
    "month.march": "March",
    "month.april": "April",
    "month.may": "May",
    "month.june": "June",
    "month.july": "July",
    "month.august": "August",
    "month.september": "September",
    "month.october": "October",
    "month.november": "November",
    "month.december": "December"
    }
}

def create_default_languages():
    for filename, content in DEFAULT_LANGUAGE.items():
        file = LANGUAGE_FOLDER / f"{filename}.json"
        if file.exists():
            continue
        with open(file, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=4, ensure_ascii=False)

def create_empty_data():
    return {"currency": "€", "language": "english", "years": {}}

def backup_data():
    if not DATA_PATH.exists():
        return
    backup_path = DATA_PATH.with_suffix(".backup.json")
    with open(DATA_PATH, "r", encoding="utf-8") as source:
        content = source.read()
    with open(backup_path, "w", encoding="utf-8") as backup:
        backup.write(content)

def load_data():
    if not DATA_PATH.exists():
        return create_empty_data()
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as error:
        messagebox.showerror(
            "Data Error",
            f"The data file could not be loaded.\n\n"
            f"Your existing data file was not modified.\n\n"
            f"Error:\n{error}\n\n"
            f"Try replacing your save file with the .backup file! \n{str(DATA_PATH.parent)}"
        )
        raise SystemExit

def upgrade_data():
    changed = False
    if "language" not in data:
        data["language"] = "english"
        changed = True
    if changed:
        save_data()

def save_data():
    try:
        backup_data()
        temp_path = DATA_PATH.with_suffix(".temp.json")
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)
        os.replace(temp_path, DATA_PATH)
    except Exception as error:
        messagebox.showerror(t("message.save_error"), str(error))

# ====================================
# Translations
# ====================================
translations = {}

def load_language(language):
    global translations
    file = LANGUAGE_FOLDER / f"{language}.json"
    if not file.exists():
        translations = {}
        return
    try:
        with open(file, "r", encoding="utf-8") as f:
            translations = json.load(f)
    except Exception:
        translations = {}

def t(key):
    if key not in translations:
        #print(f"Missing translation: {key}")
        return f"[{key}]"
    return translations[key]

def get_month_display_name(month):
    if month not in MONTH_NAMES:
        return month
    index = MONTH_NAMES.index(month)
    return t(MONTH_TRANSLATION_KEYS[index])

def get_display_months():
    return [get_month_display_name(month) for month in MONTH_NAMES]

def get_internal_month(display_name):
    for month in MONTH_NAMES:
        if get_month_display_name(month) == display_name:
            return month
    # fallback
    return display_name

def get_languages():
    languages = []
    for file in LANGUAGE_FOLDER.glob("*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                language = json.load(f)
            languages.append((file.stem, language.get("language_name", file.stem)))
        except Exception:
            continue
    languages.sort(key=lambda x: x[1])
    return languages

def change_language(language):
    global translations
    if language == data["language"]:
        return
    selected_language.set(language)
    data["language"] = language
    load_language(language)
    save_data()
    messagebox.showinfo(t("language_name"), t("message.restart_language"))

# ====================================
# DATA & Years
# ====================================
create_default_languages()
data = load_data()
upgrade_data()
load_language(data.get("language", "english"))

def ensure_year_exists(year):
    year=str(year)
    if year not in data["years"]:
        data["years"][year]={}
        for month in MONTH_NAMES:
            data["years"][year][month]={"Electricity":0, "Groceries":0}
        save_data()
        update_year_dropdown()

def get_available_years():
    current_year = datetime.now().year
    years = set(data.get("years", {}).keys())
    years.add(str(current_year))
    return sorted(years, key=int, reverse=True)

#=====================================
# UI Tools
#=====================================
def create_scrollable_frame(parent):
    canvas = tk.Canvas(parent)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    frame = tk.Frame(canvas)
    window_id = canvas.create_window((0, 0), window=frame, anchor="nw")
    frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(window_id, width=e.width))
    # -------------------------
    # Mousewheel
    # -------------------------
    def _mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _mousewheel))
    canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
    return canvas, frame

def change_currency(currency):
    selected_currency.set(currency)
    data["currency"] = currency
    save_data()
    create_month_cards()

# ====================================
# Main Window
# ====================================
root = tk.Tk()
root.withdraw()
selected_language = tk.StringVar()
selected_language.set(data["language"])
money_validator = root.register(validate_money)
root.title("Simple Expense Manager")
root.geometry("530x650")
root.minsize(530, 650)
center_window(root)
#Keeps everything on the left side
root.columnconfigure(0, weight=0)
root.rowconfigure(0, weight=0)
top_frame = tk.Frame(root)
top_frame.pack(fill="x", padx=10, pady=10)
if WINDOW_BACKGROUND_COLOR:
    root.configure(bg=WINDOW_BACKGROUND_COLOR)

#Adds footer, needs footer.png
add_footer(root, image_path="footer.png")

# ====================================
# Toolbar
# ====================================
toolbar = tk.Frame(top_frame)
toolbar.pack(fill="x", anchor="w", pady=(0, 8))
top_frame.columnconfigure(0, weight=1)

def show_all_months():
    selected_month.set(t("label.all_months"))
    reload_view()
    update_statistics_button()

def show_current_month():
    current_month = MONTH_NAMES[datetime.now().month - 1]
    current_year = datetime.now().year
    selected_year.set(str(current_year))
    selected_month.set(get_month_display_name(current_month))
    reload_view()
    update_statistics_button()

# -------------------------
# Settings Button
# -------------------------
settings_button = tk.Menubutton(toolbar, text=f"⚙ {t('menu.settings')}", relief="raised")
settings_button.pack(side="left")
settings_menu = tk.Menu(settings_button, tearoff=0)
settings_button.configure(menu=settings_menu)
settings_menu.add_command(label=t("menu.import_json"), command=lambda: import_data())
settings_menu.add_command(label=t("menu.export_json"), command=lambda: export_data())
settings_menu.add_command(label=t("menu.export_csv"), command=lambda: export_csv())
settings_menu.add_separator()

#Currency submenu
currency_menu = tk.Menu(settings_menu, tearoff=0)
for currency in CURRENCIES:
    currency_menu.add_command(label=currency, command=lambda c=currency: change_currency(c))
settings_menu.add_cascade(label=t("menu.currency"), menu=currency_menu)

#Language submenu
language_menu = tk.Menu(settings_menu, tearoff=0)
for language_id, language_name in get_languages():
    language_menu.add_radiobutton(label=language_name, variable=selected_language, value=language_id, command=lambda l=language_id: change_language(l))
settings_menu.add_cascade(label=t("menu.language"), menu=language_menu)
settings_menu.add_separator()
settings_menu.add_command(label=t("menu.delete_all"), command=lambda: delete_all_data())

# -------------------------
# Show All Months Button
# -------------------------
show_all_button = tk.Button(toolbar, text=t("button.show_all_months"), command=show_all_months)
show_all_button.pack(side="left", padx=(5,0))

# -------------------------
# Show Current Months Button
# -------------------------
current_month_button = tk.Button(toolbar, text=t("button.current_month"), command=show_current_month)
current_month_button.pack(side="left", padx=(5,0))

# -------------------------
# End Separator
# -------------------------
separator = ttk.Separator(top_frame, orient="horizontal")
separator.pack(fill="x", pady=(0, 5))

# ====================================
# Top Row
# ====================================
control_frame = tk.Frame(top_frame)
control_frame.pack(fill="x", anchor="w", padx=10, pady=(0, 10))

#Year
tk.Label(control_frame, text=f"{t('label.year')}:").grid(row=0, column=0, padx=5)
selected_year = tk.StringVar(value=str(datetime.now().year))
selected_month = tk.StringVar(value=get_month_display_name(MONTH_NAMES[datetime.now().month - 1]))
year_box = ttk.Combobox(control_frame, textvariable=selected_year, values=get_available_years(), width=10, state="readonly")
year_box.grid(row=0, column=1, padx=5)

#Month
tk.Label(control_frame, text=f"{t('label.month')}:").grid(row=0, column=2, padx=5)
month_box = ttk.Combobox(control_frame, textvariable=selected_month, values=[t("label.all_months")] + get_display_months(), width=15, state="readonly")
month_box.grid(row=0, column=3, padx=5)
selected_currency = tk.StringVar(value=data.get("currency", "€"))

#Statistics
statistics_button = tk.Button(control_frame, text=t("button.statistics"), command=lambda: open_statistics_window())
statistics_button.grid(row=0, column=6, padx=10)

def update_year_dropdown():
    year_box["values"] = get_available_years()

# ====================================
# Scrolling
# ====================================
scroll_container = tk.Frame(root)
scroll_container.pack(fill="both", expand=True, padx=10, pady=(0,10))
canvas, months_container = create_scrollable_frame(scroll_container)

# ====================================
# Window Cards
# ====================================
def create_month_cards():
    for widget in months_container.winfo_children():
        widget.destroy()
    month_frames.clear()
    energy_entries.clear()
    grocery_entries.clear()
    trend_labels.clear()
    ensure_year_exists(selected_year.get())
    # -------------------------
    # Single Month Card
    # -------------------------
    if selected_month.get() != t("label.all_months"):
        month = get_internal_month(selected_month.get())
        card = tk.LabelFrame(months_container, text=f"{get_month_display_name(month)} {selected_year.get()}", padx=20, pady=20)
        card.grid(row=0, column=0, padx=10, pady=10, sticky="nw")
        month_frames[month] = card
        create_input_field(card, month, "Electricity", 0)
        create_input_field(card, month, "Groceries", 3)
        trend_area = tk.Frame(months_container)
        trend_area.grid(row=1, column=0, padx=10, pady=10, sticky="nw")
        create_trend_box(trend_area, month)
        return
    # -------------------------
    # All Months Card
    # -------------------------
    for index, month in enumerate(MONTH_NAMES):
        row = index // 4
        column = index % 4
        card = tk.LabelFrame(months_container, text=get_month_display_name(month), padx=10, pady=10)
        card.grid(row=row, column=column, padx=5, pady=5, sticky="nw")
        month_frames[month] = card
        create_input_field(card, month, "Electricity", 0)
        create_input_field(card, month, "Groceries", 3)
    # -------------------------
    # Year Total
    # -------------------------
    year_total_frame = tk.LabelFrame(months_container, text=t("label.year_total"), padx=15, pady=10)
    year_total_frame.grid(row=3, column=0, columnspan=4, sticky="w", pady=15)
    energy_total = calculate_year_total(selected_year.get(), "Electricity")
    grocery_total = calculate_year_total(selected_year.get(), "Groceries")
    global year_energy_total_label
    global year_grocery_total_label
    #Electricity
    energy_frame = tk.Frame(year_total_frame)
    energy_frame.pack(anchor="w")
    tk.Label(energy_frame, text=f"{t('label.electricity')}: ").pack(side="left")
    year_energy_total_label = tk.Label(energy_frame, text=f"{energy_total:.2f} {selected_currency.get()}", font=("Arial", 10, "bold"))
    year_energy_total_label.pack(side="left")
    #Groceries
    grocery_frame = tk.Frame(year_total_frame)
    grocery_frame.pack(anchor="w")
    tk.Label(grocery_frame, text=f"{t('label.groceries')}: ").pack(side="left")
    year_grocery_total_label = tk.Label(grocery_frame, text=f"{grocery_total:.2f} {selected_currency.get()}", font=("Arial", 10, "bold"))
    year_grocery_total_label.pack(side="left")

def create_input_field(parent,month,category,row):
    tk.Label(parent, text=t(f"label.{category.lower()}")).grid(row=row, column=0, sticky="w")
    variable = tk.StringVar()
    if category=="Electricity":
        energy_entries[month]=variable
    else:
        grocery_entries[month]=variable
    value = data["years"][selected_year.get()][month].get(category, 0)
    variable.set(str(value))
    entry = tk.Entry(parent, textvariable=variable, width=10, validate="key", validatecommand=(money_validator, "%P"))
    entry.grid(row=row+1, column=0, sticky="w")
    tk.Label(parent, textvariable=selected_currency).grid(row=row+1, column=1, sticky="w", padx=(2,0))
    variable.trace_add("write", lambda *args, m=month, c=category: update_value(m,c))

def create_trend_box(parent, month):
    box = tk.LabelFrame(parent, text=t("trend.title"), padx=10, pady=10)
    box.pack(anchor="w")
    current_year = int(selected_year.get())
    # -------------------------
    # Previous Month Trend
    # -------------------------
    month_index = MONTH_NAMES.index(month)
    if month_index > 0:
        previous_month = MONTH_NAMES[month_index - 1]
        tk.Label(box, text=f"{t('trend.last_month')}:", font=("Arial", 9, "bold")).pack(anchor="w")
        create_trend_labels(box, month, previous_month, current_year, current_year)
    else:
        tk.Label(box, text=t("message.no_previous_month")).pack(anchor="w")
    # -------------------------
    # Same month last year trend
    # -------------------------
    tk.Label(box, text=f"{t('trend.same_month_last_year')}:", font=("Arial", 9, "bold")).pack(anchor="w", pady=(10,0))
    create_trend_labels(box, month, month, current_year, current_year-1)

def create_trend_labels(parent, current_month, old_month, current_year, old_year):
    for category in ["Electricity", "Groceries"]:
        current_value = data["years"].get(str(current_year), {}).get(current_month, {}).get(category, 0)
        old_value = data["years"].get(str(old_year), {}).get(old_month, {}).get(category, 0)
        if old_value == 0:
            percentage = 0
        else:
            percentage = ((current_value - old_value) / old_value * 100)
        if percentage > 0:
            symbol = "▲"
            color = "#FF5454"     
        elif percentage < 0:
            symbol = "▼"
            color = "#63F16A"     
        else:
            symbol = "▬"
            color = "gray"
        row = tk.Frame(parent)
        row.pack(anchor="w", pady=2)
        category_label = tk.Label(row, text=t(f"label.{category.lower()}") + ":", width=12, anchor="w")
        category_label.pack(side="left")
        arrow_label = tk.Label(row, text=symbol, fg=color, font=("Arial", 14, "bold"))
        arrow_label.pack(side="left", padx=(4, 8))
        percent_label = tk.Label(row, text=f"{percentage:+.2f}%")
        percent_label.pack(side="left")
        trend_labels[(current_month, old_month, current_year, old_year, category)] = (arrow_label, percent_label)

def update_trends():
    if not trend_labels:
        return
    for key, widgets in trend_labels.items():
        (current_month, old_month, current_year, old_year, category) = key
        arrow_label, percent_label = widgets
        current_value = data["years"].get(str(current_year), {}).get(current_month, {}).get(category, 0)
        old_value = data["years"].get(str(old_year), {}).get(old_month, {}).get(category, 0)
        if old_value == 0:
            percentage = 0
        else:
            percentage = ((current_value - old_value) / old_value * 100)
        if percentage > 0:
            symbol = "▲"
            color = "#FF5454"
        elif percentage < 0:
            symbol = "▼"
            color = "#63F16A"
        else:
            symbol = "▬"
            color = "gray"
        arrow_label.config(text=symbol, fg=color)
        percent_label.config(text=f"{percentage:+.2f}%")

def update_value(month, category):
    if category=="Electricity":
        raw = energy_entries[month].get()
    else:
        raw = grocery_entries[month].get()
    try:
        raw = raw.replace(",", ".")
        value=float(raw)
    except Exception:
        value=0
    data["years"][selected_year.get()][month][category]=value
    data["currency"]=selected_currency.get()
    save_data()
    update_year_total_display()
    update_trends()

def update_year_total_display():
    if selected_month.get() != t("label.all_months"):
        return
    if year_energy_total_label is None:
        return
    year = selected_year.get()
    energy = calculate_year_total(year, "Electricity")
    groceries = calculate_year_total(year, "Groceries")
    year_energy_total_label.config(text=f"{t('label.electricity')}: {energy:.2f} {selected_currency.get()}")
    year_grocery_total_label.config(text=f"{t('label.groceries')}: {groceries:.2f} {selected_currency.get()}")

# ====================================
# Year Total Calculations
# ====================================
def calculate_year_total(year, category):
    ensure_year_exists(year)
    total = 0
    for month in MONTH_NAMES:
        total += data["years"][str(year)][month].get(category, 0)
    return total

# ====================================
# Events
# ====================================
def reload_view(event=None):
    create_month_cards()
year_box.bind("<<ComboboxSelected>>", lambda e: (reload_view(), update_statistics_button()))
month_box.bind("<<ComboboxSelected>>", lambda e: (reload_view(), update_statistics_button()))

# ====================================
# Import / Export
# ====================================
def import_data():
    global data
    filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
    if not filename:
        return
    try:
        with open(filename, "r", encoding="utf-8") as file:
            data=json.load(file)
        selected_currency.set(data.get("currency", "€"))
        create_month_cards()
        messagebox.showinfo("Import", t("message.import_success"))
    except Exception as error:
        messagebox.showerror(f"Import {t("dialog.error")}", str(error))

def export_data():
    filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
    if not filename:
        return
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)
    messagebox.showinfo("Export", t("message.export_success"))

def export_statistics_charts():
    if month_chart_figure is None or year_chart_figure is None:
        messagebox.showerror(t("dialog.error"), t("message.no_chart"))
        return
    folder = filedialog.askdirectory()
    if not folder:
        return
    month_path = os.path.join(folder, f"{selected_year.get()}_monthly_expenses.png")
    current_year = int(selected_year.get())
    year_path = os.path.join(folder, f"{current_year-9}-{current_year}_yearly_average_trend.png")
    month_chart_figure.savefig(month_path, dpi=300, bbox_inches="tight")
    year_chart_figure.savefig(year_path, dpi=300, bbox_inches="tight")
    messagebox.showinfo(t("message.export_success"), t("message.charts_exported"))

# ====================================
# Data be Gone
# ====================================
def delete_all_data():
    first = messagebox.askyesno(t("dialog.warning"), t("message.delete_warning"))
    if not first:
        return
    second = messagebox.askyesno(t("dialog.warning_final"), f"{t('message.delete_warning2')} \n{t('dialog.confirm')}?")
    if not second:
        return
    global data
    data=create_empty_data()
    save_data()
    selected_currency.set("€")
    create_month_cards()
    messagebox.showinfo(t("dialog.deleted"), t("message.delete"))

def update_statistics_button(event=None):
    if selected_month.get() == t("label.all_months"):
        statistics_button.config(state="normal")
    else:
        statistics_button.config(state="disabled")

# ====================================
# Statistics Window
# ====================================
def calculate_average(year, category):
    year=str(year)
    if year not in data["years"]:
        return 0
    total=0
    for month in MONTH_NAMES:
        total += data["years"][year][month].get(category, 0)
    return total / 12

def get_year_difference(current_year, category, years_back):
    current=int(current_year)
    old_year=current-years_back
    current_average = calculate_average(current, category)
    old_average = calculate_average(old_year, category)
    difference = (current_average - old_average)
    if old_average == 0:
        percent = 0
    else:
        percent = (difference / old_average * 100)
    return difference, percent

def open_statistics_window():
    global statistics_window
    if selected_month.get() != t("label.all_months"):
        return
    # Close old window
    if statistics_window is not None:
        try:
            statistics_window.destroy()
        except Exception:
            pass
    year = selected_year.get()
    statistics_window = tk.Toplevel(root)
    statistics_window.title(f"{t('window.statistics')} {year}")
    statistics_window.geometry("880x850")
    statistics_window.minsize(880,850)
    if WINDOW_BACKGROUND_COLOR:
        statistics_window.configure(bg=WINDOW_BACKGROUND_COLOR)
    # -------------------------
    # Scrollable area
    # -------------------------
    stats_canvas, frame = create_scrollable_frame(statistics_window)
    #Mousewheel
    def _mousewheel(event):
        stats_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    stats_canvas.bind("<Enter>", lambda e: stats_canvas.bind_all("<MouseWheel>", _mousewheel))
    stats_canvas.bind("<Leave>", lambda e: stats_canvas.unbind_all("<MouseWheel>"))
    # -------------------------
    # Title
    # -------------------------
    tk.Label(frame, text=f"{t('statistics.title')} {year}", font=("Arial", 14, "bold")).pack(anchor="w", pady=10, padx=10)
    # -------------------------
    # Averages
    # -------------------------
    average_box = tk.LabelFrame(frame, text=t("statistics.average"), padx=10, pady=10)
    average_box.pack(fill="x", padx=10, pady=10)
    for category in ["Electricity", "Groceries"]:
        avg = calculate_average(year, category)
        row = tk.Frame(average_box)
        row.pack(anchor="w")
        tk.Label(row, text=f"{t('label.' + category.lower())}: ").pack(side="left")
        tk.Label(row, text=f"{avg:.2f} {selected_currency.get()}", font=("Arial", 10, "bold")).pack(side="left")
    # -------------------------
    # Previous 3 years
    # -------------------------
    comparison_box = tk.LabelFrame(frame, text=t("statistics.previous_years"), padx=10, pady=10)
    comparison_box.pack(fill="x", padx=10, pady=10)
    tk.Label(comparison_box, text="").grid(row=0, column=0, padx=5, sticky="w")
    tk.Label(comparison_box, text=t("label.electricity"),).grid(row=0, column=1, padx=10, sticky="w")
    tk.Label(comparison_box, text=t("label.groceries"),).grid(row=0, column=2, padx=10, sticky="w")
    for back in range(1, 4):
        previous = int(year) - back
        tk.Label(comparison_box, text=f"{previous}").grid(row=back, column=0, padx=5, pady=2, sticky="w")
        for column, category in enumerate(["Electricity", "Groceries"], start=1):
            difference, percent = get_year_difference(year, category, back)
            category_frame = tk.Frame(comparison_box)
            category_frame.grid(row=back, column=column, padx=10, sticky="w")
            value_frame = tk.Frame(category_frame)
            value_frame.pack(anchor="w")
            if percent > 0:
                symbol = "▲"
                color = "#FF5454"
            elif percent < 0:
                symbol = "▼"
                color = "#63F16A"
            else:
                symbol = "▬"
                color = "gray"
            tk.Label(value_frame, text=symbol, fg=color, font=("Arial", 12, "bold")).pack(side="left", padx=(0,5))
            tk.Label(value_frame, text=f"{difference:+.2f} {selected_currency.get()} ({percent:+.1f}%)").pack(side="left")
    # -------------------------
    # Charts
    # -------------------------
    chart_box = tk.LabelFrame(frame, text=t("label.charts"), padx=10, pady=10)
    chart_box.pack(fill="x", anchor="w", padx=10, pady=10)
    create_month_chart(chart_box, year)
    create_year_trend_chart(chart_box, year)
    export_button = tk.Button(frame, text=t("button.export_charts"), command=export_statistics_charts)
    export_button.pack(anchor="w", padx=10, pady=(0,15))
    statistics_window.protocol("WM_DELETE_WINDOW", close_statistics_window)

def close_statistics_window():
    global statistics_window
    if statistics_window is not None:
        statistics_window.destroy()
        statistics_window = None

# ====================================
# Chart Data
# ====================================
def get_monthly_values(year, category):
    ensure_year_exists(year)
    return [data["years"][str(year)][month].get(category, 0) for month in MONTH_NAMES]

def get_average_history(current_year, category):
    years = []
    averages = []
    current_year = int(current_year)
    for year in range(current_year - 9, current_year + 1):
        years.append(str(year))
        averages.append(calculate_average(year, category))
    return years, averages

# ====================================
# Chart Creation
# ====================================
def create_month_chart(parent, year):
    global month_chart_figure
    figure = Figure(figsize=(8, 4), dpi=100)
    month_chart_figure = figure
    axis = figure.add_subplot(111)
    display_months = [get_month_display_name(month) for month in MONTH_NAMES]
    energy = get_monthly_values(year, "Electricity")
    groceries = get_monthly_values(year, "Groceries")
    axis.plot(display_months, energy, color='#5DBA98', marker="s", linewidth=2, label=t("label.electricity"))
    axis.plot(display_months, groceries, color='#7C6298', marker="s", linewidth=2, label=t("label.groceries"))
    axis.set_title(f"{t('statistics.month_chart')} ({year})")
    axis.set_ylabel(f"{t('statistics.label_1')} ({selected_currency.get()})")
    axis.grid(True)
    axis.legend()
    axis.tick_params(axis="x", rotation=45)
    figure.tight_layout()
    canvas = FigureCanvasTkAgg(figure, master=parent)
    canvas.draw()
    canvas.get_tk_widget().pack(anchor="w", padx=10, pady=10)

def create_year_trend_chart(parent, year):
    global year_chart_figure
    figure = Figure(figsize=(8, 4), dpi=100)
    year_chart_figure = figure
    axis = figure.add_subplot(111)
    years, energy = get_average_history(year, "Electricity")
    _, groceries = get_average_history(year, "Groceries")
    axis.plot(years, energy, color='#5DBA98', marker="s", linewidth=2, label=t("label.electricity"))
    axis.plot(years, groceries, color='#7C6298', marker="s", linewidth=2, label=t("label.groceries"))
    axis.set_title(t("statistics.year_chart"))
    axis.set_ylabel(f"{t('statistics.label_1')} ({selected_currency.get()})")
    axis.grid(True)
    axis.legend()
    figure.tight_layout()
    canvas = FigureCanvasTkAgg(figure, master=parent)
    canvas.draw()
    canvas.get_tk_widget().pack(anchor="w", padx=10, pady=10)

# ====================================
# CSV Export
# ====================================
def export_csv():
    filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
    if not filename:
        return
    try:
        with open(filename, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file, delimiter=";")
            # Header
            writer.writerow([t("csv.year"), t("csv.month"), t("csv.electricity"), t("csv.groceries"), t("csv.currency")])
            # Data
            for year in sorted(data["years"].keys(), reverse=True):
                year_data = data["years"][year]
                for month, values in year_data.items():
                    writer.writerow([year, get_month_display_name(month), values.get("Electricity", 0), values.get("Groceries", 0), selected_currency.get()])
        messagebox.showinfo(t("dialog.confirmation"), t("message.csv_export_success"))
    except Exception as error:
        messagebox.showerror(t("dialog.error"), str(error))

# ====================================
# End Functions
# ====================================
create_month_cards()
update_statistics_button()
root.protocol("WM_DELETE_WINDOW", lambda: (save_data(), root.destroy()))
root.deiconify()
root.mainloop()