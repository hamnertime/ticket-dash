import requests
import base64
import json
import os
import sys
import pprint

# --- Configuration ---
# These settings are reused from your original script.
TOKEN_FILE = "./token.txt"
FRESHSERVICE_DOMAIN = "integotecllc.freshservice.com"
BASE_URL = f"https://{FRESHSERVICE_DOMAIN}"

# --- Helper Function to Read API Key ---
def read_api_key(file_path):
    """Reads the API key from the specified file."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abs_file_path = os.path.join(script_dir, file_path)
        print(f"Attempting to read token from: {abs_file_path}")
        with open(abs_file_path, 'r') as f:
            api_key = f.read().strip()
            if not api_key:
                print(f"Error: Token file '{abs_file_path}' is empty.", file=sys.stderr)
                sys.exit(1)
            return api_key
    except FileNotFoundError:
        print(f"Error: Token file '{abs_file_path}' not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading token file '{abs_file_path}': {e}", file=sys.stderr)
        sys.exit(1)

# --- Main Execution ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_single_requester.py <REQUESTER_ID>")
        sys.exit(1)

    requester_id = sys.argv[1]
    print("🕵️  Freshservice Single Requester Debugger")
    print("============================================")
    print(f"Targeting Domain: {FRESHSERVICE_DOMAIN}")
    print(f"Attempting to fetch Requester ID: {requester_id}")

    API_KEY = read_api_key(TOKEN_FILE)
    print(f"Using API Key: {API_KEY[:4]}...{API_KEY[-4:] if len(API_KEY) > 8 else ''}")

    # --- API Request Setup ---
    auth_str = f"{API_KEY}:X"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_auth}"
    }

    # Endpoint for a single requester
    url = f"{BASE_URL}/api/v2/requesters/{requester_id}"
    print(f"Requesting URL: {url}")

    # --- Make the API Call ---
    try:
        response = requests.get(url, headers=headers, timeout=30)

        # Raise an exception for bad status codes (4xx or 5xx)
        response.raise_for_status()

        # If successful, print the JSON response
        print("\n✅ Success! Full requester details below:")
        print("--------------------------------------------")
        pprint.pprint(response.json())

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP Error: {e.response.status_code} {e.response.reason}", file=sys.stderr)
        if e.response.status_code == 404:
            print("This 'Not Found' error likely means the requester has been deleted or the ID is incorrect.", file=sys.stderr)
        print("\nResponse Body:", file=sys.stderr)
        print(e.response.text, file=sys.stderr)

    except requests.exceptions.RequestException as e:
        print(f"\n❌ A network or request error occurred: {e}", file=sys.stderr)

    print("\nScript finished.")
