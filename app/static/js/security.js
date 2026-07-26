// Security tab: password change, TOTP enrolment and recovery codes.
//
// Listeners are registered inside DOMContentLoaded rather than at top level, so
// this file cannot throw on a page that does not contain the Security tab.

let securityState = null;

// Status glyphs carry the meaning alongside the words, so the state is readable
// without relying on colour.
const STATUS_ON = '●';
const STATUS_PENDING = '◐';
const STATUS_OFF = '○';

function setStatusIndicator(elementId, glyph, html, modifier) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.className = 'status-indicator' + (modifier ? ' ' + modifier : '');
    el.querySelector('.status-glyph').textContent = glyph;
    el.querySelector('.status-text').innerHTML = html;
}

function show(elementId, visible) {
    const el = document.getElementById(elementId);
    if (el) {
        el.classList.toggle('hidden', !visible);
    }
}

function formatTimestamp(value) {
    if (!value) return 'never';
    const parsed = new Date(value);
    return isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

async function loadSecurityTab() {
    try {
        const response = await apiFetch('/api/auth/status');
        const data = await response.json();
        if (data.error) throw new Error(data.error);

        securityState = data;
        renderSecurityTab();
    } catch (error) {
        if (error.message === 'Session expired') return;
        showNotification('Failed to load security settings', 'error');
    }
}

function renderSecurityTab() {
    if (!securityState) return;

    const usernameEl = document.getElementById('account-username');
    if (usernameEl) usernameEl.textContent = securityState.username || '—';

    const updatedEl = document.getElementById('password-updated-at');
    if (updatedEl) updatedEl.textContent = formatTimestamp(securityState.password_updated_at);

    const enabled = Boolean(securityState.totp_enabled);
    const pendingVisible = !document.getElementById('totp-enrol-pending').classList.contains('hidden');

    if (enabled) {
        setStatusIndicator(
            'totp-status', STATUS_ON,
            'Two-factor authentication: <strong>Enabled</strong>', 'status-on'
        );
    } else if (pendingVisible) {
        setStatusIndicator(
            'totp-status', STATUS_PENDING,
            'Two-factor authentication: <strong>Pending verification</strong>', 'status-pending'
        );
    } else {
        setStatusIndicator(
            'totp-status', STATUS_OFF,
            'Two-factor authentication: <strong>Disabled</strong>', 'status-off'
        );
    }

    show('totp-enrol-start', !enabled && !pendingVisible);
    show('totp-enrol-enabled', enabled);

    const remaining = securityState.recovery_codes_remaining || 0;
    const total = securityState.recovery_codes_total || 0;

    if (!enabled) {
        setStatusIndicator(
            'recovery-status', STATUS_OFF,
            'Recovery codes: <strong>Not applicable</strong> until two-factor ' +
            'authentication is enabled', 'status-off'
        );
    } else if (remaining === 0) {
        setStatusIndicator(
            'recovery-status', STATUS_OFF,
            '<strong>No recovery codes left.</strong> Generate a new set now — ' +
            'without one, losing your authenticator means losing access.',
            'status-off'
        );
    } else if (remaining <= 2) {
        setStatusIndicator(
            'recovery-status', STATUS_PENDING,
            'Recovery codes: <strong>only ' + remaining + ' of ' + total +
            ' left.</strong> Generate a new set soon.', 'status-pending'
        );
    } else {
        setStatusIndicator(
            'recovery-status', STATUS_ON,
            'Recovery codes: <strong>' + remaining + ' of ' + total + ' unused</strong>',
            'status-on'
        );
    }

    show('recovery-regenerate-form', enabled);
}

function displayRecoveryCodes(codes) {
    const list = document.getElementById('recovery-codes-list');
    if (list) list.textContent = codes.join('\n');
    show('recovery-codes-display', true);
    show('recovery-regenerate-form', false);
}

async function postJson(url, body) {
    const response = await apiFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    const data = await response.json().catch(() => ({}));
    return { response: response, data: data };
}

async function changePassword(event) {
    event.preventDefault();

    const current = document.getElementById('current-password').value;
    const next = document.getElementById('new-password').value;
    const confirm = document.getElementById('new-password-confirm').value;

    if (next !== confirm) {
        showNotification('The two new passwords do not match', 'error');
        return;
    }

    try {
        const result = await postJson('/api/auth/password', {
            current_password: current,
            new_password: next
        });
        if (!result.response.ok) {
            showNotification(result.data.error || 'Failed to change password', 'error');
            return;
        }
        document.getElementById('change-password-form').reset();
        showNotification(result.data.message || 'Password updated');
        loadSecurityTab();
    } catch (error) {
        if (error.message !== 'Session expired') {
            showNotification('Failed to change password', 'error');
        }
    }
}

async function beginTotpEnrolment(event) {
    event.preventDefault();

    const passwordField = document.getElementById('totp-begin-password');
    try {
        const result = await postJson('/api/auth/totp/begin', {
            current_password: passwordField.value
        });
        if (!result.response.ok) {
            showNotification(result.data.error || 'Could not start enrolment', 'error');
            return;
        }

        passwordField.value = '';
        document.getElementById('totp-qr').src = result.data.qr_png_data_uri;
        document.getElementById('totp-secret').textContent = result.data.secret;
        show('totp-enrol-start', false);
        show('totp-enrol-pending', true);
        renderSecurityTab();
        document.getElementById('totp-confirm-code').focus();
    } catch (error) {
        if (error.message !== 'Session expired') {
            showNotification('Could not start enrolment', 'error');
        }
    }
}

async function confirmTotpEnrolment(event) {
    event.preventDefault();

    const codeField = document.getElementById('totp-confirm-code');
    try {
        const result = await postJson('/api/auth/totp/confirm', { code: codeField.value });
        if (!result.response.ok) {
            showNotification(result.data.error || 'That code is not valid', 'error');
            codeField.select();
            return;
        }

        codeField.value = '';
        cancelTotpEnrolment();
        showNotification(result.data.message || 'Two-factor authentication enabled');
        await loadSecurityTab();
        if (result.data.recovery_codes) {
            displayRecoveryCodes(result.data.recovery_codes);
        }
    } catch (error) {
        if (error.message !== 'Session expired') {
            showNotification('Could not verify that code', 'error');
        }
    }
}

function cancelTotpEnrolment() {
    show('totp-enrol-pending', false);
    const qr = document.getElementById('totp-qr');
    if (qr) qr.removeAttribute('src');
    const secret = document.getElementById('totp-secret');
    if (secret) secret.textContent = '…';
    renderSecurityTab();
}

async function disableTotp(event) {
    event.preventDefault();

    if (!confirm('Turn off two-factor authentication? Your recovery codes will also be discarded.')) {
        return;
    }

    const passwordField = document.getElementById('totp-disable-password');
    try {
        const result = await postJson('/api/auth/totp/disable', {
            current_password: passwordField.value
        });
        if (!result.response.ok) {
            showNotification(result.data.error || 'Could not disable two-factor authentication', 'error');
            return;
        }
        passwordField.value = '';
        show('recovery-codes-display', false);
        showNotification(result.data.message || 'Two-factor authentication disabled');
        loadSecurityTab();
    } catch (error) {
        if (error.message !== 'Session expired') {
            showNotification('Could not disable two-factor authentication', 'error');
        }
    }
}

async function regenerateRecoveryCodes(event) {
    event.preventDefault();

    const passwordField = document.getElementById('recovery-password');
    try {
        const result = await postJson('/api/auth/recovery-codes', {
            current_password: passwordField.value
        });
        if (!result.response.ok) {
            showNotification(result.data.error || 'Could not generate recovery codes', 'error');
            return;
        }
        passwordField.value = '';
        showNotification(result.data.message || 'New recovery codes generated');
        await loadSecurityTab();
        displayRecoveryCodes(result.data.recovery_codes || []);
    } catch (error) {
        if (error.message !== 'Session expired') {
            showNotification('Could not generate recovery codes', 'error');
        }
    }
}

function copyRecoveryCodes() {
    const list = document.getElementById('recovery-codes-list');
    if (!list) return;

    const text = list.textContent;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
            () => showNotification('Recovery codes copied'),
            () => showNotification('Could not copy — select and copy manually', 'error')
        );
    } else {
        showNotification('Clipboard unavailable — select and copy manually', 'error');
    }
}

function downloadRecoveryCodes() {
    const list = document.getElementById('recovery-codes-list');
    if (!list) return;

    const header = 'Porkbun Certificate Sync recovery codes\n' +
        'Each code can be used once. Keep this file somewhere safe.\n\n';
    const blob = new Blob([header + list.textContent + '\n'], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'porkbun-cert-sync-recovery-codes.txt';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

document.addEventListener('DOMContentLoaded', () => {
    const bindings = [
        ['change-password-form', 'submit', changePassword],
        ['totp-begin-form', 'submit', beginTotpEnrolment],
        ['totp-confirm-form', 'submit', confirmTotpEnrolment],
        ['totp-disable-form', 'submit', disableTotp],
        ['recovery-regenerate-form', 'submit', regenerateRecoveryCodes],
        ['totp-cancel', 'click', cancelTotpEnrolment],
        ['copy-recovery-codes', 'click', copyRecoveryCodes],
        ['download-recovery-codes', 'click', downloadRecoveryCodes],
        ['dismiss-recovery-codes', 'click', () => {
            show('recovery-codes-display', false);
            renderSecurityTab();
        }]
    ];

    bindings.forEach(([id, eventName, handler]) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener(eventName, handler);
    });
});
