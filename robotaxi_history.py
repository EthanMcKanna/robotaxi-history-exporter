#!/usr/bin/env python3
"""
Robotaxi Ride History Exporter

Authenticates with Tesla API and exports Robotaxi ride history to CSV.

Usage:
  Step 1: Run without args to get auth URL
          python robotaxi_history.py

  Step 2: Run with callback URL to complete auth and fetch history
          python robotaxi_history.py "https://auth.tesla.com/void/callback?code=..."
"""

import csv
import hashlib
import base64
import secrets
import json
import sys
import os
import webbrowser
from datetime import datetime
from urllib.parse import urlencode, urlparse, parse_qs

try:
    import requests
except ImportError:
    print("Error: 'requests' library required. Install with: pip install requests")
    sys.exit(1)


# Tesla OAuth2 Configuration
AUTH_BASE_URL = "https://auth.tesla.com/oauth2/v3"
CLIENT_ID = "ownerapi"
REDIRECT_URI = "https://auth.tesla.com/void/callback"
SCOPES = "openid email offline_access phone"

# API endpoints (base_url, endpoint pairs)
API_ENDPOINTS = [
    ("https://ownership.tesla.com", "/mobile-app/ride/history"),
    ("https://akamai-apigateway-charging-ownership.tesla.com", "/mobile-app/ride/history"),
]

PAGE_SIZE = 100

# Config files stored in home directory
PKCE_FILE = os.path.expanduser("~/.robotaxi_pkce.json")
TOKENS_FILE = os.path.expanduser("~/.robotaxi_tokens.json")


def generate_pkce_pair():
    """Generate PKCE code verifier and challenge."""
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip('=')
    return code_verifier, code_challenge


def save_pkce(code_verifier):
    """Save PKCE verifier for later use."""
    with open(PKCE_FILE, 'w') as f:
        json.dump({"code_verifier": code_verifier}, f)


def load_pkce():
    """Load PKCE verifier."""
    try:
        with open(PKCE_FILE, 'r') as f:
            data = json.load(f)
            return data.get('code_verifier')
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def clear_pkce():
    """Remove PKCE file after use."""
    try:
        os.remove(PKCE_FILE)
    except FileNotFoundError:
        pass


def start_auth():
    """Start OAuth flow - generate URL and save PKCE verifier."""
    code_verifier, code_challenge = generate_pkce_pair()
    save_pkce(code_verifier)

    auth_params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": secrets.token_urlsafe(16),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    auth_url = f"{AUTH_BASE_URL}/authorize?{urlencode(auth_params)}"

    print("\n" + "=" * 60)
    print("STEP 1: AUTHENTICATE")
    print("=" * 60)
    print("\nOpening browser to Tesla login...")
    print("\nIf browser doesn't open, visit this URL:\n")
    print(auth_url)
    print("\n" + "-" * 60)
    print("\nAfter logging in, you'll be redirected to a blank page.")
    print("Copy the FULL URL from your browser's address bar and run:")
    print('\n  python robotaxi_history.py "PASTE_CALLBACK_URL_HERE"')
    print("\n" + "=" * 60)

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass


def complete_auth(callback_url):
    """Complete OAuth flow with callback URL."""
    code_verifier = load_pkce()
    if not code_verifier:
        print("Error: No pending authentication. Run without arguments first.")
        sys.exit(1)

    parsed = urlparse(callback_url)
    params = parse_qs(parsed.query)

    if 'code' not in params:
        print("Error: No authorization code found in URL")
        sys.exit(1)

    auth_code = params['code'][0]

    token_url = f"{AUTH_BASE_URL}/token"
    token_data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": auth_code,
        "code_verifier": code_verifier,
        "redirect_uri": REDIRECT_URI,
    }

    print("Exchanging authorization code for access token...")

    response = requests.post(token_url, data=token_data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
    })

    clear_pkce()

    if response.status_code != 200:
        print(f"Error getting token: {response.status_code}")
        print(response.text)
        sys.exit(1)

    tokens = response.json()
    print("Authentication successful!")

    return tokens.get('access_token'), tokens.get('refresh_token')


def authenticate_with_refresh_token(refresh_token):
    """Get new access token using refresh token."""
    token_url = f"{AUTH_BASE_URL}/token"
    token_data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }

    response = requests.post(token_url, data=token_data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
    })

    if response.status_code != 200:
        return None, None

    tokens = response.json()
    return tokens.get('access_token'), tokens.get('refresh_token')


def get_ride_history(access_token, page=1, working_endpoint=None):
    """Fetch ride history from Tesla API."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Accept-Language": "en-US",
        "charset": "utf-8",
        "cache-control": "no-cache",
        "X-Tesla-User-Agent": "TeslaApp/4.36.5-2659/abc123/ios/18.0",
    }

    params = {
        "pageNo": page,
        "deviceLanguage": "en",
        "deviceCountry": "US",
        "ttpLocale": "en_US",
    }

    if working_endpoint:
        base_url, endpoint = working_endpoint
        url = f"{base_url}{endpoint}"
        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 401:
            print("Error: Authentication expired or invalid")
            return None, None
        elif response.status_code != 200:
            print(f"Error: {response.status_code}")
            return None, None

        return response.json(), working_endpoint

    for base_url, endpoint in API_ENDPOINTS:
        url = f"{base_url}{endpoint}"
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                return response.json(), (base_url, endpoint)
        except requests.exceptions.RequestException:
            continue

    print("Error: No working API endpoint found")
    return None, None


def fetch_all_rides(access_token):
    """Fetch all ride history pages."""
    all_rides = []
    page = 1
    working_endpoint = None

    print("\nFetching ride history...")

    while True:
        print(f"  Page {page}...", end=" ", flush=True)
        data, working_endpoint = get_ride_history(access_token, page, working_endpoint)

        if data is None:
            break

        # Handle response format: {"code":200,"data":{"rides":[...]}}
        if isinstance(data, dict) and 'data' in data and isinstance(data['data'], dict):
            rides = data['data'].get('rides', [])
        elif isinstance(data, dict):
            rides = data.get('rides', data.get('data', []))
        else:
            rides = data if isinstance(data, list) else []

        if not rides:
            print("done")
            break

        print(f"{len(rides)} rides")
        all_rides.extend(rides)

        if len(rides) < PAGE_SIZE:
            break

        page += 1

    return all_rides


def format_duration(seconds):
    """Format duration in seconds to human-readable string."""
    if seconds is None:
        return ""
    try:
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    except (ValueError, TypeError):
        return str(seconds)


def format_timestamp(ts):
    """Format ISO timestamp to readable format."""
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(ts)


def export_to_csv(rides, filename):
    """Export rides to CSV file with all available fields."""
    if not rides:
        print("No rides to export")
        return

    # All fields from the API response
    fieldnames = [
        "rideIntegerId",
        "rideId",
        "state",
        "status",
        "rideRequestedAt",
        "rideStartedAt",
        "rideCompletedAt",
        "timestamp",
        "pickupLocationName",
        "pickupLocationLatitude",
        "pickupLocationLongitude",
        "pickupLocationTimezone",
        "dropoffLocationName",
        "dropoffLocationLatitude",
        "dropoffLocationLongitude",
        "dropoffLocationTimezone",
        "dropoffLocationAddressId",
        "totalDistanceMiles",
        "driveDistanceMiles",
        "billedDistanceMiles",
        "totalDurationSeconds",
        "driveDurationSeconds",
        "totalDue",
        "totalDueTaxExcl",
        "estimatedPrice",
        "estimatedPriceCurrencyCode",
        "currencyCode",
        "rideFeeStatus",
        "rideFeeProcessFlag",
        "hasAdhocFee",
        "vin",
        "licensePlate",
        "vehicleModel",
        "countryCode",
        "priceBookGuid",
        "quoteId",
        "txid",
        "route",
        "routeImageUrl",
        "rideEta",
        "fleetCongestionPercent",
        "isValid",
        "invalidReason",
        "billOverrideReason",
        "disputeReason",
        "disputeComment",
        "billingUserId",
        "billingUserUuid",
        "billingUserAddressId",
        "riderSsoId",
    ]

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()

        for ride in rides:
            # Write all fields directly from the API response
            row = {field: ride.get(field, '') for field in fieldnames}
            writer.writerow(row)

    print(f"Exported {len(rides)} rides to {filename}")


def save_tokens(access_token, refresh_token):
    """Save tokens to file for reuse."""
    with open(TOKENS_FILE, 'w') as f:
        json.dump({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "saved_at": datetime.now().isoformat()
        }, f)


def load_tokens():
    """Load tokens from file."""
    try:
        with open(TOKENS_FILE, 'r') as f:
            data = json.load(f)
            return data.get('access_token'), data.get('refresh_token')
    except (FileNotFoundError, json.JSONDecodeError):
        return None, None


def fetch_and_export(access_token, refresh_token):
    """Fetch ride history and export to CSV."""
    rides = fetch_all_rides(access_token)

    if rides:
        print(f"\nTotal rides: {len(rides)}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"robotaxi_history_{timestamp}.csv"
        json_filename = f"robotaxi_history_{timestamp}.json"

        export_to_csv(rides, csv_filename)

        with open(json_filename, 'w') as f:
            json.dump(rides, f, indent=2)
        print(f"Raw JSON saved to {json_filename}")
    else:
        print("\nNo ride history found.")


def main():
    print("=" * 60)
    print("ROBOTAXI RIDE HISTORY EXPORTER")
    print("=" * 60)

    callback_url = sys.argv[1] if len(sys.argv) > 1 else None

    access_token, refresh_token = load_tokens()

    if access_token and refresh_token and not callback_url:
        print("\nRefreshing authentication...")
        new_access, new_refresh = authenticate_with_refresh_token(refresh_token)
        if new_access:
            access_token = new_access
            refresh_token = new_refresh or refresh_token
            print("Authenticated!")
            save_tokens(access_token, refresh_token)
            fetch_and_export(access_token, refresh_token)
            return
        else:
            print("Session expired, need to re-authenticate")

    if callback_url:
        access_token, refresh_token = complete_auth(callback_url)
        if refresh_token:
            save_tokens(access_token, refresh_token)
        fetch_and_export(access_token, refresh_token)
        return

    start_auth()


if __name__ == "__main__":
    main()
