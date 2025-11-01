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
        document.getElementById('cron').value = data.schedule.cron || '0 2 * * *';
        
    } catch (error) {
        console.error('Failed to load settings:', error);
        showNotification('Failed to load settings: ' + error.message, 'error');
    }
}

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
    
    const formData = new FormData(e.target);
    const data = {
        enabled: document.getElementById('schedule_enabled').checked,
        cron: formData.get('cron')
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
    const altNamesStr = formData.get('alt_names');
    const altNames = altNamesStr ? altNamesStr.split(',').map(s => s.trim()).filter(s => s) : [];
    
    const data = {
        domain: formData.get('domain'),
        custom_name: formData.get('custom_name'),
        alt_names: altNames
    };
    
    try {
        const response = await fetch('/api/domains', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Failed to add domain');
        }
        
        showNotification(result.message || 'Domain added successfully');
        e.target.reset();
        loadDomains();
        
    } catch (error) {
        console.error('Error:', error);
        showNotification(error.message, 'error');
    }
});

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
                    <p>Custom name: ${domain.custom_name || domain.domain}</p>
                    ${domain.alt_names && domain.alt_names.length > 0 ? 
                        `<p>Alt names: ${domain.alt_names.join(', ')}</p>` : ''}
                </div>
                <button class="btn btn-danger" onclick="removeDomain('${domain.domain}')">Remove</button>
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

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
});

// Auto-refresh sync status when on sync tab
setInterval(() => {
    const syncTab = document.getElementById('sync');
    if (syncTab.classList.contains('active')) {
        loadSyncStatus();
    }
}, 5000);
