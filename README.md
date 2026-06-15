# Warframe Ducat / Platinum Trade Calculator

A small desktop app for tracking Warframe Prime Junk trades. Click ducat-value buttons to build a trade, see the platinum value in real time, log completed trades, and watch your lifetime totals update automatically.

## Features

- **Ducat value buttons** — click to add items (15 / 25 / 45 / 65 / 100 ducats) to the current trade, up to 6 items
- **Current Trade panel** — live item count, total ducats, and total platinum for the active trade
- **Lifetime Totals panel** — cumulative ducats and platinum across all logged trades, plus average ducats per platinum (rounded to the nearest tenth)
- **Log Trade** — appends the current trade's totals and a timestamp to `data/trades.json`, then resets the trade
- **Reset Trade Total** — clears all records in `trades.json` behind a confirmation dialog
- **Copy WTB Message** — copies a formatted "WTB Prime Junk" message to the clipboard
- **Settings** — configure the platinum price for each ducat tier; values are persisted to `config.json`

## Requirements

- Python 3.x (tested with 3.13)
- No external dependencies — uses the Python standard library (`tkinter`) only

## Running

```
python main.py
```

## Configuration

Platinum prices per ducat tier are stored in `config.json` in the project root. The file is created automatically with defaults on first run and can be edited via the **Settings** dialog in the app.

Trade history is stored in `data/trades.json` (created automatically, not committed to the repo).
