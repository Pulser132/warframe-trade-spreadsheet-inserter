"""Optional OCR module for auto-populating trades from the Warframe trade window.

Lazily imported from app.py (like sheets_exporter). Raises RuntimeError with
user-friendly messages on any failure so the caller can show a messagebox.

Requires (all optional — app starts normally without them):
  pip install Pillow pytesseract opencv-python
  + Tesseract-OCR binary: https://github.com/UB-Mannheim/tesseract/wiki
"""

import difflib
import json
import os
import re

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_LOOKUP_PATH = os.path.join(_BASE_DIR, "data", "ducat_lookup.json")


def scan(lookup_path=None):
    """Capture the screen, detect trade slots, OCR each, and return resolved items.

    Returns (results, skipped) where:
      results: list of {"name": str, "ducats": int} for each resolved slot
      skipped: count of detected slots whose names could not be resolved
    Both are 0/empty when no trade slots are found at all.
    Raises RuntimeError with a user-friendly message on any hard failure.
    """
    if lookup_path is None:
        lookup_path = _LOOKUP_PATH

    try:
        from PIL import Image, ImageGrab
    except ImportError:
        raise RuntimeError(
            "Pillow is not installed.\n"
            "Run: pip install Pillow"
        )
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise RuntimeError(
            "opencv-python is not installed.\n"
            "Run: pip install opencv-python"
        )
    try:
        import pytesseract
    except ImportError:
        raise RuntimeError(
            "pytesseract is not installed.\n"
            "Run: pip install pytesseract\n"
            "Also install the Tesseract-OCR binary:\n"
            "https://github.com/UB-Mannheim/tesseract/wiki"
        )

    lookup = _load_lookup(lookup_path)

    try:
        screenshot = ImageGrab.grab()
    except Exception as e:
        raise RuntimeError(f"Screen capture failed:\n{e}")

    img_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    slot_crops = _detect_slots(img_bgr)

    if not slot_crops:
        return [], 0

    results = []
    skipped = 0
    for crop_bgr in slot_crops[:6]:
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(crop_rgb)
        # Upscale 2x for better OCR accuracy on small slot regions
        pil_img = pil_img.resize(
            (pil_img.width * 2, pil_img.height * 2), Image.LANCZOS
        )
        text = pytesseract.image_to_string(pil_img, config="--psm 7").strip()
        matched_name, value = _resolve(text, lookup)
        if value is not None:
            results.append({"name": matched_name, "ducats": value})
        else:
            skipped += 1

    return results, skipped


def _detect_slots(img_bgr):
    """Return up to 6 BGR slot crops from the Warframe trade window.

    Detection strategy: threshold for the dark-grey trade UI background in HSV,
    then find rectangular contours of roughly the right size for item slots.
    Sort left-to-right, top-to-bottom and return the top 6.

    The HSV bounds and area thresholds below target a standard 1080p/1440p
    Warframe UI. Tune _SLOT_HSV_LOWER/_UPPER if your UI scale differs.
    """
    import cv2
    import numpy as np

    _SLOT_HSV_LOWER = np.array([0, 0, 15])
    _SLOT_HSV_UPPER = np.array([30, 50, 75])

    h, w = img_bgr.shape[:2]
    total_px = w * h

    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, _SLOT_HSV_LOWER, _SLOT_HSV_UPPER)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Slots occupy roughly 0.3%–4% of the screen at typical resolutions
    min_area = total_px * 0.003
    max_area = total_px * 0.04

    candidates = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        if area < min_area or area > max_area:
            continue
        aspect = cw / ch if ch > 0 else 0
        # Slots are roughly square (0.6–1.8 aspect ratio)
        if 0.6 <= aspect <= 1.8:
            candidates.append((x, y, cw, ch))

    # Sort top-to-bottom then left-to-right (group by row within ~50px tolerance)
    candidates.sort(key=lambda r: (r[1] // 50, r[0]))

    crops = []
    for (x, y, cw, ch) in candidates[:6]:
        crops.append(img_bgr[y: y + ch, x: x + cw])

    return crops


def _load_lookup(path):
    """Load and normalize the ducat lookup table, raising RuntimeError if missing."""
    if not os.path.exists(path):
        raise RuntimeError(
            "data/ducat_lookup.json not found.\n"
            "Generate it with the ducat-lookup scraper, or copy\n"
            "ducat_lookup.example.json to data/ducat_lookup.json as a starter."
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {_normalize(k): int(v) for k, v in raw.items()}
    except Exception as e:
        raise RuntimeError(f"Failed to read data/ducat_lookup.json:\n{e}")


def _normalize(text):
    """Lowercase, strip non-alphanumeric characters, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _resolve(ocr_text, lookup):
    """Return (matched_name, ducat_value), or (None, None) if unresolved.

    matched_name is the clean lookup-table key, not the raw OCR text.
    """
    if not ocr_text:
        return None, None
    norm = _normalize(ocr_text)
    if norm in lookup:
        return norm, lookup[norm]
    # Fuzzy fallback using stdlib difflib (cutoff=0.75 to avoid false positives)
    matches = difflib.get_close_matches(norm, lookup.keys(), n=1, cutoff=0.75)
    if matches:
        return matches[0], lookup[matches[0]]
    return None, None
