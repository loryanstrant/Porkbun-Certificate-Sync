"""Brute-force lockout: backoff, bucket keying, and no user enumeration."""
from app.auth import FREE_ATTEMPTS
from tests.conftest import TEST_PASSWORD, TEST_USERNAME, complete_setup, token_from_page


def _attempt(client, username=TEST_USERNAME, password='wrong-password-x', ip=None):
    token = token_from_page(client, '/login')
    kwargs = {}
    if ip:
        kwargs['environ_base'] = {'REMOTE_ADDR': ip}
    return client.post('/login', data={
        'username': username, 'password': password, 'csrf_token': token,
    }, **kwargs)


def test_first_attempts_are_not_locked_out(client):
    complete_setup(client)
    fresh = client.application.test_client()
    for _ in range(FREE_ATTEMPTS):
        assert _attempt(fresh).status_code == 401


def test_attempt_beyond_the_allowance_is_locked(client):
    complete_setup(client)
    fresh = client.application.test_client()
    for _ in range(FREE_ATTEMPTS):
        _attempt(fresh)

    response = _attempt(fresh)
    assert response.status_code == 429
    assert int(response.headers['Retry-After']) > 0
    assert 'Too many failed sign-in attempts' in response.get_data(as_text=True)


def test_lockout_blocks_the_correct_password_too(client):
    complete_setup(client)
    fresh = client.application.test_client()
    for _ in range(FREE_ATTEMPTS + 1):
        _attempt(fresh)

    response = _attempt(fresh, password=TEST_PASSWORD)
    assert response.status_code == 429
    assert fresh.get('/api/settings').status_code == 401


def test_unknown_username_locks_out_identically(client):
    """Otherwise lockout timing reveals whether an account exists."""
    complete_setup(client)

    known = client.application.test_client()
    unknown = client.application.test_client()
    for _ in range(FREE_ATTEMPTS):
        _attempt(known, ip='10.0.0.1')
        _attempt(unknown, username='nobody-here', ip='10.0.0.2')

    known_response = _attempt(known, ip='10.0.0.1')
    unknown_response = _attempt(unknown, username='nobody-here', ip='10.0.0.2')

    assert known_response.status_code == unknown_response.status_code == 429


def test_successful_login_resets_the_counter(client):
    complete_setup(client)
    fresh = client.application.test_client()
    for _ in range(FREE_ATTEMPTS):
        _attempt(fresh)

    assert _attempt(fresh, password=TEST_PASSWORD).status_code == 302

    second = client.application.test_client()
    for _ in range(FREE_ATTEMPTS):
        assert _attempt(second).status_code == 401


def test_a_different_client_ip_is_a_separate_bucket(client, auth_manager):
    """
    The IP bucket is independent of the account bucket, so a lockout triggered by
    one client's spraying does not depend on which account it targeted.
    """
    complete_setup(client)

    sprayer = client.application.test_client()
    for index in range(FREE_ATTEMPTS + 2):
        _attempt(sprayer, username=f'user{index}', ip='10.0.0.9')

    from app.auth import IP_FREE_ATTEMPTS
    assert auth_manager.check_locked([('ip', '10.0.0.9')]) == 0     # still under the IP allowance
    assert auth_manager.check_locked([('ip', '10.0.0.10')]) == 0    # untouched bucket


def test_ip_bucket_locks_after_its_own_allowance(client, auth_manager):
    from app.auth import IP_FREE_ATTEMPTS

    complete_setup(client)
    sprayer = client.application.test_client()
    for index in range(IP_FREE_ATTEMPTS + 1):
        _attempt(sprayer, username=f'user{index}', ip='10.0.0.11')

    assert auth_manager.check_locked([('ip', '10.0.0.11')]) > 0


def test_backoff_grows_and_is_capped(auth_manager):
    from app.auth import MAX_LOCKOUT

    buckets = [('user', 'someone')]
    delays = []
    for _ in range(FREE_ATTEMPTS + 6):
        delays.append(auth_manager.register_failure(buckets))

    growing = [d for d in delays if d > 0]
    assert growing == sorted(growing)
    assert all(d <= MAX_LOCKOUT for d in delays)


def test_reset_attempts_clears_everything(auth_manager):
    buckets = [('user', 'someone')]
    for _ in range(FREE_ATTEMPTS + 1):
        auth_manager.register_failure(buckets)
    assert auth_manager.check_locked(buckets) > 0

    auth_manager.reset_attempts()
    assert auth_manager.check_locked(buckets) == 0


def test_sensitive_actions_have_their_own_limiter(client):
    """A hijacked browser must not be able to brute-force the current password."""
    from app.auth import SENSITIVE_FREE_ATTEMPTS
    from tests.conftest import api_token

    complete_setup(client)
    for _ in range(SENSITIVE_FREE_ATTEMPTS):
        response = client.post(
            '/api/auth/totp/begin',
            json={'current_password': 'wrong'},
            headers={'X-CSRF-Token': api_token(client)},
        )
        assert response.status_code == 401

    response = client.post(
        '/api/auth/totp/begin',
        json={'current_password': 'wrong'},
        headers={'X-CSRF-Token': api_token(client)},
    )
    assert response.status_code == 429
    assert 'Retry-After' in response.headers
