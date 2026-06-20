"""Loading and saving the ducat-to-platinum price configuration and trade log."""

import json
import os
from datetime import datetime

from paths import user_data_path

API_CONFIG_PATH = user_data_path("configs", "api_config.json")

CONFIGS_DIR = user_data_path("configs")
CONFIG_PATH = os.path.join(CONFIGS_DIR, "config.json")

DATA_DIR = user_data_path("data")
TRADES_PATH = os.path.join(DATA_DIR, "trades.json")

DUCAT_VALUES = [15, 25, 45, 65, 100]

DEFAULT_PRICE_MAP = {15: 0, 25: 0, 45: 0, 65: 0, 100: 0}

# The four live-tunable OCR fuzziness thresholds (see resolver.py / ocr_scanner.py).
# pass1_cutoff/pass1_anchor gate Pass 1 (`ocr_scanner._resolve`); pass2_whole/pass2_token
# gate Pass 2 (`resolver.resolve_one`). Defaults equal the historically hardcoded values.
DEFAULT_OCR_THRESHOLDS = {
    "pass1_cutoff": 0.75,
    "pass1_anchor": 0.70,
    "pass2_whole": 0.85,
    "pass2_token": 0.80,
}


def load_config():
    """Return the ducat -> platinum price map, creating a default file if needed."""
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_PRICE_MAP)
        return dict(DEFAULT_PRICE_MAP)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        price_key_strs = {str(v) for v in DUCAT_VALUES}
        price_map = {int(k): int(v) for k, v in raw.items() if k in price_key_strs}
        for ducat_value in DUCAT_VALUES:
            price_map.setdefault(ducat_value, DEFAULT_PRICE_MAP[ducat_value])
        return price_map
    except (ValueError, OSError, json.JSONDecodeError):
        save_config(DEFAULT_PRICE_MAP)
        return dict(DEFAULT_PRICE_MAP)


def save_config(price_map):
    """Persist the ducat -> platinum price map, preserving other keys (e.g. ocr_hotkey)."""
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
    except Exception:
        existing = {}
    price_key_strs = {str(v) for v in DUCAT_VALUES}
    config = {k: v for k, v in existing.items() if k not in price_key_strs}
    config.update({str(k): v for k, v in price_map.items()})
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_ocr_hotkey():
    """Return the configured OCR hotkey string, defaulting to '<F8>' if unset."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("ocr_hotkey", "<F8>")
    except Exception:
        return "<F8>"


def save_ocr_hotkey(hotkey):
    """Write the OCR hotkey string to config.json, preserving all other keys."""
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}
    config["ocr_hotkey"] = hotkey
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def _clamp_unit(value):
    """Coerce to float and clamp into the inclusive 0.0–1.0 range."""
    return max(0.0, min(1.0, float(value)))


def load_ocr_thresholds():
    """Return the four OCR fuzziness thresholds, merging defaults for missing keys.

    Each value is coerced to float and clamped to 0.0–1.0. Any read/parse error
    (or a missing file) yields a fresh copy of DEFAULT_OCR_THRESHOLDS.
    """
    thresholds = dict(DEFAULT_OCR_THRESHOLDS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            stored = json.load(f).get("ocr_thresholds", {})
        if isinstance(stored, dict):
            for key in DEFAULT_OCR_THRESHOLDS:
                if key in stored:
                    thresholds[key] = _clamp_unit(stored[key])
    except Exception:
        return dict(DEFAULT_OCR_THRESHOLDS)
    return thresholds


def save_ocr_thresholds(thresholds):
    """Write the four OCR thresholds (clamped floats) to config.json, preserving other keys."""
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}
    config["ocr_thresholds"] = {
        key: _clamp_unit(thresholds.get(key, DEFAULT_OCR_THRESHOLDS[key]))
        for key in DEFAULT_OCR_THRESHOLDS
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_debug_hotkey():
    """Return the configured debug-capture hotkey string, defaulting to '<F9>' if unset."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("debug_hotkey", "<F9>")
    except Exception:
        return "<F9>"


def save_debug_hotkey(hotkey):
    """Write the debug hotkey string to config.json, preserving all other keys."""
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}
    config["debug_hotkey"] = hotkey
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_debug_auto_capture():
    """Return whether a debug bundle is written after every normal scan, default False."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("debug_auto_capture", False))
    except Exception:
        return False


def save_debug_auto_capture(value):
    """Write the debug_auto_capture flag to config.json, preserving all other keys."""
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}
    config["debug_auto_capture"] = bool(value)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_show_thumbnails():
    """Return whether the thumbnail row should be shown, defaulting to True if unset."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("show_thumbnails", True))
    except Exception:
        return True


def save_show_thumbnails(value):
    """Write the show_thumbnails flag to config.json, preserving all other keys."""
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}
    config["show_thumbnails"] = bool(value)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_trades():
    """Return the list of trade records, creating an empty trades.json if absent."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(TRADES_PATH):
        with open(TRADES_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
        return []
    try:
        with open(TRADES_PATH, "r", encoding="utf-8") as f:
            trades = json.load(f)
        return trades if isinstance(trades, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def clear_trades():
    """Overwrite trades.json with an empty array."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRADES_PATH, "w", encoding="utf-8") as f:
        json.dump([], f)


def append_trade(total_ducats, total_platinum):
    """Append a trade record to data/trades.json, creating the file if needed."""
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(TRADES_PATH):
        try:
            with open(TRADES_PATH, "r", encoding="utf-8") as f:
                trades = json.load(f)
            if not isinstance(trades, list):
                trades = []
        except (OSError, json.JSONDecodeError):
            trades = []
    else:
        trades = []

    trades.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_ducats": total_ducats,
        "total_platinum": total_platinum,
        "exported": False,
    })

    with open(TRADES_PATH, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2)


def save_trades(trades):
    """Write the full trades list back to disk (used to persist exported flags)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRADES_PATH, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2)


def delete_trade(index):
    """Remove the trade record at index, persisting the result. No-op if out of range."""
    trades = load_trades()
    if 0 <= index < len(trades):
        record = trades.pop(index)
        save_trades(trades)
        return record
    return None


def load_api_config():
    """Return the API config dict, or raise RuntimeError with a friendly message."""
    if not os.path.exists(API_CONFIG_PATH):
        raise RuntimeError(
            "configs/api_config.json not found.\n"
            "Copy api_config.example.json to configs/api_config.json and fill in your values."
        )
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to read configs/api_config.json:\n{e}")
