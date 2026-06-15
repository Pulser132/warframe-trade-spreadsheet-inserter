"""Main window for the Warframe Ducat/Platinum Trade Calculator."""

import os
import tkinter as tk
from tkinter import ttk

from config_manager import DUCAT_VALUES, load_config
from settings_window import SettingsWindow

TRADE_ITEM_LIMIT = 6

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


class DucatCalculatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Warframe Ducat/Platinum Trade Calculator")
        self.root.resizable(False, False)

        self.price_map = load_config()
        self.history = []
        self.ducat_icon = tk.PhotoImage(file=os.path.join(ASSETS_DIR, "ducat_icon.png"))

        self._build_widgets()
        self.refresh_display()

    def _build_widgets(self):
        container = ttk.Frame(self.root, padding=12)
        container.grid(row=0, column=0)

        ducat_frame = ttk.LabelFrame(container, text="Add Item by Ducat Value", padding=8)
        ducat_frame.grid(row=0, column=0, columnspan=len(DUCAT_VALUES), pady=(0, 12))

        for col, ducat_value in enumerate(DUCAT_VALUES):
            button = ttk.Button(
                ducat_frame,
                text=f"{ducat_value} ",
                image=self.ducat_icon,
                compound="right",
                command=lambda v=ducat_value: self.add_item(v),
            )
            button.grid(row=0, column=col, padx=4, pady=4)

        totals_frame = ttk.LabelFrame(container, text="Current Trade", padding=8)
        totals_frame.grid(row=1, column=0, columnspan=len(DUCAT_VALUES), sticky="ew", pady=(0, 12))

        self.items_label = ttk.Label(totals_frame, font=("Segoe UI", 11))
        self.items_label.grid(row=0, column=0, sticky="w", pady=2)

        self.ducats_label = ttk.Label(totals_frame, font=("Segoe UI", 11))
        self.ducats_label.grid(row=1, column=0, sticky="w", pady=2)

        self.platinum_label = ttk.Label(totals_frame, font=("Segoe UI", 11))
        self.platinum_label.grid(row=2, column=0, sticky="w", pady=2)

        controls_frame = ttk.Frame(container)
        controls_frame.grid(row=2, column=0, columnspan=len(DUCAT_VALUES))

        ttk.Button(controls_frame, text="Undo", command=self.undo_item).grid(row=0, column=0, padx=4)
        ttk.Button(controls_frame, text="Reset", command=self.reset_trade).grid(row=0, column=1, padx=4)
        ttk.Button(controls_frame, text="Settings", command=self.open_settings).grid(row=0, column=2, padx=4)

    def add_item(self, ducat_value):
        self.history.append(ducat_value)
        self.refresh_display()

    def undo_item(self):
        if self.history:
            self.history.pop()
            self.refresh_display()

    def reset_trade(self):
        self.history.clear()
        self.refresh_display()

    def open_settings(self):
        SettingsWindow(self)

    def refresh_display(self):
        item_count = len(self.history)
        total_ducats = sum(self.history)
        total_platinum = sum(self.price_map[d] for d in self.history)

        self.items_label.config(text=f"Items: {item_count} / {TRADE_ITEM_LIMIT}")
        self.ducats_label.config(text=f"Total Ducats: {total_ducats}")
        self.platinum_label.config(text=f"Total Platinum: {total_platinum}")

        if item_count == TRADE_ITEM_LIMIT:
            color = "#1a7f1a"
        elif item_count > TRADE_ITEM_LIMIT:
            color = "#b22222"
        else:
            color = ""

        for label in (self.items_label, self.ducats_label, self.platinum_label):
            label.config(foreground=color)
