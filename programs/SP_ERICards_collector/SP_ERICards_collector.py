import json
import os
import re
import shutil
import subprocess
import sys
import webbrowser
import tkinter as tk
import tkinter.font as tkFont
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from helper.SP_footer_picture import add_footer
from helper.SP_window_utils import center_window

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None


# --- Configuration ---
WINDOW_BACKGROUND_COLOR = "#E6E6E6"
GROUP_BORDER_COLOR = "#A7A7A7"
BOX_BORDER_THICKNESS = 0.5
BOX_INTERNAL_PADDING = 4
BOX_EXTERNAL_PADDING = 10
BUTTON_WIDTH = 20

# Navigation buttons: width follows the text, everything else (height, border, padding, font)
# is identical for every button. All of them are plain tk.Button widgets so they cannot differ.
NAV_BUTTON_OPTIONS = {
    "padx": 10, "pady": 2, "font": ("Segoe UI", 9), "height": 1,
    "relief": tk.RAISED, "bd": 2, "highlightthickness": 0, "takefocus": 0,
}
TOP_BAR_SPACING = 6

HINT_COLOR = "#1B5FA8"
DANGER_COLOR = "#C55E5E"
GO_COLOR = "#3A8B63"

APP_TITLE = "ERICards Collector"
SCHEMA_VERSION = 1
DETAIL_ICON_SIZE = 96       # ADR hazard labels on the ERICard page
STATEMENT_ICON_SIZE = 88    # GHS pictograms on the H & P Statements page
DEFAULT_LANGUAGE = "en"
DATE_STORAGE_FORMAT = "%Y-%m-%d"

SEARCH_CATEGORIES = ["All", "UN Number", "Substance Name", "ADR Class", "Hazard Number", "ERICard Number"]
STATUS_FILTERS = ["All", "Collected", "Missing"]
STATEMENT_FILTERS = ["All", "H Statements", "EUH Statements", "P Statements"]

KIND_ERICARDS = "ericards"
KIND_SUBSTANCES = "substances"

# Ways to combine an imported collection with the current one
IMPORT_KEEP_EARLIER = 0
IMPORT_USE_IMPORTED = 1
IMPORT_REPLACE = 2


# --- Storage Paths ---
DOCUMENTS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "SimplePrograms", "ERICardsCollector")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

DATABASE_FILE = os.path.join(DOCUMENTS_DIR, "ericards_db.json")
COLLECTION_FILE = os.path.join(DOCUMENTS_DIR, "collection.json")
SETTINGS_FILE = os.path.join(DOCUMENTS_DIR, "config.json")
REFERENCE_FILE = os.path.join(DOCUMENTS_DIR, "reference_texts.json")
ICONS_DIR = os.path.join(DOCUMENTS_DIR, "icons")                        # optional images: adr_<class>.png, ghs<nn>.png
BACKUP_DIR = os.path.join(DOCUMENTS_DIR, "backups")                     # backups made before imports and updates
os.makedirs(ICONS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

DEFAULT_SETTINGS = {
    "schema_version": SCHEMA_VERSION,
    "date_format": "%Y-%m-%d",
    "last_category": "All",
    "last_substance_category": "All",
    "reference_language": DEFAULT_LANGUAGE,
    "ask_date": True,
    "quick_collect": True,
}


# --- Helper Functions ---
def open_folder(path):
    if os.name == "nt":
        os.startfile(path)
    elif shutil.which("open"):
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])

def load_json(path, default):
    if not os.path.exists(path):
        return default, None
    try:
        with open(path, "r", encoding="utf-8-sig") as file:
            return json.load(file), None
    except (json.JSONDecodeError, OSError) as error:
        corrupt_path = f"{path}.corrupt-{datetime.now():%Y%m%d-%H%M%S}"
        try:
            shutil.copy2(path, corrupt_path)
            note = f"A copy of the damaged file was saved as:\n{corrupt_path}"
        except OSError:
            note = "The damaged file could not be copied."
        return default, f"Could not read '{os.path.basename(path)}': {error}\n{note}"

def save_json(path, data):
    # Write to a temporary file first so a crash cannot leave a half-written file behind
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
    os.replace(temp_path, path)

def natural_sort_key(text):
    # "2-10" sorts after "2-02"; "2.1" before "2.3"; "10" after "9"
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(text))]

def card_key(number):
    return str(number).strip().upper()

def compact(text):
    return re.sub(r"[\s\-_]", "", str(text).lower())

def calculate_percent(part, total):
    return (part / total * 100) if total else 0.0

def parse_iso_date(text):
    try:
        return datetime.strptime(str(text).strip(), DATE_STORAGE_FORMAT).date()
    except ValueError:
        return None

def format_problems(problems, limit=6):
    if not problems:
        return ""
    text = "\n\nProblems found:\n" + "\n".join(f"- {line}" for line in problems[:limit])
    if len(problems) > limit:
        text += f"\n... and {len(problems) - limit} more"
    return text

def summarize_list(values, limit=3, separator=", "):
    # Long lists (hundreds of UN numbers per card) are shortened in table cells
    if len(values) <= limit:
        return separator.join(values)
    return f"{separator.join(values[:limit])} (+{len(values) - limit} more)"

def split_sentences(text):
    # Splits running text into sentences for display as separate paragraphs. A split needs a
    # lowercase letter, digit or ")" before the period, so abbreviations like "z. B." stay together.
    parts = re.split(r"(?<=[a-zäöüß0-9)]{2}\.)\s+(?=[A-ZÄÖÜ])", str(text).strip())
    return [part.strip() for part in parts if part.strip()]

def set_readonly_text(widget, text):
    widget.config(state="normal")
    widget.delete("1.0", tk.END)
    widget.insert("1.0", text)
    widget.config(state="disabled")


# --- Sortable Table ---
class SortableTree:
    def __init__(self, parent, columns, key_overrides=None, height=10):
        self.headings = {column[0]: column[1] for column in columns}
        self.key_overrides = key_overrides or {}
        self.sort_column = None
        self.sort_reverse = False

        self.frame = tk.Frame(parent, bg=WINDOW_BACKGROUND_COLOR)
        self.tree = ttk.Treeview(
            self.frame, columns=[column[0] for column in columns], show="headings", selectmode="browse",
            height=height,
        )
        for column_id, heading, width, anchor, stretch in columns:
            self.tree.heading(column_id, text=heading, anchor=anchor, command=lambda c=column_id: self.sort_by(c))
            self.tree.column(column_id, width=width, minwidth=min(width, 40), anchor=anchor, stretch=stretch)

        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(0, weight=1)
        scrollbar = tk.Scrollbar(self.frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("collected", foreground=GO_COLOR)

    def clear(self):
        self.tree.delete(*self.tree.get_children())

    def sort_by(self, column):
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column, self.sort_reverse = column, False
        self.apply_sort()

    def apply_sort(self):
        for column_id, heading in self.headings.items():
            arrow = ""
            if column_id == self.sort_column:
                arrow = " \u25BC" if self.sort_reverse else " \u25B2"
            self.tree.heading(column_id, text=heading + arrow)
        if self.sort_column is None:
            return

        column = self.sort_column
        override = self.key_overrides.get(column)

        def sort_key(item):
            return override(item) if override else natural_sort_key(self.tree.set(item, column))

        items = sorted(self.tree.get_children(""), key=sort_key, reverse=self.sort_reverse)
        for index, item in enumerate(items):
            self.tree.move(item, "", index)


# --- Text Box ---
LABEL_PATTERN = re.compile(r"^([^:.;]{2,40}:)(?=\s|$)")

class TextBox(tk.Frame):
    def __init__(self, parent, height=4):
        super().__init__(
            parent, bg="white",
            highlightbackground=GROUP_BORDER_COLOR, highlightcolor=GROUP_BORDER_COLOR,
            highlightthickness=BOX_BORDER_THICKNESS,
        )
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.text = tk.Text(
            self, height=height, wrap="word", font=("Segoe UI", 10), state="disabled", relief="flat", bd=0,
            padx=12, pady=8, spacing2=2, cursor="arrow", highlightthickness=0,
        )
        self.scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=self._on_scroll)
        self.text.grid(row=0, column=0, sticky="nsew")

        self.text.tag_configure("paragraph", spacing3=7)
        self.text.tag_configure("bullet", lmargin1=4, lmargin2=22, tabs=(22,), spacing3=5)
        self.text.tag_configure("heading", font=("Segoe UI", 10, "bold"), spacing1=10, spacing3=2)
        self.text.tag_configure("sub_heading", font=("Segoe UI", 10, "bold"), lmargin1=14, lmargin2=14, spacing1=6)
        self.text.tag_configure("line", lmargin1=24, lmargin2=38, tabs=(38,), spacing3=2)
        self.text.tag_configure("label", font=("Segoe UI", 10, "bold"))

    def _on_scroll(self, first, last):
        self.scrollbar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scrollbar.grid_remove()
        else:
            self.scrollbar.grid(row=0, column=1, sticky="ns")

    # --- Content ---
    def _begin(self):
        self.text.config(state="normal")
        self.text.delete("1.0", tk.END)

    def _end(self):
        self.text.config(state="disabled")
        self.text.yview_moveto(0)

    def _insert_labelled(self, text, tag):
        match = LABEL_PATTERN.match(text)
        if match:
            self.text.insert(tk.END, match.group(1), (tag, "label"))
            self.text.insert(tk.END, text[match.end(1):], tag)
        else:
            self.text.insert(tk.END, text, tag)

    def show_paragraphs(self, text):
        self._begin()
        sentences = split_sentences(text)
        for index, sentence in enumerate(sentences or ["-"]):
            if index:
                self.text.insert(tk.END, "\n")
            self._insert_labelled(sentence, "paragraph")
        self._end()

    def show_bullets(self, items):
        self._begin()
        for index, item in enumerate(items or ["-"]):
            if index:
                self.text.insert(tk.END, "\n")
            if items:
                self.text.insert(tk.END, "\u2022\t", "bullet")
            self._insert_labelled(item, "bullet")
        self._end()

    def show_sections(self, sections):
        self._begin()
        if not sections:
            self.text.insert("1.0", "No detailed card text is available in this database.")
        for heading, lines in sections:
            is_sub_heading = re.match(r"^\d+\.\d+", heading) is not None
            self.text.insert(tk.END, heading + "\n", "sub_heading" if is_sub_heading else "heading")
            for line in lines:
                self.text.insert(tk.END, "\u2022\t", "line")
                self.text.insert(tk.END, line + "\n", "line")
        self._end()


# --- Icons ---
# Simplified placeholder label colours for ADR classes: (fill colour, text colour)
ADR_LABEL_STYLES = {
    "1": ("#F28C28", "black"),
    "2.1": ("#D6342C", "white"),
    "2.2": ("#2E8B57", "white"),
    "2.3": ("#FFFFFF", "black"),
    "3": ("#D6342C", "white"),
    "4.1": ("#F5F5F5", "black"),
    "4.2": ("#F5F5F5", "black"),
    "4.3": ("#1E63B5", "white"),
    "5.1": ("#F2D230", "black"),
    "5.2": ("#F2D230", "black"),
    "6.1": ("#FFFFFF", "black"),
    "6.2": ("#FFFFFF", "black"),
    "7": ("#F2D230", "black"),
    "8": ("#FFFFFF", "white"),
    "9": ("#FFFFFF", "black"),
}
DEFAULT_LABEL_STYLE = ("#CCCCCC", "black")
_icon_cache = {}

def fit_size(width, height, limit):
    scale = min(1.0, limit / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))

def zoom_subsample_factors(width, height, limit):
    # Whole-number (zoom, subsample) pair that scales an image close to `limit` pixels.
    # Only used without Pillow, e.g. 512 px -> 96 px is zoom 3 then subsample 16.
    largest = max(width, height)
    if largest <= limit:
        return 1, 1
    ratio = Fraction(limit, largest).limit_denominator(32)
    return max(ratio.numerator, 1), max(ratio.denominator, 1)

def load_icon_image(path, size):
    if not os.path.isfile(path):
        return None
    cache_key = (path, size)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]
    try:
        if Image is not None:
            with Image.open(path) as source:
                source = source.convert("RGBA")
                new_size = fit_size(source.width, source.height, size)
                resampling = getattr(Image, "Resampling", Image)
                resized = source.resize(new_size, resampling.LANCZOS)
            image = ImageTk.PhotoImage(resized)
        else:
            image = tk.PhotoImage(file=path)
            zoom, subsample = zoom_subsample_factors(image.width(), image.height(), size)
            if zoom > 1:
                image = image.zoom(zoom, zoom)
            if subsample > 1:
                image = image.subsample(subsample, subsample)
    except (tk.TclError, OSError, ValueError):
        return None
    _icon_cache[cache_key] = image
    return image

def build_image_label(parent, image):
    label = tk.Label(parent, image=image, bg=WINDOW_BACKGROUND_COLOR)
    label.image = image
    return label

def safe_icon_name(text):
    return re.sub(r"[^0-9A-Za-z.]", "", str(text))

def build_adr_icon(parent, adr_class, size=DETAIL_ICON_SIZE):
    # Uses icons/adr_<class>.png if present, otherwise draws a simple diamond placeholder
    image = load_icon_image(os.path.join(ICONS_DIR, f"adr_{safe_icon_name(adr_class)}.png"), size)
    if image is not None:
        return build_image_label(parent, image)

    main_class = adr_class.split(".")[0]
    fill, text_color = ADR_LABEL_STYLES.get(adr_class, ADR_LABEL_STYLES.get(main_class, DEFAULT_LABEL_STYLE))
    canvas = tk.Canvas(parent, width=size, height=size, bg=WINDOW_BACKGROUND_COLOR, highlightthickness=0)
    center, pad = size / 2, 2
    canvas.create_polygon(center, pad, size - pad, center, center, size - pad, pad, center, fill=fill, outline="")
    if main_class == "8":
        canvas.create_polygon(pad, center, size - pad, center, center, size - pad, fill="black", outline="")
    canvas.create_polygon(center, pad, size - pad, center, center, size - pad, pad, center, fill="", outline="black")
    canvas.create_text(center, size * 0.72, text=adr_class, fill=text_color, font=("Arial", int(size * 0.2), "bold"))
    return canvas

def build_ghs_icon(parent, pictogram_code, size=STATEMENT_ICON_SIZE):
    # Uses icons/<code>.png (for example ghs06.png) if present, otherwise draws a placeholder
    image = load_icon_image(os.path.join(ICONS_DIR, f"{safe_icon_name(pictogram_code).lower()}.png"), size)
    if image is not None:
        return build_image_label(parent, image)

    canvas = tk.Canvas(parent, width=size, height=size, bg=WINDOW_BACKGROUND_COLOR, highlightthickness=0)
    center, pad = size / 2, 3
    canvas.create_polygon(
        center, pad, size - pad, center, center, size - pad, pad, center, fill="white", outline="#D6342C", width=3,
    )
    canvas.create_text(center, center, text=pictogram_code, fill="black", font=("Arial", max(int(size * 0.14), 6), "bold"))
    return canvas


# --- Dialogs ---
class ModalDialog(tk.Toplevel):
    def __init__(self, parent, title):
        super().__init__(parent, bg=WINDOW_BACKGROUND_COLOR)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda event: self.cancel())

    def show(self):
        parent = self.master
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.wait_visibility()
        self.grab_set()
        self.wait_window(self)
        return self.result

    def cancel(self):
        self.result = None
        self.destroy()

class DateDialog(ModalDialog):
    def __init__(self, parent, title, message, initial_iso):
        super().__init__(parent, title)
        tk.Label(self, text=message, bg=WINDOW_BACKGROUND_COLOR, justify="left").pack(padx=14, pady=(12, 6), anchor="w")

        row = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        row.pack(padx=14, anchor="w")
        tk.Label(row, text="Date:", bg=WINDOW_BACKGROUND_COLOR).pack(side="left")
        self.value = tk.StringVar(value=initial_iso)
        self.entry = tk.Entry(row, textvariable=self.value, width=14)
        self.entry.pack(side="left", padx=6)
        tk.Button(row, text="Today", command=lambda: self.value.set(date.today().isoformat())).pack(side="left")

        tk.Label(
            self, text="Format: YYYY-MM-DD", bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=("Segoe UI", 8),
        ).pack(padx=14, pady=(2, 0), anchor="w")
        self.error_label = tk.Label(self, text="", bg=WINDOW_BACKGROUND_COLOR, fg=DANGER_COLOR, font=("Segoe UI", 8))
        self.error_label.pack(padx=14, anchor="w")

        buttons = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        buttons.pack(pady=(6, 12))
        tk.Button(buttons, text="OK", width=10, command=self.confirm).pack(side="left", padx=4)
        tk.Button(buttons, text="Cancel", width=10, command=self.cancel).pack(side="left", padx=4)

        self.bind("<Return>", lambda event: self.confirm())
        self.entry.focus_set()
        self.entry.select_range(0, tk.END)

    def confirm(self):
        parsed = parse_iso_date(self.value.get())
        if parsed is None:
            self.error_label.config(text="Please enter a valid date as YYYY-MM-DD.")
            return
        if parsed > date.today():
            self.error_label.config(text="The date cannot be in the future.")
            return
        self.result = parsed.isoformat()
        self.destroy()

class ChoiceDialog(ModalDialog):
    # Returns the index of the chosen option, or None if cancelled
    def __init__(self, parent, title, message, options, confirm_text="OK", default_index=0):
        super().__init__(parent, title)
        tk.Label(self, text=message, bg=WINDOW_BACKGROUND_COLOR, justify="left").pack(padx=14, pady=(12, 8), anchor="w")

        self.choice = tk.IntVar(value=default_index)
        for index, option in enumerate(options):
            tk.Radiobutton(
                self, text=option, variable=self.choice, value=index, bg=WINDOW_BACKGROUND_COLOR,
                activebackground=WINDOW_BACKGROUND_COLOR, anchor="w", justify="left",
            ).pack(fill="x", padx=14, anchor="w")

        buttons = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        buttons.pack(pady=(10, 12))
        tk.Button(buttons, text=confirm_text, width=10, command=self.confirm).pack(side="left", padx=4)
        tk.Button(buttons, text="Cancel", width=10, command=self.cancel).pack(side="left", padx=4)
        self.bind("<Return>", lambda event: self.confirm())

    def confirm(self):
        self.result = self.choice.get()
        self.destroy()

def ask_date(parent, title, message, initial_iso=None):
    return DateDialog(parent, title, message, initial_iso or date.today().isoformat()).show()

def ask_choice(parent, title, message, options, confirm_text="OK", default_index=0):
    return ChoiceDialog(parent, title, message, options, confirm_text, default_index).show()


# --- Default Reference Texts ---
# Written to reference_texts.json on first start.
GLOSSARY_ENTRIES = [
    (
        "ADR",
        "European Agreement concerning the International Carriage of Dangerous Goods by Road",
        "ADR is the international agreement that sets the rules for transporting dangerous "
        "goods by road. It defines the classes of dangerous goods, the required packaging, "
        "labels, vehicle markings (such as orange plates) and the documents that have to be "
        "carried.\n"
        "\n"
        "The abbreviation comes from the French name: Accord européen relatif au transport "
        "international des marchandises Dangereuses par Route.",
    ),
    (
        "ERICard",
        "Emergency Response Intervention Card",
        "An ERICard is a short emergency card with guidance for the first response to an "
        "incident involving a dangerous substance. It is meant for emergency responders such "
        "as fire brigades and summarises the main hazards and the recommended actions.\n"
        "\n"
        "Often one card covers several related substances. In this program every ERICard has "
        "its own page and can be marked as collected.",
    ),
    (
        "UN number",
        "United Nations number",
        "A four-digit number that identifies a dangerous substance or a group of similar "
        "substances in transport, for example UN 1203 for gasoline.\n"
        "\n"
        "It is shown on the orange plate below the hazard number and written in the transport"
        " documents. The numbers are assigned by the United Nations Committee of Experts on "
        "the Transport of Dangerous Goods.",
    ),
    (
        "Hazard number",
        "Hazard identification number (Kemler number)",
        "The hazard number has two or three digits and is shown in the top half of the orange"
        " plate. Each digit stands for a hazard:\n"
        "\n"
        "2 – emission of gas due to pressure or chemical reaction\n"
        "3 – flammability of liquids (vapours) and gases, or self-heating liquid\n"
        "4 – flammability of solids, or self-heating solid\n"
        "5 – oxidizing (fire-intensifying) effect\n"
        "6 – toxicity or risk of infection\n"
        "7 – radioactivity\n"
        "8 – corrosivity\n"
        "9 – risk of spontaneous violent reaction\n"
        "\n"
        "A doubled digit (e.g. 33) means the hazard is intensified. A zero as second digit "
        "(e.g. 30) means there is no additional hazard. The letter X in front (e.g. X423) "
        "means the substance reacts dangerously with water.",
    ),
    (
        "Orange plate",
        "Orange-coloured plate",
        "A rectangular orange plate on vehicles that carry dangerous goods. The upper number "
        "is the hazard number, the lower number is the UN number.\n"
        "\n"
        "A plate without numbers only shows that dangerous goods are being carried, not which"
        " ones.",
    ),
    (
        "ADR class",
        "ADR class of dangerous goods",
        "ADR sorts dangerous goods into nine classes by their main hazard:\n"
        "\n"
        "1 – Explosive substances and articles\n"
        "2 – Gases (2.1 flammable, 2.2 non-flammable and non-toxic, 2.3 toxic)\n"
        "3 – Flammable liquids\n"
        "4.1 – Flammable solids, self-reactive substances, polymerizing substances and "
        "desensitized explosives\n"
        "4.2 – Substances liable to spontaneous combustion\n"
        "4.3 – Substances which emit flammable gases in contact with water\n"
        "5.1 – Oxidizing substances\n"
        "5.2 – Organic peroxides\n"
        "6.1 – Toxic substances\n"
        "6.2 – Infectious substances\n"
        "7 – Radioactive material\n"
        "8 – Corrosive substances\n"
        "9 – Miscellaneous dangerous substances and articles\n"
        "\n"
        "A substance can have secondary hazards, which is why one card may show several "
        "classes.",
    ),
    (
        "Hazard label",
        "ADR hazard label",
        "A diamond-shaped warning label on packages, containers and tank vehicles. Its symbol"
        " and colour show the ADR class of the goods, and the class number is printed in the "
        "bottom corner.\n"
        "\n"
        "Goods with secondary hazards carry additional labels.",
    ),
    (
        "n.o.s.",
        "Not otherwise specified",
        "Used in the names of collective entries, for example \"Flammable liquid, n.o.s.\", for"
        " substances that have no entry of their own. The name is often followed by the "
        "technical name of the dangerous component.",
    ),
    (
        "LPG",
        "Liquefied petroleum gas",
        "A mixture of mainly propane and butane that is liquefied under moderate pressure. It"
        " is used as fuel for heating, cooking and vehicles.",
    ),
    (
        "GHS",
        "Globally Harmonized System of Classification and Labelling of Chemicals",
        "An international system developed by the United Nations that standardises how "
        "chemical hazards are classified and communicated: pictograms, signal words, hazard "
        "statements and precautionary statements.",
    ),
    (
        "CLP",
        "Classification, Labelling and Packaging",
        "The European Union regulation (EC) No 1272/2008 that applies the GHS in the EU. It "
        "defines the hazard classes as well as the pictograms, H statements and P statements "
        "used on chemical labels.",
    ),
    (
        "H statement",
        "Hazard statement",
        "A standardised sentence that describes the nature of a chemical's hazard, for "
        "example H301 \"Toxic if swallowed\". The code is the letter H followed by three "
        "digits:\n"
        "\n"
        "H2xx – physical hazards\n"
        "H3xx – health hazards\n"
        "H4xx – environmental hazards\n"
        "\n"
        "The full list is on the \"H & P Statements\" page.",
    ),
    (
        "EUH statement",
        "Supplemental hazard statement (EU)",
        "Additional hazard statements that exist only in the EU CLP regulation and are not "
        "part of the GHS. The code is EUH followed by three digits, for example EUH014 "
        "\"Reacts violently with water\".\n"
        "\n"
        "EUH0xx – additional physical or health properties\n"
        "EUH2xx – additional labelling information (for example allergen notices)\n"
        "EUH3xx / EUH4xx – newer hazards such as endocrine disruption\n"
        "\n"
        "They are listed on the \"H & P Statements\" page.",
    ),
    (
        "P statement",
        "Precautionary statement",
        "A standardised sentence with advice on how to prevent harm or what to do after an "
        "incident. The code is the letter P followed by three digits:\n"
        "\n"
        "P1xx – general\n"
        "P2xx – prevention\n"
        "P3xx – response\n"
        "P4xx – storage\n"
        "P5xx – disposal\n"
        "\n"
        "Codes joined by a plus sign, such as P301+P310, are combined statements.",
    ),
    (
        "Pictogram",
        "GHS hazard pictogram",
        "A black symbol on a white background inside a red-bordered diamond, for example a "
        "flame or a skull and crossbones. There are nine pictograms, GHS01 to GHS09.\n"
        "\n"
        "They are used on chemical labels and are not the same as the coloured ADR hazard "
        "labels used in transport.",
    ),
]

GHS_PICTOGRAMS = [
    ("GHS01", "Exploding bomb"),
    ("GHS02", "Flame"),
    ("GHS03", "Flame over circle"),
    ("GHS04", "Gas cylinder"),
    ("GHS05", "Corrosion"),
    ("GHS06", "Skull and crossbones"),
    ("GHS07", "Exclamation mark"),
    ("GHS08", "Health hazard"),
    ("GHS09", "Environment"),
]

H_STATEMENTS = [
    ("H200", "GHS01", "Unstable explosive."),
    ("H201", "GHS01", "Explosive; mass explosion hazard."),
    ("H202", "GHS01", "Explosive; severe projection hazard."),
    ("H203", "GHS01", "Explosive; fire, blast or projection hazard."),
    ("H204", "GHS01", "Fire or projection hazard."),
    ("H205", "GHS01", "May mass explode in fire."),
    ("H220", "GHS02", "Extremely flammable gas."),
    ("H221", "GHS02", "Flammable gas."),
    ("H222", "GHS02", "Extremely flammable aerosol."),
    ("H223", "GHS02", "Flammable aerosol."),
    ("H224", "GHS02", "Extremely flammable liquid and vapour."),
    ("H225", "GHS02", "Highly flammable liquid and vapour."),
    ("H226", "GHS02", "Flammable liquid and vapour."),
    ("H228", "GHS02", "Flammable solid."),
    ("H229", "", "Pressurised container: may burst if heated."),
    ("H230", "", "May react explosively even in the absence of air."),
    ("H231", "", "May react explosively even in the absence of air at elevated pressure and/or temperature."),
    ("H240", "GHS01", "Heating may cause an explosion."),
    ("H241", "GHS01 GHS02", "Heating may cause a fire or explosion."),
    ("H242", "GHS02", "Heating may cause a fire."),
    ("H250", "GHS02", "Catches fire spontaneously if exposed to air."),
    ("H251", "GHS02", "Self-heating; may catch fire."),
    ("H252", "GHS02", "Self-heating in large quantities; may catch fire."),
    ("H260", "GHS02", "In contact with water releases flammable gases which may ignite spontaneously."),
    ("H261", "GHS02", "In contact with water releases flammable gas."),
    ("H270", "GHS03", "May cause or intensify fire; oxidiser."),
    ("H271", "GHS03", "May cause fire or explosion; strong oxidiser."),
    ("H272", "GHS03", "May intensify fire; oxidiser."),
    ("H280", "GHS04", "Contains gas under pressure; may explode if heated."),
    ("H281", "GHS04", "Contains refrigerated gas; may cause cryogenic burns or injury."),
    ("H290", "GHS05", "May be corrosive to metals."),
    ("H300", "GHS06", "Fatal if swallowed."),
    ("H301", "GHS06", "Toxic if swallowed."),
    ("H302", "GHS07", "Harmful if swallowed."),
    ("H304", "GHS08", "May be fatal if swallowed and enters airways."),
    ("H310", "GHS06", "Fatal in contact with skin."),
    ("H311", "GHS06", "Toxic in contact with skin."),
    ("H312", "GHS07", "Harmful in contact with skin."),
    ("H314", "GHS05", "Causes severe skin burns and eye damage."),
    ("H315", "GHS07", "Causes skin irritation."),
    ("H317", "GHS07", "May cause an allergic skin reaction."),
    ("H318", "GHS05", "Causes serious eye damage."),
    ("H319", "GHS07", "Causes serious eye irritation."),
    ("H330", "GHS06", "Fatal if inhaled."),
    ("H331", "GHS06", "Toxic if inhaled."),
    ("H332", "GHS07", "Harmful if inhaled."),
    ("H334", "GHS08", "May cause allergy or asthma symptoms or breathing difficulties if inhaled."),
    ("H335", "GHS07", "May cause respiratory irritation."),
    ("H336", "GHS07", "May cause drowsiness or dizziness."),
    ("H340", "GHS08", "May cause genetic defects."),
    ("H341", "GHS08", "Suspected of causing genetic defects."),
    ("H350", "GHS08", "May cause cancer."),
    ("H351", "GHS08", "Suspected of causing cancer."),
    ("H360", "GHS08", "May damage fertility or the unborn child."),
    ("H361", "GHS08", "Suspected of damaging fertility or the unborn child."),
    ("H362", "", "May cause harm to breast-fed children."),
    ("H370", "GHS08", "Causes damage to organs."),
    ("H371", "GHS08", "May cause damage to organs."),
    ("H372", "GHS08", "Causes damage to organs through prolonged or repeated exposure."),
    ("H373", "GHS08", "May cause damage to organs through prolonged or repeated exposure."),
    ("H400", "GHS09", "Very toxic to aquatic life."),
    ("H410", "GHS09", "Very toxic to aquatic life with long lasting effects."),
    ("H411", "GHS09", "Toxic to aquatic life with long lasting effects."),
    ("H412", "", "Harmful to aquatic life with long lasting effects."),
    ("H413", "", "May cause long lasting harmful effects to aquatic life."),
    ("H420", "GHS07", "Harms public health and the environment by destroying ozone in the upper atmosphere."),
    ("H232", "GHS02", "May ignite spontaneously if exposed to air."),
    ("H350i", "GHS08", "May cause cancer by inhalation."),
    ("H360F", "GHS08", "May damage fertility."),
    ("H360D", "GHS08", "May damage the unborn child."),
    ("H360FD", "GHS08", "May damage fertility. May damage the unborn child."),
    ("H360Fd", "GHS08", "May damage fertility. Suspected of damaging the unborn child."),
    ("H360Df", "GHS08", "May damage the unborn child. Suspected of damaging fertility."),
    ("H361f", "GHS08", "Suspected of damaging fertility."),
    ("H361d", "GHS08", "Suspected of damaging the unborn child."),
    ("H361fd", "GHS08", "Suspected of damaging fertility. Suspected of damaging the unborn child."),
    ("H300+H310", "GHS06", "Fatal if swallowed or in contact with skin."),
    ("H300+H330", "GHS06", "Fatal if swallowed or if inhaled."),
    ("H310+H330", "GHS06", "Fatal in contact with skin or if inhaled."),
    ("H300+H310+H330", "GHS06", "Fatal if swallowed, in contact with skin or if inhaled."),
    ("H301+H311", "GHS06", "Toxic if swallowed or in contact with skin."),
    ("H301+H331", "GHS06", "Toxic if swallowed or if inhaled."),
    ("H311+H331", "GHS06", "Toxic in contact with skin or if inhaled."),
    ("H301+H311+H331", "GHS06", "Toxic if swallowed, in contact with skin or if inhaled."),
    ("H302+H312", "GHS07", "Harmful if swallowed or in contact with skin."),
    ("H302+H332", "GHS07", "Harmful if swallowed or if inhaled."),
    ("H312+H332", "GHS07", "Harmful in contact with skin or if inhaled."),
    ("H302+H312+H332", "GHS07", "Harmful if swallowed, in contact with skin or if inhaled."),
]

EUH_STATEMENTS = [
    ("EUH001", "Explosive when dry."),
    ("EUH014", "Reacts violently with water."),
    ("EUH018", "In use may form flammable/explosive vapour-air mixture."),
    ("EUH019", "May form explosive peroxides."),
    ("EUH044", "Risk of explosion if heated under confinement."),
    ("EUH029", "Contact with water liberates toxic gas."),
    ("EUH031", "Contact with acids liberates toxic gas."),
    ("EUH032", "Contact with acids liberates very toxic gas."),
    ("EUH066", "Repeated exposure may cause skin dryness or cracking."),
    ("EUH070", "Toxic by eye contact."),
    ("EUH071", "Corrosive to the respiratory tract."),
    ("EUH201", "Contains lead. Should not be used on surfaces liable to be chewed or sucked by children."),
    ("EUH201A", "Warning! Contains lead."),
    ("EUH202", "Cyanoacrylate. Danger. Bonds skin and eyes in seconds. Keep out of the reach of children."),
    ("EUH203", "Contains chromium (VI). May produce an allergic reaction."),
    ("EUH204", "Contains isocyanates. May produce an allergic reaction."),
    ("EUH205", "Contains epoxy constituents. May produce an allergic reaction."),
    ("EUH206", "Warning! Do not use together with other products. May release dangerous gases (chlorine)."),
    (
        "EUH207",
        "Warning! Contains cadmium. Dangerous fumes are formed during use. See information "
        "supplied by the manufacturer. Comply with the safety instructions.",
    ),
    ("EUH208", "Contains (name of sensitising substance). May produce an allergic reaction."),
    ("EUH209", "Can become highly flammable in use."),
    ("EUH209A", "Can become flammable in use."),
    ("EUH210", "Safety data sheet available on request."),
    ("EUH211", "Warning! Hazardous respirable droplets may be formed when sprayed. Do not breathe spray or mist."),
    ("EUH212", "Warning! Hazardous respirable dust may be formed when used. Do not breathe dust."),
    ("EUH380", "May cause endocrine disruption in humans."),
    ("EUH381", "Suspected of causing endocrine disruption in humans."),
    ("EUH401", "To avoid risks to human health and the environment, comply with the instructions for use."),
    ("EUH430", "May cause endocrine disruption in the environment."),
    ("EUH431", "Suspected of causing endocrine disruption in the environment."),
    ("EUH440", "Accumulates in the environment and living organisms including in humans."),
    ("EUH441", "Strongly accumulates in the environment and living organisms including in humans."),
    ("EUH450", "Can cause long-lasting and diffuse contamination of water resources."),
    ("EUH451", "Can cause very long-lasting and diffuse contamination of water resources."),
]

P_STATEMENTS = [
    ("P101", "If medical advice is needed, have product container or label at hand."),
    ("P102", "Keep out of reach of children."),
    ("P103", "Read label before use."),
    ("P201", "Obtain special instructions before use."),
    ("P202", "Do not handle until all safety precautions have been read and understood."),
    ("P210", "Keep away from heat, hot surfaces, sparks, open flames and other ignition sources. No smoking."),
    ("P211", "Do not spray on an open flame or other ignition source."),
    ("P220", "Keep away from clothing and other combustible materials."),
    ("P221", "Take any precaution to avoid mixing with combustibles..."),
    ("P222", "Do not allow contact with air."),
    ("P223", "Do not allow contact with water."),
    ("P230", "Keep wetted with..."),
    ("P231", "Handle and store contents under inert gas/..."),
    ("P232", "Protect from moisture."),
    ("P233", "Keep container tightly closed."),
    ("P234", "Keep only in original packaging."),
    ("P235", "Keep cool."),
    ("P240", "Ground and bond container and receiving equipment."),
    ("P241", "Use explosion-proof electrical/ventilating/lighting/... equipment."),
    ("P242", "Use non-sparking tools."),
    ("P243", "Take action to prevent static discharges."),
    ("P244", "Keep valves and fittings free from oil and grease."),
    ("P250", "Do not subject to grinding/shock/friction/..."),
    ("P251", "Do not pierce or burn, even after use."),
    ("P260", "Do not breathe dust/fume/gas/mist/vapours/spray."),
    ("P261", "Avoid breathing dust/fume/gas/mist/vapours/spray."),
    ("P262", "Do not get in eyes, on skin, or on clothing."),
    ("P263", "Avoid contact during pregnancy/while nursing."),
    ("P264", "Wash ... thoroughly after handling."),
    ("P270", "Do not eat, drink or smoke when using this product."),
    ("P271", "Use only outdoors or in a well-ventilated area."),
    ("P272", "Contaminated work clothing should not be allowed out of the workplace."),
    ("P273", "Avoid release to the environment."),
    ("P280", "Wear protective gloves/protective clothing/eye protection/face protection/..."),
    ("P282", "Wear cold insulating gloves/face shield/eye protection."),
    ("P283", "Wear fire resistant or flame retardant clothing."),
    ("P284", "[In case of inadequate ventilation] wear respiratory protection."),
    ("P301", "IF SWALLOWED:"),
    ("P302", "IF ON SKIN:"),
    ("P303", "IF ON SKIN (or hair):"),
    ("P304", "IF INHALED:"),
    ("P305", "IF IN EYES:"),
    ("P306", "IF ON CLOTHING:"),
    ("P308", "IF exposed or concerned:"),
    ("P310", "Immediately call a POISON CENTER/doctor/..."),
    ("P311", "Call a POISON CENTER/doctor/..."),
    ("P312", "Call a POISON CENTER/doctor/... if you feel unwell."),
    ("P313", "Get medical advice/attention."),
    ("P314", "Get medical advice/attention if you feel unwell."),
    ("P315", "Get immediate medical advice/attention."),
    ("P320", "Specific treatment is urgent (see ... on this label)."),
    ("P321", "Specific treatment (see ... on this label)."),
    ("P330", "Rinse mouth."),
    ("P331", "Do NOT induce vomiting."),
    ("P332", "If skin irritation occurs:"),
    ("P333", "If skin irritation or rash occurs:"),
    ("P334", "Immerse in cool water [or wrap in wet bandages]."),
    ("P335", "Brush off loose particles from skin."),
    ("P336", "Thaw frosted parts with lukewarm water. Do not rub affected area."),
    ("P337", "If eye irritation persists:"),
    ("P338", "Remove contact lenses, if present and easy to do. Continue rinsing."),
    ("P340", "Remove person to fresh air and keep comfortable for breathing."),
    ("P342", "If experiencing respiratory symptoms:"),
    ("P351", "Rinse cautiously with water for several minutes."),
    ("P352", "Wash with plenty of water/..."),
    ("P353", "Rinse skin with water [or shower]."),
    ("P360", "Rinse immediately contaminated clothing and skin with plenty of water before removing clothes."),
    ("P361", "Take off immediately all contaminated clothing."),
    ("P362", "Take off contaminated clothing."),
    ("P363", "Wash contaminated clothing before reuse."),
    ("P364", "And wash it before reuse."),
    ("P370", "In case of fire:"),
    ("P371", "In case of major fire and large quantities:"),
    ("P372", "Explosion risk."),
    ("P373", "DO NOT fight fire when fire reaches explosives."),
    ("P375", "Fight fire remotely due to the risk of explosion."),
    ("P376", "Stop leak if safe to do so."),
    ("P377", "Leaking gas fire: Do not extinguish, unless leak can be stopped safely."),
    ("P378", "Use ... to extinguish."),
    ("P380", "Evacuate area."),
    ("P381", "Eliminate all ignition sources if safe to do so."),
    ("P390", "Absorb spillage to prevent material damage."),
    ("P391", "Collect spillage."),
    ("P401", "Store in accordance with..."),
    ("P402", "Store in a dry place."),
    ("P403", "Store in a well-ventilated place."),
    ("P404", "Store in a closed container."),
    ("P405", "Store locked up."),
    ("P406", "Store in a corrosion resistant/... container with a resistant inner liner."),
    ("P407", "Maintain air gap between stacks or pallets."),
    ("P410", "Protect from sunlight."),
    ("P411", "Store at temperatures not exceeding ... °C/... °F."),
    ("P412", "Do not expose to temperatures exceeding 50 °C/122 °F."),
    ("P413", "Store bulk masses greater than ... kg/... lbs at temperatures not exceeding ... °C/... °F."),
    ("P420", "Store separately."),
    ("P422", "Store contents under..."),
    ("P501", "Dispose of contents/container to..."),
    ("P502", "Refer to manufacturer or supplier for information on recovery or recycling."),
    ("P231+P232", "Handle and store contents under inert gas/... Protect from moisture."),
    ("P235+P410", "Keep cool. Protect from sunlight."),
    ("P301+P310", "IF SWALLOWED: Immediately call a POISON CENTER/doctor/..."),
    ("P301+P312", "IF SWALLOWED: Call a POISON CENTER/doctor/... if you feel unwell."),
    ("P301+P330+P331", "IF SWALLOWED: Rinse mouth. Do NOT induce vomiting."),
    ("P302+P334", "IF ON SKIN: Immerse in cool water [or wrap in wet bandages]."),
    ("P302+P352", "IF ON SKIN: Wash with plenty of water/..."),
    (
        "P303+P361+P353",
        "IF ON SKIN (or hair): Take off immediately all contaminated clothing. Rinse skin "
        "with water [or shower].",
    ),
    ("P304+P312", "IF INHALED: Call a POISON CENTER/doctor/... if you feel unwell."),
    ("P304+P340", "IF INHALED: Remove person to fresh air and keep comfortable for breathing."),
    (
        "P305+P351+P338",
        "IF IN EYES: Rinse cautiously with water for several minutes. Remove contact lenses, "
        "if present and easy to do. Continue rinsing.",
    ),
    (
        "P306+P360",
        "IF ON CLOTHING: Rinse immediately contaminated clothing and skin with plenty of "
        "water before removing clothes.",
    ),
    ("P308+P311", "IF exposed or concerned: Call a POISON CENTER/doctor/..."),
    ("P308+P313", "IF exposed or concerned: Get medical advice/attention."),
    ("P332+P313", "If skin irritation occurs: Get medical advice/attention."),
    ("P333+P313", "If skin irritation or rash occurs: Get medical advice/attention."),
    ("P335+P334", "Brush off loose particles from skin. Immerse in cool water [or wrap in wet bandages]."),
    ("P337+P313", "If eye irritation persists: Get medical advice/attention."),
    ("P342+P311", "If experiencing respiratory symptoms: Call a POISON CENTER/doctor/..."),
    ("P361+P364", "Take off immediately all contaminated clothing and wash it before reuse."),
    ("P362+P364", "Take off contaminated clothing and wash it before reuse."),
    ("P370+P376", "In case of fire: Stop leak if safe to do so."),
    ("P370+P378", "In case of fire: Use ... to extinguish."),
    ("P370+P380", "In case of fire: Evacuate area."),
    ("P370+P380+P375", "In case of fire: Evacuate area. Fight fire remotely due to the risk of explosion."),
    (
        "P371+P380+P375",
        "In case of major fire and large quantities: Evacuate area. Fight fire remotely due "
        "to the risk of explosion.",
    ),
    ("P402+P404", "Store in a dry place. Store in a closed container."),
    ("P403+P233", "Store in a well-ventilated place. Keep container tightly closed."),
    ("P403+P235", "Store in a well-ventilated place. Keep cool."),
    ("P410+P403", "Protect from sunlight. Store in a well-ventilated place."),
    ("P410+P412", "Protect from sunlight. Do not expose to temperatures exceeding 50 °C/122 °F."),
    ("P411+P235", "Store at temperatures not exceeding ... °C/... °F. Keep cool."),
]

def build_default_reference_texts():
    language = DEFAULT_LANGUAGE
    return {
        "schema_version": SCHEMA_VERSION,
        "languages": {language: "English"},
        "glossary": {
            term: {"order": index, "title": {language: title}, "text": {language: text}}
            for index, (term, title, text) in enumerate(GLOSSARY_ENTRIES, start=1)
        },
        "pictograms": {code: {"name": {language: name}} for code, name in GHS_PICTOGRAMS},
        "hazard_statements": {
            code: {"pictograms": pictograms.split(), "text": {language: text}}
            for code, pictograms, text in H_STATEMENTS
        },
        "supplemental_statements": {code: {"text": {language: text}} for code, text in EUH_STATEMENTS},
        "precautionary_statements": {code: {"text": {language: text}} for code, text in P_STATEMENTS},
    }


# --- Data Models ---
LIST_FIELDS = ("un_numbers", "substance_names", "adr_classes", "hazard_numbers", "known_hazards", "adr_labels")

def to_string_list(value):
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]

def normalize_card(raw):
    if not isinstance(raw, dict):
        return None
    number = str(raw.get("ericard_number", "")).strip()
    if not number:
        return None

    card = {"ericard_number": number}
    for field in LIST_FIELDS:
        card[field] = to_string_list(raw.get(field))
    card["un_numbers"] = [re.sub(r"^UN\s*", "", un, flags=re.IGNORECASE) for un in card["un_numbers"]]
    card["description"] = str(raw.get("description") or "").strip()
    card["verified"] = bool(raw.get("verified", True))

    for key, value in raw.items():
        card.setdefault(key, value)
    return card

def validate_card(card):
    warnings = []
    for un in card["un_numbers"]:
        if not re.fullmatch(r"\d{4}", un):
            warnings.append(f"UN number '{un}' is not a 4-digit number")
    if not card["substance_names"]:
        warnings.append("no substance name")
    return warnings


# --- Card Details ---
def card_substances(card):
    # Returns [(UN number, substance name, hazard number)]
    rows = []
    raw = card.get("substances")
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict):
                rows.append((
                    str(entry.get("un", "")).strip(),
                    str(entry.get("name", "")).strip(),
                    str(entry.get("hin", "")).strip(),
                ))
    if rows:
        return rows
    numbers, names = card["un_numbers"], card["substance_names"]
    return [
        (numbers[i] if i < len(numbers) else "", names[i] if i < len(names) else "", "")
        for i in range(max(len(numbers), len(names)))
    ]

def card_sections(card):
    # Returns [(heading, [lines])] in the order stored in the database
    raw = card.get("sections")
    if not isinstance(raw, dict):
        return []
    return [(str(heading), to_string_list(lines)) for heading, lines in raw.items()]

def _reference_pairs(card, field, key_name, value_name):
    reference = card.get("reference")
    entries = reference.get(field) if isinstance(reference, dict) else None
    pairs = {}
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and entry.get(key_name) and entry.get(value_name):
                pairs.setdefault(str(entry[key_name]), str(entry[value_name]))
    return pairs

def card_class_names(card):
    return _reference_pairs(card, "classes", "adr_class", "name")

def card_hazard_meanings(card):
    return _reference_pairs(card, "hazard_numbers", "hin", "meaning")

def card_source_url(card):
    url = str(card.get("source_url") or "").strip()
    return url if url.startswith(("http://", "https://")) else ""


# --- Substances ---
def substance_key(un):
    return re.sub(r"^UN\s*", "", str(un).strip(), flags=re.IGNORECASE).strip()

def build_substance_index(database):
    records = {}
    for card in database.sorted_cards():
        number = card["ericard_number"]
        for un, name, hazard in card_substances(card):
            key = substance_key(un)
            if not key:
                continue
            record = records.setdefault(key, {
                "un": key, "names": [], "hazard_numbers": [], "adr_classes": [], "cards": [], "entries": [],
            })
            if name and name not in record["names"]:
                record["names"].append(name)
            if hazard and hazard not in record["hazard_numbers"]:
                record["hazard_numbers"].append(hazard)
            for adr_class in card["adr_classes"]:
                if adr_class not in record["adr_classes"]:
                    record["adr_classes"].append(adr_class)
            if number not in record["cards"]:
                record["cards"].append(number)
            record["entries"].append((name, hazard, number))

    for record in records.values():
        record["adr_classes"].sort(key=natural_sort_key)
        record["hazard_numbers"].sort(key=natural_sort_key)
        record["search_text"] = " ".join(
            [record["un"], "un" + record["un"], *record["names"], *record["adr_classes"], *record["hazard_numbers"],
             *record["cards"], *[compact(number) for number in record["cards"]]]
        ).lower()
    return records


class CardDatabase:
    # There is no built-in data: the database is whatever was loaded from a JSON file.
    def __init__(self):
        self.cards = {}
        self.meta = {}          # top-level fields of the file (source, language, ...) are kept on save
        self.last_updated = ""
        self.load_warning = None
        self._substances = None
        self._sorted_substances = None
        self.load()

    # --- Loading and Saving ---
    def load(self):
        self._substances = None
        self._sorted_substances = None
        data, self.load_warning = load_json(DATABASE_FILE, {})

        self.meta = {key: value for key, value in data.items() if key != "cards"} if isinstance(data, dict) else {}
        self.last_updated = str(self.meta.get("last_updated", ""))
        raw_cards = data.get("cards", []) if isinstance(data, dict) else data
        cards, _, _ = self.parse_cards(raw_cards)
        self.cards = {card_key(card["ericard_number"]): card for card in cards}

    def save(self, last_updated=None):
        self.last_updated = last_updated or date.today().isoformat()
        payload = {"schema_version": SCHEMA_VERSION, "last_updated": self.last_updated}
        payload.update({k: v for k, v in self.meta.items() if k not in ("schema_version", "last_updated", "cards")})
        payload["cards"] = self.sorted_cards()
        save_json(DATABASE_FILE, payload)

    def backup(self):
        if not os.path.exists(DATABASE_FILE):
            return None
        backup_path = os.path.join(BACKUP_DIR, f"ericards_db-{datetime.now():%Y%m%d-%H%M%S}.json")
        shutil.copy2(DATABASE_FILE, backup_path)
        return backup_path

    # --- Queries ---
    def get(self, key):
        return self.cards.get(card_key(key))

    def sorted_cards(self):
        return sorted(self.cards.values(), key=lambda card: natural_sort_key(card["ericard_number"]))

    @property
    def language(self):
        return str(self.meta.get("language", "")).strip()

    def substances(self):
        # {UN number: record}, built on first use and rebuilt after the cards change
        if self._substances is None:
            self._substances = build_substance_index(self)
            self._sorted_substances = sorted(
                self._substances.values(), key=lambda record: natural_sort_key(record["un"]),
            )
        return self._substances

    def get_substance(self, key):
        return self.substances().get(substance_key(key))

    def sorted_substances(self):
        self.substances()
        return self._sorted_substances

    # --- Importing ---
    @staticmethod
    def parse_cards(raw_cards):
        # Returns (valid cards without duplicates, number of skipped entries, list of problem descriptions)
        if not isinstance(raw_cards, list):
            return [], 0, ["The file does not contain a list of cards."]
        unique, skipped, problems = {}, 0, []
        for index, raw in enumerate(raw_cards, start=1):
            card = normalize_card(raw)
            if card is None:
                skipped += 1
                problems.append(f"Entry {index}: skipped (not an object with an 'ericard_number')")
                continue
            key = card_key(card["ericard_number"])
            if key in unique:
                problems.append(f"Entry {index}: ERICard {card['ericard_number']} appears twice (the last one is used)")
            for warning in validate_card(card):
                problems.append(f"ERICard {card['ericard_number']}: {warning}")
            unique[key] = card
        return list(unique.values()), skipped, problems

    @classmethod
    def parse_import(cls, data):
        if isinstance(data, dict):
            if "cards" not in data:
                return [], 0, ["The file has no 'cards' list."]
            return cls.parse_cards(data["cards"])
        return cls.parse_cards(data)

    @staticmethod
    def extract_meta(data):
        return {key: value for key, value in data.items() if key != "cards"} if isinstance(data, dict) else {}

    def plan_import(self, cards, replace):
        # Returns (resulting cards, statistics) without changing anything yet
        incoming = {card_key(card["ericard_number"]): card for card in cards}
        result = dict(incoming) if replace else {**self.cards, **incoming}
        added = sum(1 for key in incoming if key not in self.cards)
        updated = sum(1 for key, card in incoming.items() if key in self.cards and self.cards[key] != card)
        removed = sum(1 for key in self.cards if key not in result)
        return result, {
            "added": added,
            "updated": updated,
            "unchanged": len(incoming) - added - updated,
            "removed": removed,
        }

    def apply_plan(self, result, meta, replace):
        self.cards = result
        self._substances = None
        self._sorted_substances = None
        if replace or not self.meta:
            self.meta = {key: value for key, value in (meta or {}).items() if key != "cards"}
        # A replaced database keeps the date it was published with; a merge counts as updated today
        self.save(last_updated=str(self.meta.get("last_updated", "")) or None if replace else None)


class CollectionSection:
    def __init__(self, normalize_key):
        self.normalize_key = normalize_key
        self.entries = {}

    def load(self, raw):
        self.entries = {}
        if isinstance(raw, dict):
            for key, entry in raw.items():
                if isinstance(entry, dict):
                    self.entries[self.normalize_key(key)] = {"date": str(entry.get("date", ""))}

    def is_checked(self, key):
        return self.normalize_key(key) in self.entries

    def get_date(self, key):
        return self.entries.get(self.normalize_key(key), {}).get("date", "")

    def parse_import(self, raw):
        # Returns (entries, number of skipped entries, list of problem descriptions)
        entries, skipped, problems = {}, 0, []
        for key, entry in raw.items():
            parsed = parse_iso_date(entry.get("date", "")) if isinstance(entry, dict) else None
            if parsed is None:
                skipped += 1
                problems.append(f"{key}: missing or invalid date")
                continue
            entries[self.normalize_key(key)] = {"date": parsed.isoformat()}
        return entries, skipped, problems

    def merge_plan(self, imported, mode):
        # Returns (resulting entries, statistics) without changing anything yet
        if mode == IMPORT_REPLACE:
            result = dict(imported)
        else:
            result = dict(self.entries)
            for key, entry in imported.items():
                current = result.get(key)
                if current is None:
                    result[key] = entry
                elif mode == IMPORT_USE_IMPORTED:
                    result[key] = entry
                elif not current["date"] or entry["date"] < current["date"]:
                    result[key] = entry

        added = sum(1 for key in result if key not in self.entries)
        removed = sum(1 for key in self.entries if key not in result)
        changed = sum(1 for key in result if key in self.entries and result[key]["date"] != self.entries[key]["date"])
        unchanged = sum(1 for key in result if key in self.entries) - changed
        return result, {"added": added, "changed": changed, "unchanged": unchanged, "removed": removed}


class CollectionStore:
    FIELDS = {KIND_ERICARDS: "checked", KIND_SUBSTANCES: "substances_checked"}

    def __init__(self):
        self.ericards = CollectionSection(card_key)
        self.substances = CollectionSection(substance_key)
        self.load_warning = None
        self.load()

    def section(self, kind):
        return self.substances if kind == KIND_SUBSTANCES else self.ericards

    # --- Loading and Saving ---
    def load(self):
        data, self.load_warning = load_json(COLLECTION_FILE, {})
        data = data if isinstance(data, dict) else {}
        self.ericards.load(data.get(self.FIELDS[KIND_ERICARDS]))
        self.substances.load(data.get(self.FIELDS[KIND_SUBSTANCES]))

    def save(self):
        save_json(COLLECTION_FILE, {
            "schema_version": SCHEMA_VERSION,
            self.FIELDS[KIND_ERICARDS]: self.ericards.entries,
            self.FIELDS[KIND_SUBSTANCES]: self.substances.entries,
        })

    def backup(self):
        if not os.path.exists(COLLECTION_FILE):
            return None
        backup_path = os.path.join(BACKUP_DIR, f"collection-{datetime.now():%Y%m%d-%H%M%S}.json")
        shutil.copy2(COLLECTION_FILE, backup_path)
        return backup_path

    # --- Changes ---
    def set_entry(self, kind, key, iso_date):
        section = self.section(kind)
        section.entries[section.normalize_key(key)] = {"date": iso_date}
        self.save()

    def remove_entry(self, kind, key):
        section = self.section(kind)
        section.entries.pop(section.normalize_key(key), None)
        self.save()

    # --- ERICard shortcuts ---
    def is_checked(self, number):
        return self.ericards.is_checked(number)

    def get_date(self, number):
        return self.ericards.get_date(number)

    # --- Export and Import ---
    def export_data(self):
        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            self.FIELDS[KIND_ERICARDS]: self.ericards.entries,
            self.FIELDS[KIND_SUBSTANCES]: self.substances.entries,
        }

    def parse_import(self, data):
        # Returns ({kind: entries, or None if the file has no such section}, skipped, problems).
        # A section missing from the file (for example in an export from an older version)
        # stays None, so it is left untouched even when the whole collection is replaced.
        if not isinstance(data, dict):
            return {}, 0, ["The file is not a collection export."]
        imported, skipped, problems = {}, 0, []
        for kind, field in self.FIELDS.items():
            raw = data.get(field)
            if raw is None:
                imported[kind] = None
            elif not isinstance(raw, dict):
                imported[kind] = None
                problems.append(f"'{field}' is not an object and was ignored")
            else:
                entries, bad, section_problems = self.section(kind).parse_import(raw)
                imported[kind] = entries
                skipped += bad
                problems += [f"{field}: {problem}" for problem in section_problems]
        return imported, skipped, problems

    def merge_plan(self, imported, mode):
        # Returns ({kind: resulting entries}, {kind: statistics}) for every section present in the file
        results, stats = {}, {}
        for kind, entries in imported.items():
            if entries is not None:
                results[kind], stats[kind] = self.section(kind).merge_plan(entries, mode)
        return results, stats

    def apply_plan(self, results):
        for kind, entries in results.items():
            self.section(kind).entries = entries
        self.save()


class SettingsStore:
    def __init__(self):
        data, self.load_warning = load_json(SETTINGS_FILE, {})
        data = data if isinstance(data, dict) else {}
        if "info_language" in data:
            data.setdefault("reference_language", data["info_language"])
            del data["info_language"]
        self.values = {**DEFAULT_SETTINGS, **data}

    def get(self, key):
        return self.values.get(key, DEFAULT_SETTINGS.get(key))

    def set(self, key, value):
        self.values[key] = value
        save_json(SETTINGS_FILE, self.values)


# --- Reference Texts ---
LANGUAGE_CODE_PATTERN = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
H_CATEGORIES = {"2": "Physical", "3": "Health", "4": "Environmental"}
P_CATEGORIES = {"1": "General", "2": "Prevention", "3": "Response", "4": "Storage", "5": "Disposal"}
EUH_CATEGORY = "Supplemental"
STATEMENT_SECTIONS = {
    "H": "hazard_statements",
    "EUH": "supplemental_statements",
    "P": "precautionary_statements",
}

class ReferenceTexts:
    def __init__(self):
        self.data = {}
        self.load_warning = None
        self.load()

    # --- Loading ---
    def load(self):
        if not os.path.exists(REFERENCE_FILE):
            save_json(REFERENCE_FILE, build_default_reference_texts())
        data, self.load_warning = load_json(REFERENCE_FILE, {})
        self.data = data if isinstance(data, dict) else {}

    def _entries(self, section):
        entries = self.data.get(section, {})
        if not isinstance(entries, dict):
            return {}
        return {str(key): value for key, value in entries.items() if isinstance(value, dict)}

    # --- Languages ---
    def languages(self):
        names = {}
        declared = self.data.get("languages", {})
        if isinstance(declared, dict):
            for code, name in declared.items():
                names[str(code)] = str(name)
        for section in ("glossary", "pictograms", "hazard_statements", "supplemental_statements", "precautionary_statements"):
            for entry in self._entries(section).values():
                for field in ("title", "text", "name"):
                    values = entry.get(field)
                    if isinstance(values, dict):
                        for code in values:
                            if LANGUAGE_CODE_PATTERN.match(str(code)):
                                names.setdefault(str(code), str(code))
        ordered = sorted(names, key=lambda code: (code != DEFAULT_LANGUAGE, code))
        return {code: names[code] for code in ordered}

    @staticmethod
    def pick(values, language):
        # Returns (text, language actually used). Falls back to English, then to any language.
        if isinstance(values, str):
            return values, language
        if not isinstance(values, dict):
            return "", language
        for code in (language, DEFAULT_LANGUAGE):
            text = values.get(code)
            if isinstance(text, str) and text.strip():
                return text, code
        for code, text in values.items():
            if isinstance(text, str) and text.strip():
                return text, str(code)
        return "", language

    # --- Glossary ---
    def glossary(self, language):
        rows = []
        for term, entry in self._entries("glossary").items():
            title, _ = self.pick(entry.get("title"), language)
            text, used_language = self.pick(entry.get("text"), language)
            order = entry.get("order")
            rows.append({
                "term": term,
                "title": title,
                "text": text,
                "used_language": used_language,
                "order": order if isinstance(order, (int, float)) else 1000,
            })
        rows.sort(key=lambda row: (row["order"], row["term"].lower()))
        return rows

    def glossary_entry(self, term, language):
        for row in self.glossary(language):
            if row["term"] == term:
                return row
        return None

    # --- Statements ---
    def statements(self, kind, language):
        categories = H_CATEGORIES if kind == "H" else P_CATEGORIES
        rows = []
        for code, entry in self._entries(STATEMENT_SECTIONS[kind]).items():
            text, _ = self.pick(entry.get("text"), language)
            match = re.match(r"^[A-Za-z]*?(\d)", code)
            pictograms = to_string_list(entry.get("pictograms"))
            rows.append({
                "code": code,
                "kind": kind,
                "category": EUH_CATEGORY if kind == "EUH" else categories.get(match.group(1), "Other") if match else "Other",
                "text": text,
                "pictograms": pictograms,
            })
        rows.sort(key=lambda row: natural_sort_key(row["code"]))
        return rows

    def pictogram_name(self, code, language):
        entry = self._entries("pictograms").get(code, {})
        return self.pick(entry.get("name"), language)[0]


# --- Search Logic ---
def card_matches(card, query, category):
    query = query.strip().lower()
    if not query:
        return True

    if category == "UN Number":
        wanted = re.sub(r"^un\s*", "", query)
        return any(wanted in un.lower() for un in card["un_numbers"])

    if category == "Substance Name":
        names = " ".join(card["substance_names"]).lower()
        return all(token in names for token in query.split())

    if category == "ADR Class":
        wanted = re.sub(r"^(adr\s*)?(class\s*)?", "", query).strip()
        return any(c.lower() == wanted or c.lower().startswith(wanted + ".") for c in card["adr_classes"])

    if category == "Hazard Number":
        wanted = query.replace(" ", "")
        return any(wanted in hazard.lower() for hazard in card["hazard_numbers"])

    if category == "ERICard Number":
        return compact(query) in compact(card["ericard_number"])

    # --- All Fields ---
    haystack = " ".join(
        [card["ericard_number"], compact(card["ericard_number"]), card["description"]]
        + card["un_numbers"] + card["substance_names"] + card["adr_classes"]
        + card["hazard_numbers"] + card["known_hazards"]
    ).lower()
    return all(token in haystack for token in query.split())

def substance_matches(record, query, category):
    query = query.strip().lower()
    if not query:
        return True

    if category == "UN Number":
        wanted = re.sub(r"^un\s*", "", query)
        return wanted in record["un"].lower()

    if category == "Substance Name":
        names = " ".join(record["names"]).lower()
        return all(token in names for token in query.split())

    if category == "ADR Class":
        wanted = re.sub(r"^(adr\s*)?(class\s*)?", "", query).strip()
        return any(c.lower() == wanted or c.lower().startswith(wanted + ".") for c in record["adr_classes"])

    if category == "Hazard Number":
        wanted = query.replace(" ", "")
        return any(wanted in hazard.lower() for hazard in record["hazard_numbers"])

    if category == "ERICard Number":
        return any(compact(query) in compact(number) for number in record["cards"])

    # --- All Fields ---
    return all(token in record["search_text"] for token in query.split())

def statement_matches(statement, query):
    tokens = query.strip().lower().split()
    if not tokens:
        return True
    haystack = " ".join(
        [statement["code"], statement["text"], statement["category"]] + statement["pictograms"]
    ).lower()
    return all(token in haystack for token in tokens)


# --- Statistics ---
def build_stats(items, is_collected):
    total = 0
    collected = 0
    per_class = {}
    for key, adr_classes in items:
        total += 1
        collected_here = is_collected(key)
        if collected_here:
            collected += 1
        for adr_class in set(adr_classes):
            counts = per_class.setdefault(adr_class, [0, 0])
            counts[1] += 1
            if collected_here:
                counts[0] += 1

    class_rows = [
        (adr_class, counts[0], counts[1], calculate_percent(counts[0], counts[1]))
        for adr_class, counts in sorted(per_class.items(), key=lambda item: natural_sort_key(item[0]))
    ]
    return {
        "collected": collected,
        "total": total,
        "percent": calculate_percent(collected, total),
        "classes": class_rows,
    }

def calculate_stats(database, collection, kind=KIND_ERICARDS):
    section = collection.section(kind)
    if kind == KIND_SUBSTANCES:
        items = [(record["un"], record["adr_classes"]) for record in database.sorted_substances()]
    else:
        items = [(card["ericard_number"], card["adr_classes"]) for card in database.sorted_cards()]
    return build_stats(items, section.is_checked)


# --- Pages ---
class BasePage(tk.Frame):
    progress_mode = None  # KIND_* the bottom progress bar switches to while this page is shown

    def __init__(self, parent, app):
        super().__init__(parent, bg=WINDOW_BACKGROUND_COLOR)
        self.app = app

    def on_show(self, **kwargs):
        pass

class CollectionListPage(BasePage):
    kind = None
    noun = ""
    category_setting = ""
    COLUMNS = []

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.last_opened = None
        self._refresh_job = None
        self._build_widgets()

    @property
    def section(self):
        return self.app.collection.section(self.kind)

    # --- To be provided by subclasses ---
    def records(self):
        raise NotImplementedError

    def record_key(self, record):
        raise NotImplementedError

    def matches(self, record, query, category):
        raise NotImplementedError

    def row_values(self, record, is_collected):
        raise NotImplementedError

    def open_item(self, key):
        raise NotImplementedError

    # --- Widget Setup ---
    def _build_widgets(self):
        # --- Empty State (no database loaded) ---
        self.empty_frame = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        tk.Label(
            self.empty_frame, text="No database loaded", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 14, "bold"),
        ).pack(pady=(70, 6))
        tk.Label(
            self.empty_frame,
            text="Load an ERICards database file to start collecting.\n"
                 "Use the button below or Settings > Update Database...",
            bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, justify="center",
        ).pack()
        tk.Button(
            self.empty_frame, text="Load Database...", command=self.app.update_database, **NAV_BUTTON_OPTIONS,
        ).pack(pady=14)

        # --- Search Content ---
        self.content = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        controls = tk.Frame(self.content, bg=WINDOW_BACKGROUND_COLOR)
        controls.pack(fill="x", pady=(0, 6))

        tk.Label(controls, text="Search:", bg=WINDOW_BACKGROUND_COLOR).pack(side="left")
        self.query_var = tk.StringVar()
        self.query_var.trace_add("write", lambda *_: self._schedule_refresh())
        self.search_entry = tk.Entry(controls, textvariable=self.query_var, width=26)
        self.search_entry.pack(side="left", padx=(4, 10))
        self.search_entry.bind("<Return>", self._on_entry_return)
        self.search_entry.bind("<Down>", self._focus_results)

        tk.Label(controls, text="Category:", bg=WINDOW_BACKGROUND_COLOR).pack(side="left")
        saved_category = self.app.settings.get(self.category_setting)
        self.category_var = tk.StringVar(value=saved_category if saved_category in SEARCH_CATEGORIES else "All")
        category_box = ttk.Combobox(
            controls, textvariable=self.category_var, values=SEARCH_CATEGORIES, state="readonly", width=15,
        )
        category_box.pack(side="left", padx=(4, 10))
        category_box.bind("<<ComboboxSelected>>", self._on_category_changed)

        tk.Label(controls, text="Show:", bg=WINDOW_BACKGROUND_COLOR).pack(side="left")
        self.status_var = tk.StringVar(value="All")
        status_box = ttk.Combobox(
            controls, textvariable=self.status_var, values=STATUS_FILTERS, state="readonly", width=10,
        )
        status_box.pack(side="left", padx=(4, 10))
        status_box.bind("<<ComboboxSelected>>", lambda event: self.refresh_results())

        tk.Button(controls, text="Clear", width=8, command=self.clear_search).pack(side="left")

        # --- Bottom Bar ---
        bottom_bar = tk.Frame(self.content, bg=WINDOW_BACKGROUND_COLOR)
        bottom_bar.pack(side="bottom", fill="x", pady=(4, 0))
        self.count_label = tk.Label(bottom_bar, text="", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 8), anchor="w")
        self.count_label.pack(side="left")
        self.quick_button = tk.Button(
            bottom_bar, text="Mark Selected as Collected", width=26, state=tk.DISABLED, command=self.quick_toggle,
        )

        # --- Results Table ---
        self.table = SortableTree(
            self.content, self.COLUMNS, key_overrides={"date": lambda item: self.section.get_date(item)},
        )
        self.table.frame.pack(fill="both", expand=True)
        self.tree = self.table.tree
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<Return>", lambda event: self._open_selected())
        self.tree.bind("<space>", self._on_space)
        self.tree.bind("<<TreeviewSelect>>", self._update_quick_button)

    def _update_empty_state(self):
        if self.app.has_database:
            self.empty_frame.pack_forget()
            self.content.pack(fill="both", expand=True)
        else:
            self.content.pack_forget()
            self.empty_frame.pack(fill="both", expand=True)

    # --- Events ---
    def on_show(self, **kwargs):
        self._update_empty_state()
        if not self.app.has_database:
            return

        if self.app.settings.get("quick_collect"):
            self.quick_button.pack(side="right")
        else:
            self.quick_button.pack_forget()

        self.refresh_results()
        if self.last_opened and self.tree.exists(self.last_opened):
            self.tree.selection_set(self.last_opened)
            self.tree.see(self.last_opened)
        self.search_entry.focus_set()

    def _on_category_changed(self, event=None):
        self.app.settings.set(self.category_setting, self.category_var.get())
        self.refresh_results()

    def _on_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell":
            self._open_selected()

    def _on_entry_return(self, event=None):
        children = self.tree.get_children()
        if len(children) == 1:
            self.tree.selection_set(children[0])
        self._open_selected()

    def _on_space(self, event=None):
        if self.app.settings.get("quick_collect"):
            self.quick_toggle()
        return "break"

    def _focus_results(self, event=None):
        children = self.tree.get_children()
        if children:
            self.tree.focus_set()
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])

    def _open_selected(self):
        selection = self.tree.selection()
        if selection:
            self.last_opened = selection[0]
            self.open_item(selection[0])

    # --- Quick Collect ---
    def _update_quick_button(self, event=None):
        selection = self.tree.selection()
        if not selection:
            self.quick_button.config(text="Mark Selected as Collected", state=tk.DISABLED, fg="black")
        elif self.section.is_checked(selection[0]):
            self.quick_button.config(text="Unmark Selected", state=tk.NORMAL, fg=DANGER_COLOR)
        else:
            self.quick_button.config(text="Mark Selected as Collected", state=tk.NORMAL, fg=GO_COLOR)

    def quick_toggle(self):
        selection = self.tree.selection()
        if not selection:
            return
        key = selection[0]
        if self.app.toggle_collected(key, self.kind):
            self.refresh_results()
            if self.tree.exists(key):
                self.tree.selection_set(key)
                self.tree.see(key)
        self._update_quick_button()

    # --- Results ---
    def clear_search(self):
        self.query_var.set("")
        self.status_var.set("All")
        self.refresh_results()
        self.search_entry.focus_set()

    def _schedule_refresh(self):
        # Large lists (all substances) are refreshed shortly after the last keystroke
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
        delay = 150 if len(self.records()) > 500 else 1
        self._refresh_job = self.after(delay, self.refresh_results)

    def refresh_results(self):
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None

        query = self.query_var.get()
        category = self.category_var.get()
        status = self.status_var.get()
        section = self.section
        records = self.records()

        self.table.clear()
        shown = 0
        for record in records:
            key = self.record_key(record)
            is_collected = section.is_checked(key)
            if status == "Collected" and not is_collected:
                continue
            if status == "Missing" and is_collected:
                continue
            if not self.matches(record, query, category):
                continue
            self.tree.insert(
                "", "end", iid=key, tags=("collected",) if is_collected else (),
                values=self.row_values(record, is_collected),
            )
            shown += 1

        self.table.apply_sort()
        self.count_label.config(text=f"Showing {shown} of {len(records)} {self.noun}")
        self._update_quick_button()


class ERICardsPage(CollectionListPage):
    kind = KIND_ERICARDS
    progress_mode = KIND_ERICARDS
    noun = "ERICards"
    category_setting = "last_category"
    COLUMNS = [
        ("collected", "\u2714", 32, "center", False),
        ("number", "ERICard", 70, "w", False),
        ("un", "UN No.", 130, "w", False),
        ("name", "Substance", 260, "w", True),
        ("adr", "ADR Class", 80, "w", False),
        ("hazard", "Hazard No.", 80, "w", False),
        ("date", "Collected On", 95, "w", False),
    ]

    def records(self):
        return self.app.database.sorted_cards()

    def record_key(self, card):
        return card_key(card["ericard_number"])

    def matches(self, card, query, category):
        return card_matches(card, query, category)

    def row_values(self, card, is_collected):
        number = card["ericard_number"]
        return (
            "\u2714" if is_collected else "",
            number,
            summarize_list(card["un_numbers"], 3),
            summarize_list(card["substance_names"], 2, "; "),
            ", ".join(card["adr_classes"]),
            ", ".join(card["hazard_numbers"]),
            self.app.format_date(self.section.get_date(number)) if is_collected else "",
        )

    def open_item(self, key):
        self.app.open_card(key)


class SubstancesPage(CollectionListPage):
    kind = KIND_SUBSTANCES
    progress_mode = KIND_SUBSTANCES
    noun = "substances"
    category_setting = "last_substance_category"
    COLUMNS = [
        ("collected", "\u2714", 32, "center", False),
        ("un", "UN No.", 80, "w", False),
        ("name", "Substance", 300, "w", True),
        ("adr", "ADR Class", 90, "w", False),
        ("hazard", "Hazard No.", 90, "w", False),
        ("cards", "ERICard", 90, "w", False),
        ("date", "Collected On", 95, "w", False),
    ]

    def records(self):
        return self.app.database.sorted_substances()

    def record_key(self, record):
        return record["un"]

    def matches(self, record, query, category):
        return substance_matches(record, query, category)

    def row_values(self, record, is_collected):
        return (
            "\u2714" if is_collected else "",
            record["un"],
            summarize_list(record["names"], 2, "; "),
            ", ".join(record["adr_classes"]),
            summarize_list(record["hazard_numbers"], 3),
            summarize_list(record["cards"], 2),
            self.app.format_date(self.section.get_date(record["un"])) if is_collected else "",
        )

    def open_item(self, key):
        self.app.open_substance(key)


class CollectibleDetailPage(BasePage):
    # Shared parts of the ERICard and substance pages: header, collected status, large icon panel
    kind = None

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.current_key = None

    # --- Shared Widgets ---
    def _build_header(self):
        header = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        header.pack(fill="x")
        tk.Button(header, text="\u2B05 Back", width=10, command=self.app.go_back).pack(side="left")
        self.title_label = tk.Label(header, text="", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 14, "bold"))
        self.title_label.pack(side="left", padx=12)
        return header

    def _build_status_box(self):
        status_box = tk.Frame(
            self, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        status_box.pack(fill="x", pady=(8, 0))
        self.status_label = tk.Label(status_box, text="", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 9, "bold"))
        self.status_label.pack(side="left", padx=BOX_INTERNAL_PADDING + 4, pady=BOX_INTERNAL_PADDING)
        self.toggle_button = tk.Button(
            status_box, text="", width=BUTTON_WIDTH, font=tkFont.Font(family="Arial", size=9, weight="bold"),
            command=self.toggle_collected,
        )
        self.toggle_button.pack(side="right", padx=BOX_INTERNAL_PADDING, pady=BOX_INTERNAL_PADDING)
        self.date_button = tk.Button(status_box, text="Change Date...", width=14, command=self.change_date)
        self.date_button.pack(side="right", padx=(0, BOX_INTERNAL_PADDING), pady=BOX_INTERNAL_PADDING)

    def _build_icon_panel(self, parent):
        cell_width = DETAIL_ICON_SIZE + 24
        icon_panel = tk.Frame(
            parent, bg=WINDOW_BACKGROUND_COLOR, width=2 * (cell_width + 12) + 16,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        icon_panel.pack_propagate(False)
        tk.Label(
            icon_panel, text="ADR Hazard Labels", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=8, pady=(6, 0))
        self.icons_frame = tk.Frame(icon_panel, bg=WINDOW_BACKGROUND_COLOR)
        self.icons_frame.pack(anchor="n", padx=4, pady=4)
        return icon_panel

    # --- Display Helpers ---
    def _show_icons(self, adr_classes):
        for child in self.icons_frame.winfo_children():
            child.destroy()
        if not adr_classes:
            tk.Label(self.icons_frame, text="-", bg=WINDOW_BACKGROUND_COLOR).pack()
            return
        for index, adr_class in enumerate(adr_classes):
            cell = tk.Frame(self.icons_frame, bg=WINDOW_BACKGROUND_COLOR)
            cell.grid(row=index // 2, column=index % 2, padx=6, pady=6, sticky="n")
            build_adr_icon(cell, adr_class, DETAIL_ICON_SIZE).pack()
            tk.Label(cell, text=f"Class {adr_class}", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 8)).pack()

    @staticmethod
    def _lines_with_meaning(values, meanings):
        return "\n".join(
            f"{value}  \u2013  {meanings[value]}" if value in meanings else value for value in values
        ) or "-"

    def _refresh_status(self):
        section = self.app.collection.section(self.kind)
        if section.is_checked(self.current_key):
            collected_on = self.app.format_date(section.get_date(self.current_key))
            self.status_label.config(text=f"\u2714 Collected on {collected_on}", fg=GO_COLOR)
            self.toggle_button.config(text="Unmark as Collected", fg=DANGER_COLOR)
            self.date_button.config(state=tk.NORMAL)
        else:
            self.status_label.config(text="Not collected yet", fg=HINT_COLOR)
            self.toggle_button.config(text="Mark as Collected", fg=GO_COLOR)
            self.date_button.config(state=tk.DISABLED)

    # --- Actions ---
    def toggle_collected(self):
        if self.app.toggle_collected(self.current_key, self.kind):
            self._refresh_status()

    def change_date(self):
        if self.app.change_collect_date(self.current_key, self.kind):
            self._refresh_status()


class DetailPage(CollectibleDetailPage):
    kind = KIND_ERICARDS
    progress_mode = KIND_ERICARDS
    SUBSTANCE_COLUMNS = [
        ("un", "UN No.", 80, "w", False),
        ("name", "Substance", 520, "w", True),
        ("hin", "Hazard No.", 90, "w", False),
    ]

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.substance_rows = []
        self.source_url = ""
        self._build_widgets()

    # --- Widget Setup ---
    def _build_widgets(self):
        header = self._build_header()
        self.source_button = tk.Button(header, text="Open Source Page", command=self.open_source)
        self._build_status_box()

        self.notice_label = tk.Label(
            self, text="", bg=WINDOW_BACKGROUND_COLOR, fg=DANGER_COLOR, font=("Segoe UI", 8),
            justify="left", wraplength=640,
        )
        self.notice_label.pack(fill="x", anchor="w", pady=(6, 0))

        # --- Tabs ---
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, pady=(4, 0))
        self.overview_tab = tk.Frame(self.notebook, bg=WINDOW_BACKGROUND_COLOR)
        self.substances_tab = tk.Frame(self.notebook, bg=WINDOW_BACKGROUND_COLOR)
        self.text_tab = tk.Frame(self.notebook, bg=WINDOW_BACKGROUND_COLOR)
        self.notebook.add(self.overview_tab, text="Overview")
        self.notebook.add(self.substances_tab, text="Substances")
        self.notebook.add(self.text_tab, text="Card Text")
        self._build_overview_tab()
        self._build_substances_tab()
        self._build_text_tab()

    def _build_overview_tab(self):
        body = self.overview_tab
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        icon_panel = self._build_icon_panel(body)
        icon_panel.grid(row=0, column=0, sticky="ns", padx=(BOX_INTERNAL_PADDING + 4, 0), pady=BOX_INTERNAL_PADDING + 4)

        details = tk.Frame(body, bg=WINDOW_BACKGROUND_COLOR)
        details.grid(row=0, column=1, sticky="nsew", padx=BOX_INTERNAL_PADDING + 6, pady=BOX_INTERNAL_PADDING + 2)
        details.grid_columnconfigure(1, weight=1)

        captions = [
            "ADR Class(es)", "Label Combinations", "Hazard Number(s)", "Substances", "Description", "Known Hazards",
        ]
        for row, caption in enumerate(captions):
            tk.Label(
                details, text=caption, bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 9, "bold"), anchor="nw",
            ).grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=4)

        def value_label(row):
            label = tk.Label(details, text="", bg=WINDOW_BACKGROUND_COLOR, anchor="w", justify="left", wraplength=560)
            label.grid(row=row, column=1, sticky="ew", pady=4)
            return label

        self.classes_value = value_label(0)
        self.labels_value = value_label(1)
        self.hazard_value = value_label(2)
        self.substances_value = value_label(3)
        self.description_box = TextBox(details, height=4)
        self.description_box.grid(row=4, column=1, sticky="nsew", pady=4)
        self.hazards_box = TextBox(details, height=6)
        self.hazards_box.grid(row=5, column=1, sticky="nsew", pady=4)
        details.grid_rowconfigure(4, weight=2)
        details.grid_rowconfigure(5, weight=3)

    def _build_substances_tab(self):
        controls = tk.Frame(self.substances_tab, bg=WINDOW_BACKGROUND_COLOR)
        controls.pack(fill="x", padx=BOX_INTERNAL_PADDING + 4, pady=(8, 6))
        tk.Label(controls, text="Filter:", bg=WINDOW_BACKGROUND_COLOR).pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._refresh_substances())
        tk.Entry(controls, textvariable=self.filter_var, width=30).pack(side="left", padx=(4, 10))
        self.substance_count_label = tk.Label(controls, text="", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 8))
        self.substance_count_label.pack(side="left")

        self.substance_table = SortableTree(self.substances_tab, self.SUBSTANCE_COLUMNS)
        self.substance_table.frame.pack(
            fill="both", expand=True, padx=BOX_INTERNAL_PADDING + 4, pady=(0, BOX_INTERNAL_PADDING + 4),
        )
        # Double-click a substance to open its UN number card
        self.substance_table.tree.bind("<Double-Button-1>", self._on_substance_double_click)
        self.substance_table.tree.bind("<Return>", lambda event: self._open_selected_substance())

    def _build_text_tab(self):
        self.card_text_box = TextBox(self.text_tab, height=10)
        self.card_text_box.pack(
            fill="both", expand=True, padx=BOX_INTERNAL_PADDING + 4, pady=BOX_INTERNAL_PADDING + 4,
        )

    # --- Display ---
    def on_show(self, card_key=None, **kwargs):
        card = self.app.database.get(card_key) if card_key else None
        if card is None:
            self.app.go_back()
            return

        self.current_key = card_key
        self.title_label.config(text=f"ERICard {card['ericard_number']}")
        self.notice_label.config(
            text="" if card.get("verified", True) else "This entry is marked as not verified in the database."
        )

        self.source_url = card_source_url(card)
        if self.source_url:
            self.source_button.pack(side="right")
        else:
            self.source_button.pack_forget()

        # --- Overview ---
        self._show_icons(card["adr_classes"])
        self.classes_value.config(text=self._lines_with_meaning(card["adr_classes"], card_class_names(card)))
        self.labels_value.config(text="    |    ".join(card["adr_labels"]) or "-")
        self.hazard_value.config(text=self._lines_with_meaning(card["hazard_numbers"], card_hazard_meanings(card)))
        self.substance_rows = card_substances(card)
        un_count = len({row[0] for row in self.substance_rows if row[0]})
        self.substances_value.config(
            text=f"{len(self.substance_rows)} substance entries, {un_count} UN numbers (see the Substances tab)"
        )
        self.description_box.show_paragraphs(card["description"])
        self.hazards_box.show_bullets(card["known_hazards"])

        # --- Substances and Card Text ---
        self.notebook.tab(self.substances_tab, text=f"Substances ({len(self.substance_rows)})")
        self.filter_var.set("")
        self._refresh_substances()
        self.card_text_box.show_sections(card_sections(card))

        self.notebook.select(self.overview_tab)
        self._refresh_status()

    def _refresh_substances(self):
        tokens = self.filter_var.get().strip().lower().split()
        substances = self.app.collection.substances
        self.substance_table.clear()
        shown = 0
        for un, name, hin in self.substance_rows:
            if tokens:
                haystack = f"{un} {name} {hin}".lower()
                if not all(token in haystack for token in tokens):
                    continue
            is_collected = bool(un) and substances.is_checked(un)
            self.substance_table.tree.insert(
                "", "end", values=(un, name, hin), tags=("collected",) if is_collected else (),
            )
            shown += 1
        self.substance_table.apply_sort()
        self.substance_count_label.config(text=f"Showing {shown} of {len(self.substance_rows)}")

    def _on_substance_double_click(self, event):
        if self.substance_table.tree.identify_region(event.x, event.y) == "cell":
            self._open_selected_substance()

    def _open_selected_substance(self):
        tree = self.substance_table.tree
        selection = tree.selection()
        if selection:
            un = tree.set(selection[0], "un")
            if self.app.database.get_substance(un) is not None:
                self.app.open_substance(un)

    def open_source(self):
        if self.source_url:
            webbrowser.open(self.source_url)


class SubstanceDetailPage(CollectibleDetailPage):
    kind = KIND_SUBSTANCES
    progress_mode = KIND_SUBSTANCES
    CARD_COLUMNS = [
        ("collected", "\u2714", 32, "center", False),
        ("number", "ERICard", 80, "w", False),
        ("adr", "ADR Class", 140, "w", False),
        ("hazard", "Hazard No.", 110, "w", False),
    ]

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build_widgets()

    # --- Widget Setup ---
    def _build_widgets(self):
        self._build_header()
        self._build_status_box()

        body = tk.Frame(
            self, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        body.pack(fill="both", expand=True, pady=(8, 0))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        icon_panel = self._build_icon_panel(body)
        icon_panel.grid(row=0, column=0, sticky="ns", padx=(BOX_INTERNAL_PADDING + 4, 0), pady=BOX_INTERNAL_PADDING + 4)

        details = tk.Frame(body, bg=WINDOW_BACKGROUND_COLOR)
        details.grid(row=0, column=1, sticky="nsew", padx=BOX_INTERNAL_PADDING + 6, pady=BOX_INTERNAL_PADDING + 2)
        details.grid_columnconfigure(1, weight=1)

        captions = ["Substance Name(s)", "ADR Class(es)", "Hazard Number(s)", "ERICard(s)"]
        for row, caption in enumerate(captions):
            tk.Label(
                details, text=caption, bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 9, "bold"), anchor="nw",
            ).grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=4)

        self.names_box = TextBox(details, height=5)
        self.names_box.grid(row=0, column=1, sticky="nsew", pady=4)

        def value_label(row):
            label = tk.Label(details, text="", bg=WINDOW_BACKGROUND_COLOR, anchor="w", justify="left", wraplength=560)
            label.grid(row=row, column=1, sticky="ew", pady=4)
            return label

        self.classes_value = value_label(1)
        self.hazard_value = value_label(2)

        self.cards_table = SortableTree(details, self.CARD_COLUMNS, height=5)
        self.cards_table.frame.grid(row=3, column=1, sticky="nsew", pady=4)
        self.cards_table.tree.bind("<Double-Button-1>", self._on_card_double_click)
        self.cards_table.tree.bind("<Return>", lambda event: self._open_selected_card())
        details.grid_rowconfigure(0, weight=2)
        details.grid_rowconfigure(3, weight=2)

    # --- Display ---
    def on_show(self, un_key=None, **kwargs):
        database = self.app.database
        record = database.get_substance(un_key) if un_key else None
        if record is None:
            self.app.go_back()
            return

        self.current_key = record["un"]
        self.title_label.config(text=f"UN {record['un']}")

        # Class names and hazard number meanings come from the ERICards that list this substance
        cards = [card for card in (database.get(number) for number in record["cards"]) if card is not None]
        class_names, meanings = {}, {}
        for card in cards:
            for adr_class, name in card_class_names(card).items():
                class_names.setdefault(adr_class, name)
            for number, meaning in card_hazard_meanings(card).items():
                meanings.setdefault(number, meaning)

        self._show_icons(record["adr_classes"])
        self.names_box.show_bullets(record["names"])
        self.classes_value.config(text=self._lines_with_meaning(record["adr_classes"], class_names))
        self.hazard_value.config(text=self._lines_with_meaning(record["hazard_numbers"], meanings))

        collection = self.app.collection
        self.cards_table.clear()
        for card in cards:
            number = card["ericard_number"]
            hazards = []
            for _, hazard, entry_number in record["entries"]:
                if entry_number == number and hazard and hazard not in hazards:
                    hazards.append(hazard)
            is_collected = collection.is_checked(number)
            self.cards_table.tree.insert(
                "", "end", iid=card_key(number), tags=("collected",) if is_collected else (), values=(
                    "\u2714" if is_collected else "", number, ", ".join(card["adr_classes"]), ", ".join(hazards),
                ),
            )
        self.cards_table.apply_sort()
        self._refresh_status()

    # --- Events ---
    def _on_card_double_click(self, event):
        if self.cards_table.tree.identify_region(event.x, event.y) == "cell":
            self._open_selected_card()

    def _open_selected_card(self):
        selection = self.cards_table.tree.selection()
        if selection:
            self.app.open_card(selection[0])


class ProfilePage(BasePage):
    CLASS_COLUMNS = [
        ("adr", "ADR Class", 80, "w", False),
        ("collected", "Collected", 75, "e", False),
        ("total", "Total", 55, "e", False),
        ("percent", "Percent", 70, "e", False),
    ]
    ERICARD_COLUMNS = [
        ("number", "ERICard", 70, "w", False),
        ("un", "UN No.", 120, "w", False),
        ("name", "Substance", 190, "w", True),
        ("adr", "ADR Class", 90, "w", False),
        ("date", "Collected On", 95, "w", False),
    ]
    SUBSTANCE_COLUMNS = [
        ("un", "UN No.", 70, "w", False),
        ("name", "Substance", 240, "w", True),
        ("adr", "ADR Class", 90, "w", False),
        ("cards", "ERICard", 70, "w", False),
        ("date", "Collected On", 95, "w", False),
    ]
    MODE_LABELS = {KIND_ERICARDS: "ERICards", KIND_SUBSTANCES: "Substances"}

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.mode = KIND_ERICARDS
        self._build_widgets()

    # --- Widget Setup ---
    def _build_widgets(self):
        header = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        header.pack(fill="x")
        tk.Label(
            header, text="Your Profile", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 14, "bold"),
        ).pack(side="left")

        self.mode_buttons = {}
        for kind in (KIND_SUBSTANCES, KIND_ERICARDS):
            button = tk.Button(
                header, text=self.MODE_LABELS[kind], command=lambda k=kind: self.set_mode(k), **NAV_BUTTON_OPTIONS, bg=GROUP_BORDER_COLOR
            )
            button.pack(side="right", padx=(6, 0))
            self.mode_buttons[kind] = button
        for kind, button in self.mode_buttons.items():
            button.config(bg=GO_COLOR if kind == self.mode else GROUP_BORDER_COLOR, activebackground=GO_COLOR if kind == self.mode else GROUP_BORDER_COLOR
        )

        search_frame = tk.Frame(header, bg=WINDOW_BACKGROUND_COLOR)
        search_frame.pack(side="right", padx=(0, 14))
        tk.Label(search_frame, text="Search collected:", bg=WINDOW_BACKGROUND_COLOR).pack(side="left")
        self.query_var = tk.StringVar()
        self.query_var.trace_add("write", lambda *_: self.refresh())
        tk.Entry(search_frame, textvariable=self.query_var, width=24).pack(side="left", padx=(6, 0))

        # --- Summary ---
        summary_box = tk.Frame(
            self, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        summary_box.pack(fill="x", pady=(8, 0))
        self.summary_label = tk.Label(summary_box, text="", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 10, "bold"))
        self.summary_label.pack(anchor="w", padx=BOX_INTERNAL_PADDING + 4, pady=(BOX_INTERNAL_PADDING + 2, 4))
        self.summary_bar = ttk.Progressbar(
            summary_box, style="Custom.Horizontal.TProgressbar", orient="horizontal", mode="determinate",
        )
        self.summary_bar.pack(fill="x", padx=BOX_INTERNAL_PADDING + 4, pady=(0, BOX_INTERNAL_PADDING + 6))

        columns_frame = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        columns_frame.pack(fill="both", expand=True, pady=(10, 0))

        # --- ADR Class Stats ---
        class_frame = tk.Frame(columns_frame, bg=WINDOW_BACKGROUND_COLOR)
        class_frame.pack(side="left", fill="y")
        tk.Label(
            class_frame, text="Progress by ADR Class", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(0, 2))
        self.class_table = SortableTree(class_frame, self.CLASS_COLUMNS)
        self.class_table.frame.pack(fill="both", expand=True)
        tk.Label(
            class_frame, text="An item counts for every ADR class it carries.", bg=WINDOW_BACKGROUND_COLOR,
            fg=HINT_COLOR, font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(4, 0))

        tk.Frame(columns_frame, bg=GROUP_BORDER_COLOR, width=2).pack(side="left", fill="y", padx=10)

        # --- Collected List (one table per mode, only the active one is shown) ---
        collected_frame = tk.Frame(columns_frame, bg=WINDOW_BACKGROUND_COLOR)
        collected_frame.pack(side="left", fill="both", expand=True)
        self.list_title = tk.Label(
            collected_frame, text="", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 9, "bold"),
        )
        self.list_title.pack(anchor="w", pady=(0, 2))
        self.count_label = tk.Label(collected_frame, text="", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 8), anchor="w")
        self.count_label.pack(side="bottom", fill="x", pady=(4, 0))
        holder = tk.Frame(collected_frame, bg=WINDOW_BACKGROUND_COLOR)
        holder.pack(fill="both", expand=True)

        self.tables = {
            KIND_ERICARDS: SortableTree(
                holder, self.ERICARD_COLUMNS,
                key_overrides={"date": lambda item: self.app.collection.ericards.get_date(item)},
            ),
            KIND_SUBSTANCES: SortableTree(
                holder, self.SUBSTANCE_COLUMNS,
                key_overrides={"date": lambda item: self.app.collection.substances.get_date(item)},
            ),
        }
        for kind, table in self.tables.items():
            table.tree.bind("<Double-Button-1>", lambda event, k=kind: self._on_double_click(event, k))
            table.tree.bind("<Return>", lambda event, k=kind: self._open_selected(k))

    # --- Display ---
    def on_show(self, **kwargs):
        self.app.set_progress_mode(self.mode)
        self.refresh()

    def set_mode(self, kind):
        if kind == self.mode:
            return
        self.mode = kind
        self.app.set_progress_mode(kind)
        for kind, button in self.mode_buttons.items():
            if kind == self.mode:
                button.config(bg=GO_COLOR, activebackground=GO_COLOR)
            else:
                button.config(bg=GROUP_BORDER_COLOR, activebackground=GROUP_BORDER_COLOR)
        self.refresh()

    def refresh(self):
        kind = self.mode
        noun = self.MODE_LABELS[kind]
        database, collection = self.app.database, self.app.collection

        for mode_kind, button in self.mode_buttons.items():
            button.config(relief=tk.SUNKEN if mode_kind == kind else tk.RAISED)
        for mode_kind, table in self.tables.items():
            if mode_kind == kind:
                table.frame.pack(fill="both", expand=True)
            else:
                table.frame.pack_forget()

        # --- Progress ---
        stats = calculate_stats(database, collection, kind)
        if self.app.has_database:
            summary = f"{noun} collected: {stats['collected']} / {stats['total']}  ({stats['percent']:.1f}%)"
        else:
            summary = "No database loaded. Use Settings > Update Database... to load one."
        self.summary_label.config(text=summary)
        self.summary_bar.configure(maximum=max(stats["total"], 1), value=stats["collected"])

        self.class_table.clear()
        for adr_class, collected, total, percent in stats["classes"]:
            self.class_table.tree.insert("", "end", values=(adr_class, collected, total, f"{percent:.1f}%"))
        self.class_table.apply_sort()

        # --- Collected Items (filtered by the search field) ---
        self.list_title.config(text=f"Collected {noun}")
        table = self.tables[kind]
        table.clear()
        query = self.query_var.get()
        section = collection.section(kind)
        if kind == KIND_ERICARDS:
            items = [(card_key(c["ericard_number"]), c) for c in database.sorted_cards()]
            items = [(key, c) for key, c in items if section.is_checked(key)]
            total_collected = len(items)
            items = [(key, c) for key, c in items if card_matches(c, query, "All")]
        else:
            items = [(r["un"], r) for r in database.sorted_substances() if section.is_checked(r["un"])]
            total_collected = len(items)
            items = [(key, r) for key, r in items if substance_matches(r, query, "All")]
        items.sort(key=lambda item: section.get_date(item[0]), reverse=True)

        for key, record in items:
            date_text = self.app.format_date(section.get_date(key))
            if kind == KIND_ERICARDS:
                values = (
                    record["ericard_number"],
                    summarize_list(record["un_numbers"], 3),
                    summarize_list(record["substance_names"], 2, "; "),
                    ", ".join(record["adr_classes"]),
                    date_text,
                )
            else:
                values = (
                    record["un"],
                    summarize_list(record["names"], 2, "; "),
                    ", ".join(record["adr_classes"]),
                    summarize_list(record["cards"], 2),
                    date_text,
                )
            table.tree.insert("", "end", iid=key, values=values)
        table.apply_sort()
        self.count_label.config(text=f"Showing {len(items)} of {total_collected} collected")

    # --- Events ---
    def _on_double_click(self, event, kind):
        if self.tables[kind].tree.identify_region(event.x, event.y) == "cell":
            self._open_selected(kind)

    def _open_selected(self, kind):
        selection = self.tables[kind].tree.selection()
        if not selection:
            return
        if kind == KIND_ERICARDS:
            self.app.open_card(selection[0])
        else:
            self.app.open_substance(selection[0])


class GlossaryPage(BasePage):
    COLUMNS = [
        ("term", "Term", 160, "w", False),
        ("title", "Meaning", 600, "w", True),
    ]

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build_widgets()

    # --- Widget Setup ---
    def _build_widgets(self):
        tk.Label(
            self, text="Glossary", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.hint_label = tk.Label(
            self, text="", bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=("Segoe UI", 8), justify="left",
        )
        self.hint_label.pack(anchor="w", pady=(2, 6))

        self.table = SortableTree(self, self.COLUMNS)
        self.table.frame.pack(fill="both", expand=True)
        self.tree = self.table.tree
        self.tree.bind("<ButtonRelease-1>", self._on_click)
        self.tree.bind("<Return>", lambda event: self._open_selected())

    # --- Display ---
    def on_show(self, **kwargs):
        self.hint_label.config(
            text="Click a term to see what it stands for.\n"
                 f"Texts are shown in {self.app.language_name()} (change it in Settings > Glossary Text Language)."
        )
        self.table.clear()
        for row in self.app.reference.glossary(self.app.language):
            self.tree.insert("", "end", iid=row["term"], values=(row["term"], row["title"]))
        self.table.apply_sort()

    # --- Events ---
    def _on_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        item = self.tree.identify_row(event.y)
        if item:
            self.app.open_term(item)

    def _open_selected(self):
        selection = self.tree.selection()
        if selection:
            self.app.open_term(selection[0])


class TermPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build_widgets()

    # --- Widget Setup ---
    def _build_widgets(self):
        header = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        header.pack(fill="x")
        tk.Button(header, text="\u2B05 Back", width=10, command=self.app.go_back).pack(side="left")
        self.title_label = tk.Label(header, text="", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 14, "bold"))
        self.title_label.pack(side="left", padx=12)

        self.subtitle_label = tk.Label(
            self, text="", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 10, "bold"), justify="left", wraplength=640,
        )
        self.subtitle_label.pack(anchor="w", pady=(10, 0))
        self.hint_label = tk.Label(self, text="", bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=("Segoe UI", 8))
        self.hint_label.pack(anchor="w")

        body = tk.Frame(
            self, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        body.pack(fill="both", expand=True, pady=(8, 0))
        self.text = tk.Text(
            body, wrap="word", font=("Segoe UI", 10), state="disabled", relief="flat", padx=10, pady=8,
        )
        self.text.pack(fill="both", expand=True)

    # --- Display ---
    def on_show(self, term=None, **kwargs):
        language = self.app.language
        entry = self.app.reference.glossary_entry(term, language) if term else None
        if entry is None:
            self.app.go_back()
            return

        self.title_label.config(text=entry["term"])
        self.subtitle_label.config(text=entry["title"])
        if entry["used_language"] != language:
            languages = self.app.reference.languages()
            used_name = languages.get(entry["used_language"], entry["used_language"])
            self.hint_label.config(text=f"Not available in {self.app.language_name()}; showing {used_name} instead.")
        else:
            self.hint_label.config(text="")
        set_readonly_text(self.text, entry["text"] or "-")


class StatementsPage(BasePage):
    COLUMNS = [
        ("code", "Code", 80, "w", False),
        ("category", "Category", 100, "w", False),
        ("text", "Statement", 520, "w", True),
        ("pictograms", "Pictograms", 120, "w", False),
    ]

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.statements = {}
        self._build_widgets()

    # --- Widget Setup ---
    def _build_widgets(self):
        tk.Label(
            self, text="H & P Statements", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.hint_label = tk.Label(
            self, text="", bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=("Segoe UI", 8), justify="left",
        )
        self.hint_label.pack(anchor="w", pady=(2, 6))

        controls = tk.Frame(self, bg=WINDOW_BACKGROUND_COLOR)
        controls.pack(fill="x", pady=(0, 6))
        tk.Label(controls, text="Search:", bg=WINDOW_BACKGROUND_COLOR).pack(side="left")
        self.query_var = tk.StringVar()
        self.query_var.trace_add("write", lambda *_: self.refresh_results())
        self.search_entry = tk.Entry(controls, textvariable=self.query_var, width=26)
        self.search_entry.pack(side="left", padx=(4, 10))

        tk.Label(controls, text="Show:", bg=WINDOW_BACKGROUND_COLOR).pack(side="left")
        self.kind_var = tk.StringVar(value="All")
        kind_box = ttk.Combobox(
            controls, textvariable=self.kind_var, values=STATEMENT_FILTERS, state="readonly", width=16,
        )
        kind_box.pack(side="left", padx=(4, 10))
        kind_box.bind("<<ComboboxSelected>>", lambda event: self.refresh_results())
        tk.Button(controls, text="Clear", width=8, command=self.clear_search).pack(side="left")

        # --- Detail Box ---
        detail_box = tk.Frame(
            self, bg=WINDOW_BACKGROUND_COLOR, height=STATEMENT_ICON_SIZE + 66,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        detail_box.pack(side="bottom", fill="x", pady=(6, 0))
        detail_box.pack_propagate(False)
        icon_holder = tk.Frame(detail_box, bg=WINDOW_BACKGROUND_COLOR, width=2 * (STATEMENT_ICON_SIZE + 36))
        icon_holder.pack(side="left", fill="y", padx=BOX_INTERNAL_PADDING + 6)
        icon_holder.pack_propagate(False)
        self.icons_frame = tk.Frame(icon_holder, bg=WINDOW_BACKGROUND_COLOR)
        self.icons_frame.pack(expand=True)
        text_frame = tk.Frame(detail_box, bg=WINDOW_BACKGROUND_COLOR)
        text_frame.pack(side="left", fill="both", expand=True, padx=(0, BOX_INTERNAL_PADDING + 6), pady=BOX_INTERNAL_PADDING + 4)
        self.detail_title = tk.Label(
            text_frame, text="", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 10, "bold"), anchor="w",
        )
        self.detail_title.pack(fill="x")
        self.detail_text = tk.Label(
            text_frame, text="", bg=WINDOW_BACKGROUND_COLOR, anchor="nw", justify="left", wraplength=560,
        )
        self.detail_text.pack(fill="both", expand=True)

        self.count_label = tk.Label(self, text="", bg=WINDOW_BACKGROUND_COLOR, font=("Segoe UI", 8), anchor="w")
        self.count_label.pack(side="bottom", fill="x", pady=(4, 0))

        # --- Results Table ---
        self.table = SortableTree(self, self.COLUMNS)
        self.table.frame.pack(fill="both", expand=True)
        self.tree = self.table.tree
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    # --- Display ---
    def on_show(self, **kwargs):
        self.hint_label.config(
            text="Search by code (e.g. H301) or by word (e.g. toxic) in the selected glossary language: "
                 f"{self.app.language_name()}.\nClick a column heading to sort. "
                 "Select a statement to see its pictograms."
        )
        self.refresh_results()
        self.search_entry.focus_set()

    def clear_search(self):
        self.query_var.set("")
        self.kind_var.set("All")
        self.refresh_results()
        self.search_entry.focus_set()

    def refresh_results(self):
        language = self.app.language
        kind = self.kind_var.get()
        everything = []
        if kind in ("All", "H Statements"):
            everything += self.app.reference.statements("H", language)
        if kind in ("All", "EUH Statements"):
            everything += self.app.reference.statements("EUH", language)
        if kind in ("All", "P Statements"):
            everything += self.app.reference.statements("P", language)

        query = self.query_var.get()
        self.statements = {}
        self.table.clear()
        for statement in everything:
            if not statement_matches(statement, query):
                continue
            self.statements[statement["code"]] = statement
            self.tree.insert("", "end", iid=statement["code"], values=(
                statement["code"],
                statement["category"],
                statement["text"],
                ", ".join(statement["pictograms"]),
            ))
        self.table.apply_sort()
        self.count_label.config(text=f"Showing {len(self.statements)} of {len(everything)} statements")
        self._show_details(None)

    def _on_select(self, event=None):
        selection = self.tree.selection()
        self._show_details(self.statements.get(selection[0]) if selection else None)

    def _show_details(self, statement):
        for child in self.icons_frame.winfo_children():
            child.destroy()
        if statement is None:
            self.detail_title.config(text="No statement selected")
            self.detail_text.config(text="")
            return

        self.detail_title.config(text=f"{statement['code']} \u2013 {statement['category']}")
        self.detail_text.config(text=statement["text"])
        if not statement["pictograms"]:
            tk.Label(
                self.icons_frame, text="No pictogram", bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=("Segoe UI", 8),
            ).pack()
            return
        for code in statement["pictograms"]:
            cell = tk.Frame(self.icons_frame, bg=WINDOW_BACKGROUND_COLOR)
            cell.pack(side="left", padx=6)
            build_ghs_icon(cell, code, STATEMENT_ICON_SIZE).pack()
            name = self.app.reference.pictogram_name(code, self.app.language)
            tk.Label(
                cell, text=f"{code}\n{name}" if name else code, bg=WINDOW_BACKGROUND_COLOR,
                font=("Segoe UI", 7), wraplength=STATEMENT_ICON_SIZE + 24, justify="center",
            ).pack()


# --- Page Registry ---
PAGE_CLASSES = {
    "ericards": ERICardsPage,
    "substances": SubstancesPage,
    "profile": ProfilePage,
    "glossary": GlossaryPage,
    "statements": StatementsPage,
    "detail": DetailPage,
    "substance_detail": SubstanceDetailPage,
    "term": TermPage,
}
SIDE_NAV_ITEMS = [("ericards", "ERICards"), ("substances", "Substances"), ("profile", "Profile")]
TOP_NAV_ITEMS = [("glossary", "Glossary"), ("statements", "H & P Statements")]
SUB_PAGES = {"detail", "substance_detail", "term"}


# --- Application ---
class ERICardsCollector:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1100x760")
        self.root.minsize(1100, 760)
        add_footer(root, image_path="assets/footer.png")
        if WINDOW_BACKGROUND_COLOR:
            root.configure(bg=WINDOW_BACKGROUND_COLOR)
        center_window(root)

        self.settings = SettingsStore()
        self.database = CardDatabase()
        self.collection = CollectionStore()
        self.reference = ReferenceTexts()

        self.progress_mode = KIND_ERICARDS
        self.pages = {}
        self.current_page = None
        self.current_kwargs = {}
        self.back_stack = []
        self.nav_buttons = {}

        self.language_var = tk.StringVar(value=self.language)
        self.ask_date_var = tk.BooleanVar(value=bool(self.settings.get("ask_date")))
        self.quick_collect_var = tk.BooleanVar(value=bool(self.settings.get("quick_collect")))

        self.create_widgets()
        self.show_page("ericards")
        self.root.after(200, self.show_startup_warnings)

    @property
    def has_database(self):
        return bool(self.database.cards)

    # --- Glossary Language ---
    @property
    def language(self):
        languages = self.reference.languages()
        wanted = self.settings.get("reference_language")
        if wanted in languages or not languages:
            return wanted if wanted in languages else DEFAULT_LANGUAGE
        return DEFAULT_LANGUAGE if DEFAULT_LANGUAGE in languages else next(iter(languages))

    def language_name(self):
        return self.reference.languages().get(self.language, self.language)

    def change_language(self):
        self.settings.set("reference_language", self.language_var.get())
        self.refresh_current_page()

    def _rebuild_language_menu(self):
        # Rebuilt every time the menu opens, so languages added to the JSON show up
        self.language_var.set(self.language)
        self.language_menu.delete(0, tk.END)
        languages = self.reference.languages()
        if not languages:
            self.language_menu.add_command(label="No languages found", state=tk.DISABLED)
            return
        for code, name in languages.items():
            label = name if name == code else f"{name} ({code})"
            self.language_menu.add_radiobutton(
                label=label, value=code, variable=self.language_var, command=self.change_language,
            )

    # --- Widget Setup ---
    def create_widgets(self):
        self._configure_styles()
        self._build_progress_bar()
        self._build_top_bar()

        main_frame = tk.Frame(self.root, bg=WINDOW_BACKGROUND_COLOR)
        main_frame.pack(fill="both", expand=True, padx=BOX_EXTERNAL_PADDING, pady=BOX_EXTERNAL_PADDING)

        self._build_left_panel(main_frame)

        tk.Frame(main_frame, bg=GROUP_BORDER_COLOR, width=2).pack(side="left", fill="y", padx=8)

        self.page_container = tk.Frame(main_frame, bg=WINDOW_BACKGROUND_COLOR)
        self.page_container.pack(side="left", fill="both", expand=True)

        self.update_progress()

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor="#929292",
            background=GO_COLOR,
            bordercolor="#929292",
            lightcolor=GO_COLOR,
            darkcolor=GO_COLOR,
        )
        style.configure("TNotebook", background=WINDOW_BACKGROUND_COLOR, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(10, 3), font=("Segoe UI", 9))
        style.configure("Treeview", rowheight=22, background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.map(
            "Treeview",
            background=[("selected", HINT_COLOR)],
            foreground=[("selected", "white")],
        )

    def _build_progress_bar(self):
        # Packed before the main content area so it reliably reserves its
        # strip at the bottom of the window
        bottom_frame = tk.Frame(self.root, bg=WINDOW_BACKGROUND_COLOR)
        bottom_frame.pack(side="bottom", fill="x", padx=BOX_EXTERNAL_PADDING, pady=(0, BOX_EXTERNAL_PADDING))

        self.progress_bar = ttk.Progressbar(
            bottom_frame, style="Custom.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate",
        )
        self.progress_bar.pack(side="left", fill="x", expand=True)

        self.progress_label = tk.Label(bottom_frame, text="", bg=WINDOW_BACKGROUND_COLOR, width=28)
        self.progress_label.pack(side="left", padx=(8, 0))

    def _build_top_bar(self):
        top_bar = tk.Frame(self.root, bg=WINDOW_BACKGROUND_COLOR)
        top_bar.pack(side="top", fill="x", padx=BOX_EXTERNAL_PADDING, pady=(BOX_EXTERNAL_PADDING, 0))

        # --- Settings Menu ---
        settings_button = tk.Button(
            top_bar, text="⚙ Settings \u25BE", command=lambda: self._show_settings_menu(settings_button),
            **NAV_BUTTON_OPTIONS,
        )
        settings_button.pack(side="left", padx=(0, TOP_BAR_SPACING))
        menu = tk.Menu(settings_button, tearoff=0)
        self.settings_menu = menu

        menu.add_command(label="Update Database...", command=self.update_database)
        menu.add_command(label="Reload Database", command=self.reload_database)
        menu.add_command(label="Open Data Folder", command=lambda: open_folder(DOCUMENTS_DIR))
        menu.add_command(label="Open Icons Folder", command=lambda: open_folder(ICONS_DIR))
        menu.add_separator()
        menu.add_command(label="Import Collection...", command=self.import_collection)
        menu.add_command(label="Export Collection...", command=self.export_collection)
        menu.add_separator()
        self.language_menu = tk.Menu(menu, tearoff=0, postcommand=self._rebuild_language_menu)
        menu.add_cascade(label="Glossary Text Language", menu=self.language_menu)
        menu.add_command(label="Reload Glossary Texts", command=self.reload_reference)
        menu.add_separator()
        menu.add_checkbutton(
            label="Ask for Date When Marking", variable=self.ask_date_var,
            command=lambda: self.settings.set("ask_date", self.ask_date_var.get()),
        )
        menu.add_checkbutton(
            label="Quick Collect in Search Results", variable=self.quick_collect_var,
            command=self._on_quick_collect_toggled,
        )

        # --- Top Tabs ---
        for page_name, label in TOP_NAV_ITEMS:
            button = tk.Button(
                top_bar, text=label, command=lambda name=page_name: self.show_page(name), **NAV_BUTTON_OPTIONS,
            )
            button.pack(side="left", padx=(0, TOP_BAR_SPACING))
            self.nav_buttons[page_name] = button

        tk.Frame(self.root, bg=GROUP_BORDER_COLOR, height=2).pack(
            side="top", fill="x", padx=BOX_EXTERNAL_PADDING, pady=(8, 0),
        )

    def _show_settings_menu(self, button):
        x = button.winfo_rootx()
        y = button.winfo_rooty() + button.winfo_height()
        try:
            self.settings_menu.tk_popup(x, y)
        finally:
            self.settings_menu.grab_release()

    def _build_left_panel(self, parent):
        left_panel = tk.Frame(parent, bg=WINDOW_BACKGROUND_COLOR)
        left_panel.pack(side="left", fill="y", anchor="n")

        # --- Navigation Box ---
        nav_box = tk.Frame(
            left_panel, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        nav_box.pack(fill="x", anchor="nw")

        for index, (page_name, label) in enumerate(SIDE_NAV_ITEMS):
            button = tk.Button(
                nav_box, text=label, command=lambda name=page_name: self.show_page(name), **NAV_BUTTON_OPTIONS,
            )
            top_padding = BOX_INTERNAL_PADDING if index == 0 else 0
            button.pack(fill="x", padx=BOX_INTERNAL_PADDING, pady=(top_padding, 5))
            self.nav_buttons[page_name] = button

        self.cards_label = tk.Label(
            nav_box, text="", bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=("Segoe UI", 8),
            width=17, height=2, anchor="w", justify="left",
        )
        self.cards_label.pack(padx=BOX_INTERNAL_PADDING + 2, pady=(0, BOX_INTERNAL_PADDING), anchor="w")
        self.update_database_info()

    # --- Page Navigation ---
    def show_page(self, name, **kwargs):
        if name in SUB_PAGES:
            if self.current_page:
                self.back_stack.append((self.current_page, self.current_kwargs))
        else:
            self.back_stack.clear()
        self._display_page(name, kwargs)

    def go_back(self):
        if self.back_stack:
            name, kwargs = self.back_stack.pop()
        else:
            name, kwargs = "ericards", {}
        self._display_page(name, kwargs)

    def _display_page(self, name, kwargs):
        if self.current_page in self.pages:
            self.pages[self.current_page].pack_forget()

        if name not in self.pages:
            self.pages[name] = PAGE_CLASSES[name](self.page_container, self)

        self.current_page = name
        self.current_kwargs = kwargs

        # Highlight the tab of this page; sub pages highlight the page they were opened from
        highlighted = name
        if name in SUB_PAGES:
            highlighted = self.back_stack[-1][0] if self.back_stack else None
        for page_name, button in self.nav_buttons.items():
            button.config(relief=tk.SUNKEN if page_name == highlighted else tk.RAISED)

        page = self.pages[name]
        page.pack(fill="both", expand=True)
        if page.progress_mode:
            self.set_progress_mode(page.progress_mode)
        page.on_show(**kwargs)

    def refresh_current_page(self):
        if self.current_page in self.pages:
            self.pages[self.current_page].on_show(**self.current_kwargs)

    def open_card(self, key):
        self.show_page("detail", card_key=key)

    def open_substance(self, key):
        self.show_page("substance_detail", un_key=key)

    def open_term(self, term):
        self.show_page("term", term=term)

    # --- Shared State ---
    def format_date(self, iso_date):
        if not iso_date:
            return ""
        try:
            return datetime.strptime(iso_date, DATE_STORAGE_FORMAT).strftime(self.settings.get("date_format"))
        except ValueError:
            return iso_date

    def set_progress_mode(self, kind):
        if kind and kind != self.progress_mode:
            self.progress_mode = kind
            self.update_progress()

    def update_progress(self):
        stats = calculate_stats(self.database, self.collection, self.progress_mode)
        noun = "Substances" if self.progress_mode == KIND_SUBSTANCES else "ERICards"
        self.progress_bar.configure(maximum=max(stats["total"], 1), value=stats["collected"])
        self.progress_label.configure(text=f"{noun}: {stats['collected']} / {stats['total']} ({stats['percent']:.0f}%)")

    def update_database_info(self):
        self.cards_label.config(
            text=f"Cards loaded: {len(self.database.cards)}\nUN numbers: {len(self.database.substances())}"
        )

    def refresh_after_data_change(self):
        self.update_database_info()
        self.update_progress()
        self.refresh_current_page()

    def show_startup_warnings(self):
        warnings = [
            store.load_warning
            for store in (self.database, self.collection, self.settings, self.reference)
            if store.load_warning
        ]
        if warnings:
            messagebox.showwarning("Data Warning", "\n\n".join(warnings))

    def _on_quick_collect_toggled(self):
        self.settings.set("quick_collect", self.quick_collect_var.get())
        self.refresh_current_page()

    # --- Collecting ---
    def _describe(self, kind, key):
        # Name of a collectible for dialogs, or None if it no longer exists
        if kind == KIND_SUBSTANCES:
            record = self.database.get_substance(key)
            return f"UN {record['un']}" if record else None
        card = self.database.get(key)
        return f"ERICard {card['ericard_number']}" if card else None

    def toggle_collected(self, key, kind=KIND_ERICARDS):
        name = self._describe(kind, key)
        if name is None:
            return False
        section = self.collection.section(kind)

        if section.is_checked(key):
            collected_on = self.format_date(section.get_date(key))
            if not messagebox.askyesno(
                "Unmark",
                f"Remove {name} from your collection?\n\nThe collection date ({collected_on}) will be lost.",
            ):
                return False
            self.collection.remove_entry(kind, key)
        else:
            if self.settings.get("ask_date"):
                chosen = ask_date(self.root, "Collection Date", f"When did you see {name}?")
                if chosen is None:
                    return False
            else:
                chosen = date.today().isoformat()
            self.collection.set_entry(kind, key, chosen)

        self.update_progress()
        return True

    def change_collect_date(self, key, kind=KIND_ERICARDS):
        name = self._describe(kind, key)
        section = self.collection.section(kind)
        if name is None or not section.is_checked(key):
            return False
        chosen = ask_date(
            self.root, "Change Collection Date", f"New collection date for {name}:", section.get_date(key),
        )
        if chosen is None:
            return False
        self.collection.set_entry(kind, key, chosen)
        return True

    # --- Database Updates ---
    def update_database(self):
        path = filedialog.askopenfilename(
            title="Select ERICard database file",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8-sig") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            messagebox.showerror("Import Failed", f"Could not read the selected file:\n{error}")
            return

        cards, skipped, problems = CardDatabase.parse_import(data)
        if not cards:
            messagebox.showwarning(
                "Import Failed", "No valid ERICards were found in the selected file." + format_problems(problems),
            )
            return
        meta = CardDatabase.extract_meta(data)

        # An empty database is simply filled; otherwise the user chooses how to combine
        if not self.database.cards:
            replace = True
        else:
            choice = ask_choice(
                self.root, "Update Database",
                f"{len(cards)} valid ERICard(s) found in the file.\n"
                "How should they be combined with the current database?",
                [
                    "Replace the current database with the file (recommended for a full database)",
                    "Merge \u2013 add new cards and update changed ones, keep all other cards",
                ],
                confirm_text="Next",
                default_index=1,
            )
            if choice is None:
                return
            replace = choice == 0

        result, stats = self.database.plan_import(cards, replace)
        if not messagebox.askyesno(
            "Update Database",
            f"{len(cards)} valid ERICard(s) found.\n\n"
            f"New: {stats['added']}\nUpdated: {stats['updated']}\nUnchanged: {stats['unchanged']}\n"
            f"Removed: {stats['removed']}\nSkipped (invalid): {skipped}"
            f"{format_problems(problems)}\n\n"
            "A backup of the current database is created first. Your collection is not affected.\n\nContinue?",
        ):
            return

        try:
            self.database.backup()
            self.database.apply_plan(result, meta, replace)
        except OSError as error:
            messagebox.showerror("Update Failed", f"Could not update the database:\n{error}")
            return

        self.refresh_after_data_change()
        messagebox.showinfo("Database Updated", f"The database now has {len(self.database.cards)} ERICard(s).")

    def reload_database(self):
        self.database.load()
        self.refresh_after_data_change()
        if self.database.load_warning:
            messagebox.showwarning("Data Warning", self.database.load_warning)
        elif not self.database.cards:
            messagebox.showinfo("No Database", "No database file was found. Use Update Database... to load one.")
        else:
            details = f"{len(self.database.cards)} ERICard(s) and {len(self.database.substances())} UN numbers loaded."
            if self.database.language:
                details += f"\nDatabase language: {self.database.language}"
            details += f"\nLast updated: {self.database.last_updated or '-'}"
            messagebox.showinfo("Database Reloaded", details)

    def reload_reference(self):
        self.reference.load()
        _icon_cache.clear()
        self.language_var.set(self.language)
        self.refresh_current_page()
        if self.reference.load_warning:
            messagebox.showwarning("Data Warning", self.reference.load_warning)
        else:
            names = ", ".join(self.reference.languages().values()) or "none"
            messagebox.showinfo("Glossary Texts Reloaded", f"Available languages: {names}")

    # --- Collection Import and Export ---
    def export_collection(self):
        path = filedialog.asksaveasfilename(
            title="Export collection",
            defaultextension=".json",
            initialfile=f"ericards_collection_{date.today():%Y%m%d}.json",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return
        try:
            save_json(path, self.collection.export_data())
        except OSError as error:
            messagebox.showerror("Export Failed", f"Could not write the file:\n{error}")
            return
        messagebox.showinfo(
            "Export Complete",
            f"Exported {len(self.collection.ericards.entries)} ERICard(s) and "
            f"{len(self.collection.substances.entries)} substance(s) to:\n{path}",
        )

    def import_collection(self):
        path = filedialog.askopenfilename(
            title="Import collection",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8-sig") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            messagebox.showerror("Import Failed", f"Could not read the selected file:\n{error}")
            return

        imported, skipped, problems = self.collection.parse_import(data)
        found = {kind: len(entries) for kind, entries in imported.items() if entries}
        if not found:
            messagebox.showwarning(
                "Import Failed", "No collected items were found in the selected file." + format_problems(problems),
            )
            return

        labels = {KIND_ERICARDS: "ERICard(s)", KIND_SUBSTANCES: "substance(s)"}
        found_text = " and ".join(f"{count} collected {labels[kind]}" for kind, count in found.items())
        mode = ask_choice(
            self.root, "Import Collection",
            f"{found_text} found in the file.\n"
            "How should they be combined with your current collection?",
            [
                "Merge \u2013 keep the earlier date if an item is in both",
                "Merge \u2013 use the imported date if an item is in both",
                "Replace my collection with the imported one",
            ],
            confirm_text="Next",
        )
        if mode is None:
            return

        results, stats = self.collection.merge_plan(imported, mode)
        summary = "\n".join(
            f"{labels[kind].capitalize()}: new {s['added']}, date changed {s['changed']}, "
            f"unchanged {s['unchanged']}, removed {s['removed']}"
            for kind, s in stats.items()
        )
        if not messagebox.askyesno(
            "Import Collection",
            f"{summary}\nSkipped (invalid): {skipped}{format_problems(problems)}\n\n"
            "A backup of your current collection is created first.\n\nContinue?",
        ):
            return

        try:
            self.collection.backup()
            self.collection.apply_plan(results)
        except OSError as error:
            messagebox.showerror("Import Failed", f"Could not save the collection:\n{error}")
            return

        self.refresh_after_data_change()
        messagebox.showinfo(
            "Import Complete",
            f"Your collection now has {len(self.collection.ericards.entries)} ERICard(s) and "
            f"{len(self.collection.substances.entries)} substance(s).",
        )


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    app = ERICardsCollector(root)
    root.deiconify()
    root.mainloop()