# Robotaxi Ride History Exporter

Export your Tesla Robotaxi ride history to CSV and JSON.

## Requirements

- Python 3.7+
- Tesla account with Robotaxi ride history

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/robotaxi-history-exporter.git
cd robotaxi-history-exporter
pip install -r requirements.txt
```

## Usage

### Step 1: Start Authentication

```bash
python robotaxi_history.py
```

This opens your browser to Tesla's login page. Sign in with your Tesla account.

### Step 2: Complete Authentication

After logging in, you'll be redirected to a blank page. Copy the full URL from your browser's address bar (it starts with `https://auth.tesla.com/void/callback?code=...`).

Run the script again with the URL:

```bash
python robotaxi_history.py "https://auth.tesla.com/void/callback?code=..."
```

The script will fetch your ride history and export it to:
- `robotaxi_history_YYYYMMDD_HHMMSS.csv` - Spreadsheet format
- `robotaxi_history_YYYYMMDD_HHMMSS.json` - Raw API data

### Subsequent Runs

After initial authentication, just run:

```bash
python robotaxi_history.py
```

The script saves your refresh token and will automatically re-authenticate.

## Output Fields

| Field | Description |
|-------|-------------|
| ride_id | Unique ride identifier |
| started_at | Ride start timestamp |
| completed_at | Ride end timestamp |
| pickup_location | Pickup address |
| dropoff_location | Dropoff address |
| distance_miles | Trip distance |
| duration | Trip duration (seconds) |
| total_due | Amount charged |
| currency | Currency code (USD) |
| license_plate | Vehicle license plate |
| pickup_lat/lng | Pickup coordinates |
| dropoff_lat/lng | Dropoff coordinates |

## Token Storage

Authentication tokens are stored in:
- `~/.robotaxi_tokens.json`

To log out or switch accounts, delete this file.

## License

MIT
