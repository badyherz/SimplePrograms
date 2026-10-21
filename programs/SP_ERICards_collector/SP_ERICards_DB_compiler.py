import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from helper.SP_footer_picture import add_footer
    from helper.SP_window_utils import center_window
except ImportError:
    # Standalone fallback so the tool also runs outside the SimplePrograms project
    def add_footer(root, image_path=None):
        return None

    def center_window(root):
        root.update_idletasks()
        x = (root.winfo_screenwidth() - root.winfo_width()) // 2
        y = (root.winfo_screenheight() - root.winfo_height()) // 3
        root.geometry(f"+{max(x, 0)}+{max(y, 0)}")


# --- Configuration ---
WINDOW_BACKGROUND_COLOR = "#E6E6E6"
GROUP_BORDER_COLOR = "#A7A7A7"
BOX_BORDER_THICKNESS = 0.5
BOX_INTERNAL_PADDING = 8
BOX_EXTERNAL_PADDING = 10
BUTTON_WIDTH = 24

HINT_COLOR = "#1B5FA8"
DANGER_COLOR = "#C55E5E"
GO_COLOR = "#3A8B63"
WARNING_COLOR = "#B7791F"
MUTED_COLOR = "#5F5F5F"

FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 17, "bold")
FONT_SECTION = (FONT_FAMILY, 10, "bold")
FONT_NORMAL = (FONT_FAMILY, 10)
FONT_SMALL = (FONT_FAMILY, 9)
FONT_STATUS = (FONT_FAMILY, 18, "bold")
FONT_BUTTON = (FONT_FAMILY, 10, "bold")

APP_TITLE = "ERICards Database Compiler"
SCHEMA_VERSION = 1
OUTPUT_FILE_NAME = "ericards_db.json"
OUTPUT_FOLDER_PREFIX = "ERICards_DB_"
DEBUG_FOLDER_NAME = "debug"

# --- Source Configuration ---
BASE_URL = "https://www.ericards.net/psp/"
SEARCH_PAGE = "ericards.psp_search_adv?p_lang={language_id}"
DEFAULT_LANGUAGE = "English"
DEFAULT_LANGUAGE_ID = "1"               # p_lang value of the English pages
USER_AGENT = "SP_ERICards_DB_Compiler (personal offline copy of the CEFIC ERICards)"
REQUEST_DELAY = 0.4                     # seconds between requests (be polite to the server)
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3
MAX_CONSECUTIVE_FAILURES = 5            # abort when the website layout is clearly not understood (adjust parsing!)
CONSISTENCY_SAMPLE_STEP = 10            # every n-th card is read twice to confirm its text is the same for all substances

# --- Languages ---
# (English name, name as shown on ericards.net). The website offers these 19 languages.
LANGUAGES = [
    ("English", "English"),
    ("German", "Deutsch"),
    ("French", "Fran\u00e7ais"),
    ("Spanish", "Espa\u00f1ol"),
    ("Italian", "Italiano"),
    ("Dutch", "Nederlands"),
    ("Bulgarian", "\u0411\u044a\u043b\u0433\u0430\u0440\u0441\u043a\u0438"),
    ("Croatian", "Hrvatski"),
    ("Greek", "E\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03b1"),
    ("Hungarian", "Magyar"),
    ("Japanese", "\u65e5\u672c\u8a9e"),
    ("Korean", "\ud55c\uad6d\uc5b4"),
    ("Malay", "Bahasa Melayu"),
    ("Romanian", "Rom\u00e2n\u0103"),
    ("Simplified Chinese", "\u7b80\u4f53\u5b57"),
    ("Slovak", "Slovensky"),
    ("Thai", "\u0e44\u0e17\u0e22"),
    ("Traditional Chinese", "\u6b63\u9ad4\u5b57"),
    ("Turkish", "T\u00fcrk\u00e7e"),
]

# --- Expected Figures ---
# Source: "Development" page of ericards.net (version aligned to ADR 2021).
EXPECTED_CARDS_TOTAL = 243
EXPECTED_ENTRIES_TOTAL = 2291
EXPECTED_BY_CLASS = {
    # class prefix: (ERICards, substance entries)
    "1": (6, 373),
    "2": (46, 179),
    "3": (37, 486),
    "4": (27, 164),
    "5": (24, 129),
    "6": (49, 614),
    "7": (4, 25),
    "8": (43, 307),
    "9": (7, 15),
}


# --- Parsing Patterns ---
CARD_NUMBER_RE = re.compile(r"^\d{1,2}-\d{2}$")
UN_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")
HIN_RE = re.compile(r"^X?\d{2,3}$")
HIN_IN_TEXT_RE = re.compile(r"(?<![\w.])(X?\d{2,3})(?![\w.])")
ERIC_IN_TEXT_RE = re.compile(r"(?<!\d)(\d{1,2})\s*-\s*(\d{2})(?!\d)")
LABEL_OPTION_RE = re.compile(r"^\d(\.\d)?(\+\d(\.\d)?)*$")
SECTION_HEADING_RE = re.compile(r"^(\d{1,2})(?:\.(\d{1,2}))?\.?\s+(\S.{0,80})$")
ADR_CLASS_RE = re.compile(r"^(\d(?:\.\d)?)[A-Z]?$")
BOILERPLATE_RE = re.compile(
    r"European Chemical Industry Council|\(CEFIC\)|cefic\.org|^Top$|^Telephone|^Welcome to the CEFIC|Disclaimer",
    re.IGNORECASE,
)

class BuildError(Exception):
    pass


class CancelledError(Exception):
    pass


class FetchError(Exception):
    pass


class ParseError(Exception):
    pass


class EmptyCardError(Exception):
    # The website lists the ERICard, but no substance is assigned to it in the current database
    pass


# --- Helper Functions ---
def open_folder(path):
    if os.name == "nt":
        os.startfile(path)
    elif shutil.which("open"):
        subprocess.run(["open", str(path)])
    else:
        subprocess.run(["xdg-open", str(path)])

def save_json(path, data):
    # Write to a temporary file first so a crash cannot leave a half-written file behind
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
    os.replace(temp_path, path)

def natural_sort_key(text):
    # "2-10" sorts after "2-02"; "2.1" before "2.3"; "10" after "9"
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(text))]

def clean_text(text):
    return re.sub(r"\s+", " ", str(text).replace("\xa0", " ")).strip()

def unique_keep_order(items):
    seen, result = set(), []
    for item in items:
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            result.append(item)
    return result

def normalize_language_text(text):
    decomposed = unicodedata.normalize("NFKD", str(text))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold().strip()

def language_display_name(entry):
    english, native = entry
    return english if english == native else f"{english} ({native})"

def language_entry(english_name):
    for entry in LANGUAGES:
        if entry[0].lower() == english_name.lower():
            return entry
    raise BuildError(f"Unknown language '{english_name}'.")


# --- HTML Tree ---
VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "source", "wbr", "param", "track"}
SKIP_TAGS = {"script", "style", "noscript", "head"}
BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "tr", "td", "th", "table", "thead", "tbody", "tfoot", "caption",
    "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "dl", "dt", "dd", "blockquote",
    "pre", "form", "fieldset", "center",
}

# tag -> (tags it implicitly closes, boundary tags that stop the search)
IMPLICIT_CLOSE = {
    "li": ({"li"}, {"ul", "ol"}),
    "td": ({"td", "th"}, {"tr", "table"}),
    "th": ({"td", "th"}, {"tr", "table"}),
    "tr": ({"tr", "td", "th"}, {"table", "thead", "tbody", "tfoot"}),
    "thead": ({"thead", "tbody", "tfoot", "tr", "td", "th"}, {"table"}),
    "tbody": ({"thead", "tbody", "tfoot", "tr", "td", "th"}, {"table"}),
    "tfoot": ({"thead", "tbody", "tfoot", "tr", "td", "th"}, {"table"}),
    "option": ({"option"}, {"select", "optgroup"}),
    "p": ({"p"}, {"div", "td", "th", "li", "table", "body"}),
}

class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag, attrs=None, parent=None, text=""):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []
        self.parent = parent
        self.text = text

class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def _implicit_close(self, closes, boundaries):
        for index in range(len(self.stack) - 1, 0, -1):
            tag = self.stack[index].tag
            if tag in boundaries:
                return
            if tag in closes:
                del self.stack[index:]
                return

    def handle_starttag(self, tag, attrs):
        rule = IMPLICIT_CLOSE.get(tag)
        if rule:
            self._implicit_close(*rule)
        node = Node(tag, {key: (value if value is not None else "") for key, value in attrs}, parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(Node("#text", parent=self.stack[-1], text=data))

def parse_html(html):
    builder = TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root

def iter_nodes(node):
    for child in node.children:
        yield child
        yield from iter_nodes(child)

def find_all(node, tag):
    return [child for child in iter_nodes(node) if child.tag == tag]

def has_descendant(node, tags):
    return any(child.tag in tags for child in iter_nodes(node))

def _collect_text(node, out):
    if node.tag == "#text":
        out.append(node.text)
        return
    if node.tag in SKIP_TAGS:
        return
    if node.tag == "br":
        out.append("\n")
        return
    block = node.tag in BLOCK_TAGS
    if block:
        out.append("\n")
    for child in node.children:
        _collect_text(child, out)
    if block:
        out.append("\n")

def text_lines(node):
    out = []
    _collect_text(node, out)
    lines = [clean_text(line) for line in "".join(out).split("\n")]
    return [line for line in lines if line]

def text_of(node):
    return " ".join(text_lines(node))


# --- Forms ---
class FormField:
    def __init__(self, name, kind, value="", options=None, checked=False, label=""):
        self.name = name
        self.kind = kind
        self.value = value
        self.options = options or []
        self.checked = checked
        self.label = label

class Form:
    def __init__(self, action, method, fields, name=""):
        self.action = action
        self.method = method
        self.fields = fields
        self.name = name

def _following_text(node):
    # Visible text right behind a radio button or checkbox (up to the next control)
    parent = node.parent
    if parent is None:
        return ""
    if parent.tag == "label":
        return text_of(parent)
    parts, started = [], False
    for sibling in parent.children:
        if sibling is node:
            started = True
            continue
        if not started:
            continue
        if sibling.tag in ("input", "select", "br", "textarea"):
            break
        parts.append(text_of(sibling) if sibling.tag != "#text" else clean_text(sibling.text))
    return clean_text(" ".join(parts))

def extract_forms(root, page_url):
    forms = []
    for form_node in find_all(root, "form"):
        action = urllib.parse.urljoin(page_url, form_node.attrs.get("action", "") or page_url)
        method = (form_node.attrs.get("method", "get") or "get").lower()
        fields = []
        for element in iter_nodes(form_node):
            name = element.attrs.get("name", "")
            if element.tag == "input":
                kind = (element.attrs.get("type", "text") or "text").lower()
                if kind in ("button", "image", "reset", "file"):
                    continue
                if kind not in ("hidden", "radio", "checkbox", "submit"):
                    kind = "text"
                label = _following_text(element) if kind in ("radio", "checkbox") else ""
                fields.append(FormField(name, kind, element.attrs.get("value", ""),
                                        checked="checked" in element.attrs, label=label))
            elif element.tag == "select":
                options = []
                for option in find_all(element, "option"):
                    option_text = text_of(option)
                    value = option.attrs.get("value")
                    options.append((option_text if value is None else value, option_text, "selected" in option.attrs))
                fields.append(FormField(name, "select", options=options))
            elif element.tag == "textarea":
                fields.append(FormField(name, "text"))
        forms.append(Form(action, method, fields, form_node.attrs.get("name", "")))
    return forms

def locate_card_list(forms):
    # Returns (form, field, [(card_number, option_value), ...]) for the select that lists all ERICards
    for form in forms:
        for field in form.fields:
            if field.kind != "select":
                continue
            cards = [(text, value) for value, text, _ in field.options if CARD_NUMBER_RE.match(text)]
            if len(cards) >= 3:
                return form, field, sorted(cards, key=lambda item: natural_sort_key(item[0]))
    return None, None, []

def split_language_text(text):
    match = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", text.strip())
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text.strip(), text.strip()

def locate_language_field(form):
    # The language select is the one offering both English and German
    for field in form.fields:
        if field.kind != "select":
            continue
        english_names = {normalize_language_text(split_language_text(text)[1]) for _, text, _ in field.options}
        if "english" in english_names and "german" in english_names:
            return field
    return None

def option_matches_language(text, english_name, native_name):
    native_found, english_found = split_language_text(text)
    if normalize_language_text(english_found) == normalize_language_text(english_name):
        return True
    wanted, found = normalize_language_text(native_name), normalize_language_text(native_found)
    # The one-character tolerance covers look-alike letters (e.g. Latin/Greek "E" in the Greek entry)
    return found == wanted or (len(wanted) > 4 and found[1:] == wanted[1:])

def match_language_option(field, english_name, native_name):
    # Returns (value, text) of the option showing the given language, or None
    for value, text, _ in field.options:
        if option_matches_language(text, english_name, native_name):
            return value, text
    return None

def selected_option_text(field):
    for _, text, selected in field.options:
        if selected:
            return text
    return ""

def locate_label_field(form):
    # The ADR label select lists values such as "1", "2.1", "3+8", "6.1+8"
    for field in form.fields:
        if field.kind != "select":
            continue
        labels = [text for _, text, _ in field.options if LABEL_OPTION_RE.match(text.strip())]
        if len(labels) >= 10:
            return field
    return None

def build_form_data(form, language_field_name, language_value, criteria):
    # Fills the search form with exactly the given criteria ({field name: value}); everything else stays empty
    data, radio_groups, submit_added = [], {}, False
    for field in form.fields:
        if not field.name:
            continue
        if field.name in criteria:
            data.append((field.name, criteria[field.name]))
        elif field.kind == "select":
            data.append((field.name, language_value if field.name == language_field_name else ""))
        elif field.kind == "text":
            data.append((field.name, ""))
        elif field.kind == "hidden":
            data.append((field.name, field.value))
        elif field.kind == "checkbox":
            if field.checked:
                data.append((field.name, field.value or "on"))
        elif field.kind == "radio":
            radio_groups.setdefault(field.name, []).append(field)
        elif field.kind == "submit" and not submit_added:
            data.append((field.name, field.value))
            submit_added = True
    for name, group in radio_groups.items():
        # "any of the criteria" is used; only one criterion is ever filled in
        chosen = next((f for f in group if "any" in f.label.lower()), None) \
            or next((f for f in group if f.checked), None) or group[0]
        data.append((name, chosen.value))
    return data


# --- HTTP Client ---
class Fetcher:
    def __init__(self, cancel_event, delay=REQUEST_DELAY):
        self.cancel_event = cancel_event
        self.delay = delay
        self.last_request = 0.0
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.opener.addheaders = [("User-Agent", USER_AGENT)]

    def _check_cancel(self):
        if self.cancel_event.is_set():
            raise CancelledError()

    def _wait(self):
        remaining = self.delay - (time.time() - self.last_request)
        while remaining > 0:
            self._check_cancel()
            time.sleep(min(remaining, 0.1))
            remaining -= 0.1

    @staticmethod
    def _decode(response, raw):
        charset = response.headers.get_content_charset()
        if not charset:
            match = re.search(rb"charset=[\"']?([\w-]+)", raw[:3000], re.IGNORECASE)
            charset = match.group(1).decode("ascii") if match else "utf-8"
        try:
            return raw.decode(charset, errors="replace")
        except LookupError:
            return raw.decode("utf-8", errors="replace")

    def get(self, url, post_data=None, referer=""):
        # post_data: list of (name, value) pairs; when given, the request is sent as a form POST
        last_error = None
        body = urllib.parse.urlencode(post_data).encode("utf-8") if post_data is not None else None
        for attempt in range(REQUEST_RETRIES):
            self._check_cancel()
            self._wait()
            try:
                request = urllib.request.Request(url, data=body)
                if referer:
                    request.add_header("Referer", referer)
                with self.opener.open(request, timeout=REQUEST_TIMEOUT) as response:
                    raw = response.read()
                    self.last_request = time.time()
                    return self._decode(response, raw), response.geturl()
            except urllib.error.HTTPError as error:
                self.last_request = time.time()
                if 400 <= error.code < 500:
                    raise FetchError(f"HTTP {error.code} for {url}")
                last_error = error
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                self.last_request = time.time()
                last_error = error
            time.sleep(min(2 ** attempt, 8))
        raise FetchError(f"Could not load {url}: {last_error}")


# --- Result Page Parsing ---
def normalize_card_number(text):
    match = ERIC_IN_TEXT_RE.search(text or "")
    return f"{match.group(1)}-{match.group(2)}" if match else ""

def parse_result_entries(root, page_url):
    # Every hit of the result list is one table row: a link with the substance name, followed by a line like
    # "UN Number: 0004, HIN: , ERIC: 1-01" (the labels are translated, so only the value shapes are used).
    entries = []
    for tr in find_all(root, "tr"):
        if has_descendant(tr, {"table"}):
            continue
        for cell in (child for child in tr.children if child.tag in ("td", "th")):
            anchor = next((a for a in find_all(cell, "a") if a.attrs.get("href")), None)
            if anchor is None:
                continue
            name = text_of(anchor)
            detail = text_of(cell).replace(name, "", 1)
            un_match = UN_RE.search(detail)
            eric = normalize_card_number(detail)
            if not (un_match and eric):
                continue
            rest = detail.replace(un_match.group(1), " ").replace(ERIC_IN_TEXT_RE.search(detail).group(0), " ")
            hin_match = HIN_IN_TEXT_RE.search(rest)
            entries.append({
                "un": un_match.group(1),
                "name": clean_text(name),
                "hin": hin_match.group(1).upper() if hin_match else "",
                "eric": eric,
                "link": urllib.parse.urljoin(page_url, anchor.attrs["href"]),
            })
    return entries

def listed_result_count(root):
    # The result page starts with a sentence like "144 substance(s) were found matching."
    body = next((node for node in iter_nodes(root) if node.tag == "body"), root)
    for paragraph in find_all(body, "p"):
        match = re.match(r"\s*(\d+)\b", text_of(paragraph))       # the sentence starts with the number
        if match:
            return int(match.group(1))
    return None


# --- Card Page Parsing ---
def extract_numbered_sections(root):
    # ERICard pages consist of numbered sections ("1. Characteristics", "2. Hazards", "4.1 General" ...).
    # The numbers are the same in every language (the titles may end with a full stop), so they identify
    # the sections reliably. Section titles are set in bold on the page; a numbered line counts as a title only
    # if it follows the expected numbering and is bold, so list items starting with a number are never mistaken.
    body = next((node for node in iter_nodes(root) if node.tag == "body"), root)
    bold_lines = {text_of(node) for node in iter_nodes(body) if node.tag in ("b", "u", "strong")}
    lines = [line for line in text_lines(body) if not BOILERPLATE_RE.search(line)]

    preamble, sections, current = [], {}, None
    last_top, last_sub = 0, 0
    for line in lines:
        match = SECTION_HEADING_RE.match(line)
        if match and (line in bold_lines or not bold_lines):
            top, sub = int(match.group(1)), match.group(2)
            if sub is None and top == last_top + 1:
                last_top, last_sub, current = top, 0, line
                sections[current] = []
                continue
            if sub is not None and top == last_top and int(sub) == last_sub + 1:
                last_sub, current = int(sub), line
                sections[current] = []
                continue
        if current is None:
            preamble.append(line)
        else:
            sections[current].append(line)
    headline = preamble[-1] if len(preamble) >= 2 else ""
    return sections, headline

def parse_card_class(root):
    # The top table of a card page lists the facts of the opened substance as rows "name | | value":
    # substance, UN number, HIN, ADR label, ADR class, classification code, packing group, ERIC.
    # The position is the same in every language. Returns the ADR class of that substance or "".
    for table in find_all(root, "table"):
        if has_descendant(table, {"table"}):
            continue
        values = []
        for tr in find_all(table, "tr"):
            cells = [cell for cell in tr.children if cell.tag in ("td", "th")]
            if len(cells) == 3:
                values.append(text_of(cells[2]))
        if len(values) >= 8:
            match = ADR_CLASS_RE.match(values[4].strip())
            return match.group(1) if match else ""
    return ""

def derive_fields(sections, headline=""):
    # Returns (description, hazard lines). "1." is the characteristics section, "2." the hazards section.
    description_lines, hazards = [], []
    for title, lines in sections.items():
        match = re.match(r"^(\d+)\.?\s", title)
        if match and not re.match(r"^\d+\.\d", title):
            if match.group(1) == "1":
                description_lines.extend(lines)
            elif match.group(1) == "2":
                hazards.extend(lines)
    title_text = headline.capitalize() if headline.isupper() else headline
    description = " ".join(part for part in [title_text.rstrip(".") + "." if title_text else ""] + description_lines if part)
    return description, unique_keep_order(hazards)

def split_adr_classes(labels):
    classes = []
    for label in labels:
        for token in re.split(r"[+/,\s]+", label):
            match = ADR_CLASS_RE.match(token.strip())
            if match:
                classes.append(match.group(1))
    return sorted(set(classes), key=natural_sort_key)


# --- ADR Reference Data ---
# Technical classification text derived from the ADR.
# Texts exist in English and German; other languages fall back to English.
REFERENCE_TEXTS = {
    "English": {
        "classes": {
            "1": "Explosive substances and articles",
            "2.1": "Flammable gases",
            "2.2": "Non-flammable, non-toxic gases",
            "2.3": "Toxic gases",
            "3": "Flammable liquids",
            "4.1": "Flammable solids, self-reactive substances, polymerizing substances and solid desensitized explosives",
            "4.2": "Substances liable to spontaneous combustion",
            "4.3": "Substances which, in contact with water, emit flammable gases",
            "5.1": "Oxidizing substances",
            "5.2": "Organic peroxides",
            "6.1": "Toxic substances",
            "6.2": "Infectious substances",
            "7": "Radioactive material",
            "8": "Corrosive substances",
            "9": "Miscellaneous dangerous substances and articles",
        },
        "division": "{name}, division {cls}",
        "digits": {
            "2": "Emission of gas due to pressure or to chemical reaction",
            "3": "Flammability of liquids (vapours) and gases or self-heating liquid",
            "4": "Flammability of solids or self-heating solid",
            "5": "Oxidizing (fire-intensifying) effect",
            "6": "Toxicity or risk of infection",
            "7": "Radioactivity",
            "8": "Corrosivity",
            "9": "Risk of spontaneous violent reaction",
        },
        "exact": {
            "20": "Asphyxiant gas or gas without subsidiary hazard",
            "23": "Flammable gas",
            "25": "Oxidizing (fire-intensifying) gas",
            "26": "Toxic gas",
            "263": "Toxic gas, flammable",
            "265": "Toxic gas, oxidizing (fire-intensifying)",
            "268": "Toxic gas, corrosive",
            "30": "Flammable liquid (flash point between 23 \u00b0C and 60 \u00b0C)",
            "33": "Highly flammable liquid (flash point below 23 \u00b0C)",
            "40": "Flammable solid, self-reactive or self-heating substance",
            "50": "Oxidizing (fire-intensifying) substance",
            "55": "Strongly oxidizing (fire-intensifying) substance",
            "60": "Toxic or slightly toxic substance",
            "66": "Highly toxic substance",
            "70": "Radioactive material",
            "80": "Corrosive or slightly corrosive substance",
            "88": "Highly corrosive substance",
            "22": "Refrigerated gas",
            "223": "Refrigerated gas, flammable",
            "225": "Refrigerated gas, oxidizing (fire-intensifying)",
            "239": "Flammable gas which can spontaneously lead to violent reaction",
            "333": "Pyrophoric liquid",
            "43": "Spontaneously flammable (pyrophoric) solid",
            "44": "Flammable solid in the molten state at an elevated temperature",
            "539": "Flammable organic peroxide",
            "606": "Infectious substance",
            "90": "Environmentally hazardous substance; miscellaneous dangerous substance",
            "99": "Miscellaneous dangerous substance carried at an elevated temperature",
        },
        "intensified": "{meaning} (intensified)",
        "digit_summary": "Principal hazard: {principal}; subsidiary hazard(s): {subsidiary}",
        "water_reactive": "Reacts dangerously with water (use water only with the approval of experts)",
        "line_class": "ADR class {cls}: {name}",
        "line_hin": "Hazard identification number {hin}: {meaning}",
        "sentence": "Classification under ADR: {parts}.",
        "sentence_classes": "{names}",
        "sentence_class": "class {cls} ({name})",
        "sentence_hins": "hazard identification number(s) {hins}",
    },
    "German": {
        "classes": {
            "1": "Explosive Stoffe und Gegenst\u00e4nde mit Explosivstoff",
            "2.1": "Entz\u00fcndbare Gase",
            "2.2": "Nicht entz\u00fcndbare, nicht giftige Gase",
            "2.3": "Giftige Gase",
            "3": "Entz\u00fcndbare fl\u00fcssige Stoffe",
            "4.1": "Entz\u00fcndbare feste Stoffe, selbstzersetzliche Stoffe, polymerisierende Stoffe und desensibilisierte explosive feste Stoffe",
            "4.2": "Selbstentz\u00fcndliche Stoffe",
            "4.3": "Stoffe, die in Ber\u00fchrung mit Wasser entz\u00fcndbare Gase entwickeln",
            "5.1": "Entz\u00fcndend (oxidierend) wirkende Stoffe",
            "5.2": "Organische Peroxide",
            "6.1": "Giftige Stoffe",
            "6.2": "Ansteckungsgef\u00e4hrliche Stoffe",
            "7": "Radioaktive Stoffe",
            "8": "\u00c4tzende Stoffe",
            "9": "Verschiedene gef\u00e4hrliche Stoffe und Gegenst\u00e4nde",
        },
        "division": "{name}, Unterklasse {cls}",
        "digits": {
            "2": "Entweichen von Gas durch Druck oder durch chemische Reaktion",
            "3": "Entz\u00fcndbarkeit von fl\u00fcssigen Stoffen (D\u00e4mpfen) und Gasen oder selbsterhitzungsf\u00e4higer fl\u00fcssiger Stoff",
            "4": "Entz\u00fcndbarkeit von festen Stoffen oder selbsterhitzungsf\u00e4higer fester Stoff",
            "5": "Oxidierende (brandf\u00f6rdernde) Wirkung",
            "6": "Giftigkeit oder Ansteckungsgefahr",
            "7": "Radioaktivit\u00e4t",
            "8": "\u00c4tzwirkung",
            "9": "Gefahr einer spontanen heftigen Reaktion",
        },
        "exact": {
            "20": "Erstickendes Gas oder Gas ohne Nebengefahr",
            "23": "Entz\u00fcndbares Gas",
            "25": "Oxidierendes (brandf\u00f6rderndes) Gas",
            "26": "Giftiges Gas",
            "263": "Giftiges Gas, entz\u00fcndbar",
            "265": "Giftiges Gas, oxidierend (brandf\u00f6rdernd)",
            "268": "Giftiges Gas, \u00e4tzend",
            "30": "Entz\u00fcndbarer fl\u00fcssiger Stoff (Flammpunkt zwischen 23 \u00b0C und 60 \u00b0C)",
            "33": "Leicht entz\u00fcndbarer fl\u00fcssiger Stoff (Flammpunkt unter 23 \u00b0C)",
            "40": "Entz\u00fcndbarer fester Stoff, selbstzersetzlicher oder selbsterhitzungsf\u00e4higer Stoff",
            "50": "Oxidierender (brandf\u00f6rdernder) Stoff",
            "55": "Stark oxidierender (brandf\u00f6rdernder) Stoff",
            "60": "Giftiger oder gesundheitssch\u00e4dlicher Stoff",
            "66": "Sehr giftiger Stoff",
            "70": "Radioaktiver Stoff",
            "80": "\u00c4tzender oder schwach \u00e4tzender Stoff",
            "88": "Stark \u00e4tzender Stoff",
            "22": "Tiefgek\u00fchltes Gas",
            "223": "Tiefgek\u00fchltes Gas, entz\u00fcndbar",
            "225": "Tiefgek\u00fchltes Gas, oxidierend (brandf\u00f6rdernd)",
            "239": "Entz\u00fcndbares Gas, das spontan zu einer heftigen Reaktion f\u00fchren kann",
            "333": "Pyrophorer fl\u00fcssiger Stoff",
            "43": "Selbstentz\u00fcndlicher (pyrophorer) fester Stoff",
            "44": "Entz\u00fcndbarer fester Stoff, der sich bei erh\u00f6hter Temperatur im geschmolzenen Zustand befindet",
            "539": "Entz\u00fcndbares organisches Peroxid",
            "606": "Ansteckungsgef\u00e4hrlicher Stoff",
            "90": "Umweltgef\u00e4hrdender Stoff; verschiedene gef\u00e4hrliche Stoffe",
            "99": "Verschiedene gef\u00e4hrliche Stoffe, die bei erh\u00f6hter Temperatur bef\u00f6rdert werden",
        },
        "intensified": "{meaning} (verst\u00e4rkt)",
        "digit_summary": "Hauptgefahr: {principal}; Nebengefahr(en): {subsidiary}",
        "water_reactive": "Reagiert in gef\u00e4hrlicher Weise mit Wasser (Wasser nur nach Freigabe durch Fachleute einsetzen)",
        "line_class": "ADR-Klasse {cls}: {name}",
        "line_hin": "Gefahrnummer {hin}: {meaning}",
        "sentence": "Einstufung nach ADR: {parts}.",
        "sentence_classes": "{names}",
        "sentence_class": "Klasse {cls} ({name})",
        "sentence_hins": "Gefahrnummer(n) {hins}",
    },
}

ADDITIONAL_HIN_TEXTS = {
    "English": {
        "238": "Flammable gas, corrosive",
        "28": "Corrosive gas",
        "323": "Flammable liquid which reacts with water, emitting flammable gases",
        "336": "Highly flammable liquid, toxic",
        "338": "Highly flammable liquid, corrosive",
        "339": "Highly flammable liquid which can spontaneously lead to violent reaction",
        "36": "Flammable liquid (flash point between 23 \u00b0C and 60 \u00b0C), slightly toxic, or self-heating liquid, toxic",
        "362": "Flammable liquid, toxic, which reacts with water, emitting flammable gases",
        "368": "Flammable liquid, toxic, corrosive",
        "38": "Flammable liquid (flash point between 23 \u00b0C and 60 \u00b0C), slightly corrosive, or self-heating liquid, corrosive",
        "382": "Flammable liquid, corrosive, which reacts with water, emitting flammable gases",
        "39": "Flammable liquid which can spontaneously lead to violent reaction",
        "423": "Solid which reacts with water, emitting flammable gases",
        "432": "Spontaneously flammable (pyrophoric) solid which reacts with water, emitting flammable gases",
        "446": "Flammable solid, toxic, in the molten state at an elevated temperature",
        "46": "Flammable or self-heating solid, toxic",
        "462": "Toxic solid which reacts with water, emitting flammable gases",
        "48": "Flammable or self-heating solid, corrosive",
        "482": "Corrosive solid which reacts with water, emitting flammable gases",
        "558": "Strongly oxidizing (fire-intensifying) substance, corrosive",
        "559": "Strongly oxidizing (fire-intensifying) substance which can spontaneously lead to violent reaction",
        "56": "Oxidizing (fire-intensifying) substance, toxic",
        "568": "Oxidizing (fire-intensifying) substance, toxic, corrosive",
        "58": "Oxidizing (fire-intensifying) substance, corrosive",
        "59": "Oxidizing (fire-intensifying) substance which can spontaneously lead to violent reaction",
        "623": "Toxic liquid which reacts with water, emitting flammable gases",
        "63": "Toxic substance, flammable (flash point between 23 \u00b0C and 60 \u00b0C)",
        "638": "Toxic substance, flammable (flash point between 23 \u00b0C and 60 \u00b0C), corrosive",
        "639": "Toxic substance, flammable (flash point not above 60 \u00b0C), which can spontaneously lead to violent reaction",
        "64": "Toxic solid, flammable or self-heating",
        "642": "Toxic solid which reacts with water, emitting flammable gases",
        "65": "Toxic substance, oxidizing (fire-intensifying)",
        "663": "Highly toxic substance, flammable (flash point not above 60 \u00b0C)",
        "664": "Highly toxic solid, flammable or self-heating",
        "665": "Highly toxic substance, oxidizing (fire-intensifying)",
        "668": "Highly toxic substance, corrosive",
        "669": "Highly toxic substance which can spontaneously lead to violent reaction",
        "68": "Toxic substance, corrosive",
        "69": "Toxic or slightly toxic substance which can spontaneously lead to violent reaction",
        "768": "Radioactive material, toxic, corrosive",
        "823": "Corrosive liquid which reacts with water, emitting flammable gases",
        "83": "Corrosive or slightly corrosive substance, flammable (flash point between 23 \u00b0C and 60 \u00b0C)",
        "836": "Corrosive or slightly corrosive substance, flammable (flash point between 23 \u00b0C and 60 \u00b0C), toxic",
        "839": "Corrosive or slightly corrosive substance, flammable, which can spontaneously lead to violent reaction",
        "84": "Corrosive solid, flammable or self-heating",
        "842": "Corrosive solid which reacts with water, emitting flammable gases",
        "86": "Corrosive or slightly corrosive substance, toxic",
        "85": "Corrosive or slightly corrosive substance, oxidizing (fire-intensifying)",
        "856": "Corrosive or slightly corrosive substance, oxidizing (fire-intensifying), toxic",
        "883": "Highly corrosive substance, flammable (flash point between 23 \u00b0C and 60 \u00b0C)",
        "884": "Highly corrosive solid, flammable or self-heating",
        "885": "Highly corrosive substance, oxidizing (fire-intensifying)",
        "886": "Highly corrosive substance, toxic",
        "89": "Corrosive or slightly corrosive substance which can spontaneously lead to violent reaction",
    },
    "German": {
        "238": "Entz\u00fcndbares Gas, \u00e4tzend",
        "28": "\u00c4tzendes Gas",
        "323": "Entz\u00fcndbarer fl\u00fcssiger Stoff, der mit Wasser reagiert und entz\u00fcndbare Gase entwickelt",
        "336": "Leicht entz\u00fcndbarer fl\u00fcssiger Stoff, giftig",
        "338": "Leicht entz\u00fcndbarer fl\u00fcssiger Stoff, \u00e4tzend",
        "339": "Leicht entz\u00fcndbarer fl\u00fcssiger Stoff, der spontan zu einer heftigen Reaktion f\u00fchren kann",
        "36": "Entz\u00fcndbarer fl\u00fcssiger Stoff (Flammpunkt zwischen 23 \u00b0C und 60 \u00b0C), schwach giftig, oder selbsterhitzungsf\u00e4higer fl\u00fcssiger Stoff, giftig",
        "362": "Entz\u00fcndbarer fl\u00fcssiger Stoff, giftig, der mit Wasser reagiert und entz\u00fcndbare Gase entwickelt",
        "368": "Entz\u00fcndbarer fl\u00fcssiger Stoff, giftig, \u00e4tzend",
        "38": "Entz\u00fcndbarer fl\u00fcssiger Stoff (Flammpunkt zwischen 23 \u00b0C und 60 \u00b0C), schwach \u00e4tzend, oder selbsterhitzungsf\u00e4higer fl\u00fcssiger Stoff, \u00e4tzend",
        "382": "Entz\u00fcndbarer fl\u00fcssiger Stoff, \u00e4tzend, der mit Wasser reagiert und entz\u00fcndbare Gase entwickelt",
        "39": "Entz\u00fcndbarer fl\u00fcssiger Stoff, der spontan zu einer heftigen Reaktion f\u00fchren kann",
        "423": "Fester Stoff, der mit Wasser reagiert und entz\u00fcndbare Gase entwickelt",
        "432": "Selbstentz\u00fcndlicher (pyrophorer) fester Stoff, der mit Wasser reagiert und entz\u00fcndbare Gase entwickelt",
        "446": "Entz\u00fcndbarer fester Stoff, giftig, im geschmolzenen Zustand bei erh\u00f6hter Temperatur",
        "46": "Entz\u00fcndbarer oder selbsterhitzungsf\u00e4higer fester Stoff, giftig",
        "462": "Giftiger fester Stoff, der mit Wasser reagiert und entz\u00fcndbare Gase entwickelt",
        "48": "Entz\u00fcndbarer oder selbsterhitzungsf\u00e4higer fester Stoff, \u00e4tzend",
        "482": "\u00c4tzender fester Stoff, der mit Wasser reagiert und entz\u00fcndbare Gase entwickelt",
        "558": "Stark oxidierender (brandf\u00f6rdernder) Stoff, \u00e4tzend",
        "559": "Stark oxidierender (brandf\u00f6rdernder) Stoff, der spontan zu einer heftigen Reaktion f\u00fchren kann",
        "56": "Oxidierender (brandf\u00f6rdernder) Stoff, giftig",
        "568": "Oxidierender (brandf\u00f6rdernder) Stoff, giftig, \u00e4tzend",
        "58": "Oxidierender (brandf\u00f6rdernder) Stoff, \u00e4tzend",
        "59": "Oxidierender (brandf\u00f6rdernder) Stoff, der spontan zu einer heftigen Reaktion f\u00fchren kann",
        "623": "Giftiger fl\u00fcssiger Stoff, der mit Wasser reagiert und entz\u00fcndbare Gase entwickelt",
        "63": "Giftiger Stoff, entz\u00fcndbar (Flammpunkt zwischen 23 \u00b0C und 60 \u00b0C)",
        "638": "Giftiger Stoff, entz\u00fcndbar (Flammpunkt zwischen 23 \u00b0C und 60 \u00b0C), \u00e4tzend",
        "639": "Giftiger Stoff, entz\u00fcndbar (Flammpunkt nicht \u00fcber 60 \u00b0C), der spontan zu einer heftigen Reaktion f\u00fchren kann",
        "64": "Giftiger fester Stoff, entz\u00fcndbar oder selbsterhitzungsf\u00e4hig",
        "642": "Giftiger fester Stoff, der mit Wasser reagiert und entz\u00fcndbare Gase entwickelt",
        "65": "Giftiger Stoff, oxidierend (brandf\u00f6rdernd)",
        "663": "Sehr giftiger Stoff, entz\u00fcndbar (Flammpunkt nicht \u00fcber 60 \u00b0C)",
        "664": "Sehr giftiger fester Stoff, entz\u00fcndbar oder selbsterhitzungsf\u00e4hig",
        "665": "Sehr giftiger Stoff, oxidierend (brandf\u00f6rdernd)",
        "668": "Sehr giftiger Stoff, \u00e4tzend",
        "669": "Sehr giftiger Stoff, der spontan zu einer heftigen Reaktion f\u00fchren kann",
        "68": "Giftiger Stoff, \u00e4tzend",
        "69": "Giftiger oder schwach giftiger Stoff, der spontan zu einer heftigen Reaktion f\u00fchren kann",
        "768": "Radioaktiver Stoff, giftig, \u00e4tzend",
        "823": "\u00c4tzender fl\u00fcssiger Stoff, der mit Wasser reagiert und entz\u00fcndbare Gase entwickelt",
        "83": "\u00c4tzender oder schwach \u00e4tzender Stoff, entz\u00fcndbar (Flammpunkt zwischen 23 \u00b0C und 60 \u00b0C)",
        "836": "\u00c4tzender oder schwach \u00e4tzender Stoff, entz\u00fcndbar (Flammpunkt zwischen 23 \u00b0C und 60 \u00b0C), giftig",
        "839": "\u00c4tzender oder schwach \u00e4tzender Stoff, entz\u00fcndbar, der spontan zu einer heftigen Reaktion f\u00fchren kann",
        "84": "\u00c4tzender fester Stoff, entz\u00fcndbar oder selbsterhitzungsf\u00e4hig",
        "842": "\u00c4tzender fester Stoff, der mit Wasser reagiert und entz\u00fcndbare Gase entwickelt",
        "86": "\u00c4tzender oder schwach \u00e4tzender Stoff, giftig",
        "85": "\u00c4tzender oder schwach \u00e4tzender Stoff, oxidierend (brandf\u00f6rdernd)",
        "856": "\u00c4tzender oder schwach \u00e4tzender Stoff, oxidierend (brandf\u00f6rdernd), giftig",
        "883": "Stark \u00e4tzender Stoff, entz\u00fcndbar (Flammpunkt zwischen 23 \u00b0C und 60 \u00b0C)",
        "884": "Stark \u00e4tzender fester Stoff, entz\u00fcndbar oder selbsterhitzungsf\u00e4hig",
        "885": "Stark \u00e4tzender Stoff, oxidierend (brandf\u00f6rdernd)",
        "886": "Stark \u00e4tzender Stoff, giftig",
        "89": "\u00c4tzender oder schwach \u00e4tzender Stoff, der spontan zu einer heftigen Reaktion f\u00fchren kann",
    },
}
for _language, _texts in ADDITIONAL_HIN_TEXTS.items():
    REFERENCE_TEXTS[_language]["exact"].update(_texts)

def reference_texts(language):
    return REFERENCE_TEXTS.get(language) or REFERENCE_TEXTS["English"]

def describe_adr_class(adr_class, texts):
    name = texts["classes"].get(adr_class)
    if name:
        return name
    if adr_class.split(".")[0] == "1":             # divisions 1.1 to 1.6
        return texts["division"].format(name=texts["classes"]["1"], cls=adr_class)
    return ""

def describe_hin(hin, texts):
    code = hin.upper()
    water_reactive = code.startswith("X")
    code = code[1:] if water_reactive else code

    if code in texts["exact"]:
        meaning = texts["exact"][code]
    else:
        # A repeated digit intensifies the hazard of that digit; a trailing 0 means "no subsidiary hazard"
        parts = []
        previous = ""
        for digit in code:
            if digit == "0":
                previous = digit
                continue
            if digit == previous and parts:
                if not parts[-1][1]:
                    parts[-1] = (parts[-1][0], True)
                continue
            if digit in texts["digits"]:
                parts.append((digit, False))
            previous = digit
        phrases = [texts["intensified"].format(meaning=texts["digits"][digit]) if intensified
                   else texts["digits"][digit] for digit, intensified in parts]
        if len(phrases) > 1:
            meaning = texts["digit_summary"].format(principal=phrases[0], subsidiary=", ".join(phrases[1:]))
        else:
            meaning = "".join(phrases)
    if water_reactive:
        meaning = f"{meaning}; {texts['water_reactive']}" if meaning else texts["water_reactive"]
    return meaning

def build_reference(card, language):
    # Returns (structured reference dict, one technical sentence, list of hazard lines)
    texts = reference_texts(language)
    classes = [{"adr_class": adr_class, "name": describe_adr_class(adr_class, texts)} for adr_class in card["adr_classes"]]
    hins = [{"hin": hin, "meaning": describe_hin(hin, texts)} for hin in card["hazard_numbers"]]

    lines = [texts["line_class"].format(cls=item["adr_class"], name=item["name"]) for item in classes if item["name"]]
    lines += [texts["line_hin"].format(hin=item["hin"], meaning=item["meaning"]) for item in hins if item["meaning"]]

    sentence_parts = []
    class_parts = [texts["sentence_class"].format(cls=item["adr_class"], name=item["name"]) for item in classes if item["name"]]
    if class_parts:
        sentence_parts.append(", ".join(class_parts))
    if hins:
        sentence_parts.append(texts["sentence_hins"].format(hins=", ".join(item["hin"] for item in hins)))
    sentence = texts["sentence"].format(parts="; ".join(sentence_parts)) if sentence_parts else ""

    return {"classes": classes, "hazard_numbers": hins}, sentence, lines


# --- Card Collection ---
class Samples:
    # Keeps a few raw pages in memory; they are written to disk only when something went wrong
    def __init__(self):
        self.first = {}
        self.failed = {}

    def remember(self, kind, html):
        self.first.setdefault(kind, html)

    def remember_failure(self, name, html):
        if len(self.failed) < 3 and html:
            self.failed[name] = html

    def has_content(self):
        return bool(self.first or self.failed)

class BuildContext:
    # Everything that stays the same for all requests of one run
    def __init__(self, form, card_field, label_field, language, language_field_name, language_value,
                 add_reference, search_url):
        self.form = form
        self.card_field = card_field
        self.label_field = label_field
        self.language = language
        self.language_field_name = language_field_name
        self.language_value = language_value
        self.add_reference = add_reference
        self.search_url = search_url

def search(fetcher, context, criteria):
    # Runs one search and returns (entries, listed_count, html, page_url)
    form = context.form
    data = build_form_data(form, context.language_field_name, context.language_value, criteria)
    if form.method == "post":
        html, page_url = fetcher.get(form.action, data, referer=context.search_url)
    else:
        html, page_url = fetcher.get(form.action + ("&" if "?" in form.action else "?") + urllib.parse.urlencode(data),
                                     referer=context.search_url)
    root = parse_html(html)
    return parse_result_entries(root, page_url), listed_result_count(root), html, page_url

def collect_label_map(fetcher, context, samples, progress, progress_offset, total_steps):
    # One search per ADR label; the hits tell which ERICards contain substances with that label.
    # (The result list itself shows no labels, and a card can hold substances with different labels.)
    labels_by_card, warnings = {}, []
    options = [(value, text.strip()) for value, text, _ in context.label_field.options if text.strip()]
    for index, (value, text) in enumerate(options):
        progress(progress_offset + index, total_steps, f"ADR label {text}")
        try:
            entries, listed, html, _ = search(fetcher, context, {context.label_field.name: value})
        except FetchError as error:
            warnings.append(f"ADR label {text}: skipped, {error}")
            continue
        samples.remember("label_result_page", html)
        if listed is not None and listed != len(entries):
            warnings.append(f"ADR label {text}: read {len(entries)} of {listed} listed substances.")
            samples.remember_failure(f"label_{text.replace('+', '_')}.html", html)
        for entry in entries:
            labels_by_card.setdefault(entry["eric"], set()).add(text)
    return labels_by_card, warnings

def collect_card(fetcher, context, number, value, labels_by_card, samples, check_consistency=False):
    # --- Search result for this card ---
    entries, listed, html, page_url = search(fetcher, context, {context.card_field.name: value})
    own_entries = [entry for entry in entries if entry["eric"] == number]
    if not own_entries:
        if listed is None and not entries:
            raise EmptyCardError()                       # "No substances were found matching your criteria"
        samples.remember_failure(f"result_{number}.html", html)
        raise ParseError("no substances found in the search result")
    samples.remember("result_page", html)

    problems = []
    if listed is not None and listed != len(entries):
        problems.append(f"read {len(entries)} of {listed} listed substances")
        samples.remember_failure(f"result_{number}.html", html)

    # --- Card page (the card text is the same for all substances of the card) ---
    sections, headline, source_url = {}, "", ""
    card_html, source_url = fetcher.get(own_entries[0]["link"], referer=page_url)
    samples.remember("card_page", card_html)
    card_root = parse_html(card_html)
    sections, headline = extract_numbered_sections(card_root)
    if len(sections) < 3:
        samples.remember_failure(f"card_{number}.html", card_html)
        raise ParseError("card page structure not recognised")
    description, hazards = derive_fields(sections, headline)

    # Spot check: the card text must not depend on the substance the page was opened from
    if check_consistency and len(own_entries) >= 2 and own_entries[-1]["link"] != own_entries[0]["link"]:
        other_html, _ = fetcher.get(own_entries[-1]["link"], referer=page_url)
        other_sections, _ = extract_numbered_sections(parse_html(other_html))
        if other_sections != sections:
            problems.append("card text differs between its first and last substance")
            samples.remember_failure(f"card_{number}_last_substance.html", other_html)

    un_numbers = sorted({entry["un"] for entry in own_entries}, key=natural_sort_key)
    names = unique_keep_order([entry["name"] for entry in own_entries])
    hins = sorted({entry["hin"] for entry in own_entries if entry["hin"]}, key=natural_sort_key)
    labels = sorted(labels_by_card.get(number, ()), key=natural_sort_key)
    classes = split_adr_classes(labels)
    if not classes:
        # Cards without a selectable ADR label (e.g. excepted packages): use the class shown on the card page
        header_class = parse_card_class(card_root)
        if header_class:
            classes = [header_class]
        elif number.split("-")[0] in ("1", "3", "7", "8", "9"):
            classes = [number.split("-")[0]]                # these ERIC prefixes always equal the ADR class

    card = {
        "ericard_number": number,
        "un_numbers": un_numbers,
        "substance_names": names,
        "adr_classes": classes,
        "hazard_numbers": hins,
        "description": description,
        "known_hazards": hazards,
        "verified": True,
        "adr_labels": labels,
        "substances": [{"un": entry["un"], "name": entry["name"], "hin": entry["hin"]} for entry in own_entries],
        "sections": sections,
        "source_url": source_url,
        "sources": ["ericards.net"],
    }

    # --- Technical reference data (ADR) ---
    if context.add_reference:
        reference, sentence, lines = build_reference(card, context.language)
        card["description"] = " ".join(part for part in (description, sentence) if part)
        card["known_hazards"] = unique_keep_order(hazards + lines)
        card["reference"] = reference
        card["sources"].append("ADR classification reference (built in)")

    if not description:
        problems.append("no description on the card page")
    if not hazards:
        problems.append("no hazards on the card page")
    if not classes:
        problems.append("no ADR label found")
    if not hins and number.split("-")[0] not in ("1", "7"):
        problems.append("no hazard number (HIN) found")        # classes 1 and 7 have no HIN for some or all entries
    return card, problems


# --- Verification ---
def verify_cards(cards, empty_cards, card_warnings, listed_card_count, notes):
    # Completeness is checked against the card list of the website and against the figures of its
    # "Development" page, which count the substance entries (rows of the result lists) per ADR class.
    warnings = list(card_warnings)
    notes = list(notes)
    all_un = {un for card in cards for un in card["un_numbers"]}
    entry_total = sum(len(card["substances"]) for card in cards)

    if len(cards) + len(empty_cards) != listed_card_count:
        warnings.append(f"Collected {len(cards)} of {listed_card_count} listed ERICards.")
    if empty_cards:
        notes.append(f"{len(empty_cards)} listed ERICards have no substances in the current database and were "
                     f"not included: {', '.join(empty_cards)}.")
    if len(cards) != EXPECTED_CARDS_TOTAL:
        notes.append(f"{len(cards)} ERICards with substances; the Development page documents {EXPECTED_CARDS_TOTAL}.")

    # The documented class figures add up to one more than the documented total. A shortfall of that size
    # is tolerated as long as the total itself is reached.
    allowance = sum(entries for _, entries in EXPECTED_BY_CLASS.values()) - EXPECTED_ENTRIES_TOTAL
    shortfall_notes, shortfall = [], 0
    per_class, differing = {}, []
    for prefix, (cards_expected, entries_expected) in EXPECTED_BY_CLASS.items():
        class_cards = [card for card in cards if card["ericard_number"].split("-")[0] == prefix]
        entries = sum(len(card["substances"]) for card in class_cards)
        per_class[prefix] = {
            "cards": len(class_cards), "cards_documented": cards_expected,
            "substance_entries": entries, "substance_entries_documented": entries_expected,
        }
        if len(class_cards) < cards_expected:
            warnings.append(f"Class {prefix}: {len(class_cards)} ERICards, fewer than the {cards_expected} documented.")
        if entries < entries_expected:
            shortfall += entries_expected - entries
            shortfall_notes.append(f"Class {prefix}: {entries} substance entries, fewer than the {entries_expected} documented.")
        if len(class_cards) > cards_expected or entries > entries_expected:
            differing.append(prefix)
    if differing:
        notes.append("More cards or entries than documented in class(es): " + ", ".join(differing) + ".")
    if shortfall_notes:
        if entry_total >= EXPECTED_ENTRIES_TOTAL and shortfall <= allowance:
            notes.append(" ".join(shortfall_notes) + f" The documented class figures add up to "
                         f"{EXPECTED_ENTRIES_TOTAL + allowance}, the documented total is {EXPECTED_ENTRIES_TOTAL} "
                         "and was reached.")
        else:
            warnings.extend(shortfall_notes)

    return {
        "status": "ok" if not warnings else "warnings",
        "cards_found": len(cards),
        "cards_listed": listed_card_count,
        "cards_without_substances": empty_cards,
        "substance_entries": entry_total,
        "un_numbers_found": len(all_un),
        "documented_cards": EXPECTED_CARDS_TOTAL,
        "documented_substance_entries": EXPECTED_ENTRIES_TOTAL,
        "per_class": per_class,
        "notes": notes,
        "warnings": warnings[:200],
    }

def format_summary(verification, path, language):
    lines = [
        f"Language: {language}",
        f"ERICards: {verification['cards_found']} with substances ({verification['cards_listed']} listed)",
        f"Substance entries: {verification['substance_entries']} "
        f"({verification['un_numbers_found']} distinct UN numbers)",
        f"Status: {'all checks passed' if verification['status'] == 'ok' else 'completed with warnings'}",
    ]
    for note in verification.get("notes", []):
        lines.append(f"Note: {note}")
    shown = verification["warnings"][:12]
    if shown:
        lines.append("")
        lines.extend(f"- {warning}" for warning in shown)
        if len(verification["warnings"]) > len(shown):
            lines.append(f"- ... and {len(verification['warnings']) - len(shown)} more (see the verification block in the file)")
    lines.append("")
    lines.append(f"Saved to:\n{path}")
    return "\n".join(lines)


# --- Build Process ---
def output_folder_for(parent_dir, language=DEFAULT_LANGUAGE):
    # English keeps the plain scheme; other languages get a suffix so several languages can coexist
    name = f"{OUTPUT_FOLDER_PREFIX}{date.today().isoformat()}"
    if language != DEFAULT_LANGUAGE:
        name += "_" + language.replace(" ", "_")
    return Path(parent_dir) / name

def write_debug_samples(folder, samples):
    debug_dir = folder / DEBUG_FOLDER_NAME
    debug_dir.mkdir(parents=True, exist_ok=True)
    for kind, html in samples.first.items():
        (debug_dir / f"sample_{kind}.html").write_text(html, encoding="utf-8")
    for name, html in samples.failed.items():
        (debug_dir / f"failed_{name}").write_text(html, encoding="utf-8")
    return debug_dir

def prepare_context(fetcher, base_url, language, add_reference, samples, notes):
    # Loads the search page, resolves the chosen language and returns (context, card list)
    english_page = urllib.parse.urljoin(base_url, SEARCH_PAGE.format(language_id=DEFAULT_LANGUAGE_ID))
    html, final_url = fetcher.get(english_page)
    samples.remember("search_page", html)
    form, card_field, card_list = locate_card_list(extract_forms(parse_html(html), final_url))
    if not card_list:
        raise BuildError("Could not find the list of ERICards on the advanced search page. "
                         "The website layout may have changed.")
    language_field = locate_language_field(form)
    option = None

    if language_field is None:
        if language != DEFAULT_LANGUAGE:
            raise BuildError("Could not find the language selection on the advanced search page. "
                             "The website layout may have changed.")
    else:
        native_name = language_entry(language)[1]
        option = match_language_option(language_field, language, native_name)
        if option is None:
            raise BuildError(f"The website does not offer the language '{language}' ({native_name}).")

        if language != DEFAULT_LANGUAGE:
            # Reload the search page in the chosen language so the form carries that language
            html, final_url = fetcher.get(urllib.parse.urljoin(base_url, SEARCH_PAGE.format(language_id=option[0])))
            samples.remember("search_page_selected_language", html)
            new_form, new_card_field, new_card_list = locate_card_list(extract_forms(parse_html(html), final_url))
            if new_card_list:
                form, card_field, card_list = new_form, new_card_field, new_card_list
                language_field = locate_language_field(form) or language_field
            shown = selected_option_text(language_field)
            if shown and not option_matches_language(shown, language, native_name):
                notes.append(f"The website preselected '{shown}' instead of '{language}'; "
                             "the search form was set to the chosen language explicitly.")

    label_field = locate_label_field(form)
    if label_field is None:
        raise BuildError("Could not find the ADR label selection on the advanced search page. "
                         "The website layout may have changed.")
    if add_reference and language not in REFERENCE_TEXTS:
        notes.append(f"The built-in ADR classification text is not available in {language}; English is used for it.")

    context = BuildContext(
        form, card_field, label_field, language,
        language_field.name if language_field else "", option[0] if option else "",
        add_reference, final_url,
    )
    return context, card_list

def build_database(parent_dir, base_url, progress, cancel_event, delay=REQUEST_DELAY,
                   language=DEFAULT_LANGUAGE, add_reference=True):
    # Returns (json_path, verification). progress(current, total, text) is called before every request group.
    folder = output_folder_for(parent_dir, language)
    samples = Samples()
    notes = []
    fetcher = Fetcher(cancel_event, delay)

    try:
        # --- Search Form ---
        progress(0, 1, "Loading search form ...")
        context, card_list = prepare_context(fetcher, base_url, language, add_reference, samples, notes)
        label_count = len([1 for _, text, _ in context.label_field.options if text.strip()])
        total = label_count + len(card_list)

        # --- ADR Labels ---
        labels_by_card, card_warnings = collect_label_map(fetcher, context, samples, progress, 0, total)

        # --- Cards ---
        cards, empty_cards, consecutive_failures = [], [], 0
        for index, (number, value) in enumerate(card_list):
            progress(label_count + index, total, f"Card {number}")
            try:
                card, problems = collect_card(fetcher, context, number, value, labels_by_card, samples,
                                              check_consistency=index % CONSISTENCY_SAMPLE_STEP == 0)
                cards.append(card)
                card_warnings.extend(f"{number}: {problem}" for problem in problems)
                consecutive_failures = 0
            except EmptyCardError:
                empty_cards.append(number)
            except (FetchError, ParseError) as error:
                card_warnings.append(f"{number}: skipped, {error}")
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    raise BuildError(f"{MAX_CONSECUTIVE_FAILURES} cards in a row failed (last: {number}: {error}). "
                                     "The website layout may have changed.")
        progress(total, total, "Verifying ...")

        # --- Save ---
        if not cards:
            raise BuildError("No ERICards could be collected.")
        cards.sort(key=lambda card: natural_sort_key(card["ericard_number"]))
        verification = verify_cards(cards, empty_cards, card_warnings, len(card_list), notes)

        folder.mkdir(parents=True, exist_ok=True)
        json_path = folder / OUTPUT_FILE_NAME
        save_json(json_path, {
            "schema_version": SCHEMA_VERSION,
            "last_updated": date.today().isoformat(),
            "source": "https://www.ericards.net (CEFIC ERICards database)",
            "language": language,
            "verification": verification,
            "cards": cards,
        })
        if verification["status"] != "ok" and samples.has_content():
            write_debug_samples(folder, samples)
        return json_path, verification

    except BuildError as error:
        if samples.has_content():
            debug_dir = write_debug_samples(folder, samples)
            raise BuildError(f"{error}\n\nSample pages for troubleshooting were saved to:\n{debug_dir}")
        raise


# --- Application ---
class ERICardsDBBuilder:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("620x630")
        self.root.minsize(620, 630)
        add_footer(root, image_path="assets/footer.png")
        if WINDOW_BACKGROUND_COLOR:
            root.configure(bg=WINDOW_BACKGROUND_COLOR)
        center_window(root)

        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker = None
        self.running_language = DEFAULT_LANGUAGE

        self.language_var = tk.StringVar(value=language_display_name(LANGUAGES[0]))
        self.reference_var = tk.BooleanVar(value=True)

        self.create_widgets()
        self.update_folder_preview()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.poll_events)

    # --- Widget Setup ---
    def create_widgets(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor="#929292", background=GO_COLOR, bordercolor="#929292",
            lightcolor=GO_COLOR, darkcolor=GO_COLOR, thickness=18,
        )
        style.configure("Custom.TCombobox", padding=4)

        self._build_progress_bar()

        main_frame = tk.Frame(self.root, bg=WINDOW_BACKGROUND_COLOR)
        main_frame.pack(fill="both", expand=True, padx=BOX_EXTERNAL_PADDING * 2, pady=BOX_EXTERNAL_PADDING)

        self._build_header(main_frame)
        self._build_settings_box(main_frame)
        self._build_action_row(main_frame)
        self._build_status_box(main_frame)

    def _build_progress_bar(self):
        # Packed before the main content so it reliably reserves its strip at the bottom of the window
        bottom_frame = tk.Frame(self.root, bg=WINDOW_BACKGROUND_COLOR)
        bottom_frame.pack(side="bottom", fill="x", padx=BOX_EXTERNAL_PADDING * 2, pady=(0, BOX_EXTERNAL_PADDING))

        self.progress_bar = ttk.Progressbar(
            bottom_frame, style="Custom.Horizontal.TProgressbar", orient="horizontal", mode="determinate",
        )
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_label = tk.Label(bottom_frame, text="", bg=WINDOW_BACKGROUND_COLOR, font=FONT_SMALL, width=16)
        self.progress_label.pack(side="left", padx=(8, 0))

    def _build_header(self, parent):
        tk.Label(
            parent, text=APP_TITLE, bg=WINDOW_BACKGROUND_COLOR, font=FONT_TITLE, anchor="w",
        ).pack(fill="x")
        tk.Label(
            parent, bg=WINDOW_BACKGROUND_COLOR, fg=MUTED_COLOR, font=FONT_NORMAL, anchor="w", justify="left",
            wraplength=560,
            text=f"Creates {OUTPUT_FILE_NAME} for the ERICards Collector from the online CEFIC ERICards "
                 "database (ericards.net). An internet connection is required.",
        ).pack(fill="x", pady=(2, 0))
        tk.Frame(parent, bg=GROUP_BORDER_COLOR, height=2).pack(fill="x", pady=(10, 12))

    def _build_settings_box(self, parent):
        box = tk.Frame(
            parent, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        box.pack(fill="x")
        inner = tk.Frame(box, bg=WINDOW_BACKGROUND_COLOR)
        inner.pack(fill="x", padx=BOX_INTERNAL_PADDING * 2, pady=BOX_INTERNAL_PADDING * 1.5)

        tk.Label(inner, text="Settings", bg=WINDOW_BACKGROUND_COLOR, font=FONT_SECTION).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        tk.Label(inner, text="Data language:", bg=WINDOW_BACKGROUND_COLOR, font=FONT_NORMAL).grid(
            row=1, column=0, sticky="w")
        self.language_box = ttk.Combobox(
            inner, textvariable=self.language_var, state="readonly", width=34, style="Custom.TCombobox",
            values=[language_display_name(entry) for entry in LANGUAGES],
        )
        self.language_box.grid(row=1, column=1, sticky="w", padx=(10, 0))
        self.language_box.bind("<<ComboboxSelected>>", lambda event: self.update_folder_preview())

        tk.Label(
            inner, bg=WINDOW_BACKGROUND_COLOR, fg=MUTED_COLOR, font=FONT_SMALL, justify="left", wraplength=540,
            text="Language of substance names and card texts. The program interface always stays English.",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 8))

        tk.Checkbutton(
            inner, text="Add technical ADR classification details", variable=self.reference_var,
            bg=WINDOW_BACKGROUND_COLOR, activebackground=WINDOW_BACKGROUND_COLOR, font=FONT_NORMAL,
        ).grid(row=3, column=0, columnspan=2, sticky="w")
        tk.Label(
            inner, bg=WINDOW_BACKGROUND_COLOR, fg=MUTED_COLOR, font=FONT_SMALL, justify="left", wraplength=540,
            text="Extends description and known hazards with ADR class names and decoded hazard "
                 "identification numbers (English and German text; other languages use English).",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 8))

        tk.Frame(inner, bg=GROUP_BORDER_COLOR, height=1).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        tk.Label(inner, text="Output:", bg=WINDOW_BACKGROUND_COLOR, font=FONT_NORMAL).grid(
            row=6, column=0, sticky="nw")
        self.folder_label = tk.Label(
            inner, bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=FONT_NORMAL, justify="left", wraplength=440,
        )
        self.folder_label.grid(row=6, column=1, sticky="w", padx=(10, 0))

    def _build_action_row(self, parent):
        row = tk.Frame(parent, bg=WINDOW_BACKGROUND_COLOR)
        row.pack(fill="x", pady=(14, 0))

        self.build_button = tk.Button(
            row, text="Select Folder and Build...", width=BUTTON_WIDTH, font=FONT_BUTTON, pady=6,
            bg=GO_COLOR, fg="white", activebackground=GO_COLOR, activeforeground="white",
            disabledforeground="#D8D8D8", command=self.start_build,
        )
        self.build_button.pack(side="left")
        self.cancel_button = tk.Button(
            row, text="Cancel", width=12, font=FONT_BUTTON, pady=6,
            fg=DANGER_COLOR, command=self.cancel_build, state="disabled",
        )
        self.cancel_button.pack(side="left", padx=(10, 0))

    def _build_status_box(self, parent):
        box = tk.Frame(
            parent, bg=WINDOW_BACKGROUND_COLOR,
            highlightbackground=GROUP_BORDER_COLOR, highlightthickness=BOX_BORDER_THICKNESS,
        )
        box.pack(fill="both", expand=True, pady=(14, 0))
        inner = tk.Frame(box, bg=WINDOW_BACKGROUND_COLOR)
        inner.pack(fill="both", expand=True, padx=BOX_INTERNAL_PADDING * 2, pady=BOX_INTERNAL_PADDING * 1.5)

        tk.Label(inner, text="Status", bg=WINDOW_BACKGROUND_COLOR, font=FONT_SECTION, anchor="w").pack(fill="x")
        self.status_label = tk.Label(
            inner, text="Ready", bg=WINDOW_BACKGROUND_COLOR, fg=HINT_COLOR, font=FONT_STATUS, anchor="w",
        )
        self.status_label.pack(fill="x", pady=(4, 0))
        self.detail_label = tk.Label(
            inner, text="Choose a language, then start the build.", bg=WINDOW_BACKGROUND_COLOR, fg=MUTED_COLOR,
            font=FONT_NORMAL, anchor="nw", justify="left", wraplength=560,
        )
        self.detail_label.pack(fill="x", pady=(2, 0))

    # --- Display Helpers ---
    def selected_language(self):
        index = self.language_box.current()
        return LANGUAGES[index if index >= 0 else 0][0]

    def update_folder_preview(self):
        name = output_folder_for("", self.selected_language()).name
        self.folder_label.config(text=f"{name}/{OUTPUT_FILE_NAME}\ncreated inside the folder you choose")

    def set_status(self, title, detail="", color=HINT_COLOR):
        self.status_label.config(text=title, fg=color)
        self.detail_label.config(text=detail)

    # --- Build Control ---
    def start_build(self):
        parent_dir = filedialog.askdirectory(
            title="Select the folder for the ERICards database",
            initialdir=os.path.join(os.path.expanduser("~"), "Documents"),
        )
        if not parent_dir:
            return

        language = self.selected_language()
        target = output_folder_for(parent_dir, language) / OUTPUT_FILE_NAME
        if target.exists() and not messagebox.askyesno(
            "File Exists", f"{target}\n\nalready exists. Replace it?",
        ):
            return

        self.running_language = language
        self.cancel_event.clear()
        self.set_running(True)
        self.progress_bar.configure(maximum=1, value=0)
        self.progress_label.config(text="")
        self.set_status("Working ...", f"Language: {language}. Loading card list ...")
        self.worker = threading.Thread(
            target=self.run_worker, args=(parent_dir, language, self.reference_var.get()), daemon=True,
        )
        self.worker.start()

    def run_worker(self, parent_dir, language, add_reference):
        try:
            path, verification = build_database(
                parent_dir, BASE_URL,
                lambda current, total, text: self.events.put(("progress", current, total, text)),
                self.cancel_event, language=language, add_reference=add_reference,
            )
            self.events.put(("done", path, verification))
        except CancelledError:
            self.events.put(("cancelled",))
        except BuildError as error:
            self.events.put(("error", str(error)))
        except Exception as error:      # unexpected problem: report it instead of failing silently
            self.events.put(("error", f"Unexpected error: {error!r}"))

    def cancel_build(self):
        self.cancel_event.set()
        self.cancel_button.config(state="disabled")
        self.set_status("Cancelling ...", "Waiting for the current request to finish.", WARNING_COLOR)

    def set_running(self, running):
        self.build_button.config(state="disabled" if running else "normal")
        self.cancel_button.config(state="normal" if running else "disabled")
        self.language_box.config(state="disabled" if running else "readonly")

    def poll_events(self):
        try:
            while True:
                self.handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

    def handle_event(self, event):
        kind = event[0]
        if kind == "progress":
            _, current, total, text = event
            self.progress_bar.configure(maximum=max(total, 1), value=current)
            percent = current / total * 100 if total else 0
            self.progress_label.config(text=f"{current} / {total}  ({percent:.0f}%)")
            self.set_status("Working ...", f"Language: {self.running_language}. {text}")
        elif kind == "done":
            _, path, verification = event
            self.set_running(False)
            ok = verification["status"] == "ok"
            self.set_status(
                "Done" if ok else "Done with warnings",
                f"{verification['cards_found']} ERICards saved to:\n{path}",
                GO_COLOR if ok else WARNING_COLOR,
            )
            summary = format_summary(verification, path, self.running_language)
            if ok:
                messagebox.showinfo("Database Created", summary)
            else:
                messagebox.showwarning("Database Created With Warnings", summary)
            if messagebox.askyesno("Open Folder", "Open the output folder?"):
                open_folder(path.parent)
        elif kind == "cancelled":
            self.set_running(False)
            self.progress_bar.configure(value=0)
            self.progress_label.config(text="")
            self.set_status("Cancelled", "No file was written.", DANGER_COLOR)
        elif kind == "error":
            self.set_running(False)
            self.set_status("Build failed", event[1], DANGER_COLOR)
            messagebox.showerror("Build Failed", event[1])

    def on_close(self):
        self.cancel_event.set()
        self.root.destroy()


# --- Command Line Mode ---
def run_cli(arguments):
    # Usage: SP_ERICards_DB_builder.py --cli OUTPUT_DIR [--language NAME] [--no-reference]
    #                                  [--base-url URL] [--delay SECONDS]
    output_dir = arguments[0] if arguments else "."
    base_url, delay, language = BASE_URL, REQUEST_DELAY, DEFAULT_LANGUAGE
    if "--base-url" in arguments:
        base_url = arguments[arguments.index("--base-url") + 1]
    if "--delay" in arguments:
        delay = float(arguments[arguments.index("--delay") + 1])
    if "--language" in arguments:
        language = arguments[arguments.index("--language") + 1]
    try:
        path, verification = build_database(
            output_dir, base_url,
            lambda current, total, text: print(f"[{current}/{total}] {text}"),
            threading.Event(), delay, language=language_entry(language)[0],
            add_reference="--no-reference" not in arguments,
        )
    except BuildError as error:
        print(f"FAILED: {error}")
        return 1
    print(format_summary(verification, path, language))
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        sys.exit(run_cli(sys.argv[2:]))
    root = tk.Tk()
    root.withdraw()
    app = ERICardsDBBuilder(root)
    root.deiconify()
    root.mainloop()