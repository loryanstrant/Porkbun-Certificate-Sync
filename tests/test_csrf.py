"""CSRF protection across the JSON API and the HTML forms."""
import pytest

from tests.conftest import TEST_PASSWORD, api_token, complete_setup, token_from_page


def test_post_without_a_token_is_rejected(admin):
    response = admin.post('/api/domains', json={'domain': 'example.com'})
    assert response.status_code == 403
    assert response.get_json()['csrf_failed'] is True


def test_post_with_a_token_succeeds(admin, admin_headers):
    response = admin.post('/api/domains', json={'domain': 'example.com'},
                          headers=admin_headers)
    assert response.status_code == 200
    assert response.get_json()['status'] == 'success'


def test_alternate_header_name_is_accepted(admin):
    response = admin.post('/api/domains', json={'domain': 'example.net'},
                          headers={'X-CSRFToken': api_token(admin)})
    assert response.status_code == 200


def test_mismatched_token_is_rejected(admin):
    response = admin.post('/api/domains', json={'domain': 'example.com'},
                          headers={'X-CSRF-Token': 'not-the-token'})
    assert response.status_code == 403


@pytest.mark.parametrize('method,path', [
    ('delete', '/api/domains/example.com'),
    ('delete', '/api/ssh-hosts/somehost'),
    ('put', '/api/domains/example.com'),
    ('put', '/api/ssh-hosts/somehost'),
    ('post', '/api/settings/certificates'),
    ('post', '/api/settings/schedule'),
    ('post', '/api/ssh-hosts'),
    ('post', '/api/sync'),
    ('post', '/api/distribution/test'),
])
def test_every_unsafe_endpoint_requires_a_token(admin, method, path):
    """
    Covers the two call sites in app.js that historically passed no headers
    object at all (DELETE domain and DELETE ssh-host).
    """
    response = getattr(admin, method)(path, json={})
    assert response.status_code == 403, f"{method.upper()} {path}"
    assert response.get_json()['csrf_failed'] is True


def test_safe_methods_never_require_a_token(admin):
    for path in ('/api/settings', '/api/domains', '/api/ssh-hosts',
                 '/api/sync/status', '/api/auth/status', '/api/distribution/logs'):
        assert admin.get(path).status_code == 200, path


def test_health_needs_no_token_and_no_session(client):
    assert client.get('/health').status_code == 200


def test_mismatched_origin_is_rejected(admin, admin_headers):
    headers = dict(admin_headers)
    headers['Origin'] = 'https://evil.example'
    response = admin.post('/api/domains', json={'domain': 'example.com'},
                          headers=headers)
    assert response.status_code == 403


def test_matching_origin_is_accepted(admin, admin_headers):
    headers = dict(admin_headers)
    headers['Origin'] = 'http://localhost'
    response = admin.post('/api/domains', json={'domain': 'example.com'},
                          headers=headers)
    assert response.status_code == 200


def test_csrf_token_endpoint_requires_a_session(client):
    complete_setup(client)
    fresh = client.application.test_client()
    response = fresh.get('/api/csrf-token')
    assert response.status_code == 401
    assert response.get_json()['auth_required'] is True


def test_csrf_token_endpoint_is_stable_within_a_session(admin):
    assert api_token(admin) == api_token(admin)


def test_login_post_without_a_token_is_rejected(client):
    complete_setup(client)
    fresh = client.application.test_client()
    fresh.get('/login')                      # establishes the session cookie
    response = fresh.post('/login', data={'username': 'admin', 'password': TEST_PASSWORD})
    assert response.status_code == 303
    assert 'csrf_error=1' in response.headers['Location']
    assert fresh.get('/api/settings').status_code == 401


def test_setup_post_without_a_token_is_rejected(client):
    client.get('/setup')
    response = client.post('/setup', data={
        'username': 'admin', 'password': TEST_PASSWORD, 'password_confirm': TEST_PASSWORD,
    })
    assert response.status_code == 303
    from app.main import config as app_config
    assert app_config.get_auth_users() == []


def test_logout_post_without_a_token_is_rejected(admin):
    response = admin.post('/logout')
    assert response.status_code == 303
    assert admin.get('/api/settings').status_code == 200      # still signed in


def test_ssh_host_password_failure_is_403_without_the_auth_marker(admin, admin_headers):
    """
    A wrong SSH *host* password must not look like an expired session, or the
    frontend interceptor would bounce the user to the login page mid-test.
    """
    admin.post('/api/ssh-hosts', json={
        'display_name': 'testhost', 'hostname': 'example.invalid', 'port': 22,
        'username': 'root', 'password': 'hostpassword', 'cert_path': '/tmp/certs',
    }, headers=admin_headers)

    response = admin.post('/api/distribution/test', json={
        'display_name': 'testhost', 'password': 'the-wrong-password',
    }, headers=admin_headers)

    assert response.status_code == 403
    body = response.get_json()
    assert body.get('auth_required') is None
    assert body.get('csrf_failed') is None
    assert body['error'] == 'Invalid password'


def test_form_token_is_accepted_for_html_posts(client):
    """The hidden form field works as well as the header."""
    complete_setup(client)
    fresh = client.application.test_client()
    token = token_from_page(fresh, '/login')
    response = fresh.post('/login', data={
        'username': 'admin', 'password': TEST_PASSWORD, 'csrf_token': token,
    })
    assert response.status_code == 302
