// Tab Management
function openTab(tabName) {
    const tabContents = document.querySelectorAll('.tab-content');
    const tabButtons = document.querySelectorAll('.tab-button');
    
    tabContents.forEach(content => content.classList.remove('active'));
    tabButtons.forEach(button => button.classList.remove('active'));
    
    document.getElementById(tabName).classList.add('active');
    event.target.classList.add('active');
    
    // Load data when switching to specific tabs
    if (tabName === 'domains') {
        loadDomains();
    } else if (tabName === 'sync') {
        loadSyncStatus();
    } else if (tabName === 'settings') {
        loadSettings();
    }
}

// Notification System
function showNotification(message, type = 'success') {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.className = `notification ${type} show`;
    
    setTimeout(() => {
        notification.classList.remove('show');
    }, 3000);
}

// Load Settings
async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        // Update API settings
        document.getElementById('api_key').value = data.api.api_key || '';
        if (data.api.has_secret) {
            document.getElementById('secret_key').placeholder = '(hidden)';
        }
        
        // Update certificate settings
        document.getElementById('output_dir').value = data.certificates.output_dir || '/app/certificates';
        document.getElementById('naming_format').value = data.certificates.naming_format || '{domain}';
        
        // Update format checkboxes
        const formats = data.certificates.formats || ['pem'];
        document.querySelectorAll('input[name="format"]').forEach(checkbox => {
            checkbox.checked = formats.includes(checkbox.value);
        });
        
        // Update schedule settings
        document.getElementById('schedule_enabled').checked = data.schedule.enabled || false;
        parseCronToUI(data.schedule.cron || '0 2 * * *');
        
    } catch (error) {
        console.error('Failed to load settings:', error);
        showNotification('Failed to load settings: ' + error.message, 'error');
    }
}

// Parse cron expression to UI elements
function parseCronToUI(cron) {
    const parts = cron.split(' ');
    if (parts.length !== 5) {
        // Default to daily at 2 AM if invalid
        document.getElementById('frequency').value = 'daily';
        document.getElementById('hour').value = '2';
        document.getElementById('minute').value = '0';
        updateScheduleUI();
        updateCronPreview();
        return;
    }
    
    const [minute, hour, day, month, weekday] = parts;
    
    document.getElementById('minute').value = minute;
    document.getElementById('hour').value = hour;
    
    // Determine frequency
    if (hour === '*' && minute !== '*') {
        // Hourly
        document.getElementById('frequency').value = 'hourly';
    } else if (day === '*' && month === '*' && weekday === '*') {
        // Daily
        document.getElementById('frequency').value = 'daily';
    } else if (day === '*' && month === '*' && weekday !== '*' && !weekday.includes(',')) {
        // Weekly on specific day
        document.getElementById('frequency').value = 'weekly';
        document.getElementById('day_of_week').value = weekday;
    } else if (day === '*' && month === '*' && weekday !== '*' && weekday.includes(',')) {
        // Specific days
        document.getElementById('frequency').value = 'specific_days';
        const days = weekday.split(',');
        document.querySelectorAll('input[name="day"]').forEach(checkbox => {
            checkbox.checked = days.includes(checkbox.value);
        });
    } else if (day !== '*' && month === '*' && weekday === '*') {
        // Monthly
        document.getElementById('frequency').value = 'monthly';
        document.getElementById('day_of_month').value = day;
    } else {
        // Default to daily
        document.getElementById('frequency').value = 'daily';
    }
    
    updateScheduleUI();
    updateCronPreview();
}

// Update schedule UI based on frequency
function updateScheduleUI() {
    const frequency = document.getElementById('frequency').value;
    
    // Hide all optional groups
    document.getElementById('day_of_week_group').style.display = 'none';
    document.getElementById('specific_days_group').style.display = 'none';
    document.getElementById('day_of_month_group').style.display = 'none';
    document.getElementById('time_group').style.display = 'block';
    
    // Show relevant groups based on frequency
    if (frequency === 'hourly') {
        document.getElementById('time_group').style.display = 'none';
    } else if (frequency === 'weekly') {
        document.getElementById('day_of_week_group').style.display = 'block';
    } else if (frequency === 'specific_days') {
        document.getElementById('specific_days_group').style.display = 'block';
    } else if (frequency === 'monthly') {
        document.getElementById('day_of_month_group').style.display = 'block';
    }
}

// Generate cron expression from UI
function generateCronFromUI() {
    const frequency = document.getElementById('frequency').value;
    const minute = document.getElementById('minute').value;
    const hour = document.getElementById('hour').value;
    
    let cron = '';
    
    if (frequency === 'hourly') {
        cron = `${minute} * * * *`;
    } else if (frequency === 'daily') {
        cron = `${minute} ${hour} * * *`;
    } else if (frequency === 'weekly') {
        const dayOfWeek = document.getElementById('day_of_week').value;
        cron = `${minute} ${hour} * * ${dayOfWeek}`;
    } else if (frequency === 'specific_days') {
        const days = Array.from(document.querySelectorAll('input[name="day"]:checked'))
            .map(checkbox => checkbox.value)
            .sort((a, b) => parseInt(a) - parseInt(b))
            .join(',');
        cron = days ? `${minute} ${hour} * * ${days}` : `${minute} ${hour} * * *`;
    } else if (frequency === 'monthly') {
        const dayOfMonth = document.getElementById('day_of_month').value;
        cron = `${minute} ${hour} ${dayOfMonth} * *`;
    }
    
    return cron;
}

// Update cron preview
function updateCronPreview() {
    const cron = generateCronFromUI();
    document.getElementById('cron_preview').value = cron;
}

// Add event listeners for schedule changes
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('frequency').addEventListener('change', () => {
        updateScheduleUI();
        updateCronPreview();
    });
    
    ['minute', 'hour', 'day_of_week', 'day_of_month'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', updateCronPreview);
        }
    });
    
    document.querySelectorAll('input[name="day"]').forEach(checkbox => {
        checkbox.addEventListener('change', updateCronPreview);
    });
    
    loadSettings();
});

// API Form Handler
document.getElementById('api-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const data = {
        api_key: formData.get('api_key'),
        secret_key: formData.get('secret_key')
    };
    
    try {
        const response = await fetch('/api/settings/api', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Failed to update API settings');
        }
        
        showNotification(result.message || 'API credentials updated successfully');
        document.getElementById('secret_key').value = '';
        document.getElementById('secret_key').placeholder = '(hidden)';
        
    } catch (error) {
        console.error('Error:', error);
        showNotification(error.message, 'error');
    }
});

// Certificate Form Handler
document.getElementById('cert-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const formats = Array.from(document.querySelectorAll('input[name="format"]:checked'))
        .map(checkbox => checkbox.value);
    
    const data = {
        output_dir: formData.get('output_dir'),
        naming_format: formData.get('naming_format'),
        formats: formats
    };
    
    try {
        const response = await fetch('/api/settings/certificates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Failed to update certificate settings');
        }
        
        showNotification(result.message || 'Certificate settings updated successfully');
        
    } catch (error) {
        console.error('Error:', error);
        showNotification(error.message, 'error');
    }
});

// Schedule Form Handler
document.getElementById('schedule-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const cron = generateCronFromUI();
    const data = {
        enabled: document.getElementById('schedule_enabled').checked,
        cron: cron
    };
    
    try {
        const response = await fetch('/api/settings/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Failed to update schedule settings');
        }
        
        showNotification(result.message || 'Schedule settings updated successfully');
        
    } catch (error) {
        console.error('Error:', error);
        showNotification(error.message, 'error');
    }
});

// Domain Form Handler
document.getElementById('domain-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const editMode = document.getElementById('edit_mode').value === 'true';
    const originalDomain = document.getElementById('original_domain').value;
    
    const altFileNamesStr = formData.get('alt_file_names');
    const altFileNames = altFileNamesStr ? altFileNamesStr.split(',').map(s => s.trim()).filter(s => s) : [];
    
    const data = {
        domain: formData.get('domain'),
        custom_name: formData.get('custom_name'),
        separator: formData.get('separator'),
        alt_file_names: altFileNames
    };
    
    try {
        let response;
        if (editMode) {
            response = await fetch(`/api/domains/${encodeURIComponent(originalDomain)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        } else {
            response = await fetch('/api/domains', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        }
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || `Failed to ${editMode ? 'update' : 'add'} domain`);
        }
        
        showNotification(result.message || `Domain ${editMode ? 'updated' : 'added'} successfully`);
        cancelEditDomain();
        loadDomains();
        
    } catch (error) {
        console.error('Error:', error);
        showNotification(error.message, 'error');
    }
});

// Edit Domain
function editDomain(domain) {
    // Scroll to form
    document.getElementById('domain-form-title').scrollIntoView({ behavior: 'smooth' });
    
    // Set edit mode
    document.getElementById('edit_mode').value = 'true';
    document.getElementById('original_domain').value = domain.domain;
    
    // Populate form
    document.getElementById('domain').value = domain.domain;
    document.getElementById('custom_name').value = domain.custom_name || '';
    document.getElementById('separator').value = domain.separator || '_';
    document.getElementById('alt_file_names').value = (domain.alt_file_names || []).join(', ');
    
    // Update UI
    document.getElementById('domain-form-title').textContent = 'Edit Domain';
    document.getElementById('domain-submit-btn').textContent = 'Update Domain';
    document.getElementById('cancel-edit-btn').style.display = 'inline-block';
}

// Cancel Edit Domain
function cancelEditDomain() {
    // Reset form
    document.getElementById('domain-form').reset();
    document.getElementById('edit_mode').value = 'false';
    document.getElementById('original_domain').value = '';
    
    // Update UI
    document.getElementById('domain-form-title').textContent = 'Add Domain';
    document.getElementById('domain-submit-btn').textContent = 'Add Domain';
    document.getElementById('cancel-edit-btn').style.display = 'none';
}

// Load Domains
async function loadDomains() {
    const domainsList = document.getElementById('domains-list');
    
    try {
        const response = await fetch('/api/domains');
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        if (!data.domains || data.domains.length === 0) {
            domainsList.innerHTML = '<p class="loading">No domains configured yet.</p>';
            return;
        }
        
        domainsList.innerHTML = data.domains.map(domain => `
            <div class="domain-item">
                <div class="domain-info">
                    <h3>${domain.domain}</h3>
                    <p>Base name: ${domain.custom_name || domain.domain}</p>
                    <p>Separator: ${domain.separator || '_'}</p>
                    ${domain.alt_file_names && domain.alt_file_names.length > 0 ? 
                        `<p>Alternative file names: ${domain.alt_file_names.join(', ')}</p>` : ''}
                </div>
                <div style="display: flex; gap: 10px;">
                    <button class="btn btn-primary" onclick='editDomain(${JSON.stringify(domain)})'>Edit</button>
                    <button class="btn btn-danger" onclick="removeDomain('${domain.domain}')">Remove</button>
                </div>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Failed to load domains:', error);
        domainsList.innerHTML = '<p class="loading">Failed to load domains.</p>';
        showNotification('Failed to load domains: ' + error.message, 'error');
    }
}

// Remove Domain
async function removeDomain(domain) {
    if (!confirm(`Are you sure you want to remove ${domain}?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/domains/${encodeURIComponent(domain)}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Failed to remove domain');
        }
        
        showNotification(result.message || 'Domain removed successfully');
        loadDomains();
        
    } catch (error) {
        console.error('Error:', error);
        showNotification(error.message, 'error');
    }
}

// Trigger Sync
async function triggerSync() {
    const button = document.getElementById('sync-button');
    button.disabled = true;
    button.textContent = '⏳ Syncing...';
    
    try {
        const response = await fetch('/api/sync', {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.error) {
            throw new Error(result.error);
        }
        
        showNotification('Sync completed successfully');
        loadSyncStatus();
        
    } catch (error) {
        console.error('Error:', error);
        showNotification('Sync failed: ' + error.message, 'error');
    } finally {
        button.disabled = false;
        button.textContent = '🔄 Sync All Certificates Now';
    }
}

// Load Sync Status
async function loadSyncStatus() {
    try {
        const response = await fetch('/api/sync/status');
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        // Update status
        const statusDiv = document.getElementById('sync-status');
        const statusClass = `status-${data.status}`;
        statusDiv.innerHTML = `
            <p>Status: <span class="status-badge ${statusClass}">${data.status.toUpperCase()}</span></p>
            ${data.last_sync ? `<p>Last sync: ${new Date(data.last_sync).toLocaleString()}</p>` : ''}
        `;
        
        // Update results
        const resultsDiv = document.getElementById('sync-results');
        if (!data.results || data.results.length === 0) {
            resultsDiv.innerHTML = '<p class="loading">No sync results yet</p>';
            return;
        }
        
        resultsDiv.innerHTML = data.results.map(result => `
            <div class="result-item ${result.status === 'error' ? 'error' : ''}">
                <h4>${result.domain}</h4>
                <p>Status: ${result.status}</p>
                ${result.error ? `<p style="color: #e74c3c;">${result.error}</p>` : ''}
                ${result.files ? `
                    <ul>
                        ${result.files.map(file => `<li>${file}</li>`).join('')}
                    </ul>
                ` : ''}
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Failed to load sync status:', error);
        showNotification('Failed to load sync status: ' + error.message, 'error');
    }
}

// Auto-refresh sync status when on sync tab
setInterval(() => {
    const syncTab = document.getElementById('sync');
    if (syncTab.classList.contains('active')) {
        loadSyncStatus();
    }
}, 5000);

// Dark Mode Toggle
function toggleDarkMode() {
    const body = document.body;
    const icon = document.getElementById('dark-mode-icon');
    
    body.classList.toggle('dark-mode');
    
    // Update icon
    if (body.classList.contains('dark-mode')) {
        icon.textContent = '☀️';
        localStorage.setItem('darkMode', 'enabled');
    } else {
        icon.textContent = '🌙';
        localStorage.setItem('darkMode', 'disabled');
    }
}

// Load dark mode preference on page load
(function() {
    const darkMode = localStorage.getItem('darkMode');
    if (darkMode === 'enabled') {
        document.body.classList.add('dark-mode');
        document.getElementById('dark-mode-icon').textContent = '☀️';
    }
})();
