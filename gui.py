import os
import json
import datetime
from flask import Flask, render_template, jsonify, abort # send_from_directory is not used
import ssl

# --- Configuration ---
TICKETS_DIR = "./tickets"
TOKEN_FILE = "token.txt" # For security checks, actual token usage not in this script
STATIC_DIR = "static"
AGENTS_FILE = "./agents.txt"
REQUESTERS_FILE = "./requesters.txt"
AUTO_REFRESH_INTERVAL_SECONDS = 30 # Set to 0 to disable auto-refresh
FRESHSERVICE_DOMAIN = "integotecllc.freshservice.com" # Your Freshservice domain

FR_SLA_CRITICAL_HOURS = 4
FR_SLA_WARNING_HOURS = 12

# Status IDs from Freshservice
OPEN_TICKET_STATUS_ID = 2
PENDING_TICKET_STATUS_ID = 3 # Example, if used for specific styling
WAITING_ON_CUSTOMER_STATUS_ID = 9
WAITING_ON_AGENT = 26 # Freshservice ID for "Waiting on Agent"
ON_HOLD_STATUS_ID = 23 # Explicitly defined for clarity

INDEX = "index.html" # Your main template file

# SSL Certificate and Key files (using these constants now in __main__)
SSL_CERT_FILE = './cert.pem'
SSL_KEY_FILE = './key.pem'

app = Flask(__name__, static_folder=STATIC_DIR)

# --- Mappings ---
AGENT_MAPPING = {} # Global cache for agent ID to name mapping
REQUESTER_MAPPING = {} # Global cache for requester ID to name mapping

def load_agent_mapping(file_path=AGENTS_FILE):
    """Loads agent ID to name mapping from agents.txt."""
    mapping = {}
    if not os.path.exists(file_path):
        app.logger.warning(f"Agents file '{file_path}' not found. Agent names will default to IDs.")
        return mapping
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, 1):
                line = line.strip()
                if not line or ':' not in line:
                    if line: app.logger.warning(f"Malformed line {line_number} in '{file_path}': '{line}'. Skipping.")
                    continue
                parts = line.split(':', 1)
                item_id_str, name = parts[0].strip(), parts[1].strip()
                if not item_id_str or not name:
                    app.logger.warning(f"Empty ID or name on line {line_number} in '{file_path}': '{line}'. Skipping.")
                    continue
                try:
                    mapping[int(item_id_str)] = name
                except ValueError:
                    app.logger.warning(f"Could not parse agent ID '{item_id_str}' as int on line {line_number} in '{file_path}'.")
            app.logger.info(f"Successfully loaded {len(mapping)} agent(s) from '{file_path}'.")
    except Exception as e:
        app.logger.error(f"Error loading agent mapping from '{file_path}': {e}", exc_info=True)
    return mapping

def load_requester_mapping(file_path=REQUESTERS_FILE):
    """Loads requester ID to name mapping from requesters.txt."""
    mapping = {}
    if not os.path.exists(file_path):
        app.logger.warning(f"Requesters file '{file_path}' not found. Requester names will default to IDs.")
        return mapping
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, 1):
                line = line.strip()
                if not line or ':' not in line:
                    if line: app.logger.warning(f"Malformed line {line_number} in '{file_path}': '{line}'. Skipping.")
                    continue
                parts = line.split(':', 1)
                item_id_str, name = parts[0].strip(), parts[1].strip()
                if not item_id_str or not name:
                    app.logger.warning(f"Empty ID or name on line {line_number} in '{file_path}': '{line}'. Skipping.")
                    continue
                try:
                    mapping[int(item_id_str)] = name
                except ValueError:
                    app.logger.warning(f"Could not parse requester ID '{item_id_str}' as int on line {line_number} in '{file_path}'.")
            app.logger.info(f"Successfully loaded {len(mapping)} requester(s) from '{file_path}'.")
    except Exception as e:
        app.logger.error(f"Error loading requester mapping from '{file_path}': {e}", exc_info=True)
    return mapping

# --- Helper Functions ---
def parse_datetime_utc(dt_str):
    """Parses an ISO 8601 datetime string into a timezone-aware datetime object (UTC)."""
    if not dt_str: return None
    try:
        return datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        app.logger.warning(f"Could not parse datetime string: {dt_str}")
        return None

def get_fr_sla_details_for_open_ticket(target_due_dt, critical_threshold_hours, warning_threshold_hours):
    """Calculates SLA details for First Response."""
    if not target_due_dt:
        return "No FR Due Date", "sla-none", float('inf') - 1000
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    time_diff_seconds = (target_due_dt - now_utc).total_seconds()
    hours_remaining_for_status = time_diff_seconds / 3600.0

    if abs(time_diff_seconds) >= (2 * 24 * 60 * 60):
        unit, formatted_value = "days", f"{hours_remaining_for_status / 24.0:.1f}"
    elif abs(time_diff_seconds) >= (60 * 60):
        unit, formatted_value = "hours", f"{hours_remaining_for_status:.1f}"
    elif abs(time_diff_seconds) >= 60:
        unit, formatted_value = "min", f"{time_diff_seconds / 60.0:.0f}"
    else:
        unit, formatted_value = "sec", f"{time_diff_seconds:.0f}"

    status_text_prefix = "FR"
    sla_class = "sla-normal"
    sla_text = f"{formatted_value} {unit} for {status_text_prefix}"

    if hours_remaining_for_status < 0:
        sla_text = f"{status_text_prefix} Overdue by {formatted_value.lstrip('-')} {unit}"
        sla_class = "sla-overdue"
    elif hours_remaining_for_status < critical_threshold_hours:
        sla_class = "sla-critical"
    elif hours_remaining_for_status < warning_threshold_hours:
        sla_class = "sla-warning"
    return sla_text, sla_class, hours_remaining_for_status

def get_status_text(status_id):
    """Returns a human-readable status text."""
    status_map = {
        OPEN_TICKET_STATUS_ID: "Open",
        PENDING_TICKET_STATUS_ID: "Pending",
        8: "Scheduled", # Example, ensure this ID is correct for your Freshservice
        WAITING_ON_CUSTOMER_STATUS_ID: "Waiting on Customer",
        10: "Waiting on Third Party", # Example
        13: "Under Investigation", # Example
        ON_HOLD_STATUS_ID: "On Hold",
        WAITING_ON_AGENT: "Waiting on Agent",
    }
    return status_map.get(status_id, f"Unknown Status ({status_id})")

def get_priority_text(priority_id):
    """Returns human-readable priority text."""
    priority_map = {1: "Low", 2: "Medium", 3: "High", 4: "Urgent"}
    return priority_map.get(priority_id, f"P-{priority_id}")

def time_since(dt_object, default="N/A"):
    """Returns a friendly 'time since' string (e.g., '5m ago', '2h ago', '3d ago')."""
    if not dt_object: return default
    now = datetime.datetime.now(dt_object.tzinfo or datetime.timezone.utc)
    diff = now - dt_object
    seconds = diff.total_seconds()
    days = diff.days

    if days < 0: return "in the future"
    if days >= 1: return f"{days}d ago"
    if seconds >= 3600: return f"{int(seconds // 3600)}h ago"
    if seconds >= 60: return f"{int(seconds // 60)}m ago"
    if seconds >= 0: return "Just now"
    return "in the future"

def days_since(dt_object, default="N/A"):
    """Returns 'X days old', 'Today', or '1 day old'."""
    if not dt_object: return default
    now = datetime.datetime.now(dt_object.tzinfo or datetime.timezone.utc)
    diff_days = (now.date() - dt_object.date()).days

    if diff_days < 0: return "Future Date"
    if diff_days == 0: return "Today"
    if diff_days == 1: return "1 day old"
    return f"{diff_days} days old"

def load_and_process_tickets():
    """Loads tickets from JSON files, processes them, and categorizes them."""
    global AGENT_MAPPING, REQUESTER_MAPPING # Ensure global mappings are accessible
    list_status_open_tickets = []
    list_waiting_on_agent = []
    list_section3_candidates = []

    if not os.path.isdir(TICKETS_DIR):
        app.logger.error(f"Tickets directory '{TICKETS_DIR}' not found.")
        return [], [], []

    for filename in os.listdir(TICKETS_DIR):
        if filename.endswith(".txt") and filename[:-4].isdigit():
            file_path = os.path.join(TICKETS_DIR, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                ticket = {
                    'id': data.get('id', int(filename[:-4])),
                    'subject': data.get('subject', 'No Subject Provided'),
                    'requester_id': data.get('requester_id'),
                    'responder_id': data.get('responder_id'),
                    'status_raw': data.get('status'),
                    'priority_raw': data.get('priority'),
                    'description_text': data.get('description_text', ''),
                    'fr_due_by_str': data.get('fr_due_by'),
                    'updated_at_str': data.get('updated_at'),
                    'created_at_str': data.get('created_at'),
                    'type': data.get('type', 'N/A'),
                    'stats': data.get('stats', {})
                }

                agent_id_from_ticket = ticket.get('responder_id')
                ticket['agent_name'] = AGENT_MAPPING.get(agent_id_from_ticket, f"Agent ID: {agent_id_from_ticket}") if agent_id_from_ticket else 'Unassigned'

                requester_id_from_ticket = ticket.get('requester_id')
                ticket['requester_name'] = REQUESTER_MAPPING.get(requester_id_from_ticket, f"Req. ID: {requester_id_from_ticket}") if requester_id_from_ticket else 'N/A'

                ticket['fr_due_by_dt'] = parse_datetime_utc(ticket['fr_due_by_str'])
                ticket['updated_at_dt'] = parse_datetime_utc(ticket['updated_at_str'])
                ticket['created_at_dt'] = parse_datetime_utc(ticket['created_at_str'])
                ticket['first_responded_at_dt'] = parse_datetime_utc(ticket['stats'].get('first_responded_at'))
                ticket['agent_responded_at_dt'] = parse_datetime_utc(ticket['stats'].get('agent_responded_at'))
                ticket['status_updated_at_dt'] = parse_datetime_utc(ticket['stats'].get('status_updated_at'))

                ticket['priority_text'] = get_priority_text(ticket['priority_raw'])
                ticket['updated_friendly'] = time_since(ticket['updated_at_dt'])
                ticket['created_days_old'] = days_since(ticket['created_at_dt'])
                ticket['agent_responded_friendly'] = time_since(ticket['agent_responded_at_dt'])
                ticket_updated_timestamp = ticket['updated_at_dt'].timestamp() if ticket['updated_at_dt'] else 0.0

                # Get base status text early for use in default sla_text
                current_status_text = get_status_text(ticket['status_raw'])
                ticket['status_text'] = current_status_text # Store for direct display if needed

                # Default SLA text and class, may be overridden by categorization logic
                ticket['sla_text'] = f"{current_status_text} ({ticket['updated_friendly']})"
                ticket['sla_class'] = "sla-in-progress" # A general default

                if ticket['status_raw'] == OPEN_TICKET_STATUS_ID:
                    if ticket['first_responded_at_dt'] is None:
                        sla_text, sla_class, fr_sla_sort_key = get_fr_sla_details_for_open_ticket(
                            ticket['fr_due_by_dt'], FR_SLA_CRITICAL_HOURS, FR_SLA_WARNING_HOURS)
                        ticket['sla_text'], ticket['sla_class'] = sla_text, sla_class
                        ticket['action_sort_key_tuple'] = (0, fr_sla_sort_key, -ticket_updated_timestamp)
                    else:
                        ticket['sla_text'] = f"Open ({ticket['updated_friendly']})"
                        ticket['sla_class'] = "sla-in-progress"
                        ticket['action_sort_key_tuple'] = (1, -ticket_updated_timestamp, 0)
                    list_status_open_tickets.append(ticket)

                elif ticket['status_raw'] == WAITING_ON_AGENT:
                    ticket['sla_text'] = f"Waiting on Agent ({ticket['updated_friendly']})" # Changed from "Customer Replied" for consistency
                    ticket['sla_class'] = "sla-warning"
                    ticket['action_sort_key'] = ticket_updated_timestamp
                    list_waiting_on_agent.append(ticket)

                # Removed the "Review Needed" elif block here.
                # Tickets that would have matched it will now fall into the else below.

                else: # Handles all other statuses for section 3
                    if ticket['status_raw'] == WAITING_ON_CUSTOMER_STATUS_ID:
                        ticket['sla_text'] = "Waiting on Customer"
                        if ticket['agent_responded_friendly'] != 'N/A':
                            ticket['sla_text'] += f" (Agent: {ticket['agent_responded_friendly']})"
                        ticket['sla_class'] = "sla-responded"
                    elif ticket['status_raw'] == ON_HOLD_STATUS_ID:
                        ticket['sla_text'] = f"On Hold ({ticket['updated_friendly']})"
                        ticket['sla_class'] = "sla-on-hold" # Define .sla-on-hold in CSS if desired
                    elif ticket['status_raw'] == PENDING_TICKET_STATUS_ID:
                        ticket['sla_text'] = f"Pending ({ticket['updated_friendly']})"
                        ticket['sla_class'] = "sla-pending" # Define .sla-pending in CSS if desired
                    # Add more elif for other specific statuses if they need unique text/class
                    # Example:
                    # elif ticket['status_raw'] == 8: # Scheduled
                    #     ticket['sla_text'] = f"Scheduled ({ticket['updated_friendly']})"
                    #     ticket['sla_class'] = "sla-scheduled"
                    else:
                        # Fallback for any other statuses not explicitly handled above.
                        # Uses the default sla_text and sla_class set earlier.
                        # ticket['sla_text'] = f"{current_status_text} ({ticket['updated_friendly']})"
                        # ticket['sla_class'] = "sla-in-progress"
                        pass # Defaults are already set

                    ticket['action_sort_key'] = ticket_updated_timestamp
                    list_section3_candidates.append(ticket)

            except json.JSONDecodeError:
                app.logger.error(f"JSON decode error for {filename}")
            except Exception as e:
                app.logger.error(f"Error processing {filename}: {e}", exc_info=True)

    list_status_open_tickets.sort(key=lambda t: t.get('action_sort_key_tuple', (2, float('inf'), 0)))
    list_waiting_on_agent.sort(key=lambda t: t.get('action_sort_key', float('inf')))
    list_section3_candidates.sort(key=lambda t: t.get('action_sort_key', float('inf')))

    return list_status_open_tickets, list_waiting_on_agent, list_section3_candidates

# --- Flask Routes ---
@app.route(f'/{TICKETS_DIR}/<path:filename>')
def block_ticket_files(filename): abort(403)

@app.route(f'/{TOKEN_FILE}')
def block_token_file_root(): abort(403)

@app.route(f'/{STATIC_DIR}/{TOKEN_FILE}')
def block_token_file_static(): abort(403)

@app.route(f'/{AGENTS_FILE}')
def block_agents_file_root(): abort(403)

@app.route(f'/{STATIC_DIR}/{AGENTS_FILE}')
def block_agents_file_static(): abort(403)

@app.route(f'/{REQUESTERS_FILE}')
def block_requesters_file_root(): abort(403)

@app.route(f'/{STATIC_DIR}/{REQUESTERS_FILE}')
def block_requesters_file_static(): abort(403)

# Block access to SSL files if they were accidentally placed in web-accessible locations
@app.route(f'/{os.path.basename(SSL_CERT_FILE)}')
def block_ssl_cert_file_root(): abort(403)

@app.route(f'/{STATIC_DIR}/{os.path.basename(SSL_CERT_FILE)}')
def block_ssl_cert_file_static(): abort(403)

@app.route(f'/{os.path.basename(SSL_KEY_FILE)}')
def block_ssl_key_file_root(): abort(403)

@app.route(f'/{STATIC_DIR}/{os.path.basename(SSL_KEY_FILE)}')
def block_ssl_key_file_static(): abort(403)


@app.route('/')
def dashboard():
    s1_open_tickets, s2_waiting_agent_tickets, s3_remaining_tickets = load_and_process_tickets()

    generated_time_utc = datetime.datetime.now(datetime.timezone.utc)
    dashboard_display_time_utc = generated_time_utc.strftime('%Y-%m-%d %H:%M:%S %Z')
    dashboard_generated_time_iso = generated_time_utc.isoformat()

    return render_template(INDEX,
                            s1_open_tickets=s1_open_tickets,
                            s2_waiting_agent_tickets=s2_waiting_agent_tickets,
                            s3_remaining_tickets=s3_remaining_tickets,
                            dashboard_generated_time=dashboard_display_time_utc,
                            dashboard_generated_time_iso=dashboard_generated_time_iso,
                            auto_refresh_ms=AUTO_REFRESH_INTERVAL_SECONDS * 1000,
                            freshservice_base_url=f"https://{FRESHSERVICE_DOMAIN}/a/tickets/",
                            OPEN_TICKET_STATUS_ID=OPEN_TICKET_STATUS_ID,
                            WAITING_ON_CUSTOMER_STATUS_ID=WAITING_ON_CUSTOMER_STATUS_ID,
                            WAITING_ON_AGENT_STATUS_ID=WAITING_ON_AGENT)

@app.route('/health')
def health_check():
    """Simple health check endpoint."""
    return "OK", 200


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(script_dir, 'templates')

    for dir_path in [TICKETS_DIR, templates_dir, STATIC_DIR]:
        abs_dir_path = os.path.abspath(dir_path)
        if not os.path.exists(abs_dir_path):
            try:
                os.makedirs(abs_dir_path)
                app.logger.info(f"Created directory at {abs_dir_path}.")
            except OSError as e:
                app.logger.error(f"Failed to create directory {abs_dir_path}: {e}")
                if dir_path in [templates_dir, STATIC_DIR]:
                     exit(f"Error: Could not create essential directory {abs_dir_path}. Exiting.")


    AGENT_MAPPING = load_agent_mapping()
    if not AGENT_MAPPING: app.logger.warning(f"Agent mapping from '{AGENTS_FILE}' is empty or failed to load.")
    REQUESTER_MAPPING = load_requester_mapping()
    if not REQUESTER_MAPPING: app.logger.warning(f"Requester mapping from '{REQUESTERS_FILE}' is empty or failed to load.")

    static_path_abs = os.path.abspath(STATIC_DIR)
    # Check for sensitive files in web-accessible static dir or app root
    # SSL_CERT_FILE and SSL_KEY_FILE are checked here using their constant values
    sensitive_files_in_root = [TOKEN_FILE, AGENTS_FILE, REQUESTERS_FILE, SSL_CERT_FILE, SSL_KEY_FILE]

    for file_name in sensitive_files_in_root:
        app_root_file_path = os.path.join(script_dir, file_name) # Path in app root
        static_file_path = os.path.join(static_path_abs, file_name) # Path if in static dir

        if os.path.exists(static_file_path):
            level = app.logger.critical if file_name in [TOKEN_FILE, SSL_KEY_FILE] else app.logger.warning
            level(
                f"{'SECURITY WARNING' if file_name in [TOKEN_FILE, SSL_KEY_FILE] else 'NOTICE'}: '{file_name}' found in static dir '{static_path_abs}'. "
                "Consider moving it outside web-accessible folders. Direct access routes are blocked."
            )
        # For files expected in root (like mapping files, certs for loading)
        elif os.path.exists(app_root_file_path):
            if file_name in [TOKEN_FILE, SSL_KEY_FILE]: # These are more sensitive if in root
                 app.logger.critical(
                    f"SECURITY WARNING: Sensitive file '{file_name}' found in the application root '{app_root_file_path}'. "
                    "Consider moving it to a more secure, non-web-accessible location."
                )
            else: # AGENTS_FILE, REQUESTERS_FILE, SSL_CERT_FILE are expected in root for loading
                app.logger.info(f"'{file_name}' found in the application root '{app_root_file_path}'. This is expected for loading data/certs.")
        # If AGENTS_FILE or REQUESTERS_FILE are missing entirely (and not in static)
        elif file_name in [AGENTS_FILE, REQUESTERS_FILE] and not os.path.exists(app_root_file_path):
             app.logger.warning(f"Mapping file '{file_name}' not found in application root or static directory.")


    app.logger.info(f"Starting Flask app. Ticket directory: '{os.path.abspath(TICKETS_DIR)}'")
    app.logger.info(f"FR SLA Critical: < {FR_SLA_CRITICAL_HOURS} hrs, Warning: < {FR_SLA_WARNING_HOURS} hrs.")

    # Use constants for SSL file paths
    cert_path = os.path.abspath(SSL_CERT_FILE)
    key_path = os.path.abspath(SSL_KEY_FILE)

    cert_exists = os.path.exists(cert_path)
    key_exists = os.path.exists(key_path)

    if not cert_exists:
        app.logger.error(f"SSL certificate file not found at: {cert_path}")
    if not key_exists:
        app.logger.error(f"SSL private key file not found at: {key_path}")

    if cert_exists and key_exists:
        app.logger.info(f"Attempting to start HTTPS server on port 443.")
        app.logger.info(f"Using SSL certificate: {cert_path}")
        app.logger.info(f"Using SSL private key: {key_path}")
        app.logger.warning("Running on port 443 typically requires superuser privileges (e.g., use 'sudo python3 app.py').")
        try:
            app.run(host='0.0.0.0', port=443, debug=True, ssl_context=(cert_path, key_path))
        except OSError as e:
            if "Permission denied" in str(e) or "Errno 13" in str(e):
                app.logger.error(f"OSError: {e}. Could not bind to port 443. Try running with sudo.")
            else:
                app.logger.error(f"OSError: {e}. Failed to start the HTTPS server on port 443.")
        except Exception as e:
            app.logger.error(f"Failed to start HTTPS server: {e}", exc_info=True)
    else:
        app.logger.error("SSL certificate or key file missing. Cannot start HTTPS server.")
        app.logger.info("Falling back to HTTP on port 5001 for development.")
        app.run(host='0.0.0.0', port=5001, debug=True)

