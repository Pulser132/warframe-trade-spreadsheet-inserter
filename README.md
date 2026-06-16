# Warframe Ducat / Platinum Trade Calculator

A small desktop app for tracking Warframe Prime Junk trades. Click ducat-value buttons to build a trade, see the platinum value in real time, log completed trades, and watch your lifetime totals update automatically.

## Features

- **Ducat value buttons** — click to add items (15 / 25 / 45 / 65 / 100 ducats) to the current trade, up to 6 items
- **Current Trade panel** — live item count, total ducats, and total platinum for the active trade
- **Lifetime Totals panel** — cumulative ducats and platinum across all logged trades, plus average ducats per platinum (rounded to the nearest tenth)
- **Log Trade** — appends the current trade's totals and a timestamp to `data/trades.json`, then resets the trade
- **Reset Trade Total** — clears all records in `trades.json` behind a confirmation dialog
- **Export to Spreadsheet** — appends all not-yet-exported trades to a configured Google Sheet (optional; requires setup)
- **OCR Trade Scanner** — press a global hotkey to read the in-game trade window via screen OCR and auto-fill the current trade with the detected items' ducat values (optional; requires setup — see section below)
- **Copy WTB Message** — copies a formatted "WTB Prime Junk" message to the clipboard
- **Settings** — configure the platinum price for each ducat tier and the OCR hotkey; values are persisted to `configs/config.json`

## Requirements

- Python 3.x (tested with 3.13)
- Core app: no external dependencies — uses the Python standard library (`tkinter`) only
- Google Sheets export (optional): see setup section below
- OCR Trade Scanner (optional): Python OCR libraries + the Tesseract-OCR binary, plus
  Node.js / `@wfcd/items` for ducat lookups — see the OCR Trade Scanner section below

## Running

```
python main.py
```

The app launches normally even if the Google Sheets libraries aren't installed or `configs/api_config.json` doesn't exist.

## Configuration

Platinum prices per ducat tier are stored in `configs/config.json`. The file is created automatically with defaults on first run and can be edited via the **Settings** dialog in the app.

Trade history is stored in `data/trades.json` (created automatically, not committed to the repo).

## Google Sheets Export (optional)

The **Export to Spreadsheet** button appends any not-yet-exported trades to a Google Sheet you own. Each user supplies their own credentials — nothing is shared or committed to the repo.

### Setup

1. **Create a GCP project** and enable the **Google Sheets API** for it.
2. **Create a service account** in that project and download its JSON key file.
3. **Share your target Google Sheet** with the service account's email address (give it Editor access).
4. **Copy the example config** and fill in your values:
   ```
   cp api_config.example.json configs/api_config.json
   ```
   Edit `configs/api_config.json`:
   ```json
   {
     "spreadsheet_id": "your-sheet-id-from-the-url",
     "service_account_file": "configs/your-service-account-key.json"
   }
   ```
   Place the downloaded key JSON file at the path you specified (e.g. `configs/your-service-account-key.json`).
5. **Install the dependencies:**
   ```
   pip install -r requirements.txt
   ```

The `configs/` directory is gitignored, so your credentials are never committed.

## OCR Trade Scanner (optional)

Press a configurable global hotkey while the in-game trade window is open. The app captures
the screen, reads each item's on-screen name label via OCR, resolves the name to a ducat
value, and fills the current trade (up to the 6-item limit). The Current Trade totals and
platinum value update through the app's normal display logic — no manual button clicking.

### Setup

1. **Install the OCR dependencies:**
   ```
   pip install -r requirements.txt
   ```
   This installs `Pillow`, `opencv-python`, `pytesseract`, and `pynput` (the global-hotkey
   library) alongside the Google Sheets libraries.
2. **Install the Tesseract-OCR binary** (the OCR engine itself, separate from the Python
   wrapper). On Windows, use the UB-Mannheim build:
   <https://github.com/UB-Mannheim/tesseract/wiki>. The app finds it automatically if it's on
   your `PATH` or installed to a common location (e.g. `%LOCALAPPDATA%\Programs\Tesseract-OCR`).
3. **Enable ducat lookups (recommended).** Ducat values are read from a local cache,
   `data/ducat_lookup.json`, which is lazily populated from the [`@wfcd/items`](https://www.npmjs.com/package/@wfcd/items)
   dataset. To let the scanner fetch values for items it hasn't seen yet, install the
   helper's Node dependencies:
   ```
   cd scripts && npm install
   ```
   This requires [Node.js](https://nodejs.org/). The cache is self-warming: each newly
   resolved item is appended to `data/ducat_lookup.json`, so `@wfcd/items` is consulted less
   over time. Without Node installed, items already in the cache still resolve, and unknown
   items are simply skipped with a hint in the status bar.

### Usage

1. Open the trade window in Warframe with items in the slots.
2. Press the OCR hotkey (default **`<F8>`**).
3. The detected items are added to the current trade, and the status bar reports the
   result — how many items were added, how many were newly fetched from `@wfcd/items`, and
   how many could not be resolved.

The hotkey is configurable in the **Settings** dialog ("OCR Hotkey"), or directly in
`configs/config.json` via the `"ocr_hotkey"` field. Use angle-bracket syntax, e.g. `<F8>` or
`<ctrl>+<F8>`.

### Testing offline

You can exercise the full scan → OCR → resolve pipeline against saved screenshots (no game
required) by placing images in an `OCR Test Images/` folder and running:
```
python tests/ocr_offline_test.py
```
It skips cleanly if the OCR dependencies, Tesseract, the `@wfcd/items` resolver, or images
aren't available.

### Limitations & tips

OCR is best-effort — item names are read from the small on-screen text labels, and not every
read is perfect:

- **Long names that wrap onto a second line** (e.g. *Equinox Prime Chassis Blueprint*) may be
  misread or skipped, because their smaller, condensed glyphs are harder for OCR. The app
  fuzzy-matches names to absorb minor misreads, but not all of them.
- **This is a resolution/OCR issue, not a text-color issue.** Changing the in-game item-name
  text color does **not** help — measured label contrast is already good (the items that fail
  often have *higher* contrast than ones that succeed), and a lower-contrast color makes
  things worse. What actually helps: capture at your native resolution, keep the trade window
  fully visible and unobstructed, and use a **larger UI / interface scale** so the text is
  physically bigger.
- **Unresolved items are skipped** (and noted in the status bar). Just add them manually with
  the ducat-value buttons.

### Safety

The scanner is **OCR-only**: it reads screen pixels and nothing more. It never reads game
memory, injects into the game process, or automates clicks/trades. This read-only boundary
is what keeps it in the same low-risk category as tools like AlecaFrame / WFInfo.
