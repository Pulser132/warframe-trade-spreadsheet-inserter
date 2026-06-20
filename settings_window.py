"""Settings dialog for configuring platinum values per ducat tier."""

import tkinter as tk
from tkinter import messagebox, ttk

from config_manager import (
    DEFAULT_OCR_THRESHOLDS,
    DUCAT_VALUES,
    load_debug_auto_capture,
    load_debug_hotkey,
    load_ocr_hotkey,
    load_ocr_thresholds,
    save_config,
    save_debug_auto_capture,
    save_debug_hotkey,
    save_ocr_hotkey,
    save_ocr_thresholds,
)
from tooltip import Tooltip

# (config key, label, tooltip) for each tunable fuzziness threshold, in display order.
_THRESHOLD_FIELDS = [
    (
        "pass1_cutoff",
        "Pass 1 fuzzy cutoff",
        "Minimum similarity (0–1) for Pass 1's local-cache fuzzy match. Lower = "
        "looser (more matches but more false positives); raise to be stricter. "
        "Default 0.75.",
    ),
    (
        "pass1_anchor",
        "Pass 1 token anchor",
        "Minimum similarity of the leading name token before Pass 1 accepts a fuzzy "
        "match. Guards against items that share the '<prime> <component>' suffix. "
        "Default 0.70.",
    ),
    (
        "pass2_whole",
        "Pass 2 whole-string",
        "Minimum whole-string similarity for Pass 2's robust matcher (also used as "
        "its leading-token anchor). Lower it to resolve more typo'd reads. "
        "Default 0.85.",
    ),
    (
        "pass2_token",
        "Pass 2 token-overlap",
        "Minimum token-overlap score for Pass 2's fallback that recovers mid-word "
        "misreads. Default 0.80.",
    ),
]


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

        row = len(DUCAT_VALUES) + 1
        ttk.Separator(container, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=8
        )

        row += 1
        ttk.Label(container, text="OCR Hotkey").grid(row=row, column=0, padx=6, pady=4, sticky="w")
        self.hotkey_var = tk.StringVar(value=load_ocr_hotkey())
        ttk.Entry(container, textvariable=self.hotkey_var, width=16).grid(
            row=row, column=1, padx=6, pady=4
        )

        row += 1
        ttk.Label(container, text="e.g. <F8>, <ctrl>+<F8>", foreground="grey").grid(
            row=row, column=0, columnspan=3, padx=6, pady=(0, 4), sticky="w"
        )

        # --- OCR Fuzziness & Debug section ---
        row += 1
        ttk.Separator(container, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=8
        )

        row += 1
        ttk.Label(
            container, text="OCR Fuzziness & Debug", font=("Segoe UI", 10, "bold")
        ).grid(row=row, column=0, columnspan=3, padx=6, pady=(0, 6), sticky="w")

        thresholds = load_ocr_thresholds()
        self.threshold_vars = {}
        for key, label, tip in _THRESHOLD_FIELDS:
            row += 1
            ttk.Label(container, text=label).grid(row=row, column=0, padx=6, pady=4, sticky="w")
            var = tk.StringVar(value=str(thresholds.get(key, DEFAULT_OCR_THRESHOLDS[key])))
            ttk.Entry(container, textvariable=var, width=10, justify="right").grid(
                row=row, column=1, padx=6, pady=4
            )
            help_label = ttk.Label(container, text="?", foreground="blue", cursor="question_arrow")
            help_label.grid(row=row, column=2, padx=(0, 6), sticky="w")
            Tooltip(help_label, tip)
            self.threshold_vars[key] = var

        row += 1
        ttk.Label(container, text="Debug Hotkey").grid(row=row, column=0, padx=6, pady=4, sticky="w")
        self.debug_hotkey_var = tk.StringVar(value=load_debug_hotkey())
        ttk.Entry(container, textvariable=self.debug_hotkey_var, width=16).grid(
            row=row, column=1, padx=6, pady=4
        )
        debug_help = ttk.Label(container, text="?", foreground="blue", cursor="question_arrow")
        debug_help.grid(row=row, column=2, padx=(0, 6), sticky="w")
        Tooltip(
            debug_help,
            "Hotkey that writes a full OCR debug capture (screenshot, per-slot crops, "
            "scores) under debug/. Default <F9>.",
        )

        row += 1
        self.auto_capture_var = tk.BooleanVar(value=load_debug_auto_capture())
        ttk.Checkbutton(
            container,
            text="Auto-capture debug after each scan",
            variable=self.auto_capture_var,
        ).grid(row=row, column=0, columnspan=3, padx=6, pady=4, sticky="w")

        row += 1
        button_row = ttk.Frame(container)
        button_row.grid(row=row, column=0, columnspan=3, pady=(12, 0))

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

        new_thresholds = {}
        for key, label, _tip in _THRESHOLD_FIELDS:
            text = self.threshold_vars[key].get().strip()
            try:
                value = float(text)
            except ValueError:
                messagebox.showerror(
                    "Invalid value",
                    f"{label} must be a number between 0.0 and 1.0.",
                    parent=self,
                )
                return
            if not 0.0 <= value <= 1.0:
                messagebox.showerror(
                    "Invalid value",
                    f"{label} must be between 0.0 and 1.0.",
                    parent=self,
                )
                return
            new_thresholds[key] = value

        debug_hotkey = self.debug_hotkey_var.get().strip()
        if not debug_hotkey:
            messagebox.showerror("Invalid value", "Debug Hotkey cannot be empty.", parent=self)
            return

        self.parent_app.price_map = new_price_map
        save_config(new_price_map)
        save_ocr_hotkey(hotkey)
        save_ocr_thresholds(new_thresholds)
        save_debug_hotkey(debug_hotkey)
        save_debug_auto_capture(self.auto_capture_var.get())
        self.parent_app._setup_hotkeys()
        self.parent_app.refresh_display()
        self.destroy()
