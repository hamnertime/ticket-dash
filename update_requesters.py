import requests
import base64
import json
import os
import sys
import time
import pprint

# --- Configuration ---
TOKEN_FILE = "./token.txt"
FRESHSERVICE_DOMAIN = "integotecllc.freshservice.com"
BASE_URL = f"https://{FRESHSERVICE_DOMAIN}"
OUTPUT_FILE = "./requesters.txt"
# Changed from CONTACTS_PER_PAGE to REQUESTERS_PER_PAGE for clarity
REQUESTERS_PER_PAGE = 100
MAX_RETRIES = 3
RETRY_DELAY = 5 # seconds

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
        print("Please ensure 'token.txt' exists in the same directory as the script", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading token file '{abs_file_path}': {e}", file=sys.stderr)
        sys.exit(1)

# --- Function to Fetch All Requesters with Pagination ---
# Renamed function for clarity
def get_all_requesters(base_url, headers):
    """
    Fetches all requesters from Freshservice API (/api/v2/requesters)
    and returns a dictionary mapping requester_id to requester_name.
    """
    all_requesters_map = {}
    page = 1
    # Changed endpoint from /contacts to /requesters
    requesters_endpoint = f"{base_url}/api/v2/requesters"
    retries = 0

    print(f"Fetching all requesters page by page from: {requesters_endpoint}")

    while True:
        params = {
            'page': page,
            'per_page': REQUESTERS_PER_PAGE,
        }
        print(f"\nRequesting page {page} (Attempt {retries + 1}/{MAX_RETRIES + 1})...")
        print(f"  Parameters: {params}")
        current_url_attempt = "" # For logging in case of error

        try:
            # Construct the request object to get the full URL for logging if needed
            prepared_request = requests.Request('GET', requesters_endpoint, headers=headers, params=params).prepare()
            current_url_attempt = prepared_request.url

            session = requests.Session()
            response = session.send(prepared_request, timeout=30)

            if response.status_code == 429: # Rate Limiting
                if retries < MAX_RETRIES:
                    retries += 1
                    retry_after = int(response.headers.get('Retry-After', RETRY_DELAY))
                    print(f"Rate limit exceeded. Waiting {retry_after} seconds (Retry {retries}/{MAX_RETRIES})...")
                    time.sleep(retry_after)
                    continue
                else:
                    print(f"Error: Rate limit exceeded after {MAX_RETRIES + 1} retries. Aborting.", file=sys.stderr)
                    return None

            # Check for 404 specifically before general raise_for_status
            if response.status_code == 404:
                print(f"Error: Received 404 Not Found for URL: {current_url_attempt}", file=sys.stderr)
                print("This means the API endpoint is incorrect or not available.", file=sys.stderr)
                print("Please double-check the Freshservice API documentation for listing all requesters for your instance.", file=sys.stderr)
                return None


            response.raise_for_status() # Raise other HTTP errors (4xx, 5xx)
            retries = 0

            response_data = response.json()

            current_page_requesters_list = []
            # Freshservice /api/v2/requesters usually returns {"requesters": [...]}
            if 'requesters' in response_data and isinstance(response_data['requesters'], list):
                current_page_requesters_list = response_data['requesters']
            # As a fallback, check if it was 'contacts' (less likely for /requesters endpoint)
            elif 'contacts' in response_data and isinstance(response_data['contacts'], list):
                 print(f"Warning: Using 'contacts' key from response of {requesters_endpoint}. Data might be different than expected 'requesters'.")
                 current_page_requesters_list = response_data['contacts']
            else:
                print(f"Warning: Expected 'requesters' key with a list in response on page {page} from {requesters_endpoint}.", file=sys.stderr)
                print("Response structure received:")
                pprint.pprint(response_data, stream=sys.stderr)
                # Attempt to process if response_data is a direct list (uncommon for Freshservice v2 list endpoints)
                if isinstance(response_data, list):
                    print("Attempting to process response as a direct list.")
                    current_page_requesters_list = response_data
                else:
                    print("Error: Cannot process unknown response structure for requesters. Aborting this page.", file=sys.stderr)
                    # Potentially problematic, decide to return None or try next page
                    # For now, let's assume this means the end of valid data or an error
                    break


            if not current_page_requesters_list:
                print(f"No more requesters found on page {page}. Fetching complete.")
                break

            print(f"Fetched {len(current_page_requesters_list)} requesters on page {page}.")
            for requester in current_page_requesters_list:
                requester_id = requester.get('id')

                requester_name = requester.get('name')
                if not requester_name or requester_name.strip() == "":
                    first_name = requester.get('first_name', '')
                    last_name = requester.get('last_name', '')
                    if first_name.strip() or last_name.strip():
                        requester_name = f"{first_name} {last_name}".strip()
                    else:
                        requester_name = requester.get('primary_email') # Fallback to primary_email
                        if not requester_name: # If email is also empty
                             requester_name = requester.get('email', f"Requester ID {requester_id}") # Fallback to general email then placeholder

                if requester_id and requester_name:
                    all_requesters_map[requester_id] = requester_name.replace(':', '-')
                else:
                    print(f"Warning: Requester missing ID or usable name: {pprint.pformat(requester)}", file=sys.stderr)

            if len(current_page_requesters_list) < REQUESTERS_PER_PAGE:
                print("Last page reached (received fewer items than per_page).")
                break

            page += 1

        except requests.exceptions.RequestException as e:
            print(f"\nError during API request for requesters (URL: {current_url_attempt}): {e}", file=sys.stderr)
            if hasattr(e, 'response') and e.response is not None:
                print(f"Status Code: {e.response.status_code}", file=sys.stderr)
                try:
                    print(f"Response Body: {e.response.text}", file=sys.stderr)
                except Exception:
                    pass
            retries += 1
            if retries > MAX_RETRIES:
                print(f"Failed after {MAX_RETRIES + 1} attempts on page {page}.", file=sys.stderr)
                return None
            else:
                print(f"Waiting {RETRY_DELAY}s before retry {retries}/{MAX_RETRIES}...")
                time.sleep(RETRY_DELAY)
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON response for requesters on page {page} (URL: {current_url_attempt}).", file=sys.stderr)
            if 'response' in locals() and response is not None:
                 print(f"Response text: {response.text}", file=sys.stderr)
            return None

    print(f"\nTotal unique requesters processed and mapped: {len(all_requesters_map)}")
    return all_requesters_map

# --- Function to Save Mappings to File ---
def save_mappings_to_file(mapping_dict, filename):
    """Saves the id:name mapping to a file."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abs_file_path = os.path.join(script_dir, filename)
        with open(abs_file_path, 'w', encoding='utf-8') as f:
            for item_id, name in mapping_dict.items():
                f.write(f"{item_id}:{name}\n")
        print(f"Successfully saved {len(mapping_dict)} requester mappings to '{abs_file_path}'.")
    except Exception as e:
        print(f"Error saving mappings to '{abs_file_path}': {e}", file=sys.stderr)

# --- Main Execution ---
if __name__ == "__main__":
    print("🚀 Freshservice Requester Lister")
    print("============================================")
    print(f"Targeting Domain: {FRESHSERVICE_DOMAIN}")

    API_KEY = read_api_key(TOKEN_FILE)
    print(f"Using API Key: {API_KEY[:4]}...{API_KEY[-4:] if len(API_KEY) > 8 else API_KEY[:4] + '...'}")

    auth_str = f"{API_KEY}:X"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {encoded_auth}"
    }

    # Changed function call
    requester_mappings = get_all_requesters(BASE_URL, headers)

    if requester_mappings is not None:
        if requester_mappings:
            save_mappings_to_file(requester_mappings, OUTPUT_FILE)
        else:
            print("No requester data fetched or no mappings created.")
    else:
        print("\n❌ Failed to retrieve requester data. No output file generated.", file=sys.stderr)

    print("\nScript finished.")
