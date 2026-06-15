"""Loading and saving the ducat-to-platinum price configuration and trade log."""

import json
import os
from datetime import datetime

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIGS_DIR = os.path.join(_BASE_DIR, "configs")
CONFIG_PATH = os.path.join(CONFIGS_DIR, "config.json")

DATA_DIR = os.path.join(_BASE_DIR, "data")
TRADES_PATH = os.path.join(DATA_DIR, "trades.json")

DUCAT_VALUES = [15, 25, 45, 65, 100]

DEFAULT_PRICE_MAP = {15: 0, 25: 0, 45: 0, 65: 0, 100: 0}


def load_config():
    """Return the ducat -> platinum price map, creating a default file if needed."""
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_PRICE_MAP)
        return dict(DEFAULT_PRICE_MAP)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        price_map = {int(k): int(v) for k, v in raw.items()}
        for ducat_value in DUCAT_VALUES:
            price_map.setdefault(ducat_value, DEFAULT_PRICE_MAP[ducat_value])
        return price_map
    except (ValueError, OSError, json.JSONDecodeError):
        save_config(DEFAULT_PRICE_MAP)
        return dict(DEFAULT_PRICE_MAP)


def save_config(price_map):
    """Persist the ducat -> platinum price map to disk."""
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in price_map.items()}, f, indent=2)


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
    })

    with open(TRADES_PATH, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2)
