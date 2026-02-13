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
    } else if (tabName === 'distribution') {
        loadSSHHosts();
    } else if (tabName === 'logs') {
        loadDistributionLogs();
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

// Toggle SSH File Overrides Section
function toggleSSHFileOverrides() {
    const checkbox = document.getElementById('ssh_use_file_overrides');
    const section = document.getElementById('ssh-file-overrides-section');
    section.style.display = checkbox.checked ? 'block' : 'none';
}

// Reset SSH File Overrides fields
function resetSSHFileOverrides() {
    document.getElementById('ssh_use_file_overrides').checked = false;
    document.getElementById('ssh_cert_filename').value = '';
    document.getElementById('ssh_chain_filename').value = '';
    document.getElementById('ssh_privkey_filename').value = '';
    document.getElementById('ssh_fullchain_filename').value = '';
    toggleSSHFileOverrides();
}

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

// SSH Host Management
async function loadSSHHosts() {
    try {
        const response = await fetch('/api/ssh-hosts');
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        const hostsList = document.getElementById('ssh-hosts-list');
        
        if (data.hosts.length === 0) {
            hostsList.innerHTML = '<p class="no-data">No SSH hosts configured. Add one above.</p>';
            return;
        }
        
        hostsList.innerHTML = '';
        data.hosts.forEach(host => {
            const hostCard = createSSHHostCard(host);
            hostsList.appendChild(hostCard);
        });
        
    } catch (error) {
        console.error('Failed to load SSH hosts:', error);
        showNotification('Failed to load SSH hosts: ' + error.message, 'error');
    }
}

function createSSHHostCard(host) {
    const card = document.createElement('div');
    card.className = 'collapsible-card';
    
    const header = document.createElement('div');
    header.className = 'card-header';
    header.onclick = () => toggleCard(card);
    
    const title = document.createElement('h3');
    title.innerHTML = `<span class="toggle-icon">▶</span> ${host.display_name}`;
    header.appendChild(title);
    
    const content = document.createElement('div');
    content.className = 'card-content';
    content.style.display = 'none';
    
    content.innerHTML = `
        <div class="info-grid">
            <div><strong>Hostname:</strong> ${host.hostname}</div>
            <div><strong>Port:</strong> ${host.port}</div>
            <div><strong>Username:</strong> ${host.username}</div>
            <div><strong>Certificate Path:</strong> ${host.cert_path}</div>
            <div><strong>Use Sudo:</strong> ${host.use_sudo ? 'Yes' : 'No'}</div>
        </div>
        ${host.file_overrides ? 
            `<p class="file-overrides-info">✓ Using custom file names: ${
                Object.entries(host.file_overrides)
                    .map(([key, value]) => `${key}=${value}`)
                    .join(', ')
            }</p>` : ''}
        <div class="card-actions">
            <button class="btn btn-small" onclick="editSSHHost('${host.display_name}')">✏️ Edit</button>
            <button class="btn btn-small btn-danger" onclick="deleteSSHHost('${host.display_name}')">🗑️ Delete</button>
        </div>
    `;
    
    card.appendChild(header);
    card.appendChild(content);
    
    return card;
}

function toggleCard(card) {
    const content = card.querySelector('.card-content');
    const icon = card.querySelector('.toggle-icon');
    
    if (content.style.display === 'none') {
        content.style.display = 'block';
        icon.textContent = '▼';
    } else {
        content.style.display = 'none';
        icon.textContent = '▶';
    }
}

// SSH Host Form Handling
document.getElementById('ssh-host-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const editMode = document.getElementById('ssh_edit_mode').value === 'true';
    const originalDisplayName = document.getElementById('ssh_original_display_name').value;
    
    const formData = {
        display_name: document.getElementById('ssh_display_name').value,
        hostname: document.getElementById('ssh_hostname').value,
        port: parseInt(document.getElementById('ssh_port').value),
        username: document.getElementById('ssh_username').value,
        password: document.getElementById('ssh_password').value,
        cert_path: document.getElementById('ssh_cert_path').value,
        use_sudo: document.getElementById('ssh_use_sudo').checked
    };
    
    // Add file overrides if the checkbox is checked
    const useFileOverrides = document.getElementById('ssh_use_file_overrides').checked;
    if (useFileOverrides) {
        const certFilename = document.getElementById('ssh_cert_filename').value.trim();
        const chainFilename = document.getElementById('ssh_chain_filename').value.trim();
        const privkeyFilename = document.getElementById('ssh_privkey_filename').value.trim();
        const fullchainFilename = document.getElementById('ssh_fullchain_filename').value.trim();
        
        const fileOverrides = {};
        if (certFilename) fileOverrides.cert = certFilename;
        if (chainFilename) fileOverrides.chain = chainFilename;
        if (privkeyFilename) fileOverrides.privkey = privkeyFilename;
        if (fullchainFilename) fileOverrides.fullchain = fullchainFilename;
        
        if (Object.keys(fileOverrides).length > 0) {
            formData.file_overrides = fileOverrides;
        }
    }
    
    // Validate password for new hosts
    if (!editMode && !formData.password) {
        showNotification('Password is required for new SSH hosts', 'error');
        return;
    }
    
    try {
        let response;
        if (editMode) {
            response = await fetch(`/api/ssh-hosts/${encodeURIComponent(originalDisplayName)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });
        } else {
            response = await fetch('/api/ssh-hosts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });
        }
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to save SSH host');
        }
        
        showNotification(data.message, 'success');
        document.getElementById('ssh-host-form').reset();
        document.getElementById('ssh_port').value = '22';
        
        if (editMode) {
            cancelEditSSHHost();
        }
        
        loadSSHHosts();
        
    } catch (error) {
        console.error('Failed to save SSH host:', error);
        showNotification('Failed to save SSH host: ' + error.message, 'error');
    }
});

async function editSSHHost(displayName) {
    try {
        const response = await fetch('/api/ssh-hosts');
        const data = await response.json();
        
        const host = data.hosts.find(h => h.display_name === displayName);
        if (!host) {
            throw new Error('Host not found');
        }
        
        // Populate form
        document.getElementById('ssh_display_name').value = host.display_name;
        document.getElementById('ssh_hostname').value = host.hostname;
        document.getElementById('ssh_port').value = host.port;
        document.getElementById('ssh_username').value = host.username;
        document.getElementById('ssh_password').value = '';
        document.getElementById('ssh_cert_path').value = host.cert_path;
        document.getElementById('ssh_use_sudo').checked = host.use_sudo || false;
        
        // Populate file overrides if present
        if (host.file_overrides) {
            document.getElementById('ssh_use_file_overrides').checked = true;
            toggleSSHFileOverrides();
            document.getElementById('ssh_cert_filename').value = host.file_overrides.cert || '';
            document.getElementById('ssh_chain_filename').value = host.file_overrides.chain || '';
            document.getElementById('ssh_privkey_filename').value = host.file_overrides.privkey || '';
            document.getElementById('ssh_fullchain_filename').value = host.file_overrides.fullchain || '';
        } else {
            resetSSHFileOverrides();
        }
        
        // Set edit mode
        document.getElementById('ssh_edit_mode').value = 'true';
        document.getElementById('ssh_original_display_name').value = displayName;
        document.getElementById('ssh-host-form-title').textContent = 'Edit SSH Host';
        document.getElementById('ssh-host-submit-btn').textContent = 'Update SSH Host';
        document.getElementById('cancel-ssh-edit-btn').style.display = 'inline-block';
        document.getElementById('password-hint').textContent = 'Leave empty to keep existing password';
        
        // Scroll to form
        document.getElementById('ssh-host-form').scrollIntoView({ behavior: 'smooth' });
        
    } catch (error) {
        console.error('Failed to load SSH host:', error);
        showNotification('Failed to load SSH host: ' + error.message, 'error');
    }
}

function cancelEditSSHHost() {
    document.getElementById('ssh-host-form').reset();
    document.getElementById('ssh_port').value = '22';
    document.getElementById('ssh_use_sudo').checked = false;
    resetSSHFileOverrides();
    document.getElementById('ssh_edit_mode').value = 'false';
    document.getElementById('ssh_original_display_name').value = '';
    document.getElementById('ssh-host-form-title').textContent = 'Add SSH Host';
    document.getElementById('ssh-host-submit-btn').textContent = 'Add SSH Host';
    document.getElementById('cancel-ssh-edit-btn').style.display = 'none';
    document.getElementById('password-hint').textContent = 'Required for new hosts. Leave empty to keep existing password when editing.';
}

async function deleteSSHHost(displayName) {
    if (!confirm(`Are you sure you want to delete SSH host "${displayName}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/ssh-hosts/${encodeURIComponent(displayName)}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to delete SSH host');
        }
        
        showNotification(data.message, 'success');
        loadSSHHosts();
        
    } catch (error) {
        console.error('Failed to delete SSH host:', error);
        showNotification('Failed to delete SSH host: ' + error.message, 'error');
    }
}

// Distribution Logs
async function loadDistributionLogs() {
    try {
        const eventType = document.getElementById('log-filter').value;
        const url = eventType ? `/api/distribution/logs?event_type=${eventType}` : '/api/distribution/logs';
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        // Display statistics
        const statsDiv = document.getElementById('log-stats');
        statsDiv.innerHTML = `
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>${data.stats.total_syncs}</h3>
                    <p>Total Syncs</p>
                </div>
                <div class="stat-card">
                    <h3>${data.stats.total_distributions}</h3>
                    <p>Total Distributions</p>
                </div>
                <div class="stat-card success">
                    <h3>${data.stats.successful_distributions}</h3>
                    <p>Successful</p>
                </div>
                <div class="stat-card error">
                    <h3>${data.stats.failed_distributions}</h3>
                    <p>Failed</p>
                </div>
            </div>
        `;
        
        // Display logs
        const logsDiv = document.getElementById('distribution-logs');
        
        if (data.logs.length === 0) {
            logsDiv.innerHTML = '<p class="no-data">No logs found.</p>';
            return;
        }
        
        logsDiv.innerHTML = '<div class="logs-container"></div>';
        const logsContainer = logsDiv.querySelector('.logs-container');
        
        data.logs.forEach(log => {
            const logEntry = createLogEntry(log);
            logsContainer.appendChild(logEntry);
        });
        
    } catch (error) {
        console.error('Failed to load distribution logs:', error);
        showNotification('Failed to load logs: ' + error.message, 'error');
    }
}

function createLogEntry(log) {
    const entry = document.createElement('div');
    entry.className = `log-entry log-${log.status || 'info'}`;
    
    const timestamp = new Date(log.timestamp).toLocaleString();
    const eventIcon = getEventIcon(log.event_type);
    const statusBadge = getStatusBadge(log.status);
    
    let content = `
        <div class="log-header">
            <span class="log-icon">${eventIcon}</span>
            <span class="log-type">${formatEventType(log.event_type)}</span>
            ${statusBadge}
            <span class="log-time">${timestamp}</span>
        </div>
        <div class="log-details">
    `;
    
    if (log.event_type === 'certificate_sync') {
        content += `<p><strong>Domains:</strong> ${log.domains.join(', ')}</p>`;
        if (log.results && log.results.length > 0) {
            content += '<p><strong>Results:</strong></p><ul>';
            log.results.forEach(result => {
                content += `<li>${result.domain}: ${result.status}</li>`;
            });
            content += '</ul>';
        }
    } else if (log.event_type === 'certificate_distribution') {
        content += `<p><strong>Domain:</strong> ${log.domain}</p>`;
        content += `<p><strong>Host:</strong> ${log.host}</p>`;
        if (log.files && log.files.length > 0) {
            content += `<p><strong>Files:</strong> ${log.files.join(', ')}</p>`;
        }
        if (log.error) {
            content += `<p class="error-message"><strong>Error:</strong> ${log.error}</p>`;
        }
    } else if (log.event_type === 'bulk_distribution') {
        content += `<p><strong>Total Hosts:</strong> ${log.total_hosts}</p>`;
        content += `<p><strong>Successful:</strong> ${log.successful} | <strong>Failed:</strong> ${log.failed}</p>`;
        if (log.results && log.results.length > 0) {
            content += '<p><strong>Results:</strong></p><ul>';
            log.results.forEach(result => {
                content += `<li>${result.host}: ${result.status}`;
                if (result.error) {
                    content += ` - ${result.error}`;
                }
                content += '</li>';
            });
            content += '</ul>';
        }
    }
    
    content += '</div>';
    entry.innerHTML = content;
    
    return entry;
}

function getEventIcon(eventType) {
    const icons = {
        'certificate_sync': '🔄',
        'certificate_distribution': '🚀',
        'bulk_distribution': '📦'
    };
    return icons[eventType] || '📝';
}

function getStatusBadge(status) {
    if (!status) return '';
    
    const badges = {
        'success': '<span class="badge badge-success">Success</span>',
        'error': '<span class="badge badge-error">Error</span>',
        'partial': '<span class="badge badge-warning">Partial</span>'
    };
    return badges[status] || `<span class="badge">${status}</span>`;
}

function formatEventType(eventType) {
    const formats = {
        'certificate_sync': 'Certificate Sync',
        'certificate_distribution': 'Certificate Distribution',
        'bulk_distribution': 'Bulk Distribution'
    };
    return formats[eventType] || eventType;
}
