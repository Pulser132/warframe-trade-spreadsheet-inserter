"""Main window for the Warframe Ducat/Platinum Trade Calculator."""

import os
import tkinter as tk
from tkinter import messagebox, ttk

from config_manager import (
    DUCAT_VALUES,
    append_trade,
    clear_trades,
    load_api_config,
    load_config,
    load_debug_auto_capture,
    load_debug_hotkey,
    load_ocr_hotkey,
    load_show_thumbnails,
    load_trades,
    save_show_thumbnails,
    save_trades,
)
from history_window import HistoryWindow
from paths import resource_path
from settings_window import SettingsWindow

TRADE_ITEM_LIMIT = 6
THUMB_SIZE = 64

ASSETS_DIR = resource_path("assets")
ITEM_IMAGES_DIR = os.path.join(ASSETS_DIR, "item_images")


class DucatCalculatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Warframe Ducat/Platinum Trade Calculator")
        self.root.resizable(False, False)

        self.price_map = load_config()
        self.history = []
        self.trade_items = []
        self.ducat_icon = tk.PhotoImage(file=os.path.join(ASSETS_DIR, "ducat_icon.png"))
        self.placeholder_icon = tk.PhotoImage(file=os.path.join(ASSETS_DIR, "placeholder.png"))
        self._thumb_images = []  # holds PhotoImage refs so Tk doesn't garbage-collect them

        self._hotkey_listener = None
        self._debug_hotkey_listener = None
        self._status_after_id = None
        self._build_widgets()
        self.refresh_display()
        self.refresh_lifetime_totals()
        self._setup_hotkeys()
        self.root.bind("<Control-z>", lambda e: self.undo_item())
        self.root.bind("<Return>", lambda e: self.log_trade())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_hotkeys(self):
        """(Re)bind both the OCR scan hotkey and the debug-capture hotkey."""
        self._setup_ocr_hotkey()
        self._setup_debug_hotkey()

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
            self._hotkey_listener = keyboard.GlobalHotKeys({hotkey.lower(): _on_trigger})
            self._hotkey_listener.start()
        except Exception as e:
            self._hotkey_listener = None
            self._set_status(f"OCR hotkey error: {e}")

    def _setup_debug_hotkey(self):
        if self._debug_hotkey_listener is not None:
            self._debug_hotkey_listener.stop()
            self._debug_hotkey_listener = None

        hotkey = load_debug_hotkey()
        try:
            from pynput import keyboard
        except ImportError:
            return

        def _on_trigger():
            self.root.after(0, self.debug_capture_scan)

        try:
            self._debug_hotkey_listener = keyboard.GlobalHotKeys({hotkey.lower(): _on_trigger})
            self._debug_hotkey_listener.start()
        except Exception as e:
            self._debug_hotkey_listener = None
            self._set_status(f"Debug hotkey error: {e}")

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

        auto_capture = load_debug_auto_capture()
        try:
            import ocr_scanner
            if auto_capture:
                # Single scan: the debug path produces both the results and the
                # diagnostic payload, so auto-capture doesn't re-scan.
                results, skipped, unresolved, debug_payload = ocr_scanner.scan_debug()
            else:
                results, skipped, _, _ = ocr_scanner.scan()
                debug_payload = None
        except RuntimeError as e:
            self._set_status("")
            messagebox.showerror("OCR Scan Error", str(e))
            return

        if not results:
            msg = "OCR: no trade slots detected."
            if auto_capture and debug_payload is not None:
                folder, error = self._write_debug_capture(debug_payload)
                if error:
                    msg += f"  ·  debug write failed: {error}"
            self._set_status(msg)
            return

        msg = self._add_scan_results(results)
        if auto_capture and debug_payload is not None:
            folder, error = self._write_debug_capture(debug_payload)
            if folder:
                msg += f"  ·  debug saved: {folder}"
            elif error:
                msg += f"  ·  debug write failed: {error}"
        # Persistent: the summary stays until the trade is cleared (Reset/Log/Undo).
        self._set_status(msg, duration_ms=0)

    def _add_scan_results(self, results):
        """Add every detected slot to the trade (capped at TRADE_ITEM_LIMIT) and
        return the status-bar summary message. Shared by the normal and debug scans."""
        # Every detected slot is added, including 0-ducat placeholders for items
        # that couldn't be resolved (OCR garbage or non-ducat items like Arcanes).
        added_items = []
        for item in results:
            if len(self.history) >= TRADE_ITEM_LIMIT:
                break
            self.add_item(item["ducats"], item=item)
            added_items.append(item)

        names = ", ".join(
            f"{item['name'].title()} ({item['ducats']})" for item in added_items
        )
        notes = []
        new_count = sum(1 for item in added_items if item.get("source") == "fetched")
        if new_count:
            notes.append(f"{new_count} new from @wfcd/items")
        placeholder_count = sum(
            1 for item in added_items if item.get("source") == "unresolved"
        )
        if placeholder_count:
            plural = "s" if placeholder_count != 1 else ""
            notes.append(f"{placeholder_count} non-ducat placeholder{plural} @ 0")

        count = len(added_items)
        msg = f"OCR: added {count} item{'s' if count != 1 else ''} — {names}"
        if notes:
            msg += " (" + "; ".join(notes) + ")"
        return msg

    def _write_debug_capture(self, debug_payload):
        """Write a debug bundle; return (folder_path, error_message). Either may be None."""
        try:
            import debug_capture
            folder = debug_capture.write_capture(
                debug_payload, debug_payload["thresholds"]
            )
            return folder, None
        except RuntimeError as e:
            return None, str(e)

    def debug_capture_scan(self):
        """Debug-hotkey scan: resolve like a normal scan but also write a full
        diagnostic capture under debug/, reporting the saved folder."""
        self._set_status("Scanning (debug)…", duration_ms=0)
        self.root.update()  # force redraw before the blocking OCR call

        try:
            import ocr_scanner
            results, skipped, unresolved, debug_payload = ocr_scanner.scan_debug()
        except RuntimeError as e:
            self._set_status("")
            messagebox.showerror("OCR Scan Error", str(e))
            return

        msg = self._add_scan_results(results) if results else "OCR: no trade slots detected."

        folder, error = self._write_debug_capture(debug_payload)
        if folder:
            msg += f"  ·  debug saved: {folder}"
        elif error:
            # Read-only dir etc. — keep any added items, surface the error.
            msg += f"  ·  debug write failed: {error}"
        self._set_status(msg, duration_ms=0)

    def _on_close(self):
        if self._status_after_id:
            self.root.after_cancel(self._status_after_id)
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
        if self._debug_hotkey_listener is not None:
            self._debug_hotkey_listener.stop()
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

        thumb_frame = ttk.LabelFrame(container, text="Trade Items", padding=8)
        thumb_frame.grid(
            row=2, column=0, columnspan=len(DUCAT_VALUES), sticky="ew", pady=(0, 12)
        )
        self.thumb_frame = thumb_frame

        self.thumb_cells = []
        for col in range(TRADE_ITEM_LIMIT):
            cell = ttk.Frame(thumb_frame, padding=4)
            cell.grid(row=0, column=col, sticky="n")
            image_label = ttk.Label(cell, image=self.placeholder_icon)
            image_label.grid(row=0, column=0, columnspan=2)
            name_label = ttk.Label(
                cell, text="", font=("Segoe UI", 8), anchor="center",
                justify="center", wraplength=80,
            )
            name_label.grid(row=1, column=0, columnspan=2, pady=(2, 0))

            ttk.Label(cell, text="Ducats:", font=("Segoe UI", 7)).grid(row=2, column=0, sticky="e")
            ducats_var = tk.StringVar()
            ducats_entry = ttk.Entry(
                cell, textvariable=ducats_var, width=5, justify="right", font=("Segoe UI", 8),
            )
            ducats_entry.grid(row=2, column=1, sticky="w", padx=(2, 0))
            ducats_entry.bind("<Return>", lambda e, i=col: self._commit_ducats_edit(i))
            ducats_entry.bind("<FocusOut>", lambda e, i=col: self._commit_ducats_edit(i))

            ttk.Label(cell, text="Plat:", font=("Segoe UI", 7)).grid(row=3, column=0, sticky="e")
            platinum_var = tk.StringVar()
            platinum_entry = ttk.Entry(
                cell, textvariable=platinum_var, width=5, justify="right", font=("Segoe UI", 8),
            )
            platinum_entry.grid(row=3, column=1, sticky="w", padx=(2, 0))
            platinum_entry.bind("<Return>", lambda e, i=col: self._commit_platinum_edit(i))
            platinum_entry.bind("<FocusOut>", lambda e, i=col: self._commit_platinum_edit(i))

            self.thumb_cells.append({
                "image": image_label,
                "name": name_label,
                "ducats_var": ducats_var,
                "ducats_entry": ducats_entry,
                "platinum_var": platinum_var,
                "platinum_entry": platinum_entry,
            })

        self.show_thumbnails_var = tk.BooleanVar(value=load_show_thumbnails())
        if not self.show_thumbnails_var.get():
            thumb_frame.grid_remove()

        controls_frame = ttk.Frame(container)
        controls_frame.grid(row=3, column=0, columnspan=len(DUCAT_VALUES))

        ttk.Button(controls_frame, text="Undo", command=self.undo_item).grid(row=0, column=0, padx=4)
        ttk.Button(controls_frame, text="Reset", command=self.reset_trade).grid(row=0, column=1, padx=4)
        ttk.Button(controls_frame, text="Log Trade", style="LogTrade.TButton", command=self.log_trade).grid(row=0, column=2, padx=4)
        ttk.Button(controls_frame, text="Settings", command=self.open_settings).grid(row=0, column=3, padx=4)
        ttk.Button(controls_frame, text="History", command=self.open_history).grid(row=0, column=4, padx=4)
        ttk.Button(controls_frame, text="Copy WTB Message", command=self.copy_wtb_message).grid(row=0, column=5, padx=4)
        ttk.Button(controls_frame, text="Reset Trade Total", command=self.reset_trade_total).grid(row=0, column=6, padx=4)
        self.export_button = ttk.Button(controls_frame, text="Export to Spreadsheet", command=self.export_to_spreadsheet)
        self.export_button.grid(row=0, column=7, padx=4)
        ttk.Checkbutton(
            controls_frame,
            text="Show item thumbnails",
            variable=self.show_thumbnails_var,
            command=self._toggle_thumbnails,
        ).grid(row=0, column=8, padx=4)

        self._status_label = ttk.Label(
            container, text="", anchor="w", font=("Segoe UI", 9), foreground="grey"
        )
        self._status_label.grid(
            row=4, column=0, columnspan=len(DUCAT_VALUES), sticky="ew", pady=(8, 0)
        )

    def add_item(self, ducat_value, item=None):
        if len(self.history) >= TRADE_ITEM_LIMIT:
            return
        self.history.append(ducat_value)
        if item is not None:
            self.trade_items.append({
                "name": item.get("name"),
                "ducats": ducat_value,
                "image": item.get("image"),
                "source": item.get("source"),
                "platinum_override": None,
            })
        else:
            self.trade_items.append({
                "name": None, "ducats": ducat_value, "image": None, "source": "manual",
                "platinum_override": None,
            })
        self.refresh_display()

    def _item_platinum(self, entry):
        override = entry.get("platinum_override")
        if override is not None:
            return override
        return self.price_map.get(entry["ducats"], 0)

    def _commit_ducats_edit(self, index):
        if index >= len(self.trade_items):
            return
        cell = self.thumb_cells[index]
        entry = self.trade_items[index]
        text = cell["ducats_var"].get().strip()
        if not text.isdigit():
            messagebox.showerror(
                "Invalid value", "Ducat value must be a non-negative whole number."
            )
            cell["ducats_var"].set(str(entry["ducats"]))
            return
        new_value = int(text)
        if new_value == entry["ducats"]:
            return
        entry["ducats"] = new_value
        self.history[index] = new_value
        self.refresh_display()

    def _commit_platinum_edit(self, index):
        if index >= len(self.trade_items):
            return
        cell = self.thumb_cells[index]
        entry = self.trade_items[index]
        text = cell["platinum_var"].get().strip()
        if not text.isdigit():
            messagebox.showerror(
                "Invalid value", "Platinum value must be a non-negative whole number."
            )
            cell["platinum_var"].set(str(self._item_platinum(entry)))
            return
        new_value = int(text)
        if new_value == self._item_platinum(entry):
            return
        entry["platinum_override"] = new_value
        self.refresh_display()

    def undo_item(self):
        if self.history:
            self.history.pop()
            self.trade_items.pop()
            self.refresh_display()
            if not self.history:
                self._set_status("")  # trade emptied — drop the OCR summary

    def reset_trade(self):
        self.history.clear()
        self.trade_items.clear()
        self.refresh_display()
        self._set_status("")  # clear any persistent OCR summary

    def log_trade(self):
        if not self.history:
            return
        total_ducats = sum(self.history)
        total_platinum = sum(self._item_platinum(e) for e in self.trade_items)
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
        self._update_export_button()

    def _update_export_button(self):
        pending_count = sum(1 for t in load_trades() if not t.get("exported", False))
        text = "Export to Spreadsheet"
        if pending_count:
            text += f" ({pending_count})"
        self.export_button.config(text=text)

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
        self._update_export_button()

        messagebox.showinfo(
            "Export to Spreadsheet",
            f"Successfully exported {len(updated)} trade(s) to Google Sheets.",
        )

    def open_settings(self):
        SettingsWindow(self)

    def open_history(self):
        HistoryWindow(self)

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
        total_platinum = sum(self._item_platinum(e) for e in self.trade_items)

        self.items_label.config(text=f"Items: {item_count} / {TRADE_ITEM_LIMIT}")
        self.ducats_label.config(text=f"Total Ducats: {total_ducats}")
        self.platinum_label.config(text=f"Total Platinum: {total_platinum}")

        is_full = item_count >= TRADE_ITEM_LIMIT
        color = "#1a7f1a" if is_full else ""
        for label in (self.items_label, self.ducats_label, self.platinum_label):
            label.config(foreground=color)

        for button in self.ducat_buttons:
            button.state(["disabled" if is_full else "!disabled"])

        self.refresh_thumbnails()

    def _toggle_thumbnails(self):
        show = self.show_thumbnails_var.get()
        if show:
            self.thumb_frame.grid()
        else:
            self.thumb_frame.grid_remove()
        save_show_thumbnails(show)

    def refresh_thumbnails(self):
        self._thumb_images.clear()
        try:
            from PIL import Image, ImageTk
        except ImportError:
            Image = ImageTk = None

        for i, cell in enumerate(self.thumb_cells):
            if i >= len(self.trade_items):
                cell["image"].config(image=self.placeholder_icon)
                cell["name"].config(text="")
                cell["ducats_var"].set("")
                cell["platinum_var"].set("")
                cell["ducats_entry"].state(["disabled"])
                cell["platinum_entry"].state(["disabled"])
                continue

            entry = self.trade_items[i]
            photo = None
            if entry.get("image") and Image is not None:
                image_path = os.path.join(ITEM_IMAGES_DIR, entry["image"])
                try:
                    pil_image = Image.open(image_path).convert("RGBA")
                    pil_image = pil_image.resize((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(pil_image)
                except Exception:
                    photo = None

            if photo is not None:
                self._thumb_images.append(photo)
                cell["image"].config(image=photo)
            else:
                cell["image"].config(image=self.placeholder_icon)

            source = entry.get("source")
            if source == "manual":
                cell["name"].config(text="(manual)")
            elif source == "unresolved":
                cell["name"].config(text="(unresolved)")
            else:
                cell["name"].config(text=(entry.get("name") or "").title())
            cell["ducats_entry"].state(["!disabled"])
            cell["platinum_entry"].state(["!disabled"])
            cell["ducats_var"].set(str(entry.get("ducats", 0)))
            cell["platinum_var"].set(str(self._item_platinum(entry)))
