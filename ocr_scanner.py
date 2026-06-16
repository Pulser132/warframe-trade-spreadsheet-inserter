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
import subprocess

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_LOOKUP_PATH = os.path.join(_BASE_DIR, "data", "ducat_lookup.json")


def scan(lookup_path=None):
    """Capture the screen, detect trade slots, OCR each, and return resolved items.

    Resolution is cache-aside: each OCR'd name is matched against the local cache
    first (exact, then fuzzy); cache misses are batched into a single @wfcd/items
    lookup and appended back to the cache for next time.

    Returns (results, skipped, resolver_unavailable) where:
      results: list of {"name": str, "ducats": int, "source": "cache"|"fetched"}
      skipped: count of detected slots whose names could not be resolved
      resolver_unavailable: True if there were misses but Node/@wfcd/items could
        not be reached (callers surface a 'run npm install' hint)
    results is empty / skipped is 0 when no trade slots are found at all.
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
        return [], 0, False

    # OCR every detected slot first.
    slot_texts = []
    for crop_bgr in slot_crops[:6]:
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(crop_rgb)
        # Upscale 2x for better OCR accuracy on small slot regions
        pil_img = pil_img.resize(
            (pil_img.width * 2, pil_img.height * 2), Image.LANCZOS
        )
        slot_texts.append(
            pytesseract.image_to_string(pil_img, config="--psm 7").strip()
        )

    # Pass 1: resolve from the local cache (no Node).
    entries = []   # per-slot dict, or None for an unresolved slot
    misses = []    # (slot_index, normalized_query) for cache misses
    for i, text in enumerate(slot_texts):
        name, value = _resolve(text, lookup)
        if value is not None:
            entries.append({"name": name, "ducats": value, "source": "cache"})
        else:
            entries.append(None)
            norm = _normalize(text)
            if norm:
                misses.append((i, norm))

    # Pass 2: resolve cache misses against @wfcd/items in one batched call.
    resolver_unavailable = False
    if misses:
        unique_queries = sorted({q for _, q in misses})
        fetched, resolver_unavailable = _resolve_via_wfcd(unique_queries)
        new_entries = {}
        for i, q in misses:
            match = fetched.get(q)
            if match:
                entries[i] = {
                    "name": match["name"],
                    "ducats": match["ducats"],
                    "source": "fetched",
                }
                new_entries[match["name"]] = match["ducats"]
        if new_entries:
            _append_cache(lookup_path, new_entries)

    results = [e for e in entries if e is not None]
    skipped = sum(1 for e in entries if e is None)
    return results, skipped, resolver_unavailable


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
    """Load and normalize the ducat cache. A missing file means an empty cache.

    The cache is self-warming: unknown items are fetched from @wfcd/items and
    appended on the fly (see _resolve_via_wfcd), so a fresh install with no cache
    file is fine. A file that exists but can't be parsed is a real error and is
    surfaced to the caller.
    """
    if not os.path.exists(path):
        return {}
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


def _resolve_via_wfcd(queries):
    """Resolve unknown item names against @wfcd/items via the Node helper.

    Batched: one subprocess call for all queries. Returns
    (matches, resolver_unavailable) where matches maps a normalized query to
    {"name": normalized_canonical_name, "ducats": int}. resolver_unavailable is
    True when Node or scripts/node_modules is missing, or the call otherwise
    fails — callers treat that as "leave these unresolved" rather than erroring.
    """
    script_dir = os.path.join(_BASE_DIR, "scripts")
    script = os.path.join(script_dir, "wf_ducat_lookup.js")
    node_modules = os.path.join(script_dir, "node_modules")
    if not os.path.exists(script) or not os.path.isdir(node_modules):
        return {}, True

    cmd = ["node", "wf_ducat_lookup.js", "--resolve-json", *queries]
    try:
        proc = subprocess.run(
            cmd,
            cwd=script_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return {}, True
    if proc.returncode != 0:
        return {}, True

    try:
        data = json.loads(proc.stdout)
    except (ValueError, TypeError):
        return {}, True
    if not isinstance(data, list):
        return {}, True

    matches = {}
    for entry in data:
        query = entry.get("query")
        name = entry.get("name")
        ducats = entry.get("ducats")
        if query and name and ducats is not None:
            try:
                matches[_normalize(query)] = {
                    "name": _normalize(name),
                    "ducats": int(ducats),
                }
            except (TypeError, ValueError):
                continue
    return matches, False


def _append_cache(path, new_entries):
    """Merge newly-resolved {name: ducats} into the cache JSON via an atomic write."""
    existing = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, ValueError):
            existing = {}

    changed = False
    for name, ducats in new_entries.items():
        if existing.get(name) != ducats:
            existing[name] = ducats
            changed = True
    if not changed:
        return

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, sort_keys=True)
    os.replace(tmp, path)
