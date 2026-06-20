"""Offline test for the OCR trade scanner.

Runs ocr_scanner.scan() against saved trade-window screenshots in
"OCR Test Images/" instead of a live screen grab, so the detection → OCR →
resolution pipeline can be exercised without the game running.

Run it directly:

    python tests/ocr_offline_test.py

Requirements: the optional OCR deps (Pillow, opencv-python, pytesseract) plus the
Tesseract binary. Resolution itself is pure Python (resolver.py, no Node/internet
needed — see tests/test_resolver.py for resolver-only unit tests). If the deps or
images are missing the test SKIPS (exit 0) rather than failing, so it's safe in CI.

Each run uses a throwaway cache file, so your real data/ducat_lookup.json is left
untouched.
"""

import json
import os
import sys
import tempfile

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE_DIR)

IMAGES_DIR = os.path.join(_BASE_DIR, "OCR Test Images")

# Known items in each screenshot, by resolved canonical (normalized) name.
# Resolved names are stable (the resolver returns the @wfcd/items canonical form),
# even though the raw OCR text varies — so assert on these, not on OCR output.
# `expected` lists the ducat-bearing items; `placeholders` is the count of slots
# that resolve to a 0-ducat placeholder (non-ducat items like Arcanes).
EXPECTATIONS = {
    "chrome_3IXJzCdSqV.jpg": {
        "expected": {
            "stradavar prime blueprint",
            "zakti prime blueprint",
            "alternox prime barrel",
            "braton prime receiver",
            "knell prime receiver",
            "equinox prime chassis",
        },
        "min_resolved": 6,
        "placeholders": 0,
    },
    "NVIDIA_Overlay_nvw3kfUOUH.jpg": {
        "expected": {
            "akbolto prime blueprint",
            "akstiletto prime link",
            "akvasto prime blueprint",
            "alternox prime barrel",
            "akarius prime blueprint",
            "caliban prime neuroptics",
        },
        "min_resolved": 6,
        "placeholders": 0,
    },
    "NVIDIA_Overlay_TrGsLr6FWF.jpg": {
        "expected": {
            "wisp prime systems",
            "hydroid prime blueprint",
            "euphona prime barrel",
            "cedo prime receiver",
            "chroma prime chassis",
        },
        # Arcane Acceleration has no ducat value, so it lands as a 0-placeholder.
        "min_resolved": 5,
        "placeholders": 1,
    },
}


def _skip(msg):
    print(f"SKIP: {msg}")
    sys.exit(0)


def main():
    try:
        import ocr_scanner
    except ImportError as e:
        _skip(f"could not import ocr_scanner ({e})")

    if not os.path.isdir(IMAGES_DIR):
        _skip(f"no '{os.path.basename(IMAGES_DIR)}' directory")

    images = [
        f for f in sorted(os.listdir(IMAGES_DIR))
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))
    ]
    if not images:
        _skip("no test images found")

    seed_path = os.path.join(_BASE_DIR, "assets", "seed", "ducat_lookup.json")
    with open(seed_path, "r", encoding="utf-8") as f:
        seed_lookup = json.load(f)

    failures = []
    for fname in images:
        path = os.path.join(IMAGES_DIR, fname)
        # Throwaway cache so the real data/ducat_lookup.json isn't modified.
        # Mirrors the real, fully-seeded production cache (resolver.py's Pass 2
        # runs over this same data — see ocr_scanner.scan() — so it needs the
        # full 571-entry seed, not just a couple of decoy keys) while still
        # reproducing real cache-collision bugs, since these two entries are
        # genuinely in the seed at these values:
        # - "zakti prime blueprint" shares the "<prime> <component>" suffix with
        #   many items, so the Python cache-side fuzzy step (ocr_scanner._resolve)
        #   used to mis-match correctly-read names like "akbolto prime
        #   blueprint"/"hydroid prime blueprint" to it (issue #10).
        # - "chroma prime blueprint" collides with the component name "chroma
        #   prime chassis" once the in-game "Blueprint" suffix is added back —
        #   the fuzzy fallback used to prefer the shorter, wrong entry over the
        #   correct component match.
        # Items must still resolve to their true names despite these decoys
        # being present in the cache.
        tmp_cache = os.path.join(tempfile.gettempdir(), f"ocr_test_cache_{fname}.json")
        with open(tmp_cache, "w", encoding="utf-8") as f:
            json.dump(seed_lookup, f)

        try:
            results, skipped, _, unresolved = ocr_scanner.scan(
                lookup_path=tmp_cache, image=path
            )
        except RuntimeError as e:
            # Hard failure usually means missing OCR deps / Tesseract binary.
            _skip(f"{fname}: scan raised RuntimeError — {e}")
        finally:
            if os.path.exists(tmp_cache):
                os.remove(tmp_cache)

        resolved = [r for r in results if r["ducats"] > 0]
        placeholders = [r for r in results if r["ducats"] == 0]
        print(f"\n=== {fname} ===")
        print(f"  slots {len(results)} (resolved {len(resolved)}, "
              f"placeholders {len(placeholders)}), skipped {skipped}")
        for r in results:
            print(f"    [{r['source']:10}] {r['name']} -> {r['ducats']} ducats")
        for u in unresolved:
            print(f"    [UNRESOLVED] assembled={u['assembled']!r}  normalized={u['normalized']!r}")

        exp = EXPECTATIONS.get(fname)
        if not exp:
            print("  (no expectations defined — informational only)")
            continue

        resolved_set = {r["name"] for r in resolved}
        missing = exp["expected"] - resolved_set
        if len(resolved) < exp["min_resolved"]:
            failures.append(
                f"{fname}: resolved {len(resolved)} < expected min {exp['min_resolved']}"
            )
        if missing:
            failures.append(f"{fname}: missing expected items {sorted(missing)}")
        if len(placeholders) != exp["placeholders"]:
            failures.append(
                f"{fname}: {len(placeholders)} placeholders, expected {exp['placeholders']}"
            )

        # Resolved values must be valid ducat tiers; placeholders are exactly 0.
        bad = [r for r in resolved if r["ducats"] not in (15, 25, 45, 65, 100)]
        if bad:
            failures.append(f"{fname}: non-tier ducat values {bad}")

        # Resolved entries should carry an image filename that exists on disk
        # (lenient: a resolved item missing from the bundled index is informational,
        # not a failure, since the index can lag a @wfcd/items update).
        missing_images = [
            r["name"] for r in resolved
            if r.get("image") and not os.path.exists(
                os.path.join(_BASE_DIR, "assets", "item_images", r["image"])
            )
        ]
        if missing_images:
            failures.append(f"{fname}: image file missing for {missing_images}")
        no_image = [r["name"] for r in resolved if not r.get("image")]
        if no_image:
            print(f"  (no image mapping for: {no_image})")

    print()
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("PASS: all expectations met")


if __name__ == "__main__":
    main()
