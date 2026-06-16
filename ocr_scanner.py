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


def scan(lookup_path=None, image=None):
    """Read item names from a trade screenshot and resolve them to ducat values.

    image may be None (grab the screen live), a path to an image file, or a PIL
    Image — the file/Image forms enable offline testing against saved captures.

    Resolution is cache-aside: each name is matched against the local cache first
    (exact, then fuzzy); cache misses are batched into a single @wfcd/items lookup
    and appended back to the cache for next time.

    Returns (results, skipped, resolver_unavailable, unresolved) where:
      results: list of {"name": str, "ducats": int, "source": "cache"|"fetched"}
      skipped: count of detected names that could not be resolved
      resolver_unavailable: True if there were misses but Node/@wfcd/items could
        not be reached (callers surface a 'run npm install' hint)
      unresolved: list of {"assembled": str, "normalized": str} for each item
        that could not be resolved; empty list if all items resolved
    results is empty / skipped is 0 when no item names are found at all.
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

    _configure_tesseract(pytesseract)

    lookup = _load_lookup(lookup_path)

    if image is None:
        try:
            screenshot = ImageGrab.grab()
        except Exception as e:
            raise RuntimeError(f"Screen capture failed:\n{e}")
    elif isinstance(image, str):
        try:
            screenshot = Image.open(image).convert("RGB")
        except Exception as e:
            raise RuntimeError(f"Failed to open image '{image}':\n{e}")
    else:
        screenshot = image.convert("RGB") if hasattr(image, "convert") else image

    img_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    names = _extract_item_names(img_bgr, pytesseract)

    if not names:
        return [], 0, False, []

    # Pass 1: resolve every detected name from the local cache (no Node).
    entries = []   # per-item dict, or None for an unresolved name
    misses = []    # (index, normalized_query) for cache misses
    for i, text in enumerate(names):
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

    unresolved = [
        {"assembled": names[i], "normalized": _normalize(names[i])}
        for i, e in enumerate(entries)
        if e is None
    ]
    results = [e for e in entries if e is not None]
    skipped = len(unresolved)
    return results, skipped, resolver_unavailable, unresolved


def _configure_tesseract(pytesseract):
    """Point pytesseract at the Tesseract binary if it isn't already on PATH.

    The UB-Mannheim Windows installer commonly drops tesseract.exe under
    %LOCALAPPDATA% or Program Files without adding it to PATH, so probe the usual
    locations as a fallback.
    """
    import shutil

    if shutil.which("tesseract"):
        return
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local, "Programs", "Tesseract-OCR", "tesseract.exe") if local else "",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return


def _extract_item_names(img_bgr, pytesseract):
    """Extract Warframe item-name strings from a trade screenshot.

    The Trading Post UI prints each item's name as a small text label under its
    icon. Strategy: OCR the image, treat every 'Prime' word as an anchor (all
    Prime parts contain it; empty slots and UI chrome do not), then attach nearby
    words to their nearest anchor to reassemble each (possibly two-line) name.
    A second OCR pass over the tight band around the anchors sharpens the small
    label text. Returns raw name strings; the caller normalizes and resolves them.
    """
    import cv2
    import numpy as np
    from pytesseract import Output

    h, w = img_bgr.shape[:2]
    scale = 2
    gray = cv2.resize(
        cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY),
        (w * scale, h * scale),
        interpolation=cv2.INTER_CUBIC,
    )
    # Item labels are light text on a dark UI; Otsu makes them crisp for OCR.
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    def words_of(region):
        data = pytesseract.image_to_data(
            region, config="--psm 11", output_type=Output.DICT
        )
        out = []
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            if text and conf >= 45 and re.search(r"[A-Za-z]", text):
                out.append({
                    "t": text,
                    "cx": data["left"][i] + data["width"][i] / 2,
                    "cy": data["top"][i] + data["height"][i] / 2,
                    "h": data["height"][i],
                })
        return out

    def is_prime(word):
        return word["t"].lower().strip(".,:!") == "prime"

    anchors = [wd for wd in words_of(binary) if is_prime(wd)]
    if not anchors:
        return []

    # Re-OCR a tight band around the anchors — small label text reads much more
    # cleanly without the bright icons skewing the global threshold.
    line_h = float(np.median([a["h"] for a in anchors]))
    ys = [a["cy"] for a in anchors]
    y0 = max(0, int(min(ys) - line_h * 2.5))
    y1 = min(binary.shape[0], int(max(ys) + line_h * 2.5))
    words = words_of(binary[y0:y1, :])
    for wd in words:
        wd["cy"] += y0
    anchors = [wd for wd in words if is_prime(wd)] or anchors
    line_h = float(np.median([a["h"] for a in anchors]))

    # Attach each word to its nearest Prime anchor (horizontally), gated
    # vertically so a name's wrapped second line is captured but the header/footer
    # sharing the same column is not.
    anchor_ids = {id(a) for a in anchors}
    groups = {id(a): [a] for a in anchors}
    for wd in words:
        if id(wd) in anchor_ids:
            continue
        candidates = [a for a in anchors if abs(wd["cy"] - a["cy"]) <= line_h * 2.6]
        if not candidates:
            continue
        nearest = min(candidates, key=lambda a: abs(wd["cx"] - a["cx"]))
        if abs(wd["cx"] - nearest["cx"]) <= line_h * 8:
            groups[id(nearest)].append(wd)

    names = []
    for a in anchors:
        grp = sorted(
            groups[id(a)],
            key=lambda wd: (round(wd["cy"] / (line_h * 0.9)), wd["cx"]),
        )
        names.append((a["cx"], " ".join(wd["t"] for wd in grp)))
    names.sort()  # left-to-right
    return [name for _, name in names]


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
