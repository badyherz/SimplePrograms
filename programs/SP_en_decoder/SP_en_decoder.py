import tkinter as tk
import tkinter.font as tkFont

from SP_footer_picture import add_footer
from SP_window_utils import center_window

GROUP_BORDER_COLOR = "#A7A7A7"
WINDOW_BACKGROUND_COLOR = "#E6E6E6"

# --- encode & decode logic ---
def encode_hex():
    input_text = input_field.get("1.0", "end-1c")
    encoded_text = input_text.encode().hex()
    output_field.delete("1.0", "end")
    output_field.insert("1.0", encoded_text)

def decode_hex():
    input_text = input_field.get("1.0", "end-1c")
    try:
        decoded_text = bytes.fromhex(input_text).decode()
        output_field.delete("1.0", "end")
        output_field.insert("1.0", decoded_text)
    except ValueError:
        output_field.delete("1.0", "end")
        output_field.insert("1.0", "Invalid HEX input")

# --- Create main root ---
root = tk.Tk()
root.withdraw()
root.title("Text Encoder and Decoder")
root.geometry("740x420")
root.minsize(740,420)
add_footer(root, image_path="footer.png")
if WINDOW_BACKGROUND_COLOR:
    root.configure(bg=WINDOW_BACKGROUND_COLOR)
center_window(root)
# ---

label_font = tkFont.Font(family="Arial", size=10, weight="bold")

input_label = tk.Label(root, text="INPUT", font=label_font, pady=10)
input_label.pack()
input_field = tk.Text(root, height=10, width=50)
input_field.pack()

button_frame = tk.Frame(root)
button_frame.pack()

encode_button = tk.Button(button_frame, text="Encode", command=encode_hex)
encode_button.pack(side=tk.LEFT, padx=5, pady=10)

decode_button = tk.Button(button_frame, text="Decode", command=decode_hex)
decode_button.pack(side=tk.LEFT, padx=5, pady=10)

output_label = tk.Label(root, text="OUTPUT", font=label_font, pady=10)
output_label.pack()
output_field = tk.Text(root, height=10, width=50)
output_field.pack()

# ---
root.deiconify()
root.mainloop()