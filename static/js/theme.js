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
        // Simplified ISO parsing logic, ensure it handles your date formats
        if (parsableDateString.includes('T') && (parsableDateString.endsWith('Z') || parsableDateString.match(/[+-]\d{2}:\d{2}$/))) {
            // Already good ISO
        } else if (parsableDateString.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?([A-Z]+|[+-]\d{2}:\d{2})?$/i)) {
            // Try to make it more robust for various ISO-like inputs
            parsableDateString = parsableDateString.replace(' ', 'T');
            if (!parsableDateString.endsWith('Z') && !parsableDateString.match(/[+-]\d{2}:\d{2}$/)) {
                parsableDateString += 'Z'; // Assume UTC if no timezone
            }
        }


        const date = new Date(parsableDateString);
        if (isNaN(date.getTime())) {
            console.warn(`Could not parse date: "${utcDateStringInput}" (Processed as: "${parsableDateString}")`);
            return utcDateStringInput; // Return original if parsing fails
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
            // Fallback if initial timestamp not directly passed, e.g., on first load before JS sets it
            const initialIsoTime = dashboardTimeLocalEl.getAttribute('data-initial-utc-time'); // Assuming you might add this
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
            } else if (localTimeSpan) { // If no timestamp, ensure prefix is handled if exists
                localTimeSpan.textContent = (prefix && utcTimestamp === '') ? prefix + 'N/A' : 'N/A';
            }
        });
    }
    convertAllUTCToLocal(); // Initial conversion for server-rendered dates

    const FRESHSERVICE_BASE_URL = window.FRESHSERVICE_BASE_URL || '';
    const AUTO_REFRESH_INTERVAL_MS = window.AUTO_REFRESH_MS || 0;
    const CURRENT_TICKET_TYPE_SLUG = window.CURRENT_TICKET_TYPE_SLUG || 'incidents'; // Default if not set
    const CURRENT_TICKET_TYPE_DISPLAY = window.CURRENT_TICKET_TYPE_DISPLAY || 'Incident';


    window.currentApiData = {}; // To store the latest fetched data for sorting

    // Initialize sortState for each table (assuming 3 tables s1, s2, s3)
    let sortState = {
        's1-item-table': { key: null, direction: 'asc' },
        's2-item-table': { key: null, direction: 'asc' },
        's3-item-table': { key: null, direction: 'asc' }
    };

    function formatItemSubjectForRender(subject, descriptionText) {
        let subjectText = subject ? subject.substring(0, 60) + (subject.length > 60 ? '...' : '') : 'No Subject';
        let tooltipHtml = '';
        if (descriptionText) {
            // Basic stripping of HTML for tooltip, consider a more robust library if complex HTML is present
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = descriptionText; // Allow HTML for formatting, then strip for plain text
            const strippedDescription = tempDiv.textContent || tempDiv.innerText || "";
            const truncatedDescription = strippedDescription.substring(0, 300) + (strippedDescription.length > 300 ? '...' : '');
            tooltipHtml = `<span class="tooltiptext">${truncatedDescription.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</span>`; // Sanitize
        }
        return `${subjectText}${tooltipHtml}`;
    }

    function renderItemRow(item) { // Renamed from renderTicketRow / renderIncidentRow
        const itemId = item.id || 'N/A';
        const subjectHtml = formatItemSubjectForRender(item.subject, item.description_text);
        const requesterName = item.requester_name || 'N/A';
        const agentName = item.agent_name || 'Unassigned';
        const priorityText = item.priority_text || 'N/A';
        const slaText = item.sla_text || 'N/A';
        const slaClass = item.sla_class || 'sla-none';
        const updatedFriendly = item.updated_friendly || 'N/A';
        const createdDaysOld = item.created_days_old || 'N/A';

        let slaDetailHtml = '';
        // Display FR Due for items not yet first responded, or general Due for SRs
        if (item.first_responded_at_iso === null && item.fr_due_by_str) {
            slaDetailHtml = `
            <div class="datetime-container" data-utc-datetime="${item.fr_due_by_str}" data-prefix="FR Due: ">
            <small class="local-datetime">Loading...</small>
            </div>`;
        } else if (item.type === 'Service Request' && item.due_by_str) { // Check item.type
            slaDetailHtml = `
            <div class="datetime-container" data-utc-datetime="${item.due_by_str}" data-prefix="Due: ">
            <small class="local-datetime">Loading...</small>
            </div>`;
        }


        return `
        <tr>
        <td class="item-id"><a href="${FRESHSERVICE_BASE_URL}${itemId}" target="_blank">${itemId}</a></td>
        <td class="item-subject description-tooltip">${subjectHtml}</td>
        <td>${requesterName}</td>
        <td>${agentName}</td>
        <td><span class="priority-${priorityText}">${priorityText}</span></td>
        <td class="col-action-sla">
        <span class="sla-status-text ${slaClass}">${slaText}</span>
        ${slaDetailHtml}
        </td>
        <td>${updatedFriendly}</td>
        <td>${createdDaysOld}</td>
        </tr>
        `;
    }

    function updateItemSection(tableBodyId, items, noItemsMessageId, sectionItemCountId, tableId) {
        const tableBody = document.getElementById(tableBodyId);
        const noItemsMessageElement = document.getElementById(noItemsMessageId);
        const sectionItemCountElement = document.getElementById(sectionItemCountId);
        const tableElement = document.getElementById(tableId);

        if (!tableBody || !noItemsMessageElement || !sectionItemCountElement || !tableElement) {
            console.error(`One or more elements not found for section update. Required IDs: ${tableBodyId}, ${noItemsMessageId}, ${sectionItemCountId}, ${tableId}`);
            return;
        }

        sectionItemCountElement.textContent = items.length;
        tableBody.innerHTML = ''; // Clear existing rows

        if (items && items.length > 0) {
            items.forEach(item => {
                tableBody.innerHTML += renderItemRow(item);
            });
            noItemsMessageElement.style.display = 'none';
            tableElement.style.display = ''; // Show table
        } else {
            noItemsMessageElement.style.display = 'block'; // Show "no items" message
            tableElement.style.display = 'none'; // Hide table
            // Ensure the message reflects the current item type
            noItemsMessageElement.textContent = `No ${CURRENT_TICKET_TYPE_DISPLAY.toLowerCase()}s currently in this category.`;
        }
        convertAllUTCToLocal(); // Re-convert dates after re-rendering new rows
    }

    async function refreshTicketData() {
        console.log(`Refreshing data for: ${CURRENT_TICKET_TYPE_DISPLAY}s (slug: ${CURRENT_TICKET_TYPE_SLUG})`);
        try {
            const response = await fetch(`/api/tickets/${CURRENT_TICKET_TYPE_SLUG}`); // Use dynamic slug
            if (!response.ok) {
                console.error(`Failed to fetch ${CURRENT_TICKET_TYPE_DISPLAY} data:`, response.status, await response.text());
                const dashboardTimeEl = document.getElementById('dashboard-generated-time');
                if (dashboardTimeEl) dashboardTimeEl.textContent = "Error loading data!";
                return;
            }
            const data = await response.json();
            window.currentApiData = data; // Store for sorting

            const totalCountElement = document.getElementById('total-active-items-count');
            if (totalCountElement) {
                totalCountElement.textContent = data.total_active_items;
            }

            // Update section headers if they are dynamic (passed from Flask, but JS can also set them)
            // Example: document.getElementById('s1-header').textContent = data.section1_name_js || `Section 1 (${data.s1_items.length})`;


            // Apply sorting if a sort key is active for any table
            let s1Data = data.s1_items;
            let s2Data = data.s2_items;
            let s3Data = data.s3_items;

            if (sortState['s1-item-table'].key) s1Data = sortData([...data.s1_items], sortState['s1-item-table'].key, sortState['s1-item-table'].direction);
            if (sortState['s2-item-table'].key) s2Data = sortData([...data.s2_items], sortState['s2-item-table'].key, sortState['s2-item-table'].direction);
            if (sortState['s3-item-table'].key) s3Data = sortData([...data.s3_items], sortState['s3-item-table'].key, sortState['s3-item-table'].direction);

            updateItemSection('s1-items-body', s1Data, 's1-no-items-message', 's1-item-count', 's1-item-table');
            updateItemSection('s2-items-body', s2Data, 's2-no-items-message', 's2-item-count', 's2-item-table');
            updateItemSection('s3-items-body', s3Data, 's3-no-items-message', 's3-item-count', 's3-item-table');

            updateAllSortIndicators(); // Ensure sort indicators are correctly set after data refresh


            if(data.dashboard_generated_time_iso){
                convertAllUTCToLocal(data.dashboard_generated_time_iso); // Update generated time
            } else {
                convertAllUTCToLocal(); // Fallback if not in API response for some reason
            }

        } catch (error) {
            console.error(`Error refreshing ${CURRENT_TICKET_TYPE_DISPLAY} data:`, error);
            const dashboardTimeEl = document.getElementById('dashboard-generated-time');
            if (dashboardTimeEl) dashboardTimeEl.textContent = "Error loading data!";
        }
    }

    function sortData(dataArray, key, direction) {
        if (!dataArray) return [];
        dataArray.sort((a, b) => {
            let valA = a[key];
            let valB = b[key];

            if (valA == null && valB == null) return 0;
            if (valA == null) return direction === 'asc' ? 1 : -1;
            if (valB == null) return direction === 'asc' ? -1 : 1;

            // Date sorting for keys ending with _str (assuming ISO strings) or specific date keys
            // Add other date keys if necessary
            if (key.endsWith('_at_str') || key === 'fr_due_by_str' || key === 'due_by_str') {
                let dateA = new Date(valA);
                let dateB = new Date(valB);
                if (isNaN(dateA.getTime()) && isNaN(dateB.getTime())) return 0;
                if (isNaN(dateA.getTime())) return direction === 'asc' ? 1 : -1;
                if (isNaN(dateB.getTime())) return direction === 'asc' ? -1 : 1;
                return direction === 'asc' ? dateA - dateB : dateB - dateA;
            }
            // Numeric sorting for raw priority or ID
            else if (key === 'priority_raw' || key === 'id') {
                return direction === 'asc' ? Number(valA) - Number(valB) : Number(valB) - Number(valA);
            }
            // String sorting (default for subject, name, sla_text, etc.)
            else {
                valA = String(valA).toLowerCase();
                valB = String(valB).toLowerCase();
                return direction === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
            }
        });
        return dataArray;
    }

    function updateSortIndicators(tableElement, activeKey, direction) {
        if (!tableElement) return;
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
            if (tableElement && sortState[tableId].key) { // Only update if a sort is active for this table
                updateSortIndicators(tableElement, sortState[tableId].key, sortState[tableId].direction);
            }
        }
    }


    document.querySelectorAll('.sortable-header').forEach(header => {
        header.addEventListener('click', () => {
            const sortKey = header.dataset.sortKey;
            const tableElement = header.closest('.item-table'); // Generic class
            if (!tableElement) return;
            const tableId = tableElement.id;
            const tableBodyId = tableElement.querySelector('tbody').id;

            // Dynamically construct the no-items message ID and count ID from tableId prefix
            const sectionPrefix = tableId.substring(0, 2); // s1, s2, or s3
            const noItemsMessageId = `${sectionPrefix}-no-items-message`;
            const sectionItemCountId = `${sectionPrefix}-item-count`;


            let currentDataForTable; // Data specific to the table being sorted
            if (tableId === 's1-item-table' && window.currentApiData.s1_items) currentDataForTable = window.currentApiData.s1_items;
            else if (tableId === 's2-item-table' && window.currentApiData.s2_items) currentDataForTable = window.currentApiData.s2_items;
            else if (tableId === 's3-item-table' && window.currentApiData.s3_items) currentDataForTable = window.currentApiData.s3_items;

            if (!currentDataForTable) {
                console.warn("No current data to sort for table:", tableId);
                return;
            }
            // Make a copy for sorting to not alter the original window.currentApiData order
            let dataToSort = [...currentDataForTable];

            if (sortState[tableId].key === sortKey) {
                sortState[tableId].direction = sortState[tableId].direction === 'asc' ? 'desc' : 'asc';
            } else {
                sortState[tableId].key = sortKey;
                sortState[tableId].direction = 'asc'; // Default to ascending on new key
            }

            const sortedData = sortData(dataToSort, sortKey, sortState[tableId].direction);
            updateItemSection(tableBodyId, sortedData, noItemsMessageId, sectionItemCountId, tableId);
            updateSortIndicators(tableElement, sortKey, sortState[tableId].direction); // Update for the clicked table
        });
    });


    // Initial data load and setup auto-refresh
    if (AUTO_REFRESH_INTERVAL_MS > 0) {
        setTimeout(refreshTicketData, 100); // Initial slight delay
        setInterval(refreshTicketData, AUTO_REFRESH_INTERVAL_MS);
        console.log(`${CURRENT_TICKET_TYPE_DISPLAY} data will refresh every ${AUTO_REFRESH_INTERVAL_MS / 1000} seconds.`);
    } else {
        // If no auto-refresh, still do an initial load
        setTimeout(refreshTicketData, 100);
        // Update timestamp from server render if auto-refresh is off.
        if (window.DASHBOARD_GENERATED_TIME_ISO_INITIAL) { // Passed from Flask if available
            convertAllUTCToLocal(window.DASHBOARD_GENERATED_TIME_ISO_INITIAL);
        } else {
            const dashboardTimeEl = document.getElementById('dashboard-generated-time');
            if (dashboardTimeEl && dashboardTimeEl.textContent === "Loading...") { // Default text
                dashboardTimeEl.textContent = "Auto-refresh disabled";
            }
        }
    }
});
