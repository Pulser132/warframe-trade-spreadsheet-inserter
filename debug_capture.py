"""Write and prune the on-disk OCR debug bundle.

Each capture is a self-describing folder under `paths.user_data_path("debug")`:
a full `screenshot.png`, per-slot `slot{i}_binary.png` (exactly what Tesseract
saw) and `slot{i}_crop.png` (the raw color crop), a machine-readable `scan.json`
(per-slot scores, margins, a top-level `problems` array, the thresholds in
effect), and a human/Claude-readable `summary.md`. `debug/latest/` always mirrors
the newest capture so a fixed path points at it. The newest 50 captures are kept.

Pillow (an existing OCR dependency) does the PNG writes; this module is only ever
reached from the already lazy-imported OCR debug path, so it adds no always-on
dependency. A read-only target directory surfaces a friendly RuntimeError the
caller shows in the status bar — never a crash.
"""

import json
import os
import shutil
from datetime import datetime

from paths import user_data_path

# A slot is "worth looking at" when its winning score is within this margin of
# the active threshold (it barely cleared / barely missed) or of the top
# runner-up (an ambiguous near-tie). Unresolved slots are always flagged.
PROBLEM_MARGIN = 0.05

_DEBUG_DIR = user_data_path("debug")
_LATEST_DIRNAME = "latest"


def _save_gray(ndarray, path):
    """Save a single-channel (grayscale) ndarray as a PNG via Pillow."""
    from PIL import Image

    Image.fromarray(ndarray).save(path)


def _save_bgr(ndarray, path):
    """Save a BGR (OpenCV) color ndarray as a PNG via Pillow (converted to RGB)."""
    from PIL import Image

    Image.fromarray(ndarray[:, :, ::-1]).save(path)


def _active_threshold(slot, thresholds):
    """The threshold the slot's winning pass was gated on (for the margin calc)."""
    resolved_by = slot.get("resolved_by")
    if resolved_by == "pass1":
        return thresholds.get("pass1_cutoff", 0.75)
    # pass2 and unresolved are both measured against the Pass 2 whole-string gate.
    return thresholds.get("pass2_whole", 0.85)


def _runner_up(slot):
    """The best candidate score that isn't the winning candidate.

    The winner is the resolved entry's name (for resolved slots) or the top
    candidate (for unresolved slots). Returns (runner_up_norm, runner_up_score).
    """
    candidates = slot.get("candidates") or []
    result = slot.get("result") or {}
    if slot.get("resolved_by") in ("pass1", "pass2"):
        winner_norm = result.get("name")
    else:
        winner_norm = candidates[0]["norm"] if candidates else None

    best_norm, best_score = None, 0.0
    for c in candidates:
        if c["norm"] == winner_norm:
            continue
        if c["score"] > best_score:
            best_norm, best_score = c["norm"], c["score"]
    return best_norm, best_score


def _slot_margins(slot, thresholds):
    """Return the slot's margin dict: winner − active threshold, winner − runner-up."""
    winner = slot.get("score", 0.0)
    active = _active_threshold(slot, thresholds)
    runner_norm, runner_score = _runner_up(slot)
    return {
        "winner_score": winner,
        "active_threshold": active,
        "threshold": round(winner - active, 4),
        "runner_up": runner_norm,
        "runner_up_score": runner_score,
        "runner": round(winner - runner_score, 4),
    }


def _slot_problem(slot, margin):
    """Return a short reason string if the slot is a problem, else None."""
    if slot.get("resolved_by") == "unresolved":
        return "unresolved — no candidate cleared the thresholds"
    reasons = []
    if margin["threshold"] < PROBLEM_MARGIN:
        reasons.append(
            f"thin margin to threshold ({margin['winner_score']:.3f} vs "
            f"{margin['active_threshold']:.3f})"
        )
    if margin["runner"] < PROBLEM_MARGIN:
        reasons.append(
            f"near-tie with runner-up '{margin['runner_up']}' "
            f"({margin['runner_up_score']:.3f})"
        )
    return "; ".join(reasons) if reasons else None


def _unique_dir(base, name):
    """Return a non-existing path under base, appending _2, _3… on collision."""
    path = os.path.join(base, name)
    if not os.path.exists(path):
        return path
    n = 2
    while os.path.exists(f"{path}_{n}"):
        n += 1
    return f"{path}_{n}"


def write_capture(debug_payload, thresholds):
    """Write a timestamped debug bundle and refresh `debug/latest/`; prune to 50.

    Returns the written folder path. Raises RuntimeError with a friendly message
    if the debug directory can't be created/written (e.g. a read-only install).
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    folder_name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    try:
        os.makedirs(_DEBUG_DIR, exist_ok=True)
        folder = _unique_dir(_DEBUG_DIR, folder_name)
        os.makedirs(folder)
    except OSError as e:
        raise RuntimeError(f"Couldn't create the debug capture folder:\n{e}")

    slots = debug_payload.get("slots", [])

    try:
        screenshot = debug_payload.get("screenshot")
        if screenshot is not None:
            screenshot.save(os.path.join(folder, "screenshot.png"))

        problems = []
        json_slots = []
        for slot in slots:
            i = slot.get("index", len(json_slots))
            binary_name = f"slot{i}_binary.png"
            crop_name = f"slot{i}_crop.png"
            if slot.get("binary") is not None:
                _save_gray(slot["binary"], os.path.join(folder, binary_name))
            if slot.get("crop") is not None:
                _save_bgr(slot["crop"], os.path.join(folder, crop_name))

            margin = _slot_margins(slot, thresholds)
            reason = _slot_problem(slot, margin)
            if reason:
                problems.append({"slot": i, "reason": reason, "binary": binary_name})

            json_slots.append({
                "index": i,
                "bbox": list(slot["bbox"]) if slot.get("bbox") else None,
                "binary": binary_name if slot.get("binary") is not None else None,
                "crop": crop_name if slot.get("crop") is not None else None,
                "raw": slot.get("raw", ""),
                "cleaned": slot.get("cleaned", ""),
                "normalized": slot.get("normalized", ""),
                "resolved_by": slot.get("resolved_by", "unresolved"),
                "result": slot.get("result"),
                "score": slot.get("score", 0.0),
                "candidates": slot.get("candidates", []),
                "margin": margin,
            })

        scan = {
            "timestamp": timestamp,
            "thresholds": thresholds,
            "note": debug_payload.get("note"),
            "problems": problems,
            "slots": json_slots,
        }
        with open(os.path.join(folder, "scan.json"), "w", encoding="utf-8") as f:
            json.dump(scan, f, indent=2)

        with open(os.path.join(folder, "summary.md"), "w", encoding="utf-8") as f:
            f.write(_render_summary(scan))

        _refresh_latest(folder)
    except OSError as e:
        raise RuntimeError(f"Couldn't write the debug capture:\n{e}")

    prune(keep=50)
    return folder


def _render_summary(scan):
    """Build the Claude-glanceable summary.md text from the scan dict."""
    lines = ["# OCR debug capture", "", f"- Timestamp: {scan['timestamp']}"]
    t = scan["thresholds"]
    lines.append(
        "- Thresholds: "
        f"pass1_cutoff={t.get('pass1_cutoff')}, pass1_anchor={t.get('pass1_anchor')}, "
        f"pass2_whole={t.get('pass2_whole')}, pass2_token={t.get('pass2_token')}"
    )
    if scan.get("note"):
        lines.append(f"- Note: {scan['note']}")
    lines.append("")

    lines.append("## Problems")
    if scan["problems"]:
        for p in scan["problems"]:
            lines.append(f"- **slot {p['slot']}** — {p['reason']} (open `{p['binary']}`)")
    else:
        lines.append("- None — every slot resolved with a comfortable margin.")
    lines.append("")

    lines.append("## Slots")
    lines.append("")
    lines.append("| slot | raw text | → resolved | pass | score | runner-up |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for s in scan["slots"]:
        result = s.get("result") or {}
        resolved = result.get("name", "") if s["resolved_by"] != "unresolved" else "(unresolved)"
        runner = s["margin"].get("runner_up") or "—"
        runner_score = s["margin"].get("runner_up_score", 0.0)
        raw = (s.get("raw", "") or "").replace("\n", " ").strip()
        lines.append(
            f"| {s['index']} | {raw} | {resolved} | {s['resolved_by']} | "
            f"{s['score']:.3f} | {runner} ({runner_score:.3f}) |"
        )
    lines.append("")
    return "\n".join(lines)


def _refresh_latest(folder):
    """Clear debug/latest/ and copy the just-written folder's files into it."""
    latest = os.path.join(_DEBUG_DIR, _LATEST_DIRNAME)
    if os.path.isdir(latest):
        shutil.rmtree(latest, ignore_errors=True)
    os.makedirs(latest, exist_ok=True)
    for name in os.listdir(folder):
        src = os.path.join(folder, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(latest, name))


def prune(keep=50):
    """Keep only the newest `keep` timestamped capture folders (excluding latest/)."""
    try:
        entries = os.listdir(_DEBUG_DIR)
    except OSError:
        return
    folders = [
        name for name in entries
        if name != _LATEST_DIRNAME and os.path.isdir(os.path.join(_DEBUG_DIR, name))
    ]
    folders.sort(reverse=True)  # timestamp-named → newest first
    for name in folders[keep:]:
        shutil.rmtree(os.path.join(_DEBUG_DIR, name), ignore_errors=True)
