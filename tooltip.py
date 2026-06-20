"""A tiny dependency-free hover tooltip for Tkinter widgets.

Tkinter has no native tooltip, so `Tooltip(widget, text)` binds `<Enter>`/`<Leave>`
(and `<ButtonPress>`) to show/hide a small borderless `Toplevel` label near the
widget. Used for the `?` hints beside the OCR fuzziness fields in Settings.
"""

import tkinter as tk
from tkinter import ttk


class Tooltip:
    def __init__(self, widget, text, *, delay_ms=400, wraplength=260):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.wraplength = wraplength
        self._tip = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self):
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self):
        if self._tip is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(
            self._tip,
            text=self.text,
            justify="left",
            wraplength=self.wraplength,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            padding=(6, 4),
        )
        label.grid()

    def _hide(self, _event=None):
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None
