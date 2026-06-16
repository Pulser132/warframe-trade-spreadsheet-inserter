"""Settings dialog for configuring platinum values per ducat tier."""

import tkinter as tk
from tkinter import messagebox, ttk

from config_manager import DUCAT_VALUES, load_ocr_hotkey, save_config, save_ocr_hotkey


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent_app):
        super().__init__(parent_app.root)
        self.parent_app = parent_app

        self.title("Settings")
        self.resizable(False, False)
        self.transient(parent_app.root)
        self.grab_set()

        self.entries = {}

        container = ttk.Frame(self, padding=12)
        container.grid(row=0, column=0)

        ttk.Label(container, text="Ducat Value").grid(row=0, column=0, padx=6, pady=(0, 8))
        ttk.Label(container, text="Platinum Value").grid(row=0, column=1, padx=6, pady=(0, 8))

        for row, ducat_value in enumerate(DUCAT_VALUES, start=1):
            ttk.Label(container, text=f"{ducat_value} ducats").grid(row=row, column=0, padx=6, pady=4, sticky="w")
            var = tk.StringVar(value=str(parent_app.price_map[ducat_value]))
            entry = ttk.Entry(container, textvariable=var, width=10, justify="right")
            entry.grid(row=row, column=1, padx=6, pady=4)
            self.entries[ducat_value] = var

        sep_row = len(DUCAT_VALUES) + 1
        ttk.Separator(container, orient="horizontal").grid(
            row=sep_row, column=0, columnspan=3, sticky="ew", pady=8
        )

        hotkey_row = sep_row + 1
        ttk.Label(container, text="OCR Hotkey").grid(row=hotkey_row, column=0, padx=6, pady=4, sticky="w")
        self.hotkey_var = tk.StringVar(value=load_ocr_hotkey())
        ttk.Entry(container, textvariable=self.hotkey_var, width=16).grid(
            row=hotkey_row, column=1, padx=6, pady=4
        )
        ttk.Label(container, text="e.g. <F8>, <ctrl>+<F8>", foreground="grey").grid(
            row=hotkey_row + 1, column=0, columnspan=3, padx=6, pady=(0, 4)
        )

        button_row = ttk.Frame(container)
        button_row.grid(row=hotkey_row + 2, column=0, columnspan=2, pady=(12, 0))

        ttk.Button(button_row, text="Save", command=self._on_save).grid(row=0, column=0, padx=6)
        ttk.Button(button_row, text="Cancel", command=self.destroy).grid(row=0, column=1, padx=6)

    def _on_save(self):
        new_price_map = {}
        for ducat_value, var in self.entries.items():
            text = var.get().strip()
            if not text.isdigit():
                messagebox.showerror(
                    "Invalid value",
                    f"Platinum value for {ducat_value} ducats must be a non-negative whole number.",
                    parent=self,
                )
                return
            new_price_map[ducat_value] = int(text)

        hotkey = self.hotkey_var.get().strip()
        if not hotkey:
            messagebox.showerror("Invalid value", "OCR Hotkey cannot be empty.", parent=self)
            return

        self.parent_app.price_map = new_price_map
        save_config(new_price_map)
        save_ocr_hotkey(hotkey)
        self.parent_app._setup_ocr_hotkey()
        self.parent_app.refresh_display()
        self.destroy()
