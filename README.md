# Ticket Dash (Freshservice Ticket Dashboard)

**Ticket Dash** is a Flask-based web application that provides a dashboard for viewing and monitoring helpdesk tickets. It was initially designed to work with Freshservice ticket data but can be adapted for other ticketing systems by modifying the data-fetching script.

The dashboard offers categorized views of tickets, SLA status indicators, priority highlighting, and a theme toggle for user preference.

## Features

* **Near Real-Time Ticket Display:** Shows ticket data fetched and updated by the `ticket_watcher.py` script.
* **Categorized Views:**
    * Open Tickets (requiring first response or further action)
    * Tickets Waiting on Agent
    * Other Active Tickets (e.g., On Hold, Waiting on Customer)
* **SLA Status Indicators:** Visual cues for tickets that are Overdue, Critical, Warning, etc.
* **Priority Highlighting:** Clearly distinguishes ticket priorities (Low, Medium, High, Urgent).
* **Dark/Light Theme Toggle:** User-selectable interface theme.
* **Description Tooltips:** Hover over truncated ticket subjects to see a longer description.
* **Configurable Mappings:** Agent and Requester names are mapped from IDs using simple text files.
* **Adaptable:** The data source (`ticket_watcher.py`) can be rewritten to support other ticketing systems while keeping the Flask GUI largely the same.
* **Secure Setup:** Includes options for running over HTTPS.
* **Luxafor Integration:** `blinky.py` script provides visual ticket status updates via a Luxafor USB LED indicator.
* **Systemd Services:** Includes service files for running `gui.py`, `ticket_watcher.py`, and `blinky.py` as background services on boot.

## Tech Stack

* **Backend:** Python, Flask
* **Frontend:** HTML, CSS, JavaScript
* **Data Source:** Designed to read JSON files generated from the Freshservice API (via `ticket_watcher.py`).
* **Visual Indicator:** `pyluxafor` for Luxafor Flag.
* **Service Management:** `systemd` (for Linux).

## Project Files and Directories

* **`gui.py`**: The main Flask web application that serves the dashboard.
* **`ticket_watcher.py`**: Script responsible for fetching ticket data (e.g., from Freshservice) and updating the `./tickets/` directory.
* **`blinky.py`**: Script to control a Luxafor USB LED indicator based on ticket status.
* **`update_requesters.py`**: Script to fetch and update requester information.
* **`tickets/`**: Directory where `ticket_watcher.py` stores individual ticket data as JSON files (e.g., `123.txt`, `124.txt`).
* **`static/`**: Contains frontend assets.
    * **`static/css/style.css`**: Custom CSS styles for the dashboard.
    * **`static/js/theme.js`**: JavaScript for theme toggling and any other dynamic frontend logic.
* **`templates/`**: Contains HTML templates.
    * **`templates/index.html`**: The main HTML template for the dashboard.
* **`startup/`**: (Recommended) Contains systemd service files for managing the application components.
    * `ticket-dash.service`: For `gui.py`.
    * `ticket-watcher.service`: For `ticket_watcher.py`.
    * `blinky.service`: For `blinky.py`.
* **`token.txt`**: Stores the Freshservice API key. This is used by `ticket_watcher.py` and `update_requesters.py`.
* **`agents.txt`**: Maps agent IDs to display names (format: `id:Name`).
* **`requesters.txt`**: Maps requester IDs to display names (format: `id:Name`).
* **`cert.pem`**: (Optional) SSL certificate file for running the server over HTTPS.
* **`key.pem`**: (Optional) SSL private key file for running the server over HTTPS.
* **`README.md`**: This file.
* **`.gitignore`**: Specifies intentionally untracked files that Git should ignore (e.g., `token.txt`, `pyenv/`).
* **`LICENSE.md`**: (Recommended) Contains the open-source license for the project.

## Setup and Installation

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/hamnertime/ticket-dash](https://github.com/hamnertime/ticket-dash) # Or your repository URL
    cd ticket-dash
    ```

2.  **Python Environment:**
    * Ensure Python 3.7+ is installed.
    * It's highly recommended to create and activate a virtual environment:
        ```bash
        python3 -m venv pyenv
        source pyenv/bin/activate  # On Windows: pyenv\Scripts\activate
        ```

3.  **Install Dependencies:**
    * Install Flask and other Python packages. A `requirements.txt` file is recommended.
        ```bash
        pip install Flask requests pyluxafor # Add other dependencies as needed
        # Or if you have a requirements.txt:
        # pip install -r requirements.txt
        ```

4.  **Configuration:**
    * **`token.txt`:** Create this file in the root directory and place your Freshservice API key in it.
        ```
        YOUR_FRESHSERVICE_API_KEY
        ```
    * **`agents.txt`:** Create or populate this file. Each line should map an agent ID to a display name:
        ```
        1000000001:David Hamner
        1000000002:Agent Two
        ```
    * **`requesters.txt`:** Create or populate this file similarly for requester IDs (can be generated by `update_requesters.py`).
        ```
        2000000001:Client A Contact
        2000000002:Client B User
        ```
    * **`./tickets/` directory:** Ensure this directory exists. `ticket_watcher.py` will populate it.
        ```bash
        mkdir tickets
        ```
    * **User for Services:** It's recommended to create a dedicated non-root user to run these services (e.g., `ticketdashuser`).
        ```bash
        sudo adduser --system --group ticketdashuser
        ```
        Ensure this user has appropriate ownership and permissions for the `ticket-dash` directory and its contents, especially write access to the `tickets` directory, `ticket_poller.log`, and `ticket_poller.lock`.

5.  **SSL/HTTPS (Optional but Recommended for `gui.py`):**
    * If you want to run the dashboard over HTTPS (as configured in `gui.py` to run on port 443 by default if certs are present):
        * Place your SSL certificate (`cert.pem`) and private key (`key.pem`) in the root directory of the project (e.g., `/home/integotec/ticket-dash/`).
        * Ensure the user running the `gui.py` service (e.g., `ticketdashuser`) has read access to these files.
        * The application includes a fallback to HTTP on port 5001 if `cert.pem` or `key.pem` are not found.

6.  **`authbind` for Port 443 (for `gui.py`):**
    * To allow the `gui.py` service to run on port 443 without root:
        ```bash
        sudo apt-get update
        sudo apt-get install authbind
        sudo touch /etc/authbind/byport/443
        sudo chown ticketdashuser /etc/authbind/byport/443 # Replace ticketdashuser if you used a different name
        sudo chmod 750 /etc/authbind/byport/443
        ```

7.  **USB Permissions for `blinky.py` (Luxafor):**
    * The user running `blinky.py` (e.g., `ticketdashuser`) needs permission to access the Luxafor USB device. Add the user to the `dialout` or `plugdev` group:
        ```bash
        sudo usermod -a -G dialout ticketdashuser # Or plugdev
        ```
    * A reboot or re-login might be necessary for group changes to take effect. Alternatively, create custom `udev` rules for more fine-grained permissions.

## Running the Components

You can run the components manually for testing, but for production, using the provided `systemd` services is recommended.

### Manual Execution

1.  **`update_requesters.py` (Optional, as needed):**
    ```bash
    python3 update_requesters.py
    ```

2.  **`ticket_watcher.py` (Data Fetcher):**
    * Run this in a terminal. It will continuously poll for ticket updates.
    ```bash
    python3 ticket_watcher.py
    ```

3.  **`gui.py` (Flask Web Application):**
    * Run this in a separate terminal.
    * If SSL and `authbind` are configured, and you're in the project directory:
        ```bash
        authbind --deep python3 gui.py
        ```
        Access at: `https://your_server_ip_or_domain:443`
    * For HTTP on port 5001:
        ```bash
        python3 gui.py
        ```
        Access at: `http://your_server_ip_or_domain:5001`

4.  **`blinky.py` (Luxafor Indicator):**
    * Run this in another terminal.
    ```bash
    python3 blinky.py
    ```

### Running as Systemd Services (Recommended for Production/Autostart)

This project includes example `systemd` service files in the `./startup/` directory (or you can create them as described below). These files allow `gui.py`, `ticket_watcher.py`, and `blinky.py` to run as background services and start automatically on boot.

**Assumptions for service files:**
* Your project is in `/home/integotec/ticket-dash`.
* You are using a user named `ticketdashuser`.
* You are using `python3` from the system path (adjust to use a virtualenv path if needed, e.g., `/home/integotec/ticket-dash/pyenv/bin/python3`).

**Setup Steps:**

1.  **Prepare Service Files:**
    Ensure you have the following service files (e.g., in a `./startup/` directory within your project, or create them directly in `/etc/systemd/system/`):
    * `ticket-dash.service` (for `gui.py`)
    * `ticket-watcher.service` (for `ticket_watcher.py`)
    * `blinky.service` (for `blinky.py`)
    *(Refer to previous conversation or generate them based on the templates provided if you don't have them.)*

2.  **Copy Service Files to Systemd Directory:**
    ```bash
    sudo cp ./startup/ticket-dash.service /etc/systemd/system/
    sudo cp ./startup/ticket-watcher.service /etc/systemd/system/
    sudo cp ./startup/blinky.service /etc/systemd/system/
    ```
    *(Adjust the source path `./startup/` if your files are located elsewhere.)*

3.  **Reload Systemd Manager Configuration:**
    This makes `systemd` aware of the new service files.
    ```bash
    sudo systemctl daemon-reload
    ```

4.  **Enable the Services (to start on boot):**
    ```bash
    sudo systemctl enable ticket-dash.service
    sudo systemctl enable ticket-watcher.service
    sudo systemctl enable blinky.service
    ```

5.  **Start the Services Immediately:**
    ```bash
    sudo systemctl start ticket-dash.service
    sudo systemctl start ticket-watcher.service
    sudo systemctl start blinky.service
    ```

6.  **Check the Status of the Services:**
    ```bash
    sudo systemctl status ticket-dash.service
    sudo systemctl status ticket-watcher.service
    sudo systemctl status blinky.service
    ```
    You can also view logs for each service:
    ```bash
    sudo journalctl -u ticket-dash.service -f
    sudo journalctl -u ticket-watcher.service -f
    sudo journalctl -u blinky.service -f
    ```
    
**Automating `update_requesters.py` (Optional):**

If you want `update_requesters.py` to run automatically, you can set up a cron job. For example, to run it daily at 3:00 AM:

1.  Edit your crontab: `crontab -e`
2.  Add a line like this (adjust paths and schedule as needed):
    ```cron
    0 3 * * * /full/path/to/your/ticket-dash/pyenv/bin/python3 /full/path/to/your/ticket-dash/update_requesters.py >> /full/path/to/your/ticket-dash/update_requesters.log 2>&1
    ```

## Usage

Once running (ideally via `systemd` services), the dashboard will be accessible via your server's IP address or domain name on port 443 (HTTPS) or 5001 (HTTP) depending on your setup.
* Tickets are displayed in three main sections.
* Use the theme toggle button (☀️/🌙) in the top info bar to switch between light and dark modes.
* Hover over truncated ticket subjects to view a longer description in a tooltip.
* Click on a ticket ID to open the corresponding ticket directly in Freshservice (ensure `FRESHSERVICE_DOMAIN` in `gui.py` is correct).
* The Luxafor light (if `blinky.py` is running) will change color based on ticket status.

## Adapting for Other Ticketing Systems

The core of the data display logic in `gui.py` reads ticket information from JSON files in the `./tickets/` directory. To adapt this dashboard for a different ticketing system (e.g., Jira, Zendesk, ServiceNow):

1.  **Rewrite `ticket_watcher.py`:**
    * Update this script to connect to the API of your chosen ticketing system.
    * Fetch the required ticket fields (ID, subject, status, priority, requester, agent, creation/update times, description, etc.).
    * Transform the data into the JSON structure that `gui.py` expects and save each ticket as a separate file in the `./tickets/` directory. The existing `.txt` files (which are JSON) in the `tickets` directory can serve as a structural reference.

2.  **Adjust Mappings (if needed):**
    * Update `agents.txt` and `requesters.txt` if the ID formats or sources change.
    * You might need to adjust how `responder_id` (agent) and `requester_id` are extracted and mapped.

3.  **Review `gui.py` Logic:**
    * Status IDs (`OPEN_INCIDENT_STATUS_ID`, `WAITING_ON_AGENT`, etc.) will likely be different for other systems. Update these constants at the top of `gui.py`.
    * The categorization logic in `load_and_process_incidents()` might need to be tweaked based on the new system's statuses and workflow.
    * Ensure the JSON fields `gui.py` expects (e.g., `subject`, `priority_raw`, `status_raw`, `updated_at_str`, `created_at_str`, `fr_due_by_str`, `description_text`, `responder_id`, `requester_id`) are provided by your new `ticket_watcher.py`.

## Contributing

Contributions, issues, and feature requests are welcome! Please feel free to:
* Open an issue for bugs or suggestions.
* Fork the repository and submit a pull request.
