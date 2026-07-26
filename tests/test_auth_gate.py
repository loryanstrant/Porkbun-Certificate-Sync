"""The application-wide gate: what is open, what is closed, and how it says so."""
import pytest
from flask import url_for

from app.auth import PUBLIC_ENDPOINTS, safe_next
from tests.conftest import complete_setup


def test_health_is_open_before_and_after_setup(client):
    assert client.get('/health').status_code == 200
    complete_setup(client)
    assert client.get('/health').status_code == 200


def test_static_files_are_open(client):
    assert client.get('/static/css/style.css').status_code == 200


def test_api_before_setup_reports_setup_required(client):
    response = client.get('/api/settings')
    assert response.status_code == 503
    assert response.get_json()['setup_required'] is True


def test_index_before_setup_redirects_to_setup(client):
    response = client.get('/')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/setup')


def test_index_after_setup_redirects_to_login(client):
    complete_setup(client)
    fresh = client.application.test_client()
    response = fresh.get('/')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_unauthenticated_api_get_is_401_with_marker(client):
    complete_setup(client)
    fresh = client.application.test_client()
    response = fresh.get('/api/settings')
    assert response.status_code == 401
    assert response.get_json()['auth_required'] is True


def test_unauthenticated_api_post_is_401_not_403(client):
    """Auth is checked before CSRF so the client gets an actionable answer."""
    complete_setup(client)
    fresh = client.application.test_client()
    response = fresh.post('/api/domains', json={'domain': 'example.com'})
    assert response.status_code == 401
    assert response.get_json()['auth_required'] is True


def test_unknown_url_is_gated_not_404(client):
    """Route existence must not leak to anonymous callers."""
    complete_setup(client)
    fresh = client.application.test_client()
    response = fresh.get('/api/does-not-exist')
    assert response.status_code == 401


def test_authenticated_unknown_url_is_404(admin):
    assert admin.get('/api/does-not-exist').status_code == 404


def test_every_public_endpoint_resolves_and_is_reachable(app, client):
    """
    Guards the single easiest way to lock everyone out of the app: a typo like
    "login" instead of "auth.login" in PUBLIC_ENDPOINTS.
    """
    complete_setup(client)
    with app.test_request_context():
        for endpoint in PUBLIC_ENDPOINTS:
            if endpoint == 'static':
                url_for(endpoint, filename='css/style.css')
            else:
                url_for(endpoint)          # raises BuildError on a typo

    fresh = client.application.test_client()
    for path in ('/login', '/login/totp', '/health', '/static/css/style.css'):
        response = fresh.get(path)
        assert response.status_code in (200, 302), f"{path} -> {response.status_code}"


def test_login_page_does_not_redirect_to_itself(client):
    """The redirect chain must terminate."""
    complete_setup(client)
    fresh = client.application.test_client()
    response = fresh.get('/login')
    assert response.status_code == 200


@pytest.mark.parametrize('candidate,expected', [
    (None, '/'),
    ('', '/'),
    ('//evil.example', '/'),
    ('https://evil.example/x', '/'),
    ('http://evil.example', '/'),
    ('/\\evil.example', '/'),
    ('/ok\r\nX-Injected: 1', '/'),
    ('/x' * 400, '/'),
    ('/settings', '/settings'),
    ('/?tab=domains', '/?tab=domains'),
    ('/page#frag', '/page'),
])
def test_safe_next_rejects_offsite_targets(candidate, expected):
    assert safe_next(candidate) == expected


def test_login_redirect_carries_a_relative_next(client):
    complete_setup(client)
    fresh = client.application.test_client()
    response = fresh.get('/api/settings', headers={'Accept': 'text/html'})
    # /api/* always answers JSON, so use a non-API page instead
    response = fresh.get('/')
    location = response.headers['Location']
    assert '//' not in location.replace('http://', '')
