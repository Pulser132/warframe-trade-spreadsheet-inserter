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

import config_manager
import resolver
from paths import resource_path, user_data_path

_LOOKUP_PATH = user_data_path("data", "ducat_lookup.json")
_IMAGE_INDEX_PATH = resource_path("assets", "item_images", "index.json")
_SEED_LOOKUP_PATH = resource_path("assets", "seed", "ducat_lookup.json")


def scan(lookup_path=None, image=None):
    """Read item names from a trade screenshot and resolve them to ducat values.

    image may be None (grab the screen live), a path to an image file, or a PIL
    Image — the file/Image forms enable offline testing against saved captures.

    Resolution is two-pass, both pure Python (no Node/internet at runtime):
    Pass 1 is a local-cache exact/anchored-fuzzy match (`_resolve`); Pass 2 runs
    cache misses through `resolver.resolve_one` — a pure-Python port of the
    robust matcher formerly in scripts/wf_ducat_lookup.js — against the same
    cache data (`resolver.build_index(lookup)`), recovering typo'd / merged-
    token / mid-word-misread OCR reads.

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
      resolver_unavailable: deprecated, always False — Pass 2 is now pure
        Python and runs over data already in the cache, so it can't be
        "unavailable". Kept only for return-shape compatibility with callers.
      unresolved: list of {"assembled": str, "normalized": str} for each slot
        that could not be resolved; empty list if all slots resolved
    results is empty / skipped is 0 when no item names are found at all.
    Raises RuntimeError with a user-friendly message on any hard failure.
    """
    _, img_bgr, lookup, image_index, pytesseract = _prepare_scan(image, lookup_path)
    names, _diag = _extract_item_names(img_bgr, pytesseract)

    if not names:
        return [], 0, False, []

    thresholds = config_manager.load_ocr_thresholds()
    entries, unresolved = _resolve_slots(
        names, lookup, image_index, thresholds=thresholds
    )
    skipped = len(unresolved)
    # resolver_unavailable is deprecated and always False (see docstring).
    return entries, skipped, False, unresolved


def _prepare_scan(image, lookup_path):
    """Load the optional OCR deps, point Tesseract at its binary, load the lookup
    cache + image index, and produce the screenshot.

    Returns (screenshot, img_bgr, lookup, image_index, pytesseract). `image` may
    be None (grab the screen), a path string, or a PIL Image. Raises RuntimeError
    with a user-friendly message on any hard failure. Shared by scan() and
    scan_debug() so the two paths can't drift.
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
    return screenshot, img_bgr, lookup, image_index, pytesseract


def _resolve_slots(names, lookup, image_index, *, thresholds, diag_sink=None):
    """Two-pass resolve shared by scan() and scan_debug().

    Pass 1 (`_resolve`) → Pass 2 (`resolver.resolve_one`) → 0-ducat placeholder,
    attaching each entry's thumbnail filename. Returns (entries, unresolved).

    `thresholds` is the dict from config_manager.load_ocr_thresholds().
    When `diag_sink` is a list, one diagnostic dict is appended per slot (aligned
    with `names` order): resolved_by ("pass1"/"pass2"/"unresolved"), the winning
    score (Pass 1 difflib ratio or the resolved Pass 2 candidate's score),
    cleaned + normalized text, and resolver.rank_candidates(norm, index) top-N.
    """
    cutoff = thresholds["pass1_cutoff"]
    anchor = thresholds["pass1_anchor"]
    whole = thresholds["pass2_whole"]
    token = thresholds["pass2_token"]

    index = resolver.build_index(lookup)
    collect = diag_sink is not None

    # Pass 1: resolve every detected name from the local cache (no Node).
    entries = []   # per-slot dict, or None for an unresolved name
    misses = []    # (index, normalized_query) for cache misses
    pass1_scores = {}  # i -> difflib ratio of the winning Pass 1 match (diag only)
    for i, text in enumerate(names):
        name, value = _resolve(text, lookup, cutoff=cutoff, anchor=anchor)
        if value is not None:
            entries.append({"name": name, "ducats": value, "source": "cache"})
            if collect:
                q = _strip_component_blueprint(_normalize(text))
                pass1_scores[i] = difflib.SequenceMatcher(None, q, name).ratio()
        else:
            entries.append(None)
            norm = _normalize(text)
            if norm:
                misses.append((i, norm))

    # Pass 2: resolve cache misses with the pure-Python robust matcher (the
    # former Node Pass 2, ported in resolver.py), run over the cache data
    # already loaded above — no new entries to append, every match is already
    # a cache key.
    if misses:
        match_cache = {}
        for i, q in misses:
            if q not in match_cache:
                match_cache[q] = resolver.resolve_one(q, index, whole=whole, token=token)
            match = match_cache[q]
            if match:
                entries[i] = {
                    "name": match["norm"],
                    "ducats": match["ducats"],
                    "source": "fetched",
                }

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

    if collect:
        for i, entry in enumerate(entries):
            norm = _normalize(names[i])
            candidates = resolver.rank_candidates(norm, index, n=5)
            source = entry["source"]
            if source == "cache":
                resolved_by = "pass1"
                score = pass1_scores.get(i, 1.0)
            elif source == "fetched":
                resolved_by = "pass2"
                score = next(
                    (c["score"] for c in candidates if c["norm"] == entry["name"]),
                    candidates[0]["score"] if candidates else 0.0,
                )
            else:
                resolved_by = "unresolved"
                score = candidates[0]["score"] if candidates else 0.0
            diag_sink.append({
                "resolved_by": resolved_by,
                "score": score,
                "cleaned": names[i],
                "normalized": norm,
                "candidates": candidates,
            })

    return entries, unresolved


def scan_debug(image=None, lookup_path=None):
    """Like scan(), but also build a rich per-slot diagnostic payload for a debug
    capture. Returns (entries, skipped, unresolved, debug_payload).

    debug_payload carries:
      screenshot: the full PIL screenshot.
      thresholds: the four OCR thresholds in effect.
      slots: a per-slot list (aligned with entries), each with index, bbox, the
        binary (post-threshold) crop ndarray, the raw color crop ndarray, the
        raw/cleaned/normalized text, resolved_by, the final `result` entry, the
        winning `score`, and ranked top-N `candidates`.
      note: present (explanatory) only in the zero-slots case.

    The zero-slots case still returns a payload (screenshot + empty slot list) so
    a capture can be written. Raises RuntimeError on any hard failure, exactly
    like scan().
    """
    screenshot, img_bgr, lookup, image_index, pytesseract = _prepare_scan(
        image, lookup_path
    )
    thresholds = config_manager.load_ocr_thresholds()
    names, geom_diag = _extract_item_names(img_bgr, pytesseract, collect_diag=True)

    if not names:
        debug_payload = {
            "screenshot": screenshot,
            "thresholds": thresholds,
            "slots": [],
            "note": "No trade slots detected.",
        }
        return [], 0, [], debug_payload

    diag_sink = []
    entries, unresolved = _resolve_slots(
        names, lookup, image_index, thresholds=thresholds, diag_sink=diag_sink
    )

    slots = []
    for i, entry in enumerate(entries):
        g = geom_diag[i] if geom_diag and i < len(geom_diag) else {}
        d = diag_sink[i] if i < len(diag_sink) else {}
        slots.append({
            "index": i,
            "bbox": g.get("bbox"),
            "binary": g.get("binary"),
            "crop": g.get("crop"),
            "raw": g.get("raw", ""),
            "cleaned": d.get("cleaned", names[i]),
            "normalized": d.get("normalized", ""),
            "resolved_by": d.get("resolved_by", "unresolved"),
            "result": entry,
            "score": d.get("score", 0.0),
            "candidates": d.get("candidates", []),
        })

    debug_payload = {
        "screenshot": screenshot,
        "thresholds": thresholds,
        "slots": slots,
    }
    skipped = len(unresolved)
    return entries, skipped, unresolved, debug_payload


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


def _extract_item_names(img_bgr, pytesseract, *, collect_diag=False):
    """Extract the receiving-slot item names from a trade screenshot.

    The Trading Post shows the partner's offered (received) items as a row of up
    to six slots in the bottom panel, each with a one- or two-line name label
    beneath its icon. Strategy: locate the six slot columns geometrically, then
    OCR each name label in isolation with a threshold computed on just that crop.
    Per-crop thresholding is the key over a global pass — the bright item icons
    otherwise skew the threshold and bury the small label text.

    Returns (names, diag). `names` is the cleaned, left-to-right name strings for
    the filled slots only; the caller normalizes and resolves them. `diag` is
    None unless `collect_diag` is set, in which case it's a list aligned 1:1 with
    `names`, each entry a dict with the slot's `bbox` (x0, ly0, x1, ly1), its
    `binary` (post-threshold ndarray Tesseract saw), the raw color `crop`
    ndarray, and the `raw` pre-`_clean_label` OCR string.
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

    slots = []  # (center, name, diag-or-None)
    for c in centers:
        x0 = max(0, int(c - colw / 2))
        x1 = min(w, int(c + colw / 2))
        crop = gray[ly0:ly1, x0:x1]
        if crop.size == 0:
            continue
        upscaled = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        # A touch of blur smooths the upscaled aliasing; without it some
        # low-contrast labels (dark warframe silhouettes) threshold to nothing.
        upscaled = cv2.GaussianBlur(upscaled, (0, 0), 1)
        _, binary = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if np.mean(binary) < 127:
            binary = cv2.bitwise_not(binary)  # Tesseract wants dark text on light
        binary = cv2.copyMakeBorder(
            binary, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255
        )
        raw = pytesseract.image_to_string(binary, config="--psm 6")
        text = _clean_label(raw)
        if text:
            diag = None
            if collect_diag:
                diag = {
                    "bbox": (x0, ly0, x1, ly1),
                    "binary": binary,
                    "crop": img_bgr[ly0:ly1, x0:x1].copy(),
                    "raw": raw,
                }
            slots.append((c, text, diag))
    slots.sort(key=lambda s: s[0])  # left-to-right
    names = [name for _, name, _ in slots]
    if collect_diag:
        return names, [d for _, _, d in slots]
    return names, None


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

    Returns the seed JSON text when it couldn't be persisted to `path` (e.g. a
    read-only install directory), so `_load_lookup` can fall back to using it
    in-memory for this run; returns None when seeding isn't needed/applicable
    or the persisted copy now exists.
    """
    if path != _LOOKUP_PATH:
        return None
    if os.path.exists(path) or not os.path.exists(_SEED_LOOKUP_PATH):
        return None
    try:
        with open(_SEED_LOOKUP_PATH, "r", encoding="utf-8") as f:
            seed = f.read()
    except OSError:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(seed)
    except OSError:
        return seed  # Read-only install dir — scan still works read-only this run.
    return None


def _load_lookup(path):
    """Load and normalize the ducat cache. A missing file means an empty cache
    (Pass 2's resolver.resolve_one runs over whatever's in it, so a fresh
    install with no cache file beyond the seed is fine). A file that exists but
    can't be parsed is a real error and is surfaced to the caller.
    """
    fallback_seed = _ensure_lookup_seeded(path)
    if not os.path.exists(path):
        if fallback_seed is None:
            return {}
        try:
            raw = json.loads(fallback_seed)
            return {_normalize(k): int(v) for k, v in raw.items()}
        except (ValueError, TypeError, AttributeError) as e:
            raise RuntimeError(f"Failed to parse bundled seed cache:\n{e}")
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


def _resolve(ocr_text, lookup, *, cutoff=0.75, anchor=0.70):
    """Return (matched_name, ducat_value), or (None, None) if unresolved.

    matched_name is the clean lookup-table key, not the raw OCR text. `cutoff` is
    the difflib fuzzy-match cutoff and `anchor` the leading-token similarity gate;
    the defaults (0.75 / 0.70) reproduce the original hardcoded Pass 1 behavior.
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
    matches = difflib.get_close_matches(query, lookup.keys(), n=1, cutoff=cutoff)
    if matches and _leading_token_sim(query, matches[0]) >= anchor:
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

