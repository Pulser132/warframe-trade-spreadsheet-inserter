# Warframe Ducat / Platinum Trade Calculator

A small desktop app for tracking Warframe Prime Junk trades. Click ducat-value buttons to build a trade, see the platinum value in real time, log completed trades, and watch your lifetime totals update automatically.

## Features

- **Ducat value buttons** — click to add items (15 / 25 / 45 / 65 / 100 ducats) to the current trade, up to 6 items
- **Current Trade panel** — live item count, total ducats, and total platinum for the active trade
- **Lifetime Totals panel** — cumulative ducats and platinum across all logged trades, plus average ducats per platinum (rounded to the nearest tenth)
- **Log Trade** — appends the current trade's totals and a timestamp to `data/trades.json`, then resets the trade
- **Reset Trade Total** — clears all records in `trades.json` behind a confirmation dialog
- **Export to Spreadsheet** — appends all not-yet-exported trades to a configured Google Sheet (optional; requires setup)
- **Copy WTB Message** — copies a formatted "WTB Prime Junk" message to the clipboard
- **Settings** — configure the platinum price for each ducat tier; values are persisted to `configs/config.json`

## Requirements

- Python 3.x (tested with 3.13)
- Core app: no external dependencies — uses the Python standard library (`tkinter`) only
- Google Sheets export (optional): see setup section below

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
