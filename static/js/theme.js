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

    function formatToLocal(utcDateStringInput, options = {}, dateOnly = false, prefix = "") {
        if (!utcDateStringInput || utcDateStringInput.trim() === 'N/A' || utcDateStringInput.trim() === '') {
            return 'N/A';
        }
        let parsableDateString = utcDateStringInput.trim();
        if (parsableDateString.includes('T') && (parsableDateString.endsWith('Z') || parsableDateString.match(/[+-]\d{2}:\d{2}$/))) {
            // Already good ISO
        } else if (parsableDateString.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [A-Z]+$/i)) {
            parsableDateString = parsableDateString.replace(/ ([A-Z]+)$/i, "Z").replace(" ", "T");
        } else if (parsableDateString.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+(\+\d{2}:\d{2}|Z)?$/)) {
            // Handles ISO with microseconds
        } else if (parsableDateString.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)) {
            parsableDateString = parsableDateString.replace(" ", "T") + "Z";
        }

        const date = new Date(parsableDateString);
        if (isNaN(date.getTime())) {
            console.warn(`Could not parse date: "${utcDateStringInput}" (Processed as: "${parsableDateString}")`);
            return utcDateStringInput;
        }

        let Noptions = { ...options };
        if (dateOnly) {
            Noptions = { year: 'numeric', month: 'short', day: 'numeric', ...options };
        } else {
            Noptions = { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true, ...options };
        }
        return prefix + date.toLocaleString(undefined, Noptions);
    }

    function convertAllUTCToLocal(isoTimestamp) {
        const dashboardTimeLocalEl = document.getElementById('dashboard-generated-time');
        if (dashboardTimeLocalEl && isoTimestamp) {
            dashboardTimeLocalEl.textContent = formatToLocal(isoTimestamp);
        } else if (dashboardTimeLocalEl) {
            const initialIsoTime = dashboardTimeLocalEl.getAttribute('data-initial-utc-time');
            if(initialIsoTime) {
                dashboardTimeLocalEl.textContent = formatToLocal(initialIsoTime);
            }
        }

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
    convertAllUTCToLocal();

    const FRESHSERVICE_BASE_URL = window.FRESHSERVICE_BASE_URL || '';
    const AUTO_REFRESH_INTERVAL_MS = window.AUTO_REFRESH_MS || 0;
    window.currentApiData = {}; // To store the latest fetched data for sorting

    let sortState = {
        's1-incident-table': { key: null, direction: 'asc' },
        's2-incident-table': { key: null, direction: 'asc' },
        's3-incident-table': { key: null, direction: 'asc' }
    };

    function formatIncidentSubjectForRender(subject, descriptionText) {
        let subjectText = subject ? subject.substring(0, 60) + (subject.length > 60 ? '...' : '') : 'No Subject';
        let tooltipHtml = '';
        if (descriptionText) {
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = descriptionText;
            const strippedDescription = tempDiv.textContent || tempDiv.innerText || "";
            const truncatedDescription = strippedDescription.substring(0, 300) + (strippedDescription.length > 300 ? '...' : '');
            tooltipHtml = `<span class="tooltiptext">${truncatedDescription}</span>`;
        }
        return `${subjectText}${tooltipHtml}`;
    }

    function renderIncidentRow(incident) { // Renamed from renderTicketRow
        const incidentId = incident.id || 'N/A';
        const subjectHtml = formatIncidentSubjectForRender(incident.subject, incident.description_text);
        const requesterName = incident.requester_name || 'N/A';
        const agentName = incident.agent_name || 'Unassigned';
        const priorityText = incident.priority_text || 'N/A';
        const slaText = incident.sla_text || 'N/A';
        const slaClass = incident.sla_class || 'sla-none';
        const updatedFriendly = incident.updated_friendly || 'N/A';
        const createdDaysOld = incident.created_days_old || 'N/A';

        let frDueHtml = '';
        if (incident.first_responded_at_iso === null && incident.fr_due_by_str) {
            frDueHtml = `
            <div class="datetime-container" data-utc-datetime="${incident.fr_due_by_str}" data-prefix="FR Due: ">
            <small class="local-datetime">Loading...</small>
            </div>`;
        }

        return `
        <tr>
        <td class="ticket-id"><a href="${FRESHSERVICE_BASE_URL}${incidentId}" target="_blank">${incidentId}</a></td>
        <td class="ticket-subject description-tooltip">${subjectHtml}</td>
        <td>${requesterName}</td>
        <td>${agentName}</td>
        <td><span class="priority-${priorityText}">${priorityText}</span></td>
        <td class="col-action-sla">
        <span class="sla-status-text ${slaClass}">${slaText}</span>
        ${frDueHtml}
        </td>
        <td>${updatedFriendly}</td>
        <td>${createdDaysOld}</td>
        </tr>
        `;
    }

    function updateIncidentSection(tableBodyId, incidents, noIncidentsMessageId, sectionIncidentCountId, tableId) { // Renamed
        const tableBody = document.getElementById(tableBodyId);
        const noIncidentsMessageElement = document.getElementById(noIncidentsMessageId);
        const sectionIncidentCountElement = document.getElementById(sectionIncidentCountId);
        const tableElement = document.getElementById(tableId);

        if (!tableBody || !noIncidentsMessageElement || !sectionIncidentCountElement || !tableElement) {
            console.error(`One or more elements not found for section based on ID: ${tableBodyId}`);
            return;
        }

        sectionIncidentCountElement.textContent = incidents.length;
        tableBody.innerHTML = '';

        if (incidents && incidents.length > 0) {
            incidents.forEach(incident => {
                tableBody.innerHTML += renderIncidentRow(incident);
            });
            noIncidentsMessageElement.style.display = 'none';
            tableElement.style.display = '';
        } else {
            noIncidentsMessageElement.style.display = 'block';
            tableElement.style.display = 'none';
        }
        convertAllUTCToLocal(); // Re-convert dates after re-rendering
    }

    async function refreshIncidentData() { // Renamed
        console.log("Refreshing incident data...");
        try {
            const response = await fetch('/api/incidents'); // Changed API endpoint name
            if (!response.ok) {
                console.error('Failed to fetch incident data:', response.status, await response.text());
                const dashboardTimeEl = document.getElementById('dashboard-generated-time');
                if (dashboardTimeEl) dashboardTimeEl.textContent = "Error loading data!";
                return;
            }
            const data = await response.json();
            window.currentApiData = data; // Store for sorting

            const totalCountElement = document.getElementById('total-active-incidents-count');
            if (totalCountElement) {
                totalCountElement.textContent = data.total_active_incidents;
            }

            // Determine current sort or use server default if no sort active
            const s1Sort = sortState['s1-incident-table'];
            const s2Sort = sortState['s2-incident-table'];
            const s3Sort = sortState['s3-incident-table'];

            let s1Data = data.s1_open_incidents;
            let s2Data = data.s2_waiting_agent_incidents;
            let s3Data = data.s3_remaining_incidents;

            if (s1Sort.key) s1Data = sortData([...data.s1_open_incidents], s1Sort.key, s1Sort.direction);
            if (s2Sort.key) s2Data = sortData([...data.s2_waiting_agent_incidents], s2Sort.key, s2Sort.direction);
            if (s3Sort.key) s3Data = sortData([...data.s3_remaining_incidents], s3Sort.key, s3Sort.direction);


            updateIncidentSection('s1-incidents-body', s1Data, 's1-no-incidents-message', 's1-incident-count', 's1-incident-table');
            updateIncidentSection('s2-incidents-body', s2Data, 's2-no-incidents-message', 's2-incident-count', 's2-incident-table');
            updateIncidentSection('s3-incidents-body', s3Data, 's3-no-incidents-message', 's3-incident-count', 's3-incident-table');

            updateAllSortIndicators();


            if(data.dashboard_generated_time_iso){
                convertAllUTCToLocal(data.dashboard_generated_time_iso);
            } else {
                convertAllUTCToLocal();
            }

        } catch (error) {
            console.error('Error refreshing incident data:', error);
            const dashboardTimeEl = document.getElementById('dashboard-generated-time');
            if (dashboardTimeEl) dashboardTimeEl.textContent = "Error loading data!";
        }
    }

    function sortData(dataArray, key, direction) {
        if (!dataArray) return [];
        dataArray.sort((a, b) => {
            let valA = a[key];
            let valB = b[key];

            // Handle null or undefined values consistently
            if (valA == null && valB == null) return 0;
            if (valA == null) return direction === 'asc' ? 1 : -1; // nulls last if asc, first if desc
            if (valB == null) return direction === 'asc' ? -1 : 1; // nulls first if asc, last if desc


            // Date sorting for keys ending with _str (assuming ISO strings) or specific date keys
            if (key.endsWith('_at_str') || key === 'fr_due_by_str') {
                let dateA = new Date(valA);
                let dateB = new Date(valB);
                if (isNaN(dateA.getTime()) && isNaN(dateB.getTime())) return 0;
                if (isNaN(dateA.getTime())) return direction === 'asc' ? 1 : -1;
                if (isNaN(dateB.getTime())) return direction === 'asc' ? -1 : 1;
                return direction === 'asc' ? dateA - dateB : dateB - dateA;
            }
            // Numeric sorting (e.g. id, priority_raw)
            else if (typeof valA === 'number' && typeof valB === 'number') {
                return direction === 'asc' ? valA - valB : valB - valA;
            }
            // String sorting (default)
            else {
                valA = valA.toString().toLowerCase();
                valB = valB.toString().toLowerCase();
                return direction === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
            }
        });
        return dataArray;
    }

    function updateSortIndicators(tableElement, activeKey, direction) {
        tableElement.querySelectorAll('.sortable-header').forEach(th => {
            th.classList.remove('sort-asc', 'sort-desc');
            if (th.dataset.sortKey === activeKey) {
                th.classList.add(direction === 'asc' ? 'sort-asc' : 'sort-desc');
            }
        });
    }

    function updateAllSortIndicators() {
        for (const tableId in sortState) {
            const tableElement = document.getElementById(tableId);
            if (tableElement && sortState[tableId].key) {
                updateSortIndicators(tableElement, sortState[tableId].key, sortState[tableId].direction);
            }
        }
    }


    document.querySelectorAll('.sortable-header').forEach(header => {
        header.addEventListener('click', () => {
            const sortKey = header.dataset.sortKey;
            const tableElement = header.closest('.ticket-table'); // class name is still ticket-table
            const tableId = tableElement.id;
            const tableBodyId = tableElement.querySelector('tbody').id;

            // Dynamically construct the no-incidents message ID and count ID
            const sectionPrefix = tableId.substring(0, 2); // s1, s2, or s3
            const noIncidentsMessageId = `${sectionPrefix}-no-incidents-message`;
            const sectionIncidentCountId = `${sectionPrefix}-incident-count`;


            let currentData;
            if (tableId === 's1-incident-table') currentData = window.currentApiData.s1_open_incidents;
            else if (tableId === 's2-incident-table') currentData = window.currentApiData.s2_waiting_agent_incidents;
            else if (tableId === 's3-incident-table') currentData = window.currentApiData.s3_remaining_incidents;

            if (!currentData) {
                console.warn("No current data to sort for table:", tableId);
                return;
            }
            // Make a copy for sorting to not alter the original window.currentApiData order from server
            let dataToSort = [...currentData];


            if (sortState[tableId].key === sortKey) {
                sortState[tableId].direction = sortState[tableId].direction === 'asc' ? 'desc' : 'asc';
            } else {
                sortState[tableId].key = sortKey;
                sortState[tableId].direction = 'asc';
            }

            // Reset sort state for other tables if you want exclusive sort
            // for (const otherTableId in sortState) {
            //     if (otherTableId !== tableId) {
            //         const otherTableElement = document.getElementById(otherTableId);
            //          if(otherTableElement) {
            //             otherTableElement.querySelectorAll('.sortable-header').forEach(th => th.classList.remove('sort-asc', 'sort-desc'));
            //         }
            //         sortState[otherTableId].key = null;
            //     }
            // }


            const sortedData = sortData(dataToSort, sortKey, sortState[tableId].direction);
            updateIncidentSection(tableBodyId, sortedData, noIncidentsMessageId, sectionIncidentCountId, tableId);
            updateSortIndicators(tableElement, sortKey, sortState[tableId].direction);
        });
    });


    if (AUTO_REFRESH_INTERVAL_MS > 0) {
        setTimeout(refreshIncidentData, 100);
        setInterval(refreshIncidentData, AUTO_REFRESH_INTERVAL_MS);
        console.log(`Incident data will refresh every ${AUTO_REFRESH_INTERVAL_MS / 1000} seconds.`);
    } else {
        if (window.DASHBOARD_GENERATED_TIME_ISO_INITIAL) {
            convertAllUTCToLocal(window.DASHBOARD_GENERATED_TIME_ISO_INITIAL);
        } else {
            const dashboardTimeEl = document.getElementById('dashboard-generated-time');
            if (dashboardTimeEl && dashboardTimeEl.textContent === "Loading...") {
                dashboardTimeEl.textContent = "Auto-refresh disabled";
            }
        }
        // Initial fetch if no auto-refresh, after a small delay
        setTimeout(refreshIncidentData, 100);
    }
});
