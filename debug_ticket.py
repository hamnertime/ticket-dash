import os
import json
import sys
import requests # Added for API calls

# --- Configuration ---
# These should match your main configuration
FRESHSERVICE_DOMAIN = "integotecllc.freshservice.com"
TOKEN_FILE = "token.txt"

def read_token():
    """Safely reads the API token from the token file."""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        print(f"Error reading token file: {e}")
        return None

def fetch_and_dump_ticket_details(ticket_id):
    """
    Fetches ticket details directly from the Freshservice API and prints the data.
    """
    api_key = read_token()
    if not api_key:
        print(f"ERROR: API token not found or could not be read from '{TOKEN_FILE}'.")
        print("Please ensure the file exists in the same directory and contains your API key.")
        return

    # Construct the API URL for a specific ticket
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}"
    headers = {'Content-Type': 'application/json'}

    print(f"--- Querying Freshservice API for ticket {ticket_id} ---")
    print(f"--- URL: {url} ---\n")

    try:
        response = requests.get(url, headers=headers, auth=(api_key, 'X'))

        # Check for successful response
        if response.status_code == 200:
            ticket_data = response.json().get('ticket', {})
            print("--- Live Ticket Data Dump ---")
            # Use json.dumps for pretty printing the dictionary
            print(json.dumps(ticket_data, indent=4))
            print("--- End of Ticket Data ---\n")
        elif response.status_code == 404:
            print("ERROR: Ticket not found. Please check the ticket ID.")
        elif response.status_code in [401, 403]:
            print("ERROR: Authentication failed. Please check if your API token in 'token.txt' is correct and has not expired.")
        else:
            print(f"ERROR: Received an unexpected status code: {response.status_code}")
            print(f"Response Body: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the API request: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python debug_ticket.py <TICKET_ID>")
        print("Example: python debug_ticket.py 12345")
        sys.exit(1)

    # Ensure the requests library is installed
    try:
        import requests
    except ImportError:
        print("Error: The 'requests' library is not installed.")
        print("Please install it by running: pip install requests")
        sys.exit(1)

    try:
        target_ticket_id = int(sys.argv[1])
        fetch_and_dump_ticket_details(target_ticket_id)
    except ValueError:
        print("Error: The Ticket ID must be a number.")
        sys.exit(1)

