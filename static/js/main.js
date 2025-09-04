document.addEventListener('DOMContentLoaded', () => {
    const body = document.body;
    const themeToggle = document.getElementById('theme-toggle');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const agentFilter = document.getElementById('agent-filter');

    // --- Sidebar Logic ---
    function applySidebarState() {
        const isCollapsed = localStorage.getItem('sidebar_collapsed') === 'true';
        if (isCollapsed) {
            body.classList.add('sidebar-collapsed');
        } else {
            body.classList.remove('sidebar-collapsed');
        }
    }

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', () => {
            body.classList.toggle('sidebar-collapsed');
            localStorage.setItem('sidebar_collapsed', body.classList.contains('sidebar-collapsed'));
        });
    }

    // --- Theme Logic ---
    function applyTheme(theme) {
        if (theme === 'dark') {
            body.classList.remove('light-mode');
            body.classList.add('dark-mode');
            if (themeToggle) {
                themeToggle.innerHTML = '<i class="fas fa-sun"></i> <span>Light Mode</span>';
            }
        } else { // Default to light
            body.classList.remove('dark-mode');
            body.classList.add('light-mode');
            if (themeToggle) {
                themeToggle.innerHTML = '<i class="fas fa-moon"></i> <span>Dark Mode</span>';
            }
        }
    }

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            let newTheme = body.classList.contains('light-mode') ? 'dark' : 'light';
            localStorage.setItem('theme', newTheme);
            applyTheme(newTheme);
        });
    }

    // --- Agent Filter Logic ---
    if (agentFilter) {
        agentFilter.addEventListener('change', () => {
            const selectedAgentId = agentFilter.value;
            const url = new URL(window.location);
            if (selectedAgentId) {
                url.searchParams.set('agent_id', selectedAgentId);
            } else {
                url.searchParams.delete('agent_id');
            }
            window.location.href = url.toString();
        });
    }

    // --- Initial State Application ---
    const savedTheme = localStorage.getItem('theme') || 'light';
    applyTheme(savedTheme);
    applySidebarState();


    // --- Ticket Data Fetching & Rendering Logic (from theme.js) ---
    function formatToLocal(utcDateStringInput, options = {}, dateOnly = false, prefix = "") {
        if (!utcDateStringInput || utcDateStringInput.trim() === 'N/A' || utcDateStringInput.trim() === '') {
            return 'N/A';
        }
        let parsableDateString = utcDateStringInput.trim().replace(' ', 'T');
        if (!parsableDateString.endsWith('Z') && !parsableDateString.match(/[+-]\d{2}:\d{2}$/)) {
            parsableDateString += 'Z'; // Assume UTC if no timezone
        }

        const date = new Date(parsableDateString);
        if (isNaN(date.getTime())) {
            return utcDateStringInput; // Return original if parsing fails
        }

        let Noptions = dateOnly
        ? { year: 'numeric', month: 'short', day: 'numeric', ...options }
        : { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true, ...options };
        return prefix + date.toLocaleString(undefined, Noptions);
    }

    function convertAllUTCToLocal(isoTimestamp) {
        const dashboardTimeLocalEl = document.getElementById('dashboard-generated-time');
        if (dashboardTimeLocalEl && isoTimestamp) {
            dashboardTimeLocalEl.textContent = formatToLocal(isoTimestamp);
        }
        document.querySelectorAll('.datetime-container').forEach(el => {
            const utcTimestamp = el.getAttribute('data-utc-datetime');
            const prefix = el.getAttribute('data-prefix') || "";
            const localTimeSpan = el.querySelector('.local-datetime');
            if (utcTimestamp && localTimeSpan) {
                localTimeSpan.textContent = formatToLocal(utcTimestamp, {}, false, prefix);
            }
        });
    }

    const FRESHSERVICE_BASE_URL = window.FRESHSERVICE_BASE_URL || '';
    const AUTO_REFRESH_INTERVAL_MS = window.AUTO_REFRESH_MS || 0;
    const CURRENT_TICKET_TYPE_SLUG = window.CURRENT_TICKET_TYPE_SLUG || 'incidents';

    window.currentApiData = {};
    let sortState = {
        's1-item-table': { key: null, direction: 'asc' },
        's2-item-table': { key: null, direction: 'asc' },
        's3-item-table': { key: null, direction: 'asc' },
        's4-item-table': { key: null, direction: 'asc' }
    };

    function formatItemSubjectForRender(subject, descriptionText) {
        let subjectText = subject ? subject.substring(0, 60) + (subject.length > 60 ? '...' : '') : 'No Subject';
        let tooltipHtml = '';
        if (descriptionText) {
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = descriptionText;
            const strippedDescription = tempDiv.textContent || tempDiv.innerText || "";
            const truncatedDescription = strippedDescription.substring(0, 300) + (strippedDescription.length > 300 ? '...' : '');
            tooltipHtml = `<span class="tooltiptext">${truncatedDescription.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</span>`;
        }
        return `${subjectText}${tooltipHtml}`;
    }

    function renderItemRow(item) {
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
        if (item.first_responded_at_iso === null && item.fr_due_by_str) {
            slaDetailHtml = `<div class="datetime-container" data-utc-datetime="${item.fr_due_by_str}" data-prefix="FR Due: "><small class="local-datetime">Loading...</small></div>`;
        } else if (item.type === 'Service Request' && item.due_by_str) {
            slaDetailHtml = `<div class="datetime-container" data-utc-datetime="${item.due_by_str}" data-prefix="Due: "><small class="local-datetime">Loading...</small></div>`;
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
        </tr>`;
    }

    function updateItemSection(sectionIdPrefix, items) {
        const tableBody = document.getElementById(`${sectionIdPrefix}-items-body`);
        const noItemsMessageElement = document.getElementById(`${sectionIdPrefix}-no-items-message`);
        const sectionItemCountElement = document.getElementById(`${sectionIdPrefix}-item-count`);

        if (!tableBody || !noItemsMessageElement || !sectionItemCountElement) return;

        sectionItemCountElement.textContent = items.length;
        tableBody.innerHTML = '';

        if (items && items.length > 0) {
            items.forEach(item => {
                tableBody.innerHTML += renderItemRow(item);
            });
            noItemsMessageElement.style.display = 'none';
        } else {
            noItemsMessageElement.style.display = 'block';
        }
    }

    async function refreshTicketData() {
        try {
            const url = new URL(`/api/tickets/${CURRENT_TICKET_TYPE_SLUG}`, window.location.origin);
            const selectedAgentId = new URLSearchParams(window.location.search).get('agent_id');
            if (selectedAgentId) {
                url.searchParams.set('agent_id', selectedAgentId);
            }
            const response = await fetch(url);
            if (!response.ok) {
                console.error(`Failed to fetch data:`, response.status);
                return;
            }
            const data = await response.json();
            window.currentApiData = data;

            document.getElementById('total-active-items-count').textContent = data.total_active_items;

            let s1Data = data.s1_items || [];
            let s2Data = data.s2_items || [];
            let s3Data = data.s3_items || [];
            let s4Data = data.s4_items || [];

            if (sortState['s1-item-table'].key) s1Data = sortData([...s1Data], sortState['s1-item-table'].key, sortState['s1-item-table'].direction);
            if (sortState['s2-item-table'].key) s2Data = sortData([...s2Data], sortState['s2-item-table'].key, sortState['s2-item-table'].direction);
            if (sortState['s3-item-table'].key) s3Data = sortData([...s3Data], sortState['s3-item-table'].key, sortState['s3-item-table'].direction);
            if (sortState['s4-item-table'].key) s4Data = sortData([...s4Data], sortState['s4-item-table'].key, sortState['s4-item-table'].direction);

            updateItemSection('s1', s1Data);
            updateItemSection('s2', s2Data);
            updateItemSection('s3', s3Data);
            updateItemSection('s4', s4Data);

            updateAllSortIndicators();
            if(data.dashboard_generated_time_iso){
                convertAllUTCToLocal(data.dashboard_generated_time_iso);
            }

        } catch (error) {
            console.error(`Error refreshing data:`, error);
        }
    }

    function sortData(dataArray, key, direction) {
        if (!dataArray) return [];
        dataArray.sort((a, b) => {
            let valA = a[key];
            let valB = b[key];
            if (valA == null) return 1;
            if (valB == null) return -1;
            if (key.endsWith('_at_str') || key.endsWith('_by_str')) {
                return direction === 'asc' ? new Date(valA) - new Date(valB) : new Date(valB) - new Date(valA);
            } else if (typeof valA === 'number') {
                return direction === 'asc' ? valA - valB : valB - valA;
            } else {
                return direction === 'asc' ? String(valA).localeCompare(String(valB)) : String(valB).localeCompare(String(valA));
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
            if (tableElement && sortState[tableId].key) {
                updateSortIndicators(tableElement, sortState[tableId].key, sortState[tableId].direction);
            }
        }
    }

    document.querySelectorAll('.sortable-header').forEach(header => {
        header.addEventListener('click', () => {
            const sortKey = header.dataset.sortKey;
            const tableElement = header.closest('.item-table');
            if (!tableElement) return;
            const tableId = tableElement.id;
            const sectionPrefix = tableId.substring(0, 2);

            let currentDataForTable = window.currentApiData[`${sectionPrefix}_items`];
            if (!currentDataForTable) return;

            let dataToSort = [...currentDataForTable];

            if (sortState[tableId].key === sortKey) {
                sortState[tableId].direction = sortState[tableId].direction === 'asc' ? 'desc' : 'asc';
            } else {
                sortState[tableId].key = sortKey;
                sortState[tableId].direction = 'asc';
            }

            const sortedData = sortData(dataToSort, sortKey, sortState[tableId].direction);
            updateItemSection(sectionPrefix, sortedData);
            updateSortIndicators(tableElement, sortKey, sortState[tableId].direction);
            convertAllUTCToLocal(); // Re-run date conversion after re-render
        });
    });

    if (AUTO_REFRESH_INTERVAL_MS > 0) {
        setTimeout(refreshTicketData, 100);
        setInterval(refreshTicketData, AUTO_REFRESH_INTERVAL_MS);
    } else {
        setTimeout(refreshTicketData, 100);
    }
});
