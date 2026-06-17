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

from paths import resource_path, user_data_path

_LOOKUP_PATH = user_data_path("data", "ducat_lookup.json")
_IMAGE_INDEX_PATH = resource_path("assets", "item_images", "index.json")
_SEED_LOOKUP_PATH = resource_path("assets", "seed", "ducat_lookup.json")


def scan(lookup_path=None, image=None):
    """Read item names from a trade screenshot and resolve them to ducat values.

    image may be None (grab the screen live), a path to an image file, or a PIL
    Image — the file/Image forms enable offline testing against saved captures.

    Resolution is cache-aside: each name is matched against the local cache first
    (exact, then fuzzy); cache misses are batched into a single @wfcd/items lookup
    and appended back to the cache for next time.

    Each detected (filled) trade slot yields one ordered, left-to-right entry in
    results. Slots whose name can't be resolved to a ducat value (OCR garbage, or
    real but non-ducat items like Arcanes/Forma) become a 0-ducat placeholder so
    the caller can still represent every slot.

    Returns (results, skipped, resolver_unavailable, unresolved) where:
      results: list of {"name": str, "ducats": int,
                        "source": "cache"|"fetched"|"unresolved",
                        "image": str|None}, one per slot. "image" is the
        thumbnail filename under assets/item_images/ (per
        assets/item_images/index.json), or None when unresolved or not
        present in the index.
      skipped: count of 0-ducat placeholder entries (unresolved slots)
      resolver_unavailable: True if there were misses but Node/@wfcd/items could
        not be reached (callers surface a 'run npm install' hint)
      unresolved: list of {"assembled": str, "normalized": str} for each slot
        that could not be resolved; empty list if all slots resolved
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
    image_index = _load_image_index(_IMAGE_INDEX_PATH)

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
    entries = []   # per-slot dict, or None for an unresolved name
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

    # Each detected slot is a real item, so an unresolved slot becomes a 0-ducat
    # placeholder (kept in left-to-right slot order alongside resolved entries).
    unresolved = []
    for i, e in enumerate(entries):
        if e is None:
            norm = _normalize(names[i])
            entries[i] = {
                "name": norm or names[i].strip(),
                "ducats": 0,
                "source": "unresolved",
            }
            unresolved.append({"assembled": names[i], "normalized": norm})

    for entry in entries:
        entry["image"] = (
            image_index.get(entry["name"]) if entry["source"] != "unresolved" else None
        )

    skipped = len(unresolved)
    return entries, skipped, resolver_unavailable, unresolved


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


# Footer/chrome words that can bleed into the label band; never part of an item
# name, so they're dropped during cleanup.
_FOOTER_WORDS = {"not", "ready", "to", "trade", "add", "items"}


def _extract_item_names(img_bgr, pytesseract):
    """Extract the receiving-slot item names from a trade screenshot.

    The Trading Post shows the partner's offered (received) items as a row of up
    to six slots in the bottom panel, each with a one- or two-line name label
    beneath its icon. Strategy: locate the six slot columns geometrically, then
    OCR each name label in isolation with a threshold computed on just that crop.
    Per-crop thresholding is the key over a global pass — the bright item icons
    otherwise skew the threshold and bury the small label text. Returns cleaned,
    left-to-right name strings for the filled slots only; the caller normalizes
    and resolves them.
    """
    import cv2
    import numpy as np

    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    centers = _slot_centers(gray, w, h)
    colw = (centers[1] - centers[0]) * 0.98
    # Receive-panel label band as a fixed proportion of the window. The Trading
    # Post is a constant-layout menu, so this both reads the labels and keeps us
    # on the bottom (received) row rather than the player's own offer up top.
    ly0, ly1 = int(h * 0.773), int(h * 0.847)

    names = []
    for c in centers:
        x0 = max(0, int(c - colw / 2))
        x1 = min(w, int(c + colw / 2))
        crop = gray[ly0:ly1, x0:x1]
        if crop.size == 0:
            continue
        crop = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        # A touch of blur smooths the upscaled aliasing; without it some
        # low-contrast labels (dark warframe silhouettes) threshold to nothing.
        crop = cv2.GaussianBlur(crop, (0, 0), 1)
        _, binary = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if np.mean(binary) < 127:
            binary = cv2.bitwise_not(binary)  # Tesseract wants dark text on light
        binary = cv2.copyMakeBorder(
            binary, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255
        )
        text = _clean_label(pytesseract.image_to_string(binary, config="--psm 6"))
        if text:
            names.append((c, text))
    names.sort()  # left-to-right
    return [name for _, name in names]


def _slot_centers(gray, w, h):
    """Return six evenly-spaced x-centers for the bottom-panel trade slots.

    Detects the slot-icon cells via edge contours in the lower half and fits a
    regular 6-column grid to their centers (robust to a few missing/spurious
    cells). Falls back to fixed proportions of the window width when detection is
    too weak — the Trading Post is a constant-layout menu, so the proportional
    grid (centers spanning ~0.184W…0.816W) is a reliable backstop.
    """
    import cv2
    import numpy as np

    base = [w * (0.184 + (0.816 - 0.184) * i / 5) for i in range(6)]
    step = base[1] - base[0]

    ry0, ry1 = int(h * 0.55), int(h * 0.80)
    sub = gray[ry0:ry1, :]
    edges = cv2.dilate(
        cv2.Canny(sub, 30, 90), np.ones((3, 3), np.uint8), iterations=2
    )
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detected = []
    for cnt in cnts:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if w * 0.06 < bw < w * 0.18 and bh > (ry1 - ry0) * 0.4:
            detected.append(x + bw / 2.0)
    if len(detected) < 4:
        return base

    # Snap each detected center to its nearest baseline column, then least-squares
    # fit center = slope*index + intercept over those inliers to refine the grid.
    idx, cen = [], []
    for d in detected:
        i = min(range(6), key=lambda k: abs(base[k] - d))
        if abs(base[i] - d) <= step * 0.4:  # drop spurious boxes
            idx.append(i)
            cen.append(d)
    if len(set(idx)) < 4:
        return base
    A = np.vstack([idx, np.ones(len(idx))]).T
    slope, intercept = np.linalg.lstsq(A, np.array(cen), rcond=None)[0]
    if not (step * 0.6 <= slope <= step * 1.4):  # sanity-check the fitted spacing
        return base
    return [intercept + slope * i for i in range(6)]


def _clean_label(raw):
    """Reduce a raw per-slot OCR string to a clean item-name candidate.

    Drops footer words that can bleed in, junk tokens (single stray characters or
    pure punctuation/digits), and collapses whitespace. Returns '' when nothing
    meaningful remains — an empty slot has no readable label, so it's skipped.
    """
    tokens = []
    for tok in raw.lower().split():
        letters = re.sub(r"[^a-z]", "", tok)
        if len(letters) >= 2 and letters not in _FOOTER_WORDS:
            tokens.append(letters)
    if not any(len(t) >= 3 for t in tokens):
        return ""
    return " ".join(tokens)


def _ensure_lookup_seeded(path):
    """Copy the bundled seed cache to the writable path on first run, if absent.

    Only applies to the real writable lookup path: a fresh install has no
    data/ducat_lookup.json yet, so without this every item would need a Node
    round-trip (or fail entirely when scripts/ isn't bundled) before the cache
    self-warms. The seed is pre-warmed via `npm run generate` and committed at
    assets/seed/ducat_lookup.json.
    """
    if path != _LOOKUP_PATH:
        return
    if os.path.exists(path) or not os.path.exists(_SEED_LOOKUP_PATH):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(_SEED_LOOKUP_PATH, "r", encoding="utf-8") as f:
            seed = f.read()
    except OSError:
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(seed)


def _load_lookup(path):
    """Load and normalize the ducat cache. A missing file means an empty cache.

    The cache is self-warming: unknown items are fetched from @wfcd/items and
    appended on the fly (see _resolve_via_wfcd), so a fresh install with no cache
    file is fine. A file that exists but can't be parsed is a real error and is
    surfaced to the caller.
    """
    _ensure_lookup_seeded(path)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {_normalize(k): int(v) for k, v in raw.items()}
    except Exception as e:
        raise RuntimeError(f"Failed to read data/ducat_lookup.json:\n{e}")


def _load_image_index(path):
    """Load the normalized-name -> thumbnail-filename map. A missing file means no images."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


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
    # When the text reads as a component label with a trailing "Blueprint" (the
    # game appends it; @wfcd/items and this cache store components without it —
    # see _strip_component_blueprint), match on the stripped form only and don't
    # fall back to the untouched text. Falling back would let it fuzzy-collide
    # with an unrelated "<name> prime blueprint" cache entry that happens to
    # share a leading token (e.g. "chroma prime chassis blueprint" — or a merged-
    # token OCR read like "chromaprnt chassis blueprint" — against the cached
    # "chroma prime blueprint"); better to miss here and let the Node resolver
    # (Pass 2) resolve it correctly than to silently mismatch.
    query = _strip_component_blueprint(norm)
    if query in lookup:
        return query, lookup[query]
    # Fuzzy fallback using stdlib difflib (cutoff=0.75 to avoid false positives).
    # The whole-string ratio over-weights the shared "<prime> <component>" suffix
    # (e.g. "akbolto prime blueprint" scores 0.86 against "zakti prime blueprint"),
    # so anchor on the distinctive leading name token before accepting a match.
    # @wfcd names are "<item-name> prime <component>", so a differing first token
    # means a different item — defer those to the robust Node resolver in Pass 2.
    matches = difflib.get_close_matches(query, lookup.keys(), n=1, cutoff=0.75)
    if matches and _leading_token_sim(query, matches[0]) >= 0.7:
        return matches[0], lookup[matches[0]]
    return None, None


def _strip_component_blueprint(norm):
    """Drop a trailing "blueprint" the game appends to component labels.

    @wfcd/items (and this cache) store component names like "chroma prime
    chassis" without the trailing "Blueprint" the in-game label shows — only a
    warframe/weapon's own main blueprint keeps it (e.g. "hydroid prime
    blueprint"). Without this, a correctly-read component label never hits the
    cache's exact-match entry and falls into the fuzzy fallback below, where it
    can lose to a shorter, wrong "<name> prime blueprint" entry that shares the
    same leading token. Mirrors the same rule in wf_ducat_lookup.js's
    resolveByTokens.
    """
    tokens = norm.split(" ")
    if len(tokens) >= 3 and tokens[-1] == "blueprint" and tokens[-2] != "prime":
        return " ".join(tokens[:-1])
    return norm


def _leading_token_sim(query, candidate):
    """Similarity (0..1) of the first whitespace token of two normalized names."""
    q = query.split(None, 1)[0] if query else ""
    c = candidate.split(None, 1)[0] if candidate else ""
    return difflib.SequenceMatcher(None, q, c).ratio()


def _resolve_via_wfcd(queries):
    """Resolve unknown item names against @wfcd/items via the Node helper.

    Batched: one subprocess call for all queries. Returns
    (matches, resolver_unavailable) where matches maps a normalized query to
    {"name": normalized_canonical_name, "ducats": int}. resolver_unavailable is
    True when Node or scripts/node_modules is missing, or the call otherwise
    fails — callers treat that as "leave these unresolved" rather than erroring.
    """
    script_dir = resource_path("scripts")
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
