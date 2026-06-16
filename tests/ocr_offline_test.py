"""Offline test for the OCR trade scanner.

Runs ocr_scanner.scan() against saved trade-window screenshots in
"OCR Test Images/" instead of a live screen grab, so the detection → OCR →
cache/@wfcd/items resolution pipeline can be exercised without the game running.

Run it directly:

    python tests/ocr_offline_test.py

Requirements: the optional OCR deps (Pillow, opencv-python, pytesseract) plus the
Tesseract binary, and — to resolve names not already cached — Node with
@wfcd/items installed (cd scripts && npm install). If the deps or images are
missing the test SKIPS (exit 0) rather than failing, so it's safe in CI.

Each run uses a throwaway cache file, so your real data/ducat_lookup.json is left
untouched.
"""

import os
import sys
import tempfile

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE_DIR)

IMAGES_DIR = os.path.join(_BASE_DIR, "OCR Test Images")

# Known items in each screenshot, by resolved canonical (normalized) name.
# Resolved names are stable (the resolver returns the @wfcd/items canonical form),
# even though the raw OCR text varies — so assert on these, not on OCR output.
EXPECTATIONS = {
    "chrome_3IXJzCdSqV.jpg": {
        "expected": {
            "stradavar prime blueprint",
            "zakti prime blueprint",
            "alternox prime barrel",
            "braton prime receiver",
            "knell prime receiver",
            # "equinox prime chassis blueprint" is intentionally omitted: its
            # label is not legibly OCR-able in this compressed capture.
        },
        "min_resolved": 5,
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

    failures = []
    for fname in images:
        path = os.path.join(IMAGES_DIR, fname)
        # Throwaway cache so the real data/ducat_lookup.json isn't modified.
        tmp_cache = os.path.join(tempfile.gettempdir(), f"ocr_test_cache_{fname}.json")
        if os.path.exists(tmp_cache):
            os.remove(tmp_cache)

        try:
            results, skipped, resolver_unavailable, unresolved = ocr_scanner.scan(
                lookup_path=tmp_cache, image=path
            )
        except RuntimeError as e:
            # Hard failure usually means missing OCR deps / Tesseract binary.
            _skip(f"{fname}: scan raised RuntimeError — {e}")
        finally:
            if os.path.exists(tmp_cache):
                os.remove(tmp_cache)

        resolved_names = sorted(r["name"] for r in results)
        print(f"\n=== {fname} ===")
        print(f"  resolved {len(results)}, skipped {skipped}, "
              f"resolver_unavailable={resolver_unavailable}")
        for r in results:
            print(f"    [{r['source']:7}] {r['name']} -> {r['ducats']} ducats")
        for u in unresolved:
            print(f"    [UNRESOLVED] assembled={u['assembled']!r}  normalized={u['normalized']!r}")

        exp = EXPECTATIONS.get(fname)
        if not exp:
            print("  (no expectations defined — informational only)")
            continue

        if resolver_unavailable and not results:
            _skip(f"{fname}: @wfcd/items resolver unavailable "
                  "(cd scripts && npm install) — cannot validate")

        resolved_set = set(resolved_names)
        missing = exp["expected"] - resolved_set
        if len(results) < exp["min_resolved"]:
            failures.append(
                f"{fname}: resolved {len(results)} < expected min {exp['min_resolved']}"
            )
        if missing:
            failures.append(f"{fname}: missing expected items {sorted(missing)}")

        # All resolved values must be valid ducat tiers.
        bad = [r for r in results if r["ducats"] not in (15, 25, 45, 65, 100)]
        if bad:
            failures.append(f"{fname}: non-tier ducat values {bad}")

    print()
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("PASS: all expectations met")


if __name__ == "__main__":
    main()
