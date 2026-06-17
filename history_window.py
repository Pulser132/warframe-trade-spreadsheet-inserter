"""Trade History dialog listing the 10 most recent logged trades."""

import tkinter as tk
from tkinter import messagebox, ttk

from config_manager import delete_trade, load_trades

MAX_VISIBLE = 10


class HistoryWindow(tk.Toplevel):
    def __init__(self, parent_app):
        super().__init__(parent_app.root)
        self.parent_app = parent_app

        self.title("Trade History")
        self.resizable(False, False)
        self.transient(parent_app.root)
        self.grab_set()

        container = ttk.Frame(self, padding=12)
        container.grid(row=0, column=0)

        self.tree = ttk.Treeview(
            container,
            columns=("timestamp", "ducats", "platinum", "exported"),
            show="headings",
            height=MAX_VISIBLE,
        )
        self.tree.heading("timestamp", text="Timestamp")
        self.tree.heading("ducats", text="Ducats")
        self.tree.heading("platinum", text="Platinum")
        self.tree.heading("exported", text="Exported")
        self.tree.column("timestamp", width=150, anchor="w")
        self.tree.column("ducats", width=70, anchor="e")
        self.tree.column("platinum", width=70, anchor="e")
        self.tree.column("exported", width=70, anchor="center")
        self.tree.grid(row=0, column=0, columnspan=2, pady=(0, 8))

        self._status_label = ttk.Label(container, text="", foreground="grey")
        self._status_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.delete_button = ttk.Button(
            container, text="Delete Selected", command=self._on_delete
        )
        self.delete_button.grid(row=2, column=0, padx=4, sticky="e")
        ttk.Button(container, text="Close", command=self.destroy).grid(
            row=2, column=1, padx=4, sticky="w"
        )

        self._populate()

    def _populate(self):
        self.tree.delete(*self.tree.get_children())
        self._status_label.config(text="")

        trades = load_trades()
        if not trades:
            self._status_label.config(text="No trades logged yet.")
            self.delete_button.state(["disabled"])
            return

        self.delete_button.state(["!disabled"])
        start = max(0, len(trades) - MAX_VISIBLE)
        for orig_index in range(len(trades) - 1, start - 1, -1):
            t = trades[orig_index]
            self.tree.insert(
                "",
                "end",
                iid=str(orig_index),
                values=(
                    t.get("timestamp", ""),
                    t.get("total_ducats", 0),
                    t.get("total_platinum", 0),
                    "✓" if t.get("exported", False) else "✗",
                ),
            )

    def _on_delete(self):
        sel = self.tree.selection()
        if not sel:
            self._status_label.config(text="Select a trade to delete.")
            return

        orig_index = int(sel[0])
        trades = load_trades()
        if not (0 <= orig_index < len(trades)):
            self._populate()
            return

        record = trades[orig_index]
        message = (
            f"Delete this trade?\n\n"
            f"Timestamp: {record.get('timestamp', '')}\n"
            f"Ducats: {record.get('total_ducats', 0)}\n"
            f"Platinum: {record.get('total_platinum', 0)}"
        )
        if record.get("exported", False):
            message += (
                "\n\nThis trade was already exported; its row in the Google Sheet "
                "will not be removed automatically."
            )

        if messagebox.askyesno(
            "Delete trade?", message, icon=messagebox.WARNING, parent=self
        ):
            delete_trade(orig_index)
            self.parent_app.refresh_lifetime_totals()
            self._populate()
