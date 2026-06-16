"""Main window for the Warframe Ducat/Platinum Trade Calculator."""

import os
import tkinter as tk
from tkinter import messagebox, ttk

from config_manager import DUCAT_VALUES, append_trade, clear_trades, load_api_config, load_config, load_ocr_hotkey, load_trades, save_trades
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

        self._hotkey_listener = None
        self._status_after_id = None
        self._build_widgets()
        self.refresh_display()
        self.refresh_lifetime_totals()
        self._setup_ocr_hotkey()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_ocr_hotkey(self):
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

        hotkey = load_ocr_hotkey()
        try:
            from pynput import keyboard
        except ImportError:
            return

        def _on_trigger():
            self.root.after(0, self.scan_trade_window)

        try:
            self._hotkey_listener = keyboard.GlobalHotKeys({hotkey: _on_trigger})
            self._hotkey_listener.start()
        except Exception:
            self._hotkey_listener = None

    def _set_status(self, msg, duration_ms=4000):
        """Show a transient message in the status bar, auto-clearing after duration_ms."""
        if self._status_after_id:
            self.root.after_cancel(self._status_after_id)
            self._status_after_id = None
        self._status_label.config(text=msg)
        if msg and duration_ms > 0:
            self._status_after_id = self.root.after(
                duration_ms, lambda: self._status_label.config(text="")
            )

    def scan_trade_window(self):
        self._set_status("Scanning…", duration_ms=0)
        self.root.update()  # force redraw before the blocking OCR call

        try:
            import ocr_scanner
            results, skipped, resolver_unavailable, _ = ocr_scanner.scan()
        except RuntimeError as e:
            self._set_status("")
            messagebox.showerror("OCR Scan Error", str(e))
            return

        if not results and skipped == 0:
            self._set_status("OCR: no trade slots detected.")
            return

        added_items = []
        for item in results:
            v = item["ducats"]
            if v in self.price_map and len(self.history) < TRADE_ITEM_LIMIT:
                self.add_item(v)
                added_items.append(item)

        if skipped and resolver_unavailable:
            unresolved_note = f"{skipped} unresolved — run: npm install in scripts/"
        elif skipped:
            unresolved_note = f"{skipped} unresolved"
        else:
            unresolved_note = ""

        if added_items:
            names = ", ".join(
                f"{item['name'].title()} ({item['ducats']})" for item in added_items
            )
            new_count = sum(1 for item in added_items if item.get("source") == "fetched")
            notes = []
            if new_count:
                notes.append(f"{new_count} new from @wfcd/items")
            if unresolved_note:
                notes.append(unresolved_note)
            count = len(added_items)
            msg = f"OCR: added {count} item{'s' if count != 1 else ''} — {names}"
            if notes:
                msg += " (" + "; ".join(notes) + ")"
            self._set_status(msg, duration_ms=6000)
        elif not results:
            msg = f"OCR: {skipped} slot{'s' if skipped != 1 else ''} detected but no items could be resolved."
            if resolver_unavailable:
                msg += " — run: npm install in scripts/"
            self._set_status(msg)
        else:
            self._set_status("OCR: no recognizable prime items detected.")

    def _on_close(self):
        if self._status_after_id:
            self.root.after_cancel(self._status_after_id)
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
        self.root.destroy()

    def _build_widgets(self):
        style = ttk.Style()
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("LogTrade.TButton", font=("Segoe UI", 11, "bold"))

        container = ttk.Frame(self.root, padding=12)
        container.grid(row=0, column=0)

        ducat_frame = ttk.LabelFrame(container, text="Add Item by Ducat Value", padding=8)
        ducat_frame.grid(row=0, column=0, columnspan=len(DUCAT_VALUES), pady=(0, 12))

        self.ducat_buttons = []
        for col, ducat_value in enumerate(DUCAT_VALUES):
            button = ttk.Button(
                ducat_frame,
                text=f"{ducat_value} ",
                image=self.ducat_icon,
                compound="right",
                command=lambda v=ducat_value: self.add_item(v),
            )
            button.grid(row=0, column=col, padx=4, pady=4)
            self.ducat_buttons.append(button)

        middle_frame = ttk.Frame(container)
        middle_frame.grid(row=1, column=0, columnspan=len(DUCAT_VALUES), sticky="ew", pady=(0, 12))
        middle_frame.columnconfigure(0, weight=1)
        middle_frame.columnconfigure(1, weight=1)

        totals_frame = ttk.LabelFrame(middle_frame, text="Current Trade", padding=8)
        totals_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.items_label = ttk.Label(totals_frame, font=("Segoe UI", 11))
        self.items_label.grid(row=0, column=0, sticky="w", pady=2)

        self.ducats_label = ttk.Label(totals_frame, font=("Segoe UI", 11))
        self.ducats_label.grid(row=1, column=0, sticky="w", pady=2)

        self.platinum_label = ttk.Label(totals_frame, font=("Segoe UI", 11))
        self.platinum_label.grid(row=2, column=0, sticky="w", pady=2)

        lifetime_frame = ttk.LabelFrame(middle_frame, text="Lifetime Totals", padding=8)
        lifetime_frame.grid(row=0, column=1, sticky="nsew")

        self.lifetime_ducats_label = ttk.Label(lifetime_frame, font=("Segoe UI", 11))
        self.lifetime_ducats_label.grid(row=0, column=0, sticky="w", pady=2)

        self.lifetime_platinum_label = ttk.Label(lifetime_frame, font=("Segoe UI", 11))
        self.lifetime_platinum_label.grid(row=1, column=0, sticky="w", pady=2)

        self.lifetime_avg_label = ttk.Label(lifetime_frame, font=("Segoe UI", 11))
        self.lifetime_avg_label.grid(row=2, column=0, sticky="w", pady=2)

        controls_frame = ttk.Frame(container)
        controls_frame.grid(row=2, column=0, columnspan=len(DUCAT_VALUES))

        ttk.Button(controls_frame, text="Undo", command=self.undo_item).grid(row=0, column=0, padx=4)
        ttk.Button(controls_frame, text="Reset", command=self.reset_trade).grid(row=0, column=1, padx=4)
        ttk.Button(controls_frame, text="Log Trade", style="LogTrade.TButton", command=self.log_trade).grid(row=0, column=2, padx=4)
        ttk.Button(controls_frame, text="Settings", command=self.open_settings).grid(row=0, column=3, padx=4)
        ttk.Button(controls_frame, text="Copy WTB Message", command=self.copy_wtb_message).grid(row=0, column=4, padx=4)
        ttk.Button(controls_frame, text="Reset Trade Total", command=self.reset_trade_total).grid(row=0, column=5, padx=4)
        ttk.Button(controls_frame, text="Export to Spreadsheet", command=self.export_to_spreadsheet).grid(row=0, column=6, padx=4)

        self._status_label = ttk.Label(
            container, text="", anchor="w", font=("Segoe UI", 9), foreground="grey"
        )
        self._status_label.grid(
            row=3, column=0, columnspan=len(DUCAT_VALUES), sticky="ew", pady=(8, 0)
        )

    def add_item(self, ducat_value):
        if len(self.history) >= TRADE_ITEM_LIMIT:
            return
        self.history.append(ducat_value)
        self.refresh_display()

    def undo_item(self):
        if self.history:
            self.history.pop()
            self.refresh_display()

    def reset_trade(self):
        self.history.clear()
        self.refresh_display()

    def log_trade(self):
        if not self.history:
            return
        total_ducats = sum(self.history)
        total_platinum = sum(self.price_map[d] for d in self.history)
        append_trade(total_ducats, total_platinum)
        self.reset_trade()
        self.refresh_lifetime_totals()
        self._set_status("Trade logged.")

    def refresh_lifetime_totals(self):
        trades = load_trades()
        total_ducats = sum(t.get("total_ducats", 0) for t in trades)
        total_platinum = sum(t.get("total_platinum", 0) for t in trades)
        avg = round(total_ducats / total_platinum, 1) if total_platinum else "—"

        self.lifetime_ducats_label.config(text=f"Total Ducats: {total_ducats}")
        self.lifetime_platinum_label.config(text=f"Total Platinum: {total_platinum}")
        self.lifetime_avg_label.config(text=f"Avg Ducats / Plat: {avg}")

    def reset_trade_total(self):
        confirmed = messagebox.askyesno(
            title="Reset all trade history?",
            message="This will permanently delete all records in trades.json. This cannot be undone.",
            icon=messagebox.WARNING,
        )
        if confirmed:
            clear_trades()
            self.refresh_lifetime_totals()

    def export_to_spreadsheet(self):
        try:
            api_config = load_api_config()
        except RuntimeError as e:
            messagebox.showerror("Export Error", str(e))
            return

        trades = load_trades()
        pending = [t for t in trades if not t.get("exported", False)]

        if not pending:
            messagebox.showinfo("Export to Spreadsheet", "No new trades to export.")
            return

        try:
            import sheets_exporter
            updated = sheets_exporter.export_trades(pending, api_config)
        except RuntimeError as e:
            messagebox.showerror("Export Error", str(e))
            return

        exported_timestamps = {t["timestamp"] for t in updated}
        for t in trades:
            if t["timestamp"] in exported_timestamps:
                t["exported"] = True
        save_trades(trades)

        messagebox.showinfo(
            "Export to Spreadsheet",
            f"Successfully exported {len(updated)} trade(s) to Google Sheets.",
        )

    def open_settings(self):
        SettingsWindow(self)

    def copy_wtb_message(self):
        ducat_values = "/".join(str(v) for v in DUCAT_VALUES)
        platinum_values = "/".join(str(self.price_map[v]) for v in DUCAT_VALUES)
        message = (
            f"WTB Prime Junk :ducats: {ducat_values} :ducats: "
            f"= :platinum: {platinum_values} :platinum: Full trades only."
        )
        self.root.clipboard_clear()
        self.root.clipboard_append(message)
        self.root.update()
        self._set_status("WTB message copied to clipboard.")

    def refresh_display(self):
        item_count = len(self.history)
        total_ducats = sum(self.history)
        total_platinum = sum(self.price_map[d] for d in self.history)

        self.items_label.config(text=f"Items: {item_count} / {TRADE_ITEM_LIMIT}")
        self.ducats_label.config(text=f"Total Ducats: {total_ducats}")
        self.platinum_label.config(text=f"Total Platinum: {total_platinum}")

        is_full = item_count >= TRADE_ITEM_LIMIT
        color = "#1a7f1a" if is_full else ""
        for label in (self.items_label, self.ducats_label, self.platinum_label):
            label.config(foreground=color)

        for button in self.ducat_buttons:
            button.state(["disabled" if is_full else "!disabled"])
