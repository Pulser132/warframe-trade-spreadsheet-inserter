"""Loading and saving the ducat-to-platinum price configuration."""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DUCAT_VALUES = [15, 25, 45, 65, 100]

DEFAULT_PRICE_MAP = {15: 15, 25: 20, 45: 30, 65: 40, 100: 50}


def load_config():
    """Return the ducat -> platinum price map, creating a default file if needed."""
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
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in price_map.items()}, f, indent=2)
