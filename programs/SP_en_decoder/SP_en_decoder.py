import tkinter as tk
import tkinter.font as tkFont
from tkinter import messagebox
from pathlib import Path
import sys
import base64
import codecs
import urllib.parse

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from helper.SP_footer_picture import add_footer
from helper.SP_window_utils import center_window

# --- Style constants ---
GROUP_BORDER_COLOR = "#A7A7A7"
WINDOW_BACKGROUND_COLOR = "#E6E6E6"
SIDEBAR_WIDTH = 210

# --- Codec definitions ---
# Every entry in CODECS below fully describes one method: how to encode
# text -> code, how to decode code -> text, and a short human-readable
# description (allowed characters + an example) used by the "?" info button.
#
# decode functions may raise ValueError (or a subclass, e.g. UnicodeDecodeError
# or binascii.Error, which are both ValueError subclasses) on invalid input -
# this is caught generically wherever a codec is used.


def _hex_encode(text):
    return text.encode("utf-8").hex()


def _hex_decode(text):
    return bytes.fromhex(text).decode("utf-8")


def _base64_encode(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _base64_decode(text):
    return base64.b64decode(text.encode("ascii"), validate=True).decode("utf-8")


def _base32_encode(text):
    return base64.b32encode(text.encode("utf-8")).decode("ascii")


def _base32_decode(text):
    return base64.b32decode(text.encode("ascii")).decode("utf-8")


def _base85_encode(text):
    return base64.b85encode(text.encode("utf-8")).decode("ascii")


def _base85_decode(text):
    return base64.b85decode(text.encode("ascii")).decode("utf-8")


def _binary_encode(text):
    return " ".join(format(b, "08b") for b in text.encode("utf-8"))


def _binary_decode(text):
    chunks = text.split()
    if not chunks:
        return ""
    values = []
    for chunk in chunks:
        value = int(chunk, 2)
        if not (0 <= value <= 255):
            raise ValueError(f"'{chunk}' is not a single byte (0-255) in binary")
        values.append(value)
    return bytes(values).decode("utf-8")


def _octal_encode(text):
    return " ".join(format(b, "03o") for b in text.encode("utf-8"))


def _octal_decode(text):
    chunks = text.split()
    if not chunks:
        return ""
    values = []
    for chunk in chunks:
        value = int(chunk, 8)
        if not (0 <= value <= 255):
            raise ValueError(f"'{chunk}' is not a single byte (0-255) in octal")
        values.append(value)
    return bytes(values).decode("utf-8")


def _url_encode(text):
    return urllib.parse.quote(text, safe="")


def _url_decode(text):
    return urllib.parse.unquote(text, errors="strict")

def _rot13_encode(text):
    return codecs.encode(text, "rot13")


def _rot13_decode(text):
    return codecs.encode(text, "rot13")  # ROT13 is its own inverse


def _atbash_encode(text):
    result = []
    for ch in text:
        if "A" <= ch <= "Z":
            result.append(chr(ord("Z") - (ord(ch) - ord("A"))))
        elif "a" <= ch <= "z":
            result.append(chr(ord("z") - (ord(ch) - ord("a"))))
        else:
            result.append(ch)
    return "".join(result)


def _atbash_decode(text):
    return _atbash_encode(text)  # mirroring the alphabet twice returns the original


MORSE_CODE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.", "!": "-.-.--",
    "/": "-..-.", "(": "-.--.", ")": "-.--.-", "&": ".-...", ":": "---...",
    ";": "-.-.-.", "=": "-...-", "+": ".-.-.", "-": "-....-", "_": "..--.-",
    '"': ".-..-.", "$": "...-..-", "@": ".--.-.",
}
REVERSE_MORSE = {code: char for char, code in MORSE_CODE.items()}


def _morse_encode(text):
    # Words (split on whitespace) are separated by " / "; letters within a
    # word are separated by a single space.
    encoded_words = []
    for word in text.split():
        letters = []
        for ch in word.upper():
            if ch not in MORSE_CODE:
                raise ValueError(f"'{ch}' has no Morse code representation")
            letters.append(MORSE_CODE[ch])
        encoded_words.append(" ".join(letters))
    return " / ".join(encoded_words)


def _morse_decode(text):
    text = text.strip()
    if not text:
        return ""
    decoded_words = []
    for word in text.split(" / "):
        chars = []
        for code in word.split():
            if code not in REVERSE_MORSE:
                raise ValueError(f"'{code}' is not a valid Morse code sequence")
            chars.append(REVERSE_MORSE[code])
        decoded_words.append("".join(chars))
    return " ".join(decoded_words)


NATO_WORDS = {
    "A": "Alpha", "B": "Bravo", "C": "Charlie", "D": "Delta", "E": "Echo",
    "F": "Foxtrot", "G": "Golf", "H": "Hotel", "I": "India", "J": "Juliett",
    "K": "Kilo", "L": "Lima", "M": "Mike", "N": "November", "O": "Oscar",
    "P": "Papa", "Q": "Quebec", "R": "Romeo", "S": "Sierra", "T": "Tango",
    "U": "Uniform", "V": "Victor", "W": "Whiskey", "X": "X-ray", "Y": "Yankee",
    "Z": "Zulu",
    "0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four",
    "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine",
}
REVERSE_NATO = {word.upper(): char for char, word in NATO_WORDS.items()}
SPACE_TOKEN = "//"  # two characters, so it can never collide with a single
                     # passed-through character (see _nato_encode/_a1z26_encode)


def _nato_encode(text):
    tokens = []
    for ch in text:
        if ch == " ":
            tokens.append(SPACE_TOKEN)
        elif ch.upper() in NATO_WORDS:
            tokens.append(NATO_WORDS[ch.upper()])
        else:
            tokens.append(ch)
    return " ".join(tokens)


def _nato_decode(text):
    chars = []
    for token in text.split():
        if token == SPACE_TOKEN:
            chars.append(" ")
        elif token.upper() in REVERSE_NATO:
            chars.append(REVERSE_NATO[token.upper()])
        elif len(token) == 1:
            chars.append(token)
        else:
            raise ValueError(f"'{token}' is not a recognized NATO alphabet word")
    return "".join(chars)


def _a1z26_encode(text):
    tokens = []
    for ch in text:
        if ch == " ":
            tokens.append(SPACE_TOKEN)
        elif "A" <= ch.upper() <= "Z":
            tokens.append(str(ord(ch.upper()) - ord("A") + 1))
        else:
            tokens.append(ch)
    return " ".join(tokens)


def _a1z26_decode(text):
    chars = []
    for token in text.split():
        if token == SPACE_TOKEN:
            chars.append(" ")
        elif token.isdigit() and 1 <= int(token) <= 26:
            chars.append(chr(ord("A") + int(token) - 1))
        elif len(token) == 1:
            chars.append(token)
        else:
            raise ValueError(f"'{token}' is not a valid A1Z26 token")
    return "".join(chars)


LEET_MAP = {"a": "4", "b": "8", "e": "3", "g": "9", "i": "1", "o": "0", "s": "5", "t": "7"}
REVERSE_LEET = {digit: letter for letter, digit in LEET_MAP.items()}


def _leet_encode(text):
    return "".join(LEET_MAP.get(ch.lower(), ch) for ch in text)


def _leet_decode(text):
    return "".join(REVERSE_LEET.get(ch, ch) for ch in text)


CODECS = {
    "Hex": {
        "encode": _hex_encode,
        "decode": _hex_decode,
        "info": "Allowed characters: 0-9 and a-f/A-F (two hex digits per byte).\n"
                "Example: 'Hi' -> '4869'",
    },
    "Base64": {
        "encode": _base64_encode,
        "decode": _base64_decode,
        "info": "Allowed characters: A-Z, a-z, 0-9, '+', '/', padded with '='.\n"
                "Example: 'Hi' -> 'SGk='",
    },
    "Base32": {
        "encode": _base32_encode,
        "decode": _base32_decode,
        "info": "Allowed characters: A-Z and 2-7, padded with '='.\n"
                "Example: 'Hi' -> 'JBUQ===='",
    },
    "Base85": {
        "encode": _base85_encode,
        "decode": _base85_decode,
        "info": "Allowed characters: a wide range of printable ASCII letters,\n"
                "digits and punctuation.\n"
                "Example: 'Hi' -> 'NNE'",
    },
    "Binary": {
        "encode": _binary_encode,
        "decode": _binary_decode,
        "info": "Allowed characters: '0' and '1', grouped into 8-digit bytes\n"
                "separated by spaces.\n"
                "Example: 'Hi' -> '01001000 01101001'",
    },
    "Octal": {
        "encode": _octal_encode,
        "decode": _octal_decode,
        "info": "Allowed characters: digits 0-7, grouped into 3-digit bytes\n"
                "separated by spaces.\n"
                "Example: 'Hi' -> '110 151'",
    },
    "URL Encoding": {
        "encode": _url_encode,
        "decode": _url_decode,
        "info": "Reserved characters become '%' followed by two hex digits;\n"
                "letters, digits and '-_.~' stay unchanged. Malformed '%..'\n"
                "sequences are left as-is instead of raising an error.\n"
                "Example: 'Hello, World!' -> 'Hello%2C%20World%21'",
    },
    "ROT13": {
        "encode": _rot13_encode,
        "decode": _rot13_decode,
        "info": "Every letter is shifted 13 places through the alphabet;\n"
                "case and non-letters stay unchanged. Applying it twice\n"
                "returns the original text, so Encode and Decode do exactly\n"
                "the same thing here.\n"
                "Example: 'Hello' -> 'Uryyb'",
    },
    "Atbash Cipher": {
        "encode": _atbash_encode,
        "decode": _atbash_decode,
        "info": "Each letter A-Z/a-z is mirrored in the alphabet (A<->Z,\n"
                "B<->Y, ...); case is preserved, and anything else (accented\n"
                "letters, digits, punctuation) stays unchanged. Just like\n"
                "ROT13, this cipher is its own inverse.\n"
                "Example: 'Hello' -> 'Svool'",
    },
    "Morse Code": {
        "encode": _morse_encode,
        "decode": _morse_decode,
        "info": "Allowed characters: letters, digits and common punctuation\n"
                "(.,?'!/()&:;=+-_\"$@); anything else can't be encoded.\n"
                "Dots/dashes within one letter have no separator, letters\n"
                "within a word are separated by a space, and words by ' / '.\n"
                "Decoded text always comes out upper-case.\n"
                "Example: 'Hi there' -> '.... .. / - .... . .-. .'",
    },
    "NATO Phonetic Alphabet": {
        "encode": _nato_encode,
        "decode": _nato_decode,
        "info": "Letters and digits become their phonetic spelling word\n"
                "(Alpha, Bravo, ... Zero, One, ...), separated by spaces; a\n"
                "space in the input becomes '//'. Other characters pass\n"
                "through unchanged, and letter case is not preserved on\n"
                "decoding.\n"
                "Example: 'Hi 5' -> 'Hotel India // Five'",
    },
    "A1Z26 Cipher": {
        "encode": _a1z26_encode,
        "decode": _a1z26_decode,
        "info": "Each letter becomes its position in the alphabet (A=1 ...\n"
                "Z=26), separated by spaces; a space in the input becomes\n"
                "'//'. Other characters pass through unchanged, but any\n"
                "number already in the text will decode back into a letter\n"
                "too, so digits don't round-trip. Letter case isn't\n"
                "preserved either.\n"
                "Example: 'Hi' -> '8 9'",
    },
    "Leetspeak": {
        "encode": _leet_encode,
        "decode": _leet_decode,
        "info": "A simple substitution: a/b/e/g/i/o/s/t <-> 4/8/3/9/1/0/5/7;\n"
                "every other character stays unchanged. Not a strict,\n"
                "uniquely-reversible standard - decoding turns any of these\n"
                "digits back into letters, even ones that were already\n"
                "digits in the original text.\n"
                "Example: 'Leet speak' -> 'L337 5p34k'",
    },
}
METHOD_NAMES = sorted(CODECS.keys())

# --- Application state ---
app_state = {
    "selected_method": None,  # name of the currently selected method, or None
    "mode": None,             # "encode", "decode", or None
}
visible_methods = list(METHOD_NAMES)  # methods currently shown in the listbox (after search filtering)


# --- Core logic ---
def _apply_transform():
    method = app_state["selected_method"]
    mode = app_state["mode"]
    if method is None or mode is None:
        return
    text = input_field.get("1.0", "end-1c")
    try:
        if mode == "encode":
            result = CODECS[method]["encode"](text)
        else:
            result = CODECS[method]["decode"](text)
    except ValueError:
        result = (
            f"Invalid input for {method} encoding"
            if mode == "encode"
            else f"Invalid {method} input"
        )
    output_field.delete("1.0", "end")
    output_field.insert("1.0", result)


def run_encode():
    method = app_state["selected_method"]
    if method is None:
        return
    _set_mode("encode")
    _apply_transform()


def run_decode():
    method = app_state["selected_method"]
    if method is None:
        return
    _set_mode("decode")
    _apply_transform()


def _on_input_modified(_event=None):
    if input_field.edit_modified():
        input_field.edit_modified(False)
        _apply_transform()


def _set_mode(mode):
    app_state["mode"] = mode
    method = app_state["selected_method"]
    if mode == "encode":
        encode_button.config(state=tk.DISABLED)
        decode_button.config(state=tk.NORMAL)
        input_label.config(text="Input (Text)")
        output_label.config(text=f"Output ({method})")
    elif mode == "decode":
        encode_button.config(state=tk.NORMAL)
        decode_button.config(state=tk.DISABLED)
        input_label.config(text=f"Input ({method})")
        output_label.config(text="Output (Text)")


def select_method(name):
    app_state["selected_method"] = name
    app_state["mode"] = None
    input_field.delete("1.0", "end")
    output_field.delete("1.0", "end")
    input_label.config(text="Input")
    output_label.config(text="Output")
    encode_button.config(state=tk.NORMAL)
    decode_button.config(state=tk.NORMAL)
    status_label.config(text=f"Selected method: {name}  \u2014  choose Encode or Decode to begin.")
    info_button.config(state=tk.NORMAL, command=lambda: _show_method_info(name))


def _show_method_info(name):
    messagebox.showinfo(title=f"{name} - Format Info", message=CODECS[name]["info"])


def _on_listbox_select(_event):
    selection = method_listbox.curselection()
    if not selection:
        return
    name = visible_methods[selection[0]]
    select_method(name)


def _filter_methods(*_args):
    global visible_methods
    query = search_var.get().strip().lower()
    if query:
        visible_methods = [m for m in METHOD_NAMES if query in m.lower()]
    else:
        visible_methods = list(METHOD_NAMES)

    method_listbox.delete(0, tk.END)
    for m in visible_methods:
        method_listbox.insert(tk.END, m)

    if app_state["selected_method"] in visible_methods:
        method_listbox.selection_set(visible_methods.index(app_state["selected_method"]))


# --- Main window setup ---
root = tk.Tk()
root.withdraw()
root.title("Text Encoder and Decoder")
root.geometry("900x520")
root.minsize(760, 460)
add_footer(root, image_path="assets/footer.png")
if WINDOW_BACKGROUND_COLOR:
    root.configure(bg=WINDOW_BACKGROUND_COLOR)
center_window(root)

label_font = tkFont.Font(family="Arial", size=10, weight="bold")
text_other_font = tkFont.Font(family="Arial", size=10)

main_frame = tk.Frame(root, bg=WINDOW_BACKGROUND_COLOR)
main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
main_frame.columnconfigure(0, weight=0)
main_frame.columnconfigure(1, weight=1)
main_frame.rowconfigure(0, weight=1)

# --- Sidebar UI (method search & list) ---
sidebar_frame = tk.Frame(
    main_frame,
    width=SIDEBAR_WIDTH,
    bg=WINDOW_BACKGROUND_COLOR,
    highlightbackground=GROUP_BORDER_COLOR,
    highlightthickness=1,
)
sidebar_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
sidebar_frame.grid_propagate(False)
sidebar_frame.columnconfigure(0, weight=1)
sidebar_frame.rowconfigure(2, weight=1)

sidebar_title = tk.Label(
    sidebar_frame, text="Methods", font=label_font, bg=WINDOW_BACKGROUND_COLOR, anchor="w"
)
sidebar_title.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

search_var = tk.StringVar()
search_entry = tk.Entry(sidebar_frame, textvariable=search_var)
search_entry.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
search_var.trace_add("write", _filter_methods)

list_frame = tk.Frame(sidebar_frame)
list_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
list_frame.rowconfigure(0, weight=1)
list_frame.columnconfigure(0, weight=1)

list_scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
method_listbox = tk.Listbox(
    list_frame,
    exportselection=False,
    activestyle="none",
    yscrollcommand=list_scrollbar.set,
)
list_scrollbar.config(command=method_listbox.yview)
method_listbox.grid(row=0, column=0, sticky="nsew")
list_scrollbar.grid(row=0, column=1, sticky="ns")

for _name in METHOD_NAMES:
    method_listbox.insert(tk.END, _name)
method_listbox.bind("<<ListboxSelect>>", _on_listbox_select)

# --- Content UI (input / buttons / output) ---
content_frame = tk.Frame(
    main_frame,
    bg=WINDOW_BACKGROUND_COLOR,
    highlightbackground=GROUP_BORDER_COLOR,
    highlightthickness=1,
)
content_frame.grid(row=0, column=1, sticky="nsew")
content_frame.columnconfigure(0, weight=1)
content_frame.rowconfigure(2, weight=1)  # input text field expands
content_frame.rowconfigure(5, weight=1)  # output text field expands

status_frame = tk.Frame(content_frame, bg=WINDOW_BACKGROUND_COLOR)
status_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
status_frame.columnconfigure(0, weight=1)

status_label = tk.Label(
    status_frame,
    text="Select a method from the list on the left to enable encoding and decoding.",
    font=text_other_font,
    fg="#5E5E5E",
    bg=WINDOW_BACKGROUND_COLOR,
    anchor="w",
    justify="left",
    wraplength=1,  # updated on <Configure> below so long status text wraps instead of clipping
)
status_label.grid(row=0, column=0, sticky="ew")
status_frame.bind(
    "<Configure>", lambda e: status_label.config(wraplength=max(e.width - 40, 100))
)

info_button = tk.Button(status_frame, text="?", width=2, state=tk.DISABLED)
info_button.grid(row=0, column=1, sticky="ne", padx=(6, 0))

input_label = tk.Label(
    content_frame, text="Input", font=label_font, bg=WINDOW_BACKGROUND_COLOR, anchor="w"
)
input_label.grid(row=1, column=0, sticky="w", padx=8, pady=(6, 2))

input_frame = tk.Frame(content_frame)
input_frame.grid(row=2, column=0, sticky="nsew", padx=8)
input_frame.rowconfigure(0, weight=1)
input_frame.columnconfigure(0, weight=1)

input_scrollbar = tk.Scrollbar(input_frame, orient=tk.VERTICAL)
input_field = tk.Text(
    input_frame, height=8, width=40, wrap="char", font="TkFixedFont",
    yscrollcommand=input_scrollbar.set,
)
input_scrollbar.config(command=input_field.yview)
input_field.grid(row=0, column=0, sticky="nsew")
input_scrollbar.grid(row=0, column=1, sticky="ns")
input_field.bind("<<Modified>>", _on_input_modified)

button_frame = tk.Frame(content_frame, bg=WINDOW_BACKGROUND_COLOR)
button_frame.grid(row=3, column=0, pady=8)

encode_button = tk.Button(
    button_frame, text="Encode", width=10, state=tk.DISABLED, command=run_encode
)
encode_button.pack(side=tk.LEFT, padx=5)

decode_button = tk.Button(
    button_frame, text="Decode", width=10, state=tk.DISABLED, command=run_decode
)
decode_button.pack(side=tk.LEFT, padx=5)

output_label = tk.Label(
    content_frame, text="Output", font=label_font, bg=WINDOW_BACKGROUND_COLOR, anchor="w"
)
output_label.grid(row=4, column=0, sticky="w", padx=8, pady=(6, 2))

output_frame = tk.Frame(content_frame)
output_frame.grid(row=5, column=0, sticky="nsew", padx=8, pady=(0, 8))
output_frame.rowconfigure(0, weight=1)
output_frame.columnconfigure(0, weight=1)

output_scrollbar = tk.Scrollbar(output_frame, orient=tk.VERTICAL)
output_field = tk.Text(
    output_frame, height=8, width=40, wrap="char", font="TkFixedFont",
    yscrollcommand=output_scrollbar.set,
)
output_scrollbar.config(command=output_field.yview)
output_field.grid(row=0, column=0, sticky="nsew")
output_scrollbar.grid(row=0, column=1, sticky="ns")

# --- Run application ---
root.deiconify()
root.mainloop()