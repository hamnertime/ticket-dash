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

## Tech Stack

* **Backend:** Python, Flask
* **Frontend:** HTML, CSS, JavaScript
* **Data Source:** Designed to read JSON files generated from the Freshservice API (via `ticket_watcher.py`).

## Project Files and Directories

* **`gui.py`**: The main Flask web application that serves the dashboard.
* **`ticket_watcher.py`**: Script responsible for fetching ticket data (e.g., from Freshservice) and updating the `./tickets/` directory. *(This script needs to be implemented/provided by the user.)*
* **`tickets/`**: Directory where `ticket_watcher.py` stores individual ticket data as JSON files (e.g., `123.txt`, `124.txt`).
* **`static/`**: Contains frontend assets.
    * **`static/css/style.css`**: Custom CSS styles for the dashboard.
    * **`static/js/theme.js`**: JavaScript for theme toggling and any other dynamic frontend logic.
* **`templates/`**: Contains HTML templates.
    * **`templates/index.html`**: The main HTML template for the dashboard.
* **`token.txt`**: Stores the Freshservice API key. This is used by `ticket_watcher.py`. 
* **`agents.txt`**: Maps agent IDs to display names (format: `id:Name`).
* **`requesters.txt`**: Maps requester IDs to display names (format: `id:Name`).
* **`cert.pem`**: (Optional) SSL certificate file for running the server over HTTPS.
* **`key.pem`**: (Optional) SSL private key file for running the server over HTTPS.
* **`README.md`**: This file.
* **`.gitignore`**: Specifies intentionally untracked files that Git should ignore (e.g., `token.txt`, `venv/`).
* **`LICENSE.md`**: (Recommended) Contains the open-source license for the project.

## Setup and Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/hamnertime/ticket-dash
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
    * The primary dependency for `gui.py` is Flask.
        ```bash
        pip install Flask
        ```
    * `ticket_watcher.py` will likely require the `requests` library (or similar) for API calls. Install it if you're using the provided watcher or adapt as needed:
        ```bash
        pip install requests
        ```

4.  **Configuration:**
    * **`token.txt`:** Create this file in the root directory and place your Freshservice API key in it. This file is used by `ticket_watcher.py`.
        ```
        YOUR_FRESHSERVICE_API_KEY
        ```
    * **`agents.txt`:** Create or populate this file. Each line should map an agent ID to a display name:
        ```
        1000000001:David Hamner
        1000000002:Agent Two
        ```
    * **`requesters.txt`:** Create or populate this file similarly for requester IDs. (./update_requesters.py)
        ```
        2000000001:Client A Contact
        2000000002:Client B User
        ```
    * **`./tickets/` directory:** Ensure this directory exists. `ticket_watcher.py` will populate it.

6.  **SSL/HTTPS (Optional but Recommended):**
    * If you want to run the dashboard over HTTPS (as configured in `gui.py` to run on port 443 by default if certs are present):
        * Place your SSL certificate (`cert.pem`) and private key (`key.pem`) in the root directory of the project.
        * If you don't have these, you can generate a self-signed certificate for development or obtain one from a Certificate Authority.
        * The application includes a fallback to HTTP on port 5001 if `cert.pem` or `key.pem` are not found.

## Running the Dashboard

There are two main components to run:

1.  **`ticket_watcher.py` (Data Fetcher):**
    * This script is responsible for connecting to your ticketing system (e.g., Freshservice using the API key in `token.txt`), fetching ticket data, and saving/updating individual ticket files (e.g., as JSON `.txt` files) in the `./tickets/` directory.
    * You will need to run this script periodically to keep the dashboard data fresh. How you run it (e.g., cron job, scheduled task, manual execution) depends on your needs and how `ticket_watcher.py` is designed.
        ```bash
        python ticket_watcher.py
        ```
    * *(Note: The specifics of `ticket_watcher.py` are not detailed here and would need to be implemented or adapted by you.)*

2.  **`gui.py` (Flask Web Application):**
    * This script runs the web server that serves the dashboard.
    * If SSL certificate and key are configured and present, it will attempt to run on HTTPS port 443:
        ```bash
        sudo python gui.py  # sudo is often required for port 443
        ```
        Access at: `https://localhost:443` (or your server's IP/domain)
    * If SSL files are not found, it will fall back to HTTP on port 5001:
        ```bash
        python gui.py
        ```
        Access at: `http://localhost:5001`

## Usage

Once running, open the dashboard URL in your web browser.
* Tickets are displayed in three main sections.
* Use the theme toggle button (☀️/🌙) in the top info bar to switch between light and dark modes.
* Hover over truncated ticket subjects to view a longer description in a tooltip.
* Click on a ticket ID to open the corresponding ticket directly in Freshservice (ensure `FRESHSERVICE_DOMAIN` in `gui.py` is correct).

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
    * Status IDs (`OPEN_TICKET_STATUS_ID`, `WAITING_ON_AGENT`, etc.) will likely be different for other systems. Update these constants at the top of `gui.py`.
    * The categorization logic in `load_and_process_tickets()` might need to be tweaked based on the new system's statuses and workflow.
    * Ensure the JSON fields `gui.py` expects (e.g., `subject`, `priority_raw`, `status_raw`, `updated_at_str`, `created_at_str`, `fr_due_by_str`, `description_text`, `responder_id`, `requester_id`) are provided by your new `ticket_watcher.py`.

## Contributing

Contributions, issues, and feature requests are welcome! Please feel free to:
* Open an issue for bugs or suggestions.
* Fork the repository and submit a pull request.

## License

This project is open source. Consider adding a `LICENSE.md` file (e.g., with the AGPL License):
