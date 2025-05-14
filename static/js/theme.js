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

    // --- Timezone Conversion ---
    function formatToLocal(utcDateStringInput, options = {}, dateOnly = false, prefix = "") {
        if (!utcDateStringInput || utcDateStringInput.trim() === 'N/A' || utcDateStringInput.trim() === '') {
            return 'N/A';
        }
        let parsableDateString = utcDateStringInput.trim();

        if (parsableDateString.includes('T') && (parsableDateString.endsWith('Z') || parsableDateString.match(/[+-]\d{2}:\d{2}$/))) {
            // Already good ISO
        } else if (parsableDateString.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [A-Z]+$/i)) { // Handles YYYY-MM-DD HH:MM:SS ZZZ
            parsableDateString = parsableDateString.replace(/ ([A-Z]+)$/i, "Z").replace(" ", "T");
        } else if (parsableDateString.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+(\+\d{2}:\d{2}|Z)?$/)) { // Handles ISO with microseconds from Python's isoformat()
             // This regex handles formats like "2023-10-26T10:30:00.123456+00:00"
             // No specific transformation needed here if it's already like this.
        } else if (parsableDateString.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)) { // YYYY-MM-DD HH:MM:SS
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

    function convertAllUTCToLocal() {
        // Dashboard Generated Time
        const dashboardTimeUtcEl = document.getElementById('dashboard-time-utc'); // This holds the data-utc-time attribute
        const dashboardTimeLocalEl = document.getElementById('dashboard-time-local');
        if (dashboardTimeUtcEl && dashboardTimeLocalEl) {
            const utcDateString = dashboardTimeUtcEl.getAttribute('data-utc-time'); // Get from data-utc-time
            if (utcDateString) {
                dashboardTimeLocalEl.textContent = formatToLocal(utcDateString);
                // dashboardTimeUtcEl.style.display = 'none'; // Optionally hide the original UTC if it's a separate element
            } else {
                dashboardTimeLocalEl.textContent = 'Error';
            }
        }

        // Ticket Datetimes (Now primarily for FR Due if it exists)
        document.querySelectorAll('.datetime-container').forEach(el => {
            const utcTimestamp = el.getAttribute('data-utc-datetime');
            // Friendly time is now directly rendered by server for "Updated" and "Created" columns
            // const friendlyTime = el.getAttribute('data-friendly-time');
            const dateOnly = el.getAttribute('data-date-only') === 'true';
            const prefix = el.getAttribute('data-prefix') || "";

            const localTimeSpan = el.querySelector('.local-datetime');
            // const friendlyTimeSpan = el.querySelector('.friendly-datetime');
            // const utcDetailSpan = el.querySelector('.utc-detail');

            if (utcTimestamp && localTimeSpan) { // Only update if localTimeSpan exists for this container
                localTimeSpan.textContent = formatToLocal(utcTimestamp, {}, dateOnly, prefix);
            } else if (localTimeSpan) { // If the span exists but no timestamp, clear or set N/A
                localTimeSpan.textContent = (prefix && utcTimestamp === '') ? prefix + 'N/A' : 'N/A';
            }
        });
    }
    convertAllUTCToLocal();
});
