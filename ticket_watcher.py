import requests
import base64
import json
import os
import sys
import time
import datetime # Added for archive date
import shutil   # Added for moving files

# --- Configuration ---
TOKEN_FILE = "./token.txt"
FRESHSERVICE_DOMAIN = "integotecllc.freshservice.com"
BASE_URL = f"https://{FRESHSERVICE_DOMAIN}"
STATUS_IDS_TO_INCLUDE = [2, 3, 8, 9, 10, 13, 19, 23, 26, 27] # Statuses to fetch
TYPES_TO_INCLUDE = ["Incident", "Service Request"] # Define types to process

ORDER_BY_FIELD = "updated_at" # Not directly used by /api/v2/tickets/filter, but good for reference
ORDER_TYPE = "desc" # Not directly used by /api/v2/tickets/filter
TICKETS_PER_PAGE = 30
MAX_RETRIES = 3
RETRY_DELAY = 5 # seconds for general retries
INDIVIDUAL_TICKET_RETRY_DELAY = 10 # seconds for single ticket fetch retries
MAX_PAGES = 50 # Max pages for the initial list fetch

DELAY_BETWEEN_DETAIL_FETCHES = 0.75

TICKETS_DIR = "./tickets"
ARCHIVE_DIR_BASE = os.path.join(TICKETS_DIR, "archive")
POLL_INTERVAL = 120 # MODIFIED: Adjusted polling interval
LOG_FILE = "./ticket_poller.log"

# --- Logging Function ---
def log_message(message, is_error=False):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{timestamp}] {message}"
    stream = sys.stderr if is_error else sys.stdout
    print(formatted_message, file=stream)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(formatted_message + "\n")
    except Exception as e:
        print(f"[{timestamp}] CRITICAL: Failed to write to log file '{LOG_FILE}': {e}", file=sys.stderr)

# --- Helper Function to Read API Key ---
def read_api_key(file_path):
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abs_file_path = os.path.join(script_dir, file_path)
        if not os.path.exists(abs_file_path):
            abs_file_path = os.path.abspath(file_path)
            log_message(f"Token file not found at script dir, trying CWD: {abs_file_path}")

        log_message(f"Attempting to read token from: {abs_file_path}")
        with open(abs_file_path, 'r') as f:
            api_key = f.read().strip()
            if not api_key:
                log_message(f"Error: Token file '{abs_file_path}' is empty.", is_error=True)
                sys.exit(1)
            return api_key
    except FileNotFoundError:
        log_message(f"Error: Token file '{abs_file_path}' not found.", is_error=True)
        sys.exit(1)
    except Exception as e:
        log_message(f"Error reading token file '{abs_file_path}': {e}", is_error=True)
        sys.exit(1)

# --- Ensure Directories Exist ---
def ensure_directories():
    try:
        os.makedirs(TICKETS_DIR, exist_ok=True)
        os.makedirs(ARCHIVE_DIR_BASE, exist_ok=True)
        log_message(f"Ensured directories '{TICKETS_DIR}' and '{ARCHIVE_DIR_BASE}' exist.")
    except OSError as e:
        log_message(f"Error creating directories: {e}", is_error=True)
        sys.exit(1)

# --- Get Existing Ticket IDs from Filesystem ---
def get_local_ticket_ids(directory):
    local_ids = set()
    if not os.path.isdir(directory):
        log_message(f"Directory {directory} does not exist or is not accessible for reading local IDs.")
        return local_ids
    try:
        for filename in os.listdir(directory):
            if filename.endswith(".txt") and filename[:-4].isdigit():
                local_ids.add(int(filename[:-4]))
        log_message(f"Found {len(local_ids)} local ticket files in '{directory}'.")
    except OSError as e:
        log_message(f"Error reading directory '{directory}': {e}", is_error=True)
    return local_ids

# --- Write Ticket Data to File ---
def write_ticket_file(ticket_data):
    ticket_id = ticket_data.get('id')
    if not ticket_id:
        log_message(f"Ticket data missing 'id'. Cannot write file. Data: {ticket_data}", is_error=True)
        return
    file_path = os.path.join(TICKETS_DIR, f"{ticket_id}.txt")
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(ticket_data, f, indent=4)
    except IOError as e:
        log_message(f"Error writing ticket file {file_path}: {e}", is_error=True)
    except Exception as e:
        log_message(f"Unexpected error writing ticket file {file_path}: {e}", is_error=True)

# --- Archive Ticket File ---
def archive_ticket_file(ticket_id):
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    archive_date_dir = os.path.join(ARCHIVE_DIR_BASE, today_str)
    try:
        os.makedirs(archive_date_dir, exist_ok=True)
    except OSError as e:
        log_message(f"Error creating archive dir '{archive_date_dir}': {e}", is_error=True)
        return

    source_path = os.path.join(TICKETS_DIR, f"{ticket_id}.txt")
    destination_path = os.path.join(archive_date_dir, f"{ticket_id}.txt")

    if os.path.exists(source_path):
        try:
            shutil.move(source_path, destination_path)
            log_message(f"Archived ticket {ticket_id} to {destination_path}")
        except Exception as e:
            log_message(f"Error archiving ticket {ticket_id} from {source_path} to {destination_path}: {e}", is_error=True)
    else:
        log_message(f"Archive source file {source_path} not found for ticket {ticket_id}.", is_error=True)


# --- Fetch Filtered Ticket List (Step 1) ---
# API Query only filters by status. Type filtering happens after detail fetch.
def get_filtered_ticket_list(base_url, headers, status_ids, order_by, order_type):
    all_basic_tickets = []
    page = 1
    filter_endpoint = f"{base_url}/api/v2/tickets/filter"
    fetched_ids_current_run = set()

    status_queries = [f"status:{status_id}" for status_id in status_ids]
    raw_query_value = f"({' OR '.join(status_queries)})"
    query_param_value = f'"{raw_query_value}"'

    log_message(f"Fetching filtered ticket list. Query: {query_param_value}")

    while page <= MAX_PAGES:
        params = {
            'query': query_param_value,
            'page': page,
            'per_page': TICKETS_PER_PAGE
        }
        retries = 0
        while retries <= MAX_RETRIES:
            try:
                response = requests.get(filter_endpoint, headers=headers, params=params, timeout=30)
                if response.status_code == 429:
                    if retries < MAX_RETRIES:
                        retry_after = int(response.headers.get('Retry-After', RETRY_DELAY))
                        log_message(f"Rate limit on list fetch. Waiting {retry_after}s. Retry {retries+1}/{MAX_RETRIES}...", is_error=True)
                        time.sleep(retry_after)
                        retries += 1
                        continue
                    else:
                        log_message(f"List fetch rate limit exceeded after {MAX_RETRIES} retries.", is_error=True)
                        return None

                if response.status_code == 400:
                    err_details = response.json() if response.content and 'application/json' in response.headers.get('Content-Type','') else response.text
                    log_message(f"400 Bad Request for list. URL: {response.url}. Details: {err_details}", is_error=True)
                    return None

                response.raise_for_status()
                response_data = response.json()
                current_page_tickets = response_data.get('tickets', [])

                if not current_page_tickets:
                    log_message(f"No more tickets found on list page {page}. Fetching complete.")
                    return all_basic_tickets

                new_on_page = 0
                for ticket_data in current_page_tickets:
                    if isinstance(ticket_data, dict) and ticket_data.get('id') and ticket_data.get('id') not in fetched_ids_current_run:
                        fetched_ids_current_run.add(ticket_data['id'])
                        all_basic_tickets.append(ticket_data)
                        new_on_page +=1
                log_message(f"List Page {page}: Fetched {len(current_page_tickets)} items, {new_on_page} new unique. Total basic: {len(all_basic_tickets)}")

                if len(current_page_tickets) < TICKETS_PER_PAGE:
                    return all_basic_tickets

                page += 1
                break

            except requests.exceptions.Timeout:
                log_message(f"Timeout on list fetch, page {page}. Retry {retries+1}/{MAX_RETRIES}...", is_error=True)
            except requests.exceptions.RequestException as e:
                log_message(f"Request Exception on list fetch, page {page}: {e}. Retry {retries+1}/{MAX_RETRIES}...", is_error=True)

            retries += 1
            if retries <= MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                log_message(f"Failed list fetch for page {page} after {MAX_RETRIES} retries.", is_error=True)
                return None
        if retries > MAX_RETRIES and page <= MAX_PAGES :
             return None

    if page > MAX_PAGES:
        log_message(f"Warning: List fetch reached MAX_PAGES ({MAX_PAGES}). Some tickets might be missed if total > {MAX_PAGES * TICKETS_PER_PAGE}.", is_error=True)
    return all_basic_tickets

# --- Fetch Single Ticket Details with Stats (Step 2) ---
def get_ticket_details_with_stats(ticket_id, base_url, headers):
    detail_endpoint = f"{base_url}/api/v2/tickets/{ticket_id}"
    params = {'include': 'stats'}
    retries = 0

    while retries <= MAX_RETRIES:
        try:
            response = requests.get(detail_endpoint, headers=headers, params=params, timeout=20)
            if response.status_code == 429:
                if retries < MAX_RETRIES:
                    retry_after = int(response.headers.get('Retry-After', INDIVIDUAL_TICKET_RETRY_DELAY))
                    log_message(f"Rate limit on detail fetch for ticket {ticket_id}. Waiting {retry_after}s. Retry {retries+1}/{MAX_RETRIES}...", is_error=True)
                    time.sleep(retry_after)
                    retries += 1
                    continue
                else:
                    log_message(f"Detail fetch rate limit exceeded for ticket {ticket_id}.", is_error=True)
                    return None

            if response.status_code == 404:
                log_message(f"Ticket {ticket_id} not found (404). Might have been deleted since list fetch.", is_error=True)
                return None

            response.raise_for_status()
            response_json = response.json()
            if "ticket" in response_json:
                return response_json["ticket"]
            else:
                log_message(f"Unexpected response structure for ticket {ticket_id} details (missing 'ticket' key): {response_json}", is_error=True)
                return response_json

        except requests.exceptions.Timeout:
            log_message(f"Timeout fetching details for ticket {ticket_id}. Retry {retries+1}/{MAX_RETRIES}...", is_error=True)
        except requests.exceptions.RequestException as e:
            log_message(f"Request Exception for ticket {ticket_id} details: {e}. Retry {retries+1}/{MAX_RETRIES}...", is_error=True)
        except json.JSONDecodeError:
            log_message(f"JSON decode error for ticket {ticket_id} details. Response: {response.text[:200]}", is_error=True)
            return None

        retries += 1
        if retries <= MAX_RETRIES:
            time.sleep(INDIVIDUAL_TICKET_RETRY_DELAY)
        else:
            log_message(f"Failed to fetch details for ticket {ticket_id} after {MAX_RETRIES} retries.", is_error=True)
            return None
    return None

# --- Main Background Process Loop ---
def main_loop():
    log_message("🚀 Starting Freshservice Ticket Poller")
    log_message(f"Polling interval: {POLL_INTERVAL} seconds.")
    log_message(f"Tickets directory: '{TICKETS_DIR}'")
    log_message(f"Archive directory base: '{ARCHIVE_DIR_BASE}'")
    log_message(f"Fetching tickets with status IDs: {STATUS_IDS_TO_INCLUDE}")
    log_message(f"Max pages per API list fetch: {MAX_PAGES}, Tickets per page: {TICKETS_PER_PAGE}")
    log_message(f"Delay between individual ticket detail fetches: {DELAY_BETWEEN_DETAIL_FETCHES}s")
    log_message(f"Creating local files for tickets of types: {TYPES_TO_INCLUDE}") # MODIFIED Log

    ensure_directories()
    API_KEY = read_api_key(TOKEN_FILE)
    log_message(f"API Key loaded: {API_KEY[:4]}...{API_KEY[-4:] if len(API_KEY) > 8 else API_KEY[:4] + '...'}")

    auth_str = f"{API_KEY}:X"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {encoded_auth}"
    }

    while True:
        current_cycle_start_time = time.time()
        log_message("--- Poll Cycle Start ---")

        basic_ticket_data_list = get_filtered_ticket_list(
            BASE_URL, headers, STATUS_IDS_TO_INCLUDE, ORDER_BY_FIELD, ORDER_TYPE
        )

        if basic_ticket_data_list is None:
            log_message("API fetch for ticket list failed. Retrying next cycle.", is_error=True)
            # Calculate sleep time carefully if the cycle was short due to immediate failure
            cycle_duration = time.time() - current_cycle_start_time
            sleep_duration = max(0, POLL_INTERVAL - cycle_duration)
            if sleep_duration > 0: time.sleep(sleep_duration)
            continue

        processed_ticket_data_list = [] # Renamed from enriched_ticket_data_list for clarity
        if not basic_ticket_data_list:
            log_message("No tickets found in the initial list fetch for the given criteria.")
        else:
            log_message(f"Fetched {len(basic_ticket_data_list)} basic ticket entries. Now fetching details and filtering for types: {TYPES_TO_INCLUDE}...")
            for i, basic_ticket in enumerate(basic_ticket_data_list):
                ticket_id = basic_ticket.get('id')
                if not ticket_id:
                    log_message(f"Skipping basic ticket data without ID: {basic_ticket}", is_error=True)
                    continue

                detailed_ticket = get_ticket_details_with_stats(ticket_id, BASE_URL, headers)
                if detailed_ticket:
                    ticket_type = detailed_ticket.get('type')
                    # MODIFIED: Filter to include types from TYPES_TO_INCLUDE list
                    if ticket_type in TYPES_TO_INCLUDE:
                        processed_ticket_data_list.append(detailed_ticket)
                    # else:
                        # log_message(f"Ticket ID {ticket_id} (Type: {ticket_type}) is not in TYPES_TO_INCLUDE. Skipping.")
                else:
                    log_message(f"Failed to fetch details for ticket ID {ticket_id}. It will be excluded.", is_error=True)

                if i < len(basic_ticket_data_list) - 1:
                    time.sleep(DELAY_BETWEEN_DETAIL_FETCHES)
            log_message(f"After detail fetch and type filtering, {len(processed_ticket_data_list)} tickets of types {TYPES_TO_INCLUDE} remain for processing.")

        api_ticket_ids_for_saving = set() # Renamed for clarity
        if processed_ticket_data_list:
            for ticket_data in processed_ticket_data_list:
                if isinstance(ticket_data, dict) and 'id' in ticket_data:
                     api_ticket_ids_for_saving.add(ticket_data['id'])
        log_message(f"API returned {len(api_ticket_ids_for_saving)} unique ticket IDs of specified types this cycle.")

        local_ticket_ids_before_processing = get_local_ticket_ids(TICKETS_DIR)
        log_message(f"State: {len(local_ticket_ids_before_processing)} local files, {len(api_ticket_ids_for_saving)} FreshService tickets of specified types are active.")

        active_files_written_count = 0
        if processed_ticket_data_list:
            for ticket_data in processed_ticket_data_list: # Iterate through the already filtered list
                # The check `ticket_data.get('type') in TYPES_TO_INCLUDE` is redundant here as it's already filtered
                if isinstance(ticket_data, dict) and 'id' in ticket_data:
                    write_ticket_file(ticket_data)
                    active_files_written_count +=1
        log_message(f"Wrote/updated {active_files_written_count} ticket files for types {TYPES_TO_INCLUDE} in '{TICKETS_DIR}'.")

        # Files to archive are those present locally but NOT in the current list of active tickets (of specified types) from API
        closed_or_missing_ids = local_ticket_ids_before_processing - api_ticket_ids_for_saving
        num_tickets_archived_this_cycle = 0
        if closed_or_missing_ids:
            log_message(f"Found {len(closed_or_missing_ids)} local files to archive (no longer active or not of specified types): {closed_or_missing_ids}")
            for ticket_id_to_archive in closed_or_missing_ids:
                archive_ticket_file(ticket_id_to_archive)
                num_tickets_archived_this_cycle += 1
        else:
            log_message("No local ticket files to archive in this cycle.")

        newly_added_ids = api_ticket_ids_for_saving - local_ticket_ids_before_processing
        log_message(f"Changes: {len(newly_added_ids)} new tickets processed, {num_tickets_archived_this_cycle} old/non-specified-type files archived.")

        cycle_duration = time.time() - current_cycle_start_time
        log_message(f"--- Poll cycle finished in {cycle_duration:.2f} seconds. ---")

        sleep_duration = max(0, POLL_INTERVAL - cycle_duration)
        if sleep_duration > 0:
            log_message(f"Sleeping for {sleep_duration:.2f} seconds...")
            time.sleep(sleep_duration)
        else:
            log_message(f"Warning: Poll cycle took longer than POLL_INTERVAL ({POLL_INTERVAL}s). Running next cycle immediately.", is_error=True)

if __name__ == '__main__':
    try:
        main_loop()
    except KeyboardInterrupt:
        log_message("Poller interrupted by user (Ctrl+C). Exiting gracefully.")
    except Exception as e:
        log_message(f"Unhandled exception in main_loop: {e}", is_error=True)
        import traceback
        log_message(traceback.format_exc(), is_error=True)
