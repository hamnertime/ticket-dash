import os
import json
import datetime
from flask import Flask, render_template, jsonify, abort
import ssl
import logging

# --- Configuration ---
TICKETS_DIR = "./tickets" # This directory still stores "ticket" files from Freshservice
TOKEN_FILE = "token.txt"
STATIC_DIR = "static"
AGENTS_FILE = "./agents.txt"
REQUESTERS_FILE = "./requesters.txt"
AUTO_REFRESH_INTERVAL_SECONDS = 30
FRESHSERVICE_DOMAIN = "integotecllc.freshservice.com"

FR_SLA_CRITICAL_HOURS = 4
FR_SLA_WARNING_HOURS = 12

# Status IDs from Freshservice (these refer to Freshservice's internal status for "tickets"/"incidents")
OPEN_INCIDENT_STATUS_ID = 2 # Renamed variable for clarity in this script's context
PENDING_TICKET_STATUS_ID = 3
WAITING_ON_CUSTOMER_STATUS_ID = 9
WAITING_ON_AGENT = 26
ON_HOLD_STATUS_ID = 23

INDEX = "index.html"

SSL_CERT_FILE = './cert.pem'
SSL_KEY_FILE = './key.pem'

app = Flask(__name__, static_folder=STATIC_DIR)

if not app.debug:
    app.logger.setLevel(logging.INFO)
else:
    app.logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s '
    '[in %(pathname)s:%(lineno)d]'
))
app.logger.addHandler(handler)

AGENT_MAPPING = {}
REQUESTER_MAPPING = {}

def load_agent_mapping(file_path=AGENTS_FILE):
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


def parse_datetime_utc(dt_str):
    if not dt_str: return None
    try:
        if dt_str.endswith('Z'):
            dt_str = dt_str[:-1] + '+00:00'
        return datetime.datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        app.logger.warning(f"Could not parse datetime string: {dt_str}")
        return None

def get_fr_sla_details_for_open_incident(target_due_dt, critical_threshold_hours, warning_threshold_hours): # Renamed
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
    status_map = {
        OPEN_INCIDENT_STATUS_ID: "Open", # Used renamed constant
        PENDING_TICKET_STATUS_ID: "Pending", # This one can remain if it's a generic status
        8: "Scheduled",
        WAITING_ON_CUSTOMER_STATUS_ID: "Waiting on Customer",
        10: "Waiting on Third Party",
        13: "Under Investigation",
        ON_HOLD_STATUS_ID: "On Hold",
        WAITING_ON_AGENT: "Waiting on Agent",
    }
    return status_map.get(status_id, f"Unknown Status ({status_id})")

def get_priority_text(priority_id):
    priority_map = {1: "Low", 2: "Medium", 3: "High", 4: "Urgent"}
    return priority_map.get(priority_id, f"P-{priority_id}")

def time_since(dt_object, default="N/A"):
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
    if not dt_object: return default
    now = datetime.datetime.now(dt_object.tzinfo or datetime.timezone.utc)
    diff_days = (now.date() - dt_object.date()).days

    if diff_days < 0: return "Future Date"
    if diff_days == 0: return "Today"
    if diff_days == 1: return "1 day old"
    return f"{diff_days} days old"

def load_and_process_incidents(): # Renamed function
    global AGENT_MAPPING, REQUESTER_MAPPING
    list_status_open_incidents = []
    list_waiting_on_agent_incidents = []
    list_section3_candidates = [] # For other active incidents

    if not os.path.isdir(TICKETS_DIR): # Directory still named TICKETS_DIR as it holds raw data
        app.logger.error(f"Data directory '{TICKETS_DIR}' not found.")
        return [], [], []

    for filename in os.listdir(TICKETS_DIR):
        if filename.endswith(".txt") and filename[:-4].isdigit():
            file_path = os.path.join(TICKETS_DIR, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Freshservice items are called "tickets", but we display them as "incidents"
                # For clarity, internal variable is 'incident_data_item'
                incident_data_item = {
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
                    'type': data.get('type', 'N/A'), # This should be "Incident" based on watcher
                    'stats': data.get('stats', {})
                }

                first_responded_at_val = incident_data_item['stats'].get('first_responded_at')
                incident_data_item['first_responded_at_iso'] = first_responded_at_val if first_responded_at_val else None

                agent_id_from_item = incident_data_item.get('responder_id')
                incident_data_item['agent_name'] = AGENT_MAPPING.get(agent_id_from_item, f"Agent ID: {agent_id_from_item}") if agent_id_from_item else 'Unassigned'

                requester_id_from_item = incident_data_item.get('requester_id')
                incident_data_item['requester_name'] = REQUESTER_MAPPING.get(requester_id_from_item, f"Req. ID: {requester_id_from_item}") if requester_id_from_item else 'N/A'

                incident_data_item['fr_due_by_dt'] = parse_datetime_utc(incident_data_item['fr_due_by_str'])
                incident_data_item['updated_at_dt'] = parse_datetime_utc(incident_data_item['updated_at_str'])
                incident_data_item['created_at_dt'] = parse_datetime_utc(incident_data_item['created_at_str'])
                incident_data_item['first_responded_at_dt'] = parse_datetime_utc(incident_data_item['first_responded_at_iso'])
                incident_data_item['agent_responded_at_dt'] = parse_datetime_utc(incident_data_item['stats'].get('agent_responded_at'))

                incident_data_item['priority_text'] = get_priority_text(incident_data_item['priority_raw'])
                incident_data_item['updated_friendly'] = time_since(incident_data_item['updated_at_dt'])
                incident_data_item['created_days_old'] = days_since(incident_data_item['created_at_dt'])
                incident_data_item['agent_responded_friendly'] = time_since(incident_data_item['agent_responded_at_dt'])
                item_updated_timestamp = incident_data_item['updated_at_dt'].timestamp() if incident_data_item['updated_at_dt'] else 0.0

                current_status_text = get_status_text(incident_data_item['status_raw'])
                incident_data_item['status_text'] = current_status_text
                incident_data_item['sla_text'] = f"{current_status_text} ({incident_data_item['updated_friendly']})"
                incident_data_item['sla_class'] = "sla-in-progress"

                if incident_data_item['status_raw'] == OPEN_INCIDENT_STATUS_ID: # Use renamed constant
                    if incident_data_item['first_responded_at_dt'] is None:
                        sla_text, sla_class, fr_sla_sort_key = get_fr_sla_details_for_open_incident(
                            incident_data_item['fr_due_by_dt'], FR_SLA_CRITICAL_HOURS, FR_SLA_WARNING_HOURS)
                        incident_data_item['sla_text'], incident_data_item['sla_class'] = sla_text, sla_class
                        incident_data_item['action_sort_key_tuple'] = (0, fr_sla_sort_key, -item_updated_timestamp)
                    else:
                        incident_data_item['sla_text'] = f"Open ({incident_data_item['updated_friendly']})"
                        incident_data_item['sla_class'] = "sla-responded"
                        incident_data_item['action_sort_key_tuple'] = (1, -item_updated_timestamp, 0)
                    list_status_open_incidents.append(incident_data_item)

                elif incident_data_item['status_raw'] == WAITING_ON_AGENT:
                    incident_data_item['sla_text'] = f"Waiting on Agent ({incident_data_item['updated_friendly']})"
                    incident_data_item['sla_class'] = "sla-warning"
                    incident_data_item['action_sort_key'] = item_updated_timestamp
                    list_waiting_on_agent_incidents.append(incident_data_item)

                else:
                    if incident_data_item['status_raw'] == WAITING_ON_CUSTOMER_STATUS_ID:
                        incident_data_item['sla_text'] = "Waiting on Customer"
                        if incident_data_item['agent_responded_friendly'] != 'N/A':
                            incident_data_item['sla_text'] += f" (Agent: {incident_data_item['agent_responded_friendly']})"
                        incident_data_item['sla_class'] = "sla-responded"
                    elif incident_data_item['status_raw'] == ON_HOLD_STATUS_ID:
                        incident_data_item['sla_text'] = f"On Hold ({incident_data_item['updated_friendly']})"
                        incident_data_item['sla_class'] = "sla-none"
                    elif incident_data_item['status_raw'] == PENDING_TICKET_STATUS_ID: # or PENDING_INCIDENT_STATUS_ID if defined
                        incident_data_item['sla_text'] = f"Pending ({incident_data_item['updated_friendly']})"
                        incident_data_item['sla_class'] = "sla-in-progress"

                    incident_data_item['action_sort_key'] = item_updated_timestamp
                    list_section3_candidates.append(incident_data_item)

            except json.JSONDecodeError:
                app.logger.error(f"JSON decode error for {filename}")
            except Exception as e:
                app.logger.error(f"Error processing {filename}: {e}", exc_info=True)

    list_status_open_incidents.sort(key=lambda i: i.get('action_sort_key_tuple', (2, float('inf'), 0)))
    list_waiting_on_agent_incidents.sort(key=lambda i: i.get('action_sort_key', float('inf')))
    list_section3_candidates.sort(key=lambda i: i.get('action_sort_key', float('inf')))

    for incident_list in [list_status_open_incidents, list_waiting_on_agent_incidents, list_section3_candidates]:
        for item_data in incident_list: # Renamed from ticket_data to item_data
            item_data.pop('fr_due_by_dt', None)
            item_data.pop('updated_at_dt', None)
            item_data.pop('created_at_dt', None)
            item_data.pop('first_responded_at_dt', None)
            item_data.pop('agent_responded_at_dt', None)
            item_data.pop('action_sort_key_tuple', None)
            item_data.pop('action_sort_key', None)

    return list_status_open_incidents, list_waiting_on_agent_incidents, list_section3_candidates

@app.route(f'/{TICKETS_DIR}/<path:filename>')
def block_ticket_files(filename): abort(403) # TICKETS_DIR still refers to data source

# ... (other block routes for TOKEN_FILE, AGENTS_FILE etc. remain the same) ...
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
    s1_open_incidents, s2_waiting_agent_incidents, s3_remaining_incidents = load_and_process_incidents() # Renamed
    generated_time_utc = datetime.datetime.now(datetime.timezone.utc)
    dashboard_generated_time_iso = generated_time_utc.isoformat()

    return render_template(INDEX,
                            s1_open_incidents=s1_open_incidents,
                            s2_waiting_agent_incidents=s2_waiting_agent_incidents,
                            s3_remaining_incidents=s3_remaining_incidents,
                            dashboard_generated_time_iso=dashboard_generated_time_iso,
                            auto_refresh_ms=AUTO_REFRESH_INTERVAL_SECONDS * 1000,
                            freshservice_base_url=f"https://{FRESHSERVICE_DOMAIN}/a/tickets/", # Freshservice URL still uses /tickets/
                            OPEN_INCIDENT_STATUS_ID=OPEN_INCIDENT_STATUS_ID, # Pass renamed constant
                            WAITING_ON_CUSTOMER_STATUS_ID=WAITING_ON_CUSTOMER_STATUS_ID,
                            WAITING_ON_AGENT_STATUS_ID=WAITING_ON_AGENT)

@app.route('/api/incidents') # Renamed API endpoint
def api_incidents(): # Renamed function
    app.logger.debug("API: /api/incidents called")
    s1_open_incidents, s2_waiting_agent_incidents, s3_remaining_incidents = load_and_process_incidents() # Renamed

    response_data = {
        's1_open_incidents': s1_open_incidents, # Renamed key
        's2_waiting_agent_incidents': s2_waiting_agent_incidents, # Renamed key
        's3_remaining_incidents': s3_remaining_incidents, # Renamed key
        'total_active_incidents': len(s1_open_incidents) + len(s2_waiting_agent_incidents) + len(s3_remaining_incidents), # Renamed key
        'dashboard_generated_time_iso': datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    app.logger.debug(f"API: Returning {response_data['total_active_incidents']} total incidents.")
    return jsonify(response_data)


@app.route('/health')
def health_check():
    return "OK", 200


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(script_dir, 'templates')

    for dir_path in [TICKETS_DIR, templates_dir, STATIC_DIR]: # TICKETS_DIR is data source
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

    # ... (rest of the security checks and server run logic remains largely the same) ...
    static_path_abs = os.path.abspath(STATIC_DIR)
    sensitive_files_in_root = [TOKEN_FILE, AGENTS_FILE, REQUESTERS_FILE, SSL_CERT_FILE, SSL_KEY_FILE]

    for file_name in sensitive_files_in_root:
        app_root_file_path = os.path.join(script_dir, file_name)
        static_file_path = os.path.join(static_path_abs, file_name)

        if os.path.exists(static_file_path):
            level = app.logger.critical if file_name in [TOKEN_FILE, SSL_KEY_FILE] else app.logger.warning
            level(
                f"{'SECURITY WARNING' if file_name in [TOKEN_FILE, SSL_KEY_FILE] else 'NOTICE'}: '{file_name}' found in static dir '{static_path_abs}'. "
                "Consider moving it outside web-accessible folders. Direct access routes are blocked."
            )
        elif os.path.exists(app_root_file_path):
            if file_name in [TOKEN_FILE, SSL_KEY_FILE]:
                 app.logger.critical(
                    f"SECURITY WARNING: Sensitive file '{file_name}' found in the application root '{app_root_file_path}'. "
                    "Consider moving it to a more secure, non-web-accessible location."
                )
        elif file_name in [AGENTS_FILE, REQUESTERS_FILE] and not os.path.exists(app_root_file_path):
             app.logger.warning(f"Mapping file '{file_name}' not found in application root or static directory.")


    app.logger.info(f"Starting Flask app. Data directory: '{os.path.abspath(TICKETS_DIR)}'") # TICKETS_DIR is data source
    app.logger.info(f"FR SLA Critical: < {FR_SLA_CRITICAL_HOURS} hrs, Warning: < {FR_SLA_WARNING_HOURS} hrs.")

    cert_path = os.path.abspath(SSL_CERT_FILE)
    key_path = os.path.abspath(SSL_KEY_FILE)

    cert_exists = os.path.exists(cert_path)
    key_exists = os.path.exists(key_path)

    if not cert_exists:
        app.logger.warning(f"SSL certificate file not found at: {cert_path}") # Changed to warning
    if not key_exists:
        app.logger.warning(f"SSL private key file not found at: {key_path}") # Changed to warning

    use_https = cert_exists and key_exists
    protocol = "https" if use_https else "http"
    port = 443 if use_https else 5001

    if use_https:
        app.logger.info(f"Attempting to start HTTPS server on port {port}.")
        app.logger.info(f"Using SSL certificate: {cert_path}")
        app.logger.info(f"Using SSL private key: {key_path}")
        if port == 443 and os.name != 'nt': # sudo usually not needed on Windows for ports
            app.logger.warning("Running on port 443 typically requires superuser privileges (e.g., use 'sudo python3 gui.py').")
        ssl_context = (cert_path, key_path)
    else:
        app.logger.info("SSL certificate or key file missing or not fully configured. Cannot start HTTPS server.")
        app.logger.info(f"Falling back to HTTP on port {port} for development.")
        ssl_context = None

    app.logger.info(f"Incident Dashboard will be available at {protocol}://localhost:{port}/")

    try:
        app.run(host='0.0.0.0', port=port, debug=False, ssl_context=ssl_context)
    except OSError as e:
        if ("Permission denied" in str(e) or "Errno 13" in str(e)) and port == 443 and os.name != 'nt':
            app.logger.error(f"OSError: {e}. Could not bind to port 443. Try running with sudo.")
        else:
            app.logger.error(f"OSError: {e}. Failed to start the server on port {port}.")
    except Exception as e:
        app.logger.error(f"Failed to start server: {e}", exc_info=True)
