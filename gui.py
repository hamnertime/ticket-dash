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

# Professional Services Group ID from your debug script
PROFESSIONAL_SERVICES_GROUP_ID = 19000234009

FR_SLA_CRITICAL_HOURS = 4
FR_SLA_WARNING_HOURS = 12

# Status IDs from Freshservice
OPEN_STATUS_ID = 2
PENDING_STATUS_ID = 3
WAITING_ON_CUSTOMER_STATUS_ID = 9
WAITING_ON_AGENT_STATUS_ID = 26 # This is now "Customer Replied"
ON_HOLD_STATUS_ID = 23
UPDATE_NEEDED_STATUS_ID = 19

# --- NEW: View Configuration ---
SUPPORTED_VIEWS = {
    "helpdesk": "Helpdesk",
    "professional-services": "Professional Services"
}
DEFAULT_VIEW_SLUG = "helpdesk"

INDEX_TEMPLATE = "index.html"

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

SLA_UPDATE_THRESHOLDS = {
    4: datetime.timedelta(minutes=30),  # Urgent
    3: datetime.timedelta(days=2),    # High
    2: datetime.timedelta(days=3),    # Medium
    1: datetime.timedelta(days=4),    # Low
}

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
    sla_prefix = "FR"
    if ticket_type == "Service Request":
        sla_prefix = "Due"

    if not target_due_dt:
        return f"No {sla_prefix} Due Date", "sla-none", float('inf') - 1000

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


def get_status_text(status_id, ticket_type=""):
    status_map = {
        OPEN_STATUS_ID: "Open",
        PENDING_STATUS_ID: "Pending",
        8: "Scheduled",
        WAITING_ON_CUSTOMER_STATUS_ID: "Waiting on Customer",
        10: "Waiting on Third Party",
        13: "Under Investigation",
        UPDATE_NEEDED_STATUS_ID: "Update Needed",
        ON_HOLD_STATUS_ID: "On Hold",
        WAITING_ON_AGENT_STATUS_ID: "Customer Replied", # UPDATED
    }
    default_text = f"Unknown Status ({status_id})"
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

def load_and_process_tickets(current_view_slug):
    global AGENT_MAPPING, REQUESTER_MAPPING
    list_section1_items = []
    list_section2_items = [] # NEW: Customer Replied
    list_section3_items = [] # Was s2, now Needs Agent / Update Overdue
    list_section4_items = [] # Was s3, now Other

    if not os.path.isdir(TICKETS_DIR):
        app.logger.error(f"Data directory '{TICKETS_DIR}' not found.")
        return [], [], [], []

    now_utc = datetime.datetime.now(datetime.timezone.utc)

    for filename in os.listdir(TICKETS_DIR):
        if filename.endswith(".txt") and filename[:-4].isdigit():
            file_path = os.path.join(TICKETS_DIR, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                group_id = data.get('group_id')
                is_prof_services_ticket = (group_id == PROFESSIONAL_SERVICES_GROUP_ID)

                if current_view_slug == 'professional-services' and not is_prof_services_ticket:
                    continue
                if current_view_slug == 'helpdesk' and is_prof_services_ticket:
                    continue

                ticket_data_item = {
                    'id': data.get('id', int(filename[:-4])),
                    'subject': data.get('subject', 'No Subject Provided'),
                    'requester_id': data.get('requester_id'),
                    'responder_id': data.get('responder_id'),
                    'status_raw': data.get('status'),
                    'priority_raw': data.get('priority'),
                    'description_text': data.get('description_text', ''),
                    'fr_due_by_str': data.get('fr_due_by'),
                    'due_by_str': data.get('due_by'),
                    'updated_at_str': data.get('updated_at'),
                    'created_at_str': data.get('created_at'),
                    'type': data.get('type', 'Unknown'),
                    'stats': data.get('stats', {})
                }

                first_responded_at_val = ticket_data_item['stats'].get('first_responded_at')
                ticket_data_item['first_responded_at_iso'] = first_responded_at_val if first_responded_at_val else None
                agent_id_from_item = ticket_data_item.get('responder_id')
                ticket_data_item['agent_name'] = AGENT_MAPPING.get(agent_id_from_item, f"Agent ID: {agent_id_from_item}") if agent_id_from_item else 'Unassigned'
                requester_id_from_item = ticket_data_item.get('requester_id')
                ticket_data_item['requester_name'] = REQUESTER_MAPPING.get(requester_id_from_item, f"Req. ID: {requester_id_from_item}") if requester_id_from_item else 'N/A'
                sla_target_due_dt_str = ticket_data_item['due_by_str'] if ticket_data_item['type'] == 'Service Request' else ticket_data_item['fr_due_by_str']
                ticket_data_item['sla_target_due_dt_obj'] = parse_datetime_utc(sla_target_due_dt_str)
                ticket_data_item['updated_at_dt_obj'] = parse_datetime_utc(ticket_data_item['updated_at_str'])
                ticket_data_item['created_at_dt_obj'] = parse_datetime_utc(ticket_data_item['created_at_str'])
                ticket_data_item['first_responded_at_dt_obj'] = parse_datetime_utc(ticket_data_item['first_responded_at_iso'])
                ticket_data_item['agent_responded_at_dt_obj'] = parse_datetime_utc(ticket_data_item['stats'].get('agent_responded_at'))
                ticket_data_item['priority_text'] = get_priority_text(ticket_data_item['priority_raw'])
                ticket_data_item['updated_friendly'] = time_since(ticket_data_item['updated_at_dt_obj'])
                ticket_data_item['created_days_old'] = days_since(ticket_data_item['created_at_dt_obj'])
                ticket_data_item['agent_responded_friendly'] = time_since(ticket_data_item['agent_responded_at_dt_obj'])
                original_status_text = get_status_text(ticket_data_item['status_raw'], ticket_data_item['type'])
                ticket_data_item['status_text'] = original_status_text
                ticket_data_item['sla_text'] = f"{original_status_text} ({ticket_data_item['updated_friendly']})"
                ticket_data_item['sla_class'] = "sla-in-progress"

                priority_raw = ticket_data_item.get('priority_raw')
                updated_at_dt = ticket_data_item['updated_at_dt_obj']
                is_update_sla_breached = False
                time_since_update_seconds = float('inf')
                if updated_at_dt:
                    time_diff_since_update = now_utc - updated_at_dt
                    time_since_update_seconds = time_diff_since_update.total_seconds()
                    update_sla_threshold_for_priority = SLA_UPDATE_THRESHOLDS.get(priority_raw)
                    if update_sla_threshold_for_priority and time_diff_since_update > update_sla_threshold_for_priority:
                        is_update_sla_breached = True

                ticket_data_item['_sort_is_update_breached'] = 0 if is_update_sla_breached else 1
                ticket_data_item['_sort_priority'] = (4 - priority_raw) if priority_raw else 4
                ticket_data_item['_sort_neg_time_since_update'] = -time_since_update_seconds
                needs_fr = ticket_data_item['first_responded_at_dt_obj'] is None
                ticket_data_item['_sort_needs_fr'] = 0 if needs_fr else 1
                fr_sla_metric = float('inf')
                if needs_fr and ticket_data_item['type'] == 'Incident':
                     _, _, fr_hours_remaining = get_fr_sla_details(
                        ticket_data_item['type'], ticket_data_item['sla_target_due_dt_obj'],
                        FR_SLA_CRITICAL_HOURS, FR_SLA_WARNING_HOURS
                    )
                     fr_sla_metric = fr_hours_remaining
                ticket_data_item['_sort_fr_sla_metric'] = fr_sla_metric

                # --- NEW Categorization Logic ---
                if ticket_data_item['status_raw'] == WAITING_ON_AGENT_STATUS_ID:
                    ticket_data_item['sla_text'] = f"Customer Replied ({ticket_data_item['updated_friendly']})"
                    ticket_data_item['sla_class'] = "sla-warning"
                    list_section2_items.append(ticket_data_item)
                elif is_update_sla_breached:
                    ticket_data_item['sla_text'] = f"Update Overdue ({original_status_text}, {ticket_data_item['updated_friendly']})"
                    ticket_data_item['sla_class'] = "sla-critical"
                    list_section3_items.append(ticket_data_item) # FIX: Was list_section3_item
                else:
                    section1_trigger_statuses = [OPEN_STATUS_ID, UPDATE_NEEDED_STATUS_ID, PENDING_STATUS_ID]
                    if ticket_data_item['status_raw'] in section1_trigger_statuses:
                        if needs_fr:
                            sla_text_fr, sla_class_fr, _ = get_fr_sla_details(
                                ticket_data_item['type'], ticket_data_item['sla_target_due_dt_obj'],
                                FR_SLA_CRITICAL_HOURS, FR_SLA_WARNING_HOURS
                            )
                            ticket_data_item['sla_text'], ticket_data_item['sla_class'] = sla_text_fr, sla_class_fr
                        else:
                            ticket_data_item['sla_text'] = f"{original_status_text} (FR Met)"
                            ticket_data_item['sla_class'] = "sla-responded"
                        list_section1_items.append(ticket_data_item)
                    else:
                        if ticket_data_item['status_raw'] == WAITING_ON_CUSTOMER_STATUS_ID:
                            ticket_data_item['sla_text'] = "Waiting on Customer"
                            if ticket_data_item['agent_responded_friendly'] != 'N/A':
                                ticket_data_item['sla_text'] += f" (Agent: {ticket_data_item['agent_responded_friendly']})"
                            ticket_data_item['sla_class'] = "sla-responded"
                        elif ticket_data_item['status_raw'] == ON_HOLD_STATUS_ID:
                            ticket_data_item['sla_text'] = f"On Hold ({ticket_data_item['updated_friendly']})"
                            ticket_data_item['sla_class'] = "sla-none"
                        list_section4_items.append(ticket_data_item)

            except json.JSONDecodeError:
                app.logger.error(f"JSON decode error for {filename}")
            except Exception as e:
                app.logger.error(f"Error processing {filename}: {e}", exc_info=True)

    # --- Sorting Logic ---
    list_section1_items.sort(key=lambda i: (
        i['_sort_needs_fr'], i['_sort_fr_sla_metric'], i['_sort_priority'], i['_sort_neg_time_since_update']
    ))
    common_sort_key = lambda i: (
        i['_sort_is_update_breached'], i['_sort_priority'], i['_sort_neg_time_since_update']
    )
    list_section2_items.sort(key=common_sort_key)
    list_section3_items.sort(key=common_sort_key)
    list_section4_items.sort(key=common_sort_key)

    for ticket_list in [list_section1_items, list_section2_items, list_section3_items, list_section4_items]:
        for item_data in ticket_list:
            for key in list(item_data.keys()):
                if key.startswith('_sort_') or key.endswith('_obj'):
                    item_data.pop(key, None)

    return list_section1_items, list_section2_items, list_section3_items, list_section4_items


# --- Routes (unchanged) ---
# ...

# --- Main Dashboard Route ---
@app.route('/')
def dashboard_default():
    return redirect(url_for('dashboard_typed', view_slug=DEFAULT_VIEW_SLUG))

@app.route('/<view_slug>')
def dashboard_typed(view_slug):
    if view_slug not in SUPPORTED_VIEWS:
        abort(404, description=f"Unsupported view: {view_slug}")

    current_view_display = SUPPORTED_VIEWS[view_slug]
    app.logger.info(f"Loading dashboard for view: {current_view_display} (slug: {view_slug})")

    s1_items, s2_items, s3_items, s4_items = load_and_process_tickets(view_slug)
    generated_time_utc = datetime.datetime.now(datetime.timezone.utc)
    dashboard_generated_time_iso = generated_time_utc.isoformat()

    section1_name = f"Open {current_view_display} Tickets"
    section2_name = "Customer Replied"
    section3_name = "Needs Agent / Update Overdue"
    section4_name = f"Other Active {current_view_display} Tickets"

    return render_template(INDEX_TEMPLATE,
                            s1_items=s1_items,
                            s2_items=s2_items,
                            s3_items=s3_items,
                            s4_items=s4_items,
                            dashboard_generated_time_iso=dashboard_generated_time_iso,
                            auto_refresh_ms=AUTO_REFRESH_INTERVAL_SECONDS * 1000,
                            freshservice_base_url=f"https://{FRESHSERVICE_DOMAIN}/a/tickets/",
                            current_view_slug=view_slug,
                            current_view_display=current_view_display,
                            supported_views=SUPPORTED_VIEWS,
                            page_title_display=current_view_display,
                            section1_name=section1_name,
                            section2_name=section2_name,
                            section3_name=section3_name,
                            section4_name=section4_name,
                            OPEN_STATUS_ID=OPEN_STATUS_ID,
                            PENDING_STATUS_ID=PENDING_STATUS_ID,
                            WAITING_ON_CUSTOMER_STATUS_ID=WAITING_ON_CUSTOMER_STATUS_ID,
                            WAITING_ON_AGENT_STATUS_ID=WAITING_ON_AGENT_STATUS_ID
                           )

# --- API Endpoint ---
@app.route('/api/tickets/<view_slug>')
def api_tickets(view_slug):
    if view_slug not in SUPPORTED_VIEWS:
        return jsonify({"error": f"Unsupported view: {view_slug}"}), 404

    current_view_display = SUPPORTED_VIEWS[view_slug]
    app.logger.debug(f"API: /api/tickets/{view_slug} called for view: {current_view_display}")

    s1_items, s2_items, s3_items, s4_items = load_and_process_tickets(view_slug)

    section1_name_api = f"Open {current_view_display} Tickets"
    section2_name_api = "Customer Replied"
    section3_name_api = "Needs Agent / Update Overdue"
    section4_name_api = f"Other Active {current_view_display} Tickets"

    response_data = {
        's1_items': s1_items,
        's2_items': s2_items,
        's3_items': s3_items,
        's4_items': s4_items,
        'total_active_items': len(s1_items) + len(s2_items) + len(s3_items) + len(s4_items),
        'dashboard_generated_time_iso': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'view': current_view_display,
        'section1_name_js': section1_name_api,
        'section2_name_js': section2_name_api,
        'section3_name_js': section3_name_api,
        'section4_name_js': section4_name_api
    }
    app.logger.debug(f"API: Returning {response_data['total_active_items']} total items for view {current_view_display}.")
    return jsonify(response_data)


# ... (rest of the file is unchanged)
if __name__ == '__main__':
    # Startup logic remains the same
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # ...
    try:
        app.run(host='0.0.0.0', port=5001, debug=False, ssl_context=None)
    except Exception as e:
        app.logger.error(f"Failed to start server: {e}", exc_info=True)
