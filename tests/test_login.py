"""Sign in, sign out, and session invalidation."""
from app.main import config as app_config
from tests.conftest import (
    TEST_PASSWORD,
    TEST_USERNAME,
    api_token,
    complete_setup,
    token_from_page,
)


def _login(client, username=TEST_USERNAME, password=TEST_PASSWORD, next_url=None):
    token = token_from_page(client, '/login')
    data = {'username': username, 'password': password, 'csrf_token': token}
    if next_url is not None:
        data['next'] = next_url
    return client.post('/login', data=data)


def test_correct_credentials_authenticate(client):
    complete_setup(client)
    fresh = client.application.test_client()

    response = _login(fresh)
    assert response.status_code == 302
    assert fresh.get('/api/settings').status_code == 200


def test_last_login_is_recorded(client):
    complete_setup(client)
    fresh = client.application.test_client()
    _login(fresh)
    assert app_config.get_auth_users()[0]['last_login_at'] is not None


def test_wrong_password_and_unknown_user_are_indistinguishable(client):
    complete_setup(client)

    wrong_password = _login(client.application.test_client(), password='wrong-password-x')
    unknown_user = _login(client.application.test_client(), username='nobody')

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert 'Invalid username or password.' in wrong_password.get_data(as_text=True)
    assert 'Invalid username or password.' in unknown_user.get_data(as_text=True)


def test_failed_login_leaves_the_client_unauthenticated(client):
    complete_setup(client)
    fresh = client.application.test_client()
    _login(fresh, password='wrong-password-x')
    assert fresh.get('/api/settings').status_code == 401


def test_login_honours_a_relative_next(client):
    complete_setup(client)
    fresh = client.application.test_client()
    response = _login(fresh, next_url='/?tab=domains')
    assert response.headers['Location'].endswith('/?tab=domains')


def test_login_discards_an_offsite_next(client):
    complete_setup(client)
    fresh = client.application.test_client()
    response = _login(fresh, next_url='https://evil.example/steal')
    assert 'evil.example' not in response.headers['Location']


def test_already_signed_in_get_login_redirects(admin):
    response = admin.get('/login')
    assert response.status_code == 302


def test_logout_clears_the_session(admin):
    token = api_token(admin)
    response = admin.post('/logout', data={'csrf_token': token})
    assert response.status_code == 302
    assert admin.get('/api/settings').status_code == 401


def test_logout_rejects_get(admin):
    assert admin.get('/logout').status_code == 405


def test_password_change_ends_other_sessions(client):
    complete_setup(client)

    second = client.application.test_client()
    _login(second)
    assert second.get('/api/settings').status_code == 200

    response = client.post(
        '/api/auth/password',
        json={'current_password': TEST_PASSWORD, 'new_password': 'a-brand-new-password'},
        headers={'X-CSRF-Token': api_token(client)},
    )
    assert response.status_code == 200

    # The session that made the change survives; the other one does not.
    assert client.get('/api/settings').status_code == 200
    assert second.get('/api/settings').status_code == 401


def test_password_change_requires_the_current_password(admin):
    response = admin.post(
        '/api/auth/password',
        json={'current_password': 'not-the-password', 'new_password': 'a-brand-new-password'},
        headers={'X-CSRF-Token': api_token(admin)},
    )
    assert response.status_code == 401
    assert response.get_json()['error'] == 'Current password is incorrect'


def test_password_change_enforces_the_policy(admin):
    response = admin.post(
        '/api/auth/password',
        json={'current_password': TEST_PASSWORD, 'new_password': 'short'},
        headers={'X-CSRF-Token': api_token(admin)},
    )
    assert response.status_code == 400


def test_new_password_works_for_the_next_login(client):
    complete_setup(client)
    new_password = 'another-good-password'
    client.post(
        '/api/auth/password',
        json={'current_password': TEST_PASSWORD, 'new_password': new_password},
        headers={'X-CSRF-Token': api_token(client)},
    )

    fresh = client.application.test_client()
    assert _login(fresh, password=TEST_PASSWORD).status_code == 401

    fresh2 = client.application.test_client()
    assert _login(fresh2, password=new_password).status_code == 302


def test_auth_status_reports_the_account(admin):
    data = admin.get('/api/auth/status').get_json()
    assert data['username'] == TEST_USERNAME
    assert data['totp_enabled'] is False
    assert data['recovery_codes_remaining'] == 0
