function toggleGuide() {
    const guide = document.getElementById('coverageGuide');
    const isHidden = guide.style.display === 'none';
    guide.style.display = isHidden ? 'block' : 'none';

    const button = document.querySelector('.guide-toggle');
    button.textContent = isHidden ? '📘 Hide Coverage Guide' : '📘 View Coverage Format Guide';
}

function changeTerm(termId) {
    // Navigate to the same page with the new term_id parameter
    if (termId) {
        const url = new URL(window.location);
        url.searchParams.set('term_id', termId);
        window.location.href = url.toString();
    }
}

function toggleTermForm() {
    const form = document.getElementById('create-term-form');
    const isHidden = form.style.display === 'none';
    form.style.display = isHidden ? 'block' : 'none';

    // Set minimum dates
    if (isHidden) {
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('start_date').setAttribute('min', today);
        document.getElementById('end_date').setAttribute('min', today);
        document.getElementById('availability_deadline').setAttribute('min', today);
    }
}

// Set default times based on common patterns
document.addEventListener('DOMContentLoaded', function () {
    console.log('DEBUG: DOM loaded');

    // Add debug event listener to term form
    const termForm = document.querySelector('.term-creation-form');
    if (termForm) {
        console.log('DEBUG: Found term form, adding submit listener');
        termForm.addEventListener('submit', function (e) {
            console.log('DEBUG: Term form submit triggered');
            console.log('DEBUG: Form data:', new FormData(this));
            // Don't prevent default, let it submit
        });
    } else {
        console.log('DEBUG: Term form not found!');
    }

    const startTime = document.getElementById('start_time');
    const endTime = document.getElementById('end_time');

    // Set default to 9AM-5PM if empty
    if (startTime && !startTime.value) startTime.value = '09:00';
    if (endTime && !endTime.value) endTime.value = '17:00';

    // Auto-update end time when start time changes
    startTime.addEventListener('change', function () {
        if (this.value && !endTime.value) {
            const start = new Date('2000-01-01 ' + this.value);
            start.setHours(start.getHours() + 8); // Default 8-hour shift
            endTime.value = start.toTimeString().slice(0, 5);
        }
    });
});

function toggleGapDashboard() {
    const panel = document.getElementById('gapDashboard');
    const btn = document.getElementById('gapToggle');
    if (!panel || !btn) return;
    const table = panel.querySelector('.gap-table');
    if (!table) return;
    if (table.style.display === 'none') {
        table.style.display = 'table';
        btn.textContent = 'Hide';
    } else {
        table.style.display = 'none';
        btn.textContent = 'Show';
    }
}

function clearAllCoverage() {
    if (!confirm('Are you sure you want to delete ALL coverage requirements? This action cannot be undone.')) return;
    const form = document.createElement('form');
    form.method = 'POST';
    form.innerHTML = '<input type="hidden" name="action" value="clear_all">';
    document.body.appendChild(form);
    form.submit();
}

function exportCoverage() {
    // Convert coverage data to CSV format
    const table = document.querySelector('.coverage-table');
    if (!table) {
        alert('No coverage data to export.');
        return;
    }

    let csv = 'Day,Start Time,End Time,Role,Required Count\n';

    const rows = table.querySelectorAll('tbody tr');
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 4) {
            const day = cells[0].textContent.trim();
            const timeRange = cells[1].textContent.trim();
            const [startTime, endTime] = timeRange.split(' - ');
            const role = cells[2].textContent.trim();
            const count = cells[3].textContent.trim();

            csv += `"${day}","${startTime}","${endTime}","${role}","${count}"\n`;
        }
    });

    // Download CSV
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'staffing_requirements.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

function viewAnalytics() {
    // Calculate some basic analytics
    const table = document.querySelector('.coverage-table');
    if (!table) {
        alert('No coverage data available for analysis.');
        return;
    }

    const rows = table.querySelectorAll('tbody tr');
    let totalHours = 0;
    let totalStaffHours = 0;
    let roleCount = {};

    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 4) {
            const timeRange = cells[1].textContent.trim();
            const [startTime, endTime] = timeRange.split(' - ');
            const role = cells[2].textContent.trim();
            const count = parseInt(cells[3].textContent.trim());

            // Calculate hours
            const start = new Date('2000-01-01 ' + startTime);
            const end = new Date('2000-01-01 ' + endTime);
            const hours = (end - start) / (1000 * 60 * 60);

            totalHours += hours;
            totalStaffHours += hours * count;

            roleCount[role] = (roleCount[role] || 0) + (hours * count);
        }
    });

    let analytics = `Coverage Analytics:\n\n`;
    analytics += `Total Coverage Hours: ${totalHours.toFixed(1)} hours\n`;
    analytics += `Total Staff Hours Required: ${totalStaffHours.toFixed(1)} hours\n\n`;
    analytics += `Hours by Role:\n`;

    Object.entries(roleCount).forEach(([role, hours]) => {
        analytics += `- ${role}: ${hours.toFixed(1)} hours\n`;
    });

    alert(analytics);
}

function validateCoverage() {
    const table = document.querySelector('.coverage-table');
    if (!table) {
        alert('No coverage data to validate.');
        return;
    }

    const rows = table.querySelectorAll('tbody tr');
    let issues = [];
    let daysCovered = new Set();

    rows.forEach((row, index) => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 4) {
            const day = cells[0].textContent.trim();
            const timeRange = cells[1].textContent.trim();
            const count = parseInt(cells[3].textContent.trim());

            daysCovered.add(day);

            // Check for reasonable counts
            if (count > 5) {
                issues.push(`High staff count (${count}) on ${day} at ${timeRange}`);
            }

            // Check for very short coverage windows
            const [startTime, endTime] = timeRange.split(' - ');
            const start = new Date('2000-01-01 ' + startTime);
            const end = new Date('2000-01-01 ' + endTime);
            const hours = (end - start) / (1000 * 60 * 60);

            if (hours < 1) {
                issues.push(`Very short coverage window (${hours}h) on ${day}`);
            }
        }
    });

    // Check for missing weekday coverage
    const weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];
    weekdays.forEach(day => {
        if (!daysCovered.has(day)) {
            issues.push(`No coverage defined for ${day}`);
        }
    });

    let validation = 'Coverage Validation Results:\n\n';
    if (issues.length === 0) {
        validation += '✅ All coverage requirements look good!\n';
        validation += `\n📊 Summary:\n`;
        validation += `- Days with coverage: ${daysCovered.size}\n`;
        validation += `- Total requirements: ${rows.length}\n`;
    } else {
        validation += '⚠️ Issues found:\n\n';
        issues.forEach(issue => {
            validation += `• ${issue}\n`;
        });
    }

    alert(validation);
}

// Form validation for coverage form only
document.getElementById('coverage-form').addEventListener('submit', function (e) {
    const startTime = document.getElementById('start_time').value;
    const endTime = document.getElementById('end_time').value;
    const action = e.target.querySelector('input[name="action"]').value;

    if (action === 'add_coverage' && startTime && endTime && startTime >= endTime) {
        e.preventDefault();
        alert('Start time must be before end time.');
        return false;
    }
});