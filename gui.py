import os
import json
import datetime
from flask import Flask, render_template, jsonify, abort, redirect, url_for
import ssl
import logging

# --- Configuration ---
TICKETS_DIR = "./tickets"
TOKEN_FILE = "token.txt"
STATIC_DIR = "static"
AGENTS_FILE = "./agents.txt"
REQUESTERS_FILE = "./requesters.txt"
AUTO_REFRESH_INTERVAL_SECONDS = 30
FRESHSERVICE_DOMAIN = "integotecllc.freshservice.com"

FR_SLA_CRITICAL_HOURS = 4
FR_SLA_WARNING_HOURS = 12

# Status IDs from Freshservice
OPEN_STATUS_ID = 2 # Generic "Open" - might be named "Open" for Incidents, "Pending" for SRs
PENDING_STATUS_ID = 3 # Often used for SRs waiting for items/approvals
WAITING_ON_CUSTOMER_STATUS_ID = 9
WAITING_ON_AGENT_STATUS_ID = 26 # More specific to Freshservice workflow
ON_HOLD_STATUS_ID = 23
UPDATE_NEEDED_STATUS_ID = 19


# Ticket Types (as they appear in Freshservice data)
TICKET_TYPE_INCIDENT = "Incident"
TICKET_TYPE_SERVICE_REQUEST = "Service Request"
SUPPORTED_TICKET_TYPES = {
    "incidents": TICKET_TYPE_INCIDENT,
    "service-requests": TICKET_TYPE_SERVICE_REQUEST
}
DEFAULT_TICKET_TYPE_SLUG = "incidents"


INDEX_TEMPLATE = "index.html" # Renamed for clarity

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

def load_mapping_file(file_path, item_type_name="item"):
    mapping = {}
    if not os.path.exists(file_path):
        app.logger.warning(f"{item_type_name.capitalize()}s file '{file_path}' not found. Names will default to IDs.")
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
                    app.logger.warning(f"Could not parse {item_type_name} ID '{item_id_str}' as int on line {line_number} in '{file_path}'.")
            app.logger.info(f"Successfully loaded {len(mapping)} {item_type_name}(s) from '{file_path}'.")
    except Exception as e:
        app.logger.error(f"Error loading {item_type_name} mapping from '{file_path}': {e}", exc_info=True)
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

def get_fr_sla_details(ticket_type, target_due_dt, critical_threshold_hours, warning_threshold_hours):
    # FR SLA might be more relevant for Incidents. Service Requests might use overall 'due_by'.
    # For now, keep generic, but this could be customized.
    sla_prefix = "FR" # Default to First Response
    if ticket_type == TICKET_TYPE_SERVICE_REQUEST:
        sla_prefix = "Due" # Or "Resolution" - depends on what `fr_due_by` means for SRs in Freshservice

    if not target_due_dt:
        return f"No {sla_prefix} Due Date", "sla-none", float('inf') - 1000 # Sort key

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    time_diff_seconds = (target_due_dt - now_utc).total_seconds()
    hours_remaining_for_status = time_diff_seconds / 3600.0

    if abs(time_diff_seconds) >= (2 * 24 * 60 * 60): # 2 days
        unit, formatted_value = "days", f"{hours_remaining_for_status / 24.0:.1f}"
    elif abs(time_diff_seconds) >= (60 * 60): # 1 hour
        unit, formatted_value = "hours", f"{hours_remaining_for_status:.1f}"
    elif abs(time_diff_seconds) >= 60: # 1 minute
        unit, formatted_value = "min", f"{time_diff_seconds / 60.0:.0f}"
    else:
        unit, formatted_value = "sec", f"{time_diff_seconds:.0f}"

    sla_class = "sla-normal"
    sla_text = f"{formatted_value} {unit} for {sla_prefix}"

    if hours_remaining_for_status < 0:
        sla_text = f"{sla_prefix} Overdue by {formatted_value.lstrip('-')} {unit}"
        sla_class = "sla-overdue"
    elif hours_remaining_for_status < critical_threshold_hours:
        sla_class = "sla-critical"
    elif hours_remaining_for_status < warning_threshold_hours:
        sla_class = "sla-warning"
    return sla_text, sla_class, hours_remaining_for_status


def get_status_text(status_id, ticket_type=""): # ticket_type can be used for more specific status text if needed
    # These are common Freshservice statuses. They might apply to both Incidents and SRs,
    # or SRs might have more specific ones like "Fulfilled", "Cancelled".
    status_map = {
        OPEN_STATUS_ID: "Open",
        PENDING_STATUS_ID: "Pending",
        8: "Scheduled", # Might be custom
        WAITING_ON_CUSTOMER_STATUS_ID: "Waiting on Customer",
        10: "Waiting on Third Party", # Might be custom
        13: "Under Investigation", # Likely Incident specific
        19: "Update Needed",       # <-- ADD THIS LINE (using 19 directly or UPDATE_NEEDED_STATUS_ID if defined)
        ON_HOLD_STATUS_ID: "On Hold",
        WAITING_ON_AGENT_STATUS_ID: "Waiting on Agent",
        # Add Service Request specific statuses if known, e.g.:
        # 4: "Resolved", # If used for SRs
        # 5: "Closed",   # If used for SRs
        # 20: "Request Fulfilled" # Example
    }
    default_text = f"Unknown Status ({status_id})"
    # if ticket_type == TICKET_TYPE_SERVICE_REQUEST and status_id == OPEN_STATUS_ID:
    #     return "Pending" # Example: "Open" for Incident might mean "Pending" for SR
    return status_map.get(status_id, default_text)


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

def load_and_process_tickets(current_ticket_type_filter):
    global AGENT_MAPPING, REQUESTER_MAPPING
    list_section1_items = [] # e.g., Open Incidents / Pending SRs needing FR/Due attention
    list_section2_items = [] # e.g., Waiting on Agent
    list_section3_items = [] # Other active tickets

    if not os.path.isdir(TICKETS_DIR):
        app.logger.error(f"Data directory '{TICKETS_DIR}' not found.")
        return [], [], []

    for filename in os.listdir(TICKETS_DIR):
        if filename.endswith(".txt") and filename[:-4].isdigit():
            file_path = os.path.join(TICKETS_DIR, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                ticket_type_from_file = data.get('type', 'Unknown')
                if ticket_type_from_file != current_ticket_type_filter:
                    continue # Skip if not the type we are currently displaying

                ticket_data_item = {
                    'id': data.get('id', int(filename[:-4])),
                    'subject': data.get('subject', 'No Subject Provided'),
                    'requester_id': data.get('requester_id'),
                    'responder_id': data.get('responder_id'),
                    'status_raw': data.get('status'),
                    'priority_raw': data.get('priority'),
                    'description_text': data.get('description_text', ''),
                    'fr_due_by_str': data.get('fr_due_by'), # May represent 'due_by' for SRs
                    'due_by_str': data.get('due_by'), # Actual resolution due date, more common for SRs
                    'updated_at_str': data.get('updated_at'),
                    'created_at_str': data.get('created_at'),
                    'type': ticket_type_from_file,
                    'stats': data.get('stats', {})
                }

                first_responded_at_val = ticket_data_item['stats'].get('first_responded_at')
                ticket_data_item['first_responded_at_iso'] = first_responded_at_val if first_responded_at_val else None

                agent_id_from_item = ticket_data_item.get('responder_id')
                ticket_data_item['agent_name'] = AGENT_MAPPING.get(agent_id_from_item, f"Agent ID: {agent_id_from_item}") if agent_id_from_item else 'Unassigned'

                requester_id_from_item = ticket_data_item.get('requester_id')
                ticket_data_item['requester_name'] = REQUESTER_MAPPING.get(requester_id_from_item, f"Req. ID: {requester_id_from_item}") if requester_id_from_item else 'N/A'

                # Use 'due_by_str' for Service Requests if 'fr_due_by_str' is not primary for them.
                # For simplicity, we'll use fr_due_by for SLA logic for now, but this can be refined.
                # If 'due_by_str' (resolution due) is more relevant for SRs, use that for sla_target_due_dt
                sla_target_due_dt_str = ticket_data_item['fr_due_by_str']
                if ticket_data_item['type'] == TICKET_TYPE_SERVICE_REQUEST and ticket_data_item['due_by_str']:
                     # Potentially prioritize 'due_by' for SRs if it's the main SLA driver
                     # sla_target_due_dt_str = ticket_data_item['due_by_str']
                     pass # For now, keep fr_due_by consistent for SLA logic below

                ticket_data_item['sla_target_due_dt'] = parse_datetime_utc(sla_target_due_dt_str)
                ticket_data_item['updated_at_dt'] = parse_datetime_utc(ticket_data_item['updated_at_str'])
                ticket_data_item['created_at_dt'] = parse_datetime_utc(ticket_data_item['created_at_str'])
                ticket_data_item['first_responded_at_dt'] = parse_datetime_utc(ticket_data_item['first_responded_at_iso'])
                ticket_data_item['agent_responded_at_dt'] = parse_datetime_utc(ticket_data_item['stats'].get('agent_responded_at'))

                ticket_data_item['priority_text'] = get_priority_text(ticket_data_item['priority_raw'])
                ticket_data_item['updated_friendly'] = time_since(ticket_data_item['updated_at_dt'])
                ticket_data_item['created_days_old'] = days_since(ticket_data_item['created_at_dt'])
                ticket_data_item['agent_responded_friendly'] = time_since(ticket_data_item['agent_responded_at_dt'])
                item_updated_timestamp = ticket_data_item['updated_at_dt'].timestamp() if ticket_data_item['updated_at_dt'] else 0.0

                current_status_text = get_status_text(ticket_data_item['status_raw'], ticket_data_item['type'])
                ticket_data_item['status_text'] = current_status_text
                ticket_data_item['sla_text'] = f"{current_status_text} ({ticket_data_item['updated_friendly']})"
                ticket_data_item['sla_class'] = "sla-in-progress" # Default

                # Section 1: Items requiring first response / initial action (Open Incidents, Pending SRs)
                # OPEN_STATUS_ID for incidents, PENDING_STATUS_ID or OPEN_STATUS_ID for SRs might be relevant here.
                # This logic needs to be flexible for both types.
                # For Incidents, fr_due_by is key. For SRs, fr_due_by or due_by might be key.
                section1_trigger_statuses = [OPEN_STATUS_ID, UPDATE_NEEDED_STATUS_ID] # Added UPDATE_NEEDED_STATUS_ID
                if ticket_data_item['type'] == TICKET_TYPE_SERVICE_REQUEST:
                    section1_trigger_statuses.append(PENDING_STATUS_ID) # SRs might be "Pending" but need action

                if ticket_data_item['status_raw'] in section1_trigger_statuses:
                    # For Incidents, if not first responded, show FR SLA.
                    # For Service Requests, if not first responded (if applicable) or overall due_by is approaching.
                    # We use 'first_responded_at_dt' as a common check.
                    if ticket_data_item['first_responded_at_dt'] is None: # or check based on SR specific fields
                        sla_text, sla_class, sla_sort_key = get_fr_sla_details(
                            ticket_data_item['type'],
                            ticket_data_item['sla_target_due_dt'],
                            FR_SLA_CRITICAL_HOURS, FR_SLA_WARNING_HOURS
                        )
                        ticket_data_item['sla_text'], ticket_data_item['sla_class'] = sla_text, sla_class
                        ticket_data_item['action_sort_key_tuple'] = (0, sla_sort_key, -item_updated_timestamp)
                    else: # Already responded or FR not applicable/passed
                        ticket_data_item['sla_text'] = f"{current_status_text} ({ticket_data_item['updated_friendly']})"
                        ticket_data_item['sla_class'] = "sla-responded" # Or some other appropriate class
                        ticket_data_item['action_sort_key_tuple'] = (1, -item_updated_timestamp, 0)
                    list_section1_items.append(ticket_data_item)

                elif ticket_data_item['status_raw'] == WAITING_ON_AGENT_STATUS_ID:
                    ticket_data_item['sla_text'] = f"Waiting on Agent ({ticket_data_item['updated_friendly']})"
                    ticket_data_item['sla_class'] = "sla-warning" # Or a color indicating agent action needed
                    ticket_data_item['action_sort_key'] = item_updated_timestamp
                    list_section2_items.append(ticket_data_item)

                else: # Other active statuses (Waiting on Customer, On Hold, etc.)
                    if ticket_data_item['status_raw'] == WAITING_ON_CUSTOMER_STATUS_ID:
                        ticket_data_item['sla_text'] = "Waiting on Customer"
                        if ticket_data_item['agent_responded_friendly'] != 'N/A':
                            ticket_data_item['sla_text'] += f" (Agent: {ticket_data_item['agent_responded_friendly']})"
                        ticket_data_item['sla_class'] = "sla-responded" # Or "sla-customer-reply"
                    elif ticket_data_item['status_raw'] == ON_HOLD_STATUS_ID:
                        ticket_data_item['sla_text'] = f"On Hold ({ticket_data_item['updated_friendly']})"
                        ticket_data_item['sla_class'] = "sla-none"
                    # Add more else-if for other statuses relevant to section 3

                    ticket_data_item['action_sort_key'] = item_updated_timestamp
                    list_section3_items.append(ticket_data_item)

            except json.JSONDecodeError:
                app.logger.error(f"JSON decode error for {filename}")
            except Exception as e:
                app.logger.error(f"Error processing {filename}: {e}", exc_info=True)

    # Sort each list
    list_section1_items.sort(key=lambda i: i.get('action_sort_key_tuple', (2, float('inf'), 0)))
    list_section2_items.sort(key=lambda i: i.get('action_sort_key', float('inf')))
    list_section3_items.sort(key=lambda i: i.get('action_sort_key', float('inf')))

    # Clean up temporary datetime objects and sort keys before sending to template/JSON
    for ticket_list in [list_section1_items, list_section2_items, list_section3_items]:
        for item_data in ticket_list:
            item_data.pop('sla_target_due_dt', None)
            item_data.pop('updated_at_dt', None)
            item_data.pop('created_at_dt', None)
            item_data.pop('first_responded_at_dt', None)
            item_data.pop('agent_responded_at_dt', None)
            item_data.pop('action_sort_key_tuple', None)
            item_data.pop('action_sort_key', None)

    return list_section1_items, list_section2_items, list_section3_items


# --- Routes to block direct access to sensitive files ---
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

@app.route(f'/{os.path.basename(SSL_CERT_FILE)}')
def block_ssl_cert_file_root(): abort(403)

@app.route(f'/{STATIC_DIR}/{os.path.basename(SSL_CERT_FILE)}')
def block_ssl_cert_file_static(): abort(403)

@app.route(f'/{os.path.basename(SSL_KEY_FILE)}')
def block_ssl_key_file_root(): abort(403)

@app.route(f'/{STATIC_DIR}/{os.path.basename(SSL_KEY_FILE)}')
def block_ssl_key_file_static(): abort(403)


# --- Main Dashboard Route ---
@app.route('/')
def dashboard_default():
    return redirect(url_for('dashboard_typed', ticket_type_slug=DEFAULT_TICKET_TYPE_SLUG))

@app.route('/<ticket_type_slug>')
def dashboard_typed(ticket_type_slug):
    if ticket_type_slug not in SUPPORTED_TICKET_TYPES:
        abort(404, description=f"Unsupported ticket type: {ticket_type_slug}")

    current_ticket_type = SUPPORTED_TICKET_TYPES[ticket_type_slug]
    app.logger.info(f"Loading dashboard for ticket type: {current_ticket_type} (slug: {ticket_type_slug})")

    s1_items, s2_items, s3_items = load_and_process_tickets(current_ticket_type)
    generated_time_utc = datetime.datetime.now(datetime.timezone.utc)
    dashboard_generated_time_iso = generated_time_utc.isoformat()

    # Determine display names for sections based on ticket type
    section1_name = "Open Incidents"
    section2_name = "Incidents Waiting on Agent"
    section3_name = "Other Active Incidents"
    page_title_type = "Incident"

    if current_ticket_type == TICKET_TYPE_SERVICE_REQUEST:
        section1_name = "Pending Service Requests" # Or "Open SRs Needing Action"
        section2_name = "Service Requests Waiting on Agent"
        section3_name = "Other Active Service Requests"
        page_title_type = "Service Request"


    return render_template(INDEX_TEMPLATE,
                            s1_items=s1_items,
                            s2_items=s2_items,
                            s3_items=s3_items,
                            dashboard_generated_time_iso=dashboard_generated_time_iso,
                            auto_refresh_ms=AUTO_REFRESH_INTERVAL_SECONDS * 1000,
                            freshservice_base_url=f"https://{FRESHSERVICE_DOMAIN}/a/tickets/",
                            current_ticket_type_slug=ticket_type_slug,
                            current_ticket_type_display=current_ticket_type,
                            supported_ticket_types=SUPPORTED_TICKET_TYPES,
                            page_title_type=page_title_type,
                            section1_name=section1_name,
                            section2_name=section2_name,
                            section3_name=section3_name,
                            # Pass status IDs if needed by template, though JS might handle this based on type
                            OPEN_STATUS_ID=OPEN_STATUS_ID,
                            PENDING_STATUS_ID=PENDING_STATUS_ID,
                            WAITING_ON_CUSTOMER_STATUS_ID=WAITING_ON_CUSTOMER_STATUS_ID,
                            WAITING_ON_AGENT_STATUS_ID=WAITING_ON_AGENT_STATUS_ID
                           )

# --- API Endpoint ---
@app.route('/api/tickets/<ticket_type_slug>')
def api_tickets(ticket_type_slug):
    if ticket_type_slug not in SUPPORTED_TICKET_TYPES:
        return jsonify({"error": f"Unsupported ticket type: {ticket_type_slug}"}), 404

    current_ticket_type = SUPPORTED_TICKET_TYPES[ticket_type_slug]
    app.logger.debug(f"API: /api/tickets/{ticket_type_slug} called for type: {current_ticket_type}")

    s1_items, s2_items, s3_items = load_and_process_tickets(current_ticket_type)

    response_data = {
        's1_items': s1_items,
        's2_items': s2_items,
        's3_items': s3_items,
        'total_active_items': len(s1_items) + len(s2_items) + len(s3_items),
        'dashboard_generated_time_iso': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'ticket_type': current_ticket_type
    }
    app.logger.debug(f"API: Returning {response_data['total_active_items']} total items for type {current_ticket_type}.")
    return jsonify(response_data)


@app.route('/health')
def health_check():
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
                if dir_path in [templates_dir, STATIC_DIR]: # Essential for Flask
                     exit(f"Error: Could not create essential directory {abs_dir_path}. Exiting.")

    AGENT_MAPPING = load_mapping_file(AGENTS_FILE, "agent")
    if not AGENT_MAPPING: app.logger.warning(f"Agent mapping from '{AGENTS_FILE}' is empty or failed to load.")
    REQUESTER_MAPPING = load_mapping_file(REQUESTERS_FILE, "requester")
    if not REQUESTER_MAPPING: app.logger.warning(f"Requester mapping from '{REQUESTERS_FILE}' is empty or failed to load.")

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


    app.logger.info(f"Starting Flask app. Data directory: '{os.path.abspath(TICKETS_DIR)}'")
    app.logger.info(f"FR SLA Critical: < {FR_SLA_CRITICAL_HOURS} hrs, Warning: < {FR_SLA_WARNING_HOURS} hrs.")
    app.logger.info(f"Supported ticket types: {SUPPORTED_TICKET_TYPES}")


    cert_path = os.path.abspath(SSL_CERT_FILE)
    key_path = os.path.abspath(SSL_KEY_FILE)
    cert_exists = os.path.exists(cert_path)
    key_exists = os.path.exists(key_path)

    if not cert_exists: app.logger.warning(f"SSL certificate file not found at: {cert_path}")
    if not key_exists: app.logger.warning(f"SSL private key file not found at: {key_path}")

    use_https = cert_exists and key_exists
    protocol = "https" if use_https else "http"
    port = 443 if use_https else 5001
    ssl_context = (cert_path, key_path) if use_https else None

    if use_https:
        app.logger.info(f"Attempting to start HTTPS server on port {port}.")
        app.logger.info(f"Using SSL certificate: {cert_path}")
        app.logger.info(f"Using SSL private key: {key_path}")
    else:
        app.logger.info("SSL certificate or key file missing or not fully configured.")
        app.logger.info(f"Falling back to HTTP on port {port}.")

    app.logger.info(f"Dashboard will be available at {protocol}://localhost:{port}/")
    if port == 443 and os.name != 'nt' and not use_https: # Warn if trying HTTP on 443 without intending HTTPS
         app.logger.warning("Running on port 443 without HTTPS. This is unusual. Ensure `authbind` is used if not running as root.")
    elif port == 443 and os.name != 'nt' and use_https:
        app.logger.info("If not running as root, ensure `authbind --deep python3 gui.py` is used for port 443.")


    try:
        app.run(host='0.0.0.0', port=port, debug=False, ssl_context=ssl_context)
    except OSError as e:
        if ("Permission denied" in str(e) or "Errno 13" in str(e)) and port == 443 and os.name != 'nt':
            app.logger.error(f"OSError: {e}. Could not bind to port 443. Try running with sudo or using authbind.")
        else:
            app.logger.error(f"OSError: {e}. Failed to start the server on port {port}.")
    except Exception as e:
        app.logger.error(f"Failed to start server: {e}", exc_info=True)
