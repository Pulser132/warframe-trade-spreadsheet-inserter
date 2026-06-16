"""Google Sheets export logic — imported lazily when the export button is clicked."""


def export_trades(trades, api_config):
    """Append unexported trades to the configured Google Sheet.

    Returns the list of trade dicts with 'exported' set to True on success.
    Raises RuntimeError with a user-friendly message on any failure.
    """
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Google API libraries are not installed.\n"
            "Run: pip install -r requirements.txt"
        )

    spreadsheet_id = api_config.get("spreadsheet_id", "").strip()
    service_account_file = api_config.get("service_account_file", "").strip()

    if not spreadsheet_id:
        raise RuntimeError("'spreadsheet_id' is missing or empty in configs/api_config.json.")
    if not service_account_file:
        raise RuntimeError("'service_account_file' is missing or empty in configs/api_config.json.")

    try:
        creds = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    except FileNotFoundError:
        raise RuntimeError(
            f"Service account key file not found: {service_account_file}\n"
            "Check the path in configs/api_config.json."
        )
    except Exception as e:
        raise RuntimeError(f"Failed to load service account credentials:\n{e}")

    try:
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        rows = [
            [t["timestamp"], t["total_ducats"], t["total_platinum"]]
            for t in trades
        ]

        sheet.values().append(
            spreadsheetId=spreadsheet_id,
            range="A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()
    except Exception as e:
        raise RuntimeError(f"Google Sheets API error:\n{e}")

    for t in trades:
        t["exported"] = True
    return trades
