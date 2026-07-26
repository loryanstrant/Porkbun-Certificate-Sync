"""Regression tests for issues found in security review."""
from app.auth import log_safe, request_is_https
from tests.conftest import TEST_PASSWORD, api_token, complete_setup, token_from_page


# ---------------------------------------------------------------------------
# Secure cookie flag behind a TLS-terminating proxy
# ---------------------------------------------------------------------------

def _login_and_get_cookie_header(client, base_url=None, headers=None):
    token = token_from_page(client, '/login')
    kwargs = {'headers': headers or {}}
    if base_url:
        # base_url, not environ_base: the EnvironBuilder derives wsgi.url_scheme
        # from the URL and would overwrite an environ_base entry.
        kwargs['base_url'] = base_url
    response = client.post(
        '/login',
        data={'username': 'admin', 'password': TEST_PASSWORD, 'csrf_token': token},
        **kwargs,
    )
    return '; '.join(response.headers.getlist('Set-Cookie'))


def test_cookie_is_secure_over_direct_https(app, client, monkeypatch):
    complete_setup(client)
    monkeypatch.setitem(app.config, 'SESSION_COOKIE_SECURE_MODE', 'auto')

    fresh = client.application.test_client()
    header = _login_and_get_cookie_header(fresh, base_url='https://localhost')
    assert 'Secure' in header


def test_cookie_is_secure_behind_a_tls_proxy_without_proxyfix(app, client, monkeypatch):
    """
    The recommended deployment is a TLS-terminating reverse proxy. If the Secure
    flag depended on the opt-in ProxyFix, that exact setup would hand out a cookie
    without it, and one plain-HTTP request would leak a working session.
    """
    complete_setup(client)
    monkeypatch.setitem(app.config, 'SESSION_COOKIE_SECURE_MODE', 'auto')

    fresh = client.application.test_client()
    header = _login_and_get_cookie_header(fresh, headers={'X-Forwarded-Proto': 'https'})
    assert 'Secure' in header

    fresh2 = client.application.test_client()
    header2 = _login_and_get_cookie_header(
        fresh2, headers={'Forwarded': 'for=203.0.113.9;proto=https'}
    )
    assert 'Secure' in header2


def test_cookie_is_not_secure_over_plain_http(app, client, monkeypatch):
    """Marking it Secure on plain HTTP would make sign-in silently loop."""
    complete_setup(client)
    monkeypatch.setitem(app.config, 'SESSION_COOKIE_SECURE_MODE', 'auto')

    fresh = client.application.test_client()
    header = _login_and_get_cookie_header(fresh)
    assert 'Secure' not in header
    assert 'HttpOnly' in header
    assert 'SameSite=Lax' in header


def test_secure_mode_can_be_forced_either_way(app, client, monkeypatch):
    complete_setup(client)

    monkeypatch.setitem(app.config, 'SESSION_COOKIE_SECURE_MODE', 'true')
    forced_on = _login_and_get_cookie_header(client.application.test_client())
    assert 'Secure' in forced_on

    monkeypatch.setitem(app.config, 'SESSION_COOKIE_SECURE_MODE', 'false')
    forced_off = _login_and_get_cookie_header(
        client.application.test_client(), base_url='https://localhost',
    )
    assert 'Secure' not in forced_off


def test_request_is_https_ignores_a_non_https_forwarded_proto(app):
    with app.test_request_context(headers={'X-Forwarded-Proto': 'http'}):
        assert request_is_https() is False
    with app.test_request_context(headers={'X-Forwarded-Proto': 'https, http'}):
        assert request_is_https() is True


# ---------------------------------------------------------------------------
# The in-progress TOTP secret must not travel in the session cookie
# ---------------------------------------------------------------------------

def test_enrolment_secret_never_enters_the_session_cookie(admin, admin_headers):
    """
    The session cookie is signed but NOT encrypted. A seed placed in it and then
    captured in transit outlives the session, the password and credential_version.
    """
    response = admin.post('/api/auth/totp/begin',
                          json={'current_password': TEST_PASSWORD},
                          headers=admin_headers)
    secret = response.get_json()['secret']

    cookie_material = '; '.join(response.headers.getlist('Set-Cookie'))
    assert secret not in cookie_material

    with admin.session_transaction() as session:
        assert 'totp_pending' not in session
        assert secret not in str(dict(session))


def test_enrolment_secret_is_held_server_side(admin, admin_headers, auth_manager):
    response = admin.post('/api/auth/totp/begin',
                          json={'current_password': TEST_PASSWORD},
                          headers=admin_headers)
    secret = response.get_json()['secret']

    user = auth_manager.config.get_auth_users()[0]
    assert auth_manager.get_enrolment_secret(user['id']) == secret

    auth_manager.clear_enrolment(user['id'])
    assert auth_manager.get_enrolment_secret(user['id']) is None

    # With the pending secret gone, confirm must refuse rather than enrol
    confirm = admin.post('/api/auth/totp/confirm', json={'code': '123456'},
                         headers=admin_headers)
    assert confirm.status_code == 409


def test_expired_enrolment_is_forgotten(admin, admin_headers, auth_manager, monkeypatch):
    admin.post('/api/auth/totp/begin', json={'current_password': TEST_PASSWORD},
               headers=admin_headers)
    user_id = auth_manager.config.get_auth_users()[0]['id']

    # Wind the stored expiry into the past
    auth_manager._pending_enrolments[user_id]['exp'] = 0
    assert auth_manager.get_enrolment_secret(user_id) is None


# ---------------------------------------------------------------------------
# Log injection
# ---------------------------------------------------------------------------

def test_log_safe_strips_newlines_and_control_characters():
    forged = "zz' from 1.2.3.4\n2026-07-27 09:00:00 - app.auth - INFO - 'admin' signed in"
    cleaned = log_safe(forged)
    assert '\n' not in cleaned
    assert '\r' not in cleaned
    assert len(cleaned) <= 64
    assert log_safe('\x00\x1b[31m') == '??[31m'
    assert log_safe('') == '<empty>'
    assert log_safe(None) == '<empty>'
    assert log_safe('  admin  ') == 'admin'


def test_failed_login_cannot_forge_a_log_entry(client, caplog):
    """An unauthenticated caller must not be able to write extra audit lines."""
    complete_setup(client)
    fresh = client.application.test_client()
    token = token_from_page(fresh, '/login')

    forged = "zz\n2026-07-27 09:00:00 - app.auth - INFO - 'admin' signed in from 10.0.0.9"
    with caplog.at_level('WARNING', logger='app.auth'):
        fresh.post('/login', data={
            'username': forged, 'password': 'wrong-password', 'csrf_token': token,
        })

    messages = [record.getMessage() for record in caplog.records]
    assert messages, "the failed sign-in was not logged at all"
    for message in messages:
        assert '\n' not in message
        assert 'signed in from 10.0.0.9' not in message


# ---------------------------------------------------------------------------
# CSRF token comparison must fail closed, not 500
# ---------------------------------------------------------------------------

def test_non_ascii_csrf_token_is_rejected_cleanly(admin):
    """compare_digest raises TypeError on non-ASCII str, which would be a 500."""
    response = admin.post('/api/domains', json={'domain': 'example.com'},
                          headers={'X-CSRF-Token': 'café-☃-token'})
    assert response.status_code == 403
    assert response.get_json()['csrf_failed'] is True


def test_non_ascii_csrf_form_field_is_rejected_cleanly(client):
    complete_setup(client)
    fresh = client.application.test_client()
    fresh.get('/login')
    response = fresh.post('/login', data={
        'username': 'admin', 'password': TEST_PASSWORD, 'csrf_token': 'café-☃',
    })
    assert response.status_code == 303
    assert fresh.get('/api/settings').status_code == 401


def test_correct_token_still_works_after_the_bytes_change(admin, admin_headers):
    response = admin.post('/api/domains', json={'domain': 'still-works.example'},
                          headers=admin_headers)
    assert response.status_code == 200
