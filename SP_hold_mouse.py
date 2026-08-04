import tkinter as tk
from tkinter import messagebox
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Listener, Key, KeyCode

mouse = MouseController()

class MouseSimulatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simulated Mouse Button Holding")
        self.root.geometry("360x280")  # Increased window size
        self.simulating = False
        self.hold_mode = True
        self.custom_key = None
        self.mouse_button = Button.left
        self.capture_key_mode = False

        self.create_widgets()

        # Listener to monitor key presses
        self.listener = Listener(on_press=self.on_key_press, on_release=self.on_key_release)
        self.listener.start()

    def create_widgets(self):
        # Mouse button selection
        tk.Label(self.root, text="Choose Mouse Button:").pack(anchor="w", padx=10, pady=5)
        self.mouse_button_var = tk.StringVar(value="left")
        tk.Radiobutton(self.root, text="Left", variable=self.mouse_button_var, value="left", command=self.set_mouse_button).pack(anchor="w", padx=20)
        tk.Radiobutton(self.root, text="Right", variable=self.mouse_button_var, value="right", command=self.set_mouse_button).pack(anchor="w", padx=20)

        # Hold mode selection
        tk.Label(self.root, text="Choose Mode:").pack(anchor="w", padx=10, pady=5)
        self.hold_mode_var = tk.BooleanVar(value=True)
        tk.Radiobutton(self.root, text="Hold", variable=self.hold_mode_var, value=True, command=self.set_hold_mode).pack(anchor="w", padx=20)
        tk.Radiobutton(self.root, text="Toggle", variable=self.hold_mode_var, value=False, command=self.set_hold_mode).pack(anchor="w", padx=20)

        # Custom key selection
        tk.Label(self.root, text="Set Custom Key to Activate:").pack(anchor="w", padx=10, pady=5)
        self.key_label = tk.Label(self.root, text="Click here to set a key", bg="lightgrey", width=25)
        self.key_label.pack(anchor="w", padx=20, pady=5)
        self.key_label.bind("<Button-1>", self.activate_key_capture)

        # Exit button
        tk.Button(self.root, text="Exit", command=self.exit_program).pack(side=tk.LEFT, padx=20, pady=10)

    def set_mouse_button(self):
        self.mouse_button = Button.left if self.mouse_button_var.get() == "left" else Button.right

    def set_hold_mode(self):
        self.hold_mode = self.hold_mode_var.get()

    def activate_key_capture(self, event):
        self.capture_key_mode = True
        self.key_label.config(text="Press a key to set...")

    def on_key_press(self, key):
        if self.capture_key_mode:
            # Capture the key
            if isinstance(key, KeyCode):
                self.custom_key = key.char
            elif isinstance(key, Key):
                self.custom_key = key.name
            self.key_label.config(text=f"Key: {self.custom_key}")
            self.capture_key_mode = False
            return

        # Check if the pressed key matches the custom key
        if self.custom_key and (key == KeyCode.from_char(self.custom_key) or key.name == self.custom_key):
            if self.hold_mode:
                mouse.press(self.mouse_button)
            else:
                if not self.simulating:
                    mouse.press(self.mouse_button)
                    self.simulating = True
                else:
                    mouse.release(self.mouse_button)
                    self.simulating = False

    def on_key_release(self, key):
        if self.hold_mode and self.simulating:
            mouse.release(self.mouse_button)
            self.simulating = False

    def exit_program(self):
        self.listener.stop()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = MouseSimulatorApp(root)
    root.mainloop()
