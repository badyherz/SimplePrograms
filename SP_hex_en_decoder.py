import tkinter as tk

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

# Create the main window
window = tk.Tk()
window.title("HEX Encoder and Decoder")

# Create the input field
input_label = tk.Label(window, text="INPUT")
input_label.pack()
input_field = tk.Text(window, height=5, width=50)
input_field.pack()

# Create a frame to hold the buttons
button_frame = tk.Frame(window)
button_frame.pack()

# Create the encode button
encode_button = tk.Button(button_frame, text="Encode", command=encode_hex)
encode_button.pack(side=tk.LEFT, padx=5)

# Create the decode button
decode_button = tk.Button(button_frame, text="Decode", command=decode_hex)
decode_button.pack(side=tk.LEFT, padx=5)

# Create the output field
output_label = tk.Label(window, text="OUTPUT")
output_label.pack()
output_field = tk.Text(window, height=5, width=50)
output_field.pack()

# Start the main event loop
window.mainloop()
