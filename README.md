# Warframe Ducat / Platinum Trade Calculator

A small desktop app for tracking Warframe Prime Junk trades. Click ducat-value buttons to build a trade, see the platinum value in real time, log completed trades, and watch your lifetime totals update automatically.

## Features

- **Ducat value buttons** — click to add items (15 / 25 / 45 / 65 / 100 ducats) to the current trade, up to 6 items
- **Current Trade panel** — live item count, total ducats, and total platinum for the active trade
- **Lifetime Totals panel** — cumulative ducats and platinum across all logged trades, plus average ducats per platinum (rounded to the nearest tenth)
- **Log Trade** — appends the current trade's totals and a timestamp to `data/trades.json`, then resets the trade
- **Reset Trade Total** — clears all records in `trades.json` behind a confirmation dialog
- **Export to Spreadsheet** — appends all not-yet-exported trades to a configured Google Sheet (optional; requires setup); the button label shows the pending count, e.g. `Export to Spreadsheet (3)`
- **OCR Trade Scanner** — press a global hotkey to read the in-game trade window via screen OCR and auto-fill the current trade with the detected items' ducat values (optional; requires setup — see section below)
- **Copy WTB Message** — copies a formatted "WTB Prime Junk" message to the clipboard
- **Settings** — configure the platinum price for each ducat tier and the OCR hotkey; values are persisted to `configs/config.json`
- **Keyboard shortcuts** — `Ctrl+Z` to undo the last item, `Enter` to log the current trade

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

## Build / Install (Windows executable)

For users who don't want to set up Python, the app can be packaged as a standalone
Windows executable via [PyInstaller](https://pyinstaller.org/).

### Building

1. **Install dependencies:**
   ```
   pip install -r requirements.txt -r requirements-build.txt
   ```
   `requirements.txt` is optional but recommended — any library missing at build time is
   silently left out of the bundle (the build script warns about this). Node.js is only
   needed to refresh the pre-warmed ducat cache (`assets/seed/ducat_lookup.json`); without
   it the build reuses the existing committed seed. Tesseract is a runtime-only OCR
   dependency and isn't needed to build.
2. **Run the build script:**
   ```
   .\build.ps1
   ```
   This validates the environment, refreshes the seed cache (if Node is available), cleans
   previous output, runs PyInstaller against the committed `WarframeDucatCalculator.spec`,
   and zips the result. Re-run it after any feature change — output always lands at
   `dist/WarframeDucatCalculator/` plus a versioned zip (`dist/WarframeDucatCalculator-<version>.zip`).

### Installing (end users)

1. Unzip `WarframeDucatCalculator-<version>.zip` to a **stable location** — `configs/` and
   `data/` are created beside the exe and persist there across runs, so don't unzip to a
   temp folder you'll delete.
2. Run `WarframeDucatCalculator.exe`. No Python install required.
3. For Google Sheets export, copy `api_config.example.json` (shipped beside the exe) to
   `configs/api_config.json` and fill in your values — see the Google Sheets Export section
   below.
4. For the OCR Trade Scanner, install the Tesseract-OCR binary (see the OCR section below);
   the ducat-value cache ships pre-warmed, so no Node.js install is needed at runtime.

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
the screen, locates the six **receiving** slots (the bottom panel — the other trader's
offer), reads each item's on-screen name label via OCR, resolves the name to a ducat value,
and fills the current trade (up to the 6-item limit). The Current Trade totals and platinum
value update through the app's normal display logic — no manual button clicking. Slots whose
name can't be resolved to a ducat value (an unreadable label, or a non-ducat item such as an
Arcane) are added as a **0-ducat placeholder** so every slot is still represented.

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
   items are added as 0-ducat placeholders with a hint in the status bar.

   To pre-populate the **entire** cache up front (every tradable prime part) instead of
   letting it warm over many scans, run the generator once after installing the Node deps:
   ```
   cd scripts && npm run generate
   ```
   This overwrites `data/ducat_lookup.json` with the full dataset, so afterward scans resolve
   instantly and offline without per-item `@wfcd/items` lookups.

### Usage

1. Open the trade window in Warframe with items in the slots.
2. Press the OCR hotkey (default **`<F8>`**).
3. The detected items are added to the current trade, and the status bar reports the
   result — how many items were added, how many were newly fetched from `@wfcd/items`, and
   how many were added as 0-ducat placeholders. The summary stays in the status bar until you
   clear the trade (Reset, Log Trade, or undoing back to empty).

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

- **Long names that wrap onto a second line** (e.g. *Equinox Prime Chassis Blueprint*) have
  smaller, condensed glyphs that are harder for OCR. These are usually handled now — each slot
  is read in isolation and names are resolved by token, absorbing a misread word like
  *Prime* → *Print* — but a badly garbled label can still slip through.
- **This is a resolution/OCR issue, not a text-color issue.** Changing the in-game item-name
  text color does **not** help — measured label contrast is already good (the items that fail
  often have *higher* contrast than ones that succeed), and a lower-contrast color makes
  things worse. What actually helps: capture at your native resolution, keep the trade window
  fully visible and unobstructed, and use a **larger UI / interface scale** so the text is
  physically bigger.
- **Unresolved items become 0-ducat placeholders** (and are noted in the status bar). If one
  should carry a ducat value, undo it and add it manually with the ducat-value buttons.

### Safety

The scanner is **OCR-only**: it reads screen pixels and nothing more. It never reads game
memory, injects into the game process, or automates clicks/trades. This read-only boundary
is what keeps it in the same low-risk category as tools like AlecaFrame / WFInfo.
