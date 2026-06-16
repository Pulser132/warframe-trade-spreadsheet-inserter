"""Diagnostic: dump every word Tesseract sees in the test image, with confidence.

Run: python tests/ocr_diag.py
"""
import os, re, sys
import cv2, numpy as np
from PIL import Image
import pytesseract
from pytesseract import Output

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import ocr_scanner

ocr_scanner._configure_tesseract(pytesseract)

IMG = os.path.join(BASE, "OCR Test Images", "chrome_3IXJzCdSqV.jpg")
screenshot = Image.open(IMG).convert("RGB")
img_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

h, w = img_bgr.shape[:2]
scale = 2
gray = cv2.resize(
    cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY),
    (w * scale, h * scale),
    interpolation=cv2.INTER_CUBIC,
)
_, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

data = pytesseract.image_to_data(binary, config="--psm 11", output_type=Output.DICT)

rows = []
for i in range(len(data["text"])):
    t = data["text"][i].strip()
    if not t:
        continue
    try:
        conf = float(data["conf"][i])
    except (TypeError, ValueError):
        conf = -1.0
    cx = data["left"][i] + data["width"][i] / 2
    cy = data["top"][i] + data["height"][i] / 2
    rows.append((cy, cx, conf, t))

rows.sort()

CONF_THRESHOLD = 45

print(f"{'CY':>6}  {'CX':>6}  {'CONF':>6}  {'FLAG':<6}  TEXT")
print("-" * 60)
for cy, cx, conf, t in rows:
    norm_t = t.lower().strip(".,;:!")
    flag = ""
    if norm_t == "prime":
        flag = "ANCHOR"
    elif conf < CONF_THRESHOLD:
        flag = "LOW"
    print(f"{cy:6.0f}  {cx:6.0f}  {conf:6.1f}  {flag:<6}  {t!r}")

# Also show final assembled names from the scanner
print()
print("=== _extract_item_names output ===")
names = ocr_scanner._extract_item_names(img_bgr, pytesseract)
for name in names:
    print(f"  {name!r}")
