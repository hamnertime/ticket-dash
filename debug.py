import requests
import base64
import json
import os
import sys

# --- Configuration ---
TOKEN_FILE = "./token.txt"
# Corrected domain to match your other scripts
FRESHSERVICE_DOMAIN = "integotecllc.freshservice.com"
BASE_URL = f"https://{FRESHSERVICE_DOMAIN}"
TICKET_ID_TO_CHECK = 16837

# Updated Professional Services Group ID from your input
PROFESSIONAL_SERVICES_GROUP_ID = 19000234009

def read_api_key(file_path):
    """Reads the API key from the specified file."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abs_file_path = os.path.join(script_dir, file_path)
        if not os.path.exists(abs_file_path):
            abs_file_path = os.path.abspath(file_path)

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

def get_ticket_details(ticket_id, base_url, headers):
    """Fetches the full details for a single ticket."""
    detail_endpoint = f"{base_url}/api/v2/tickets/{ticket_id}"
    print(f"Fetching details for ticket ID: {ticket_id} from {detail_endpoint}")
    try:
        response = requests.get(detail_endpoint, headers=headers, timeout=20)
        response.raise_for_status()
        response_json = response.json()
        if "ticket" in response_json:
            return response_json["ticket"]
        else:
            print(f"Unexpected response structure for ticket {ticket_id} (missing 'ticket' key).", file=sys.stderr)
            return None
    except requests.exceptions.RequestException as e:
        print(f"Request Exception for ticket {ticket_id} details: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Status Code: {e.response.status_code}", file=sys.stderr)
            print(f"Response Body: {e.response.text}", file=sys.stderr)
        return None
    except json.JSONDecodeError:
        print(f"JSON decode error for ticket {ticket_id} details.", file=sys.stderr)
        return None

def main():
    """Main function to check ticket group and categorize it."""
    print("--- Ticket Group Debugger ---")

    # 1. Read API Key
    api_key = read_api_key(TOKEN_FILE)
    auth_str = f"{api_key}:X"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {encoded_auth}"
    }

    # 2. Fetch Ticket Details
    ticket_data = get_ticket_details(TICKET_ID_TO_CHECK, BASE_URL, headers)

    if not ticket_data:
        print(f"\nCould not retrieve data for ticket {TICKET_ID_TO_CHECK}. Exiting.")
        return

    # 3. Analyze the group and categorize
    print("\n--- Analysis ---")
    group_id = ticket_data.get('group_id')

    if group_id is None:
        print(f"Ticket {TICKET_ID_TO_CHECK} is not assigned to any group.")
        print("Category: Helpdesk Ticket")
        return

    print(f"Ticket {TICKET_ID_TO_CHECK} is assigned to Group ID: {group_id}")

    if group_id == PROFESSIONAL_SERVICES_GROUP_ID:
        print(f"This matches the Professional Services Group ID ({PROFESSIONAL_SERVICES_GROUP_ID}).")
        print("\nCategory: Professional Services Ticket")
    else:
        print(f"This does NOT match the Professional Services Group ID ({PROFESSIONAL_SERVICES_GROUP_ID}).")
        print("\nCategory: Helpdesk Ticket")

    print("\n--- Raw Ticket Data (for reference) ---")
    print(json.dumps(ticket_data, indent=2))


if __name__ == '__main__':
    main()
