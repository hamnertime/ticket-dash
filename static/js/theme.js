// static/js/theme.js
document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('theme-toggle');
    const body = document.body;

    function applyTheme(theme) {
        if (theme === 'light') {
            body.classList.add('light-mode');
            if (themeToggle) themeToggle.textContent = '🌙 Dark Mode';
        } else { // Default to dark
            body.classList.remove('light-mode');
            if (themeToggle) themeToggle.textContent = '☀️ Light Mode';
        }
    }

    let currentTheme = localStorage.getItem('theme') || 'dark'; // Default to dark
    applyTheme(currentTheme);

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            let newTheme = body.classList.contains('light-mode') ? 'dark' : 'light';
            localStorage.setItem('theme', newTheme);
            applyTheme(newTheme);
        });
    }

    // --- Timezone Conversion (existing function) ---
    function formatToLocal(utcDateStringInput, options = {}, dateOnly = false, prefix = "") {
        if (!utcDateStringInput || utcDateStringInput.trim() === 'N/A' || utcDateStringInput.trim() === '') {
            return 'N/A';
        }
        let parsableDateString = utcDateStringInput.trim();

        if (parsableDateString.includes('T') && (parsableDateString.endsWith('Z') || parsableDateString.match(/[+-]\d{2}:\d{2}$/))) {
            // Already good ISO
        } else if (parsableDateString.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [A-Z]+$/i)) { // Handles YYYY-MM-DD HH:MM:SS ZZZ
            parsableDateString = parsableDateString.replace(/ ([A-Z]+)$/i, "Z").replace(" ", "T");
        } else if (parsableDateString.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+(\+\d{2}:\d{2}|Z)?$/)) {
            // Handles ISO with microseconds from Python's isoformat()
        } else if (parsableDateString.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)) { // YYYY-MM-DD HH:MM:SS
            parsableDateString = parsableDateString.replace(" ", "T") + "Z"; // Assume UTC if no timezone
        }


        const date = new Date(parsableDateString);
        if (isNaN(date.getTime())) {
            console.warn(`Could not parse date: "${utcDateStringInput}" (Processed as: "${parsableDateString}")`);
            return utcDateStringInput; // Return original if parsing failed
        }

        let Noptions = { ...options };
        if (dateOnly) {
            Noptions = { year: 'numeric', month: 'short', day: 'numeric', ...options };
        } else {
            Noptions = { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true, ...options };
        }
        return prefix + date.toLocaleString(undefined, Noptions);
    }

    // --- Convert All UTC to Local (existing function, might need dashboard time update) ---
    function convertAllUTCToLocal(isoTimestamp) {
        // Dashboard Generated Time
        const dashboardTimeLocalEl = document.getElementById('dashboard-generated-time');
        if (dashboardTimeLocalEl && isoTimestamp) {
            dashboardTimeLocalEl.textContent = formatToLocal(isoTimestamp);
        } else if (dashboardTimeLocalEl) {
            // Initial load from Jinja if dashboard_generated_time_iso is passed to template
            // Or set to loading / N/A if not immediately available
            const initialIsoTime = dashboardTimeLocalEl.getAttribute('data-initial-utc-time');
            if(initialIsoTime) {
                dashboardTimeLocalEl.textContent = formatToLocal(initialIsoTime);
            }
        }


        // Ticket Datetimes (Now primarily for FR Due if it exists in dynamically generated rows)
        document.querySelectorAll('.datetime-container').forEach(el => {
            const utcTimestamp = el.getAttribute('data-utc-datetime');
            const dateOnly = el.getAttribute('data-date-only') === 'true';
            const prefix = el.getAttribute('data-prefix') || "";
            const localTimeSpan = el.querySelector('.local-datetime');

            if (utcTimestamp && localTimeSpan) {
                localTimeSpan.textContent = formatToLocal(utcTimestamp, {}, dateOnly, prefix);
            } else if (localTimeSpan) {
                localTimeSpan.textContent = (prefix && utcTimestamp === '') ? prefix + 'N/A' : 'N/A';
            }
        });
    }
    convertAllUTCToLocal(); // Initial call for server-rendered dates


    // --- NEW AJAX REFRESH LOGIC ---
    // Get config from global window objects set in index.html
    const FRESHSERVICE_BASE_URL = window.FRESHSERVICE_BASE_URL || '';
    const AUTO_REFRESH_INTERVAL_MS = window.AUTO_REFRESH_MS || 0;
    // const OPEN_TICKET_STATUS_ID_JS = window.OPEN_TICKET_STATUS_ID; // Available if needed
    // const WAITING_ON_CUSTOMER_STATUS_ID_JS = window.WAITING_ON_CUSTOMER_STATUS_ID; // Available if needed


    function formatTicketSubjectForRender(subject, descriptionText) {
        let subjectText = subject ? subject.substring(0, 60) + (subject.length > 60 ? '...' : '') : 'No Subject';
        let tooltipHtml = '';
        if (descriptionText) {
            // Strip HTML tags for tooltip, then truncate
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = descriptionText;
            const strippedDescription = tempDiv.textContent || tempDiv.innerText || "";
            const truncatedDescription = strippedDescription.substring(0, 300) + (strippedDescription.length > 300 ? '...' : '');
            tooltipHtml = `<span class="tooltiptext">${truncatedDescription}</span>`;
        }
        return `${subjectText}${tooltipHtml}`;
    }

    function renderTicketRow(ticket) {
        const ticketId = ticket.id || 'N/A';
        const subjectHtml = formatTicketSubjectForRender(ticket.subject, ticket.description_text);
        const requesterName = ticket.requester_name || 'N/A';
        const agentName = ticket.agent_name || 'Unassigned';
        const priorityText = ticket.priority_text || 'N/A';
        const slaText = ticket.sla_text || 'N/A';
        const slaClass = ticket.sla_class || 'sla-none';
        const updatedFriendly = ticket.updated_friendly || 'N/A';
        const createdDaysOld = ticket.created_days_old || 'N/A';

        let frDueHtml = '';
        // Check ticket.first_responded_at_iso (should be null if FR not met, or an ISO string)
        // And ticket.fr_due_by_str should be the due date string
        if (ticket.first_responded_at_iso === null && ticket.fr_due_by_str) {
            frDueHtml = `
            <div class="datetime-container" data-utc-datetime="${ticket.fr_due_by_str}" data-prefix="FR Due: ">
            <small class="local-datetime">Loading...</small>
            </div>`;
        }

        // Specific logic for Section 3's "Action / SLA" column if needed, but gui.py should prepare sla_text
        // Example for section 3, if WAITING_ON_CUSTOMER and agent_responded_friendly needs to be shown:
        // let additionalSlaDetail = '';
        // if (ticket.status_raw === WAITING_ON_CUSTOMER_STATUS_ID_JS && ticket.agent_responded_friendly && ticket.agent_responded_friendly !== 'N/A') {
        //    additionalSlaDetail = `<br><small>Agent: ${ticket.agent_responded_friendly}</small>`;
        // } // This kind of logic is now mostly handled by Python side's sla_text generation.

        return `
        <tr>
        <td class="ticket-id"><a href="${FRESHSERVICE_BASE_URL}${ticketId}" target="_blank">${ticketId}</a></td>
        <td class="ticket-subject description-tooltip">${subjectHtml}</td>
        <td>${requesterName}</td>
        <td>${agentName}</td>
        <td><span class="priority-${priorityText}">${priorityText}</span></td>
        <td class="col-action-sla">
        <span class="sla-status-text ${slaClass}">${slaText}</span>
        ${frDueHtml}
        {# ${additionalSlaDetail} #}
        </td>
        <td>${updatedFriendly}</td>
        <td>${createdDaysOld}</td>
        </tr>
        `;
    }

    function updateTicketSection(tableBodyId, tickets, noTicketsMessageId, sectionTicketCountId, tableId) {
        const tableBody = document.getElementById(tableBodyId);
        const noTicketsMessageElement = document.getElementById(noTicketsMessageId);
        const sectionTicketCountElement = document.getElementById(sectionTicketCountId);
        const tableElement = document.getElementById(tableId);

        if (!tableBody || !noTicketsMessageElement || !sectionTicketCountElement || !tableElement) {
            console.error(`One or more elements not found for section based on ID: ${tableBodyId}`);
            return;
        }

        sectionTicketCountElement.textContent = tickets.length;
        tableBody.innerHTML = ''; // Clear existing rows

        if (tickets && tickets.length > 0) {
            tickets.forEach(ticket => {
                tableBody.innerHTML += renderTicketRow(ticket);
            });
            noTicketsMessageElement.style.display = 'none';
            tableElement.style.display = ''; // Show table (could be 'table' or 'block' depending on CSS default)
        } else {
            noTicketsMessageElement.style.display = 'block';
            tableElement.style.display = 'none'; // Hide table
        }
    }

    async function refreshTicketData() {
        console.log("Refreshing ticket data...");
        try {
            const response = await fetch('/api/tickets');
            if (!response.ok) {
                console.error('Failed to fetch ticket data:', response.status, await response.text());
                document.getElementById('dashboard-generated-time').textContent = "Error loading data!";
                return;
            }
            const data = await response.json();

            // Update total count
            const totalCountElement = document.getElementById('total-active-tickets-count');
            if (totalCountElement) {
                totalCountElement.textContent = data.total_active_tickets;
            }

            // Update tables for each section
            updateTicketSection('s1-tickets-body', data.s1_open_tickets, 's1-no-tickets-message', 's1-ticket-count', 's1-ticket-table');
            updateTicketSection('s2-tickets-body', data.s2_waiting_agent_tickets, 's2-no-tickets-message', 's2-ticket-count', 's2-ticket-table');
            updateTicketSection('s3-tickets-body', data.s3_remaining_tickets, 's3-no-tickets-message', 's3-ticket-count', 's3-ticket-table');

            // Update dashboard generated time (using the new data from API)
            if(data.dashboard_generated_time_iso){
                convertAllUTCToLocal(data.dashboard_generated_time_iso); // This will update the #dashboard-generated-time element
            } else {
                convertAllUTCToLocal(); // Fallback to re-process existing datetime elements
            }


        } catch (error) {
            console.error('Error refreshing ticket data:', error);
            const dashboardTimeEl = document.getElementById('dashboard-generated-time');
            if (dashboardTimeEl) dashboardTimeEl.textContent = "Error loading data!";
        }
    }

    // Initial call and interval for refresh
    if (AUTO_REFRESH_INTERVAL_MS > 0) {
        refreshTicketData(); // Call once immediately to load data via JS if desired (optional, page loads with server data first)
setInterval(refreshTicketData, AUTO_REFRESH_INTERVAL_MS);
console.log(`Ticket data will refresh every ${AUTO_REFRESH_INTERVAL_MS / 1000} seconds.`);
    } else {
        // If auto-refresh is disabled, still ensure initial dates are converted.
        // This is already called at the end of DOMContentLoaded for server-rendered dates.
        // And update the dashboard generated time once from initial load data.
        const initialDashboardTimeIso = "{{ dashboard_generated_time_iso }}"; // Jinja var from initial page load
        if (initialDashboardTimeIso) {
            convertAllUTCToLocal(initialDashboardTimeIso);
        }
    }
});
