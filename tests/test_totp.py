"""TOTP: RFC vectors, enrolment, two-step login, replay and recovery codes."""
import time

import pytest

from app.auth import hotp, verify_totp
from app.main import config as app_config
from tests.conftest import (
    TEST_PASSWORD,
    TEST_USERNAME,
    api_token,
    complete_setup,
    token_from_page,
)

# RFC 6238 test secret: ASCII "12345678901234567890" in base32
RFC_SECRET = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'


@pytest.mark.parametrize('at,expected', [
    (59, '287082'),
    (1111111109, '081804'),
    (1111111111, '050471'),
    (1234567890, '005924'),
])
def test_rfc6238_vectors(at, expected):
    ok, _counter = verify_totp(RFC_SECRET, expected, at=at)
    assert ok, f"RFC vector {expected} at t={at} did not verify"


def test_code_generation_matches_the_rfc_vector():
    key = b'12345678901234567890'
    assert hotp(key, 59 // 30) == '287082'


def test_window_accepts_neighbouring_steps_and_rejects_beyond():
    code = '287082'                       # valid for the step containing t=59
    assert verify_totp(RFC_SECRET, code, at=59)[0]
    assert verify_totp(RFC_SECRET, code, at=30)[0]             # start of the same step
    assert verify_totp(RFC_SECRET, code, at=59 + 30)[0]        # one step late, allowed
    assert verify_totp(RFC_SECRET, code, at=59 - 30)[0]        # one step early, allowed
    assert not verify_totp(RFC_SECRET, code, at=59 + 60)[0]    # two steps: outside
    assert not verify_totp(RFC_SECRET, code, at=59 + 300)[0]   # far outside


def test_last_counter_blocks_replay():
    ok, counter = verify_totp(RFC_SECRET, '287082', at=59)
    assert ok
    replay, _ = verify_totp(RFC_SECRET, '287082', at=59, last_counter=counter)
    assert not replay


def test_malformed_codes_are_rejected():
    assert not verify_totp(RFC_SECRET, '', at=59)[0]
    assert not verify_totp(RFC_SECRET, '12345', at=59)[0]
    assert not verify_totp(RFC_SECRET, 'abcdef', at=59)[0]
    assert not verify_totp('not base32 at all!', '287082', at=59)[0]


# ---------------------------------------------------------------------------
# Enrolment
# ---------------------------------------------------------------------------

def _current_code(secret, offset=0):
    from app.auth import _decode_base32
    return hotp(_decode_base32(secret), int(time.time() // 30) + offset)


def _enrol(client):
    """Complete TOTP enrolment; returns (secret, recovery_codes)"""
    begin = client.post(
        '/api/auth/totp/begin',
        json={'current_password': TEST_PASSWORD},
        headers={'X-CSRF-Token': api_token(client)},
    )
    assert begin.status_code == 200, begin.get_data(as_text=True)
    secret = begin.get_json()['secret']

    confirm = client.post(
        '/api/auth/totp/confirm',
        json={'code': _current_code(secret)},
        headers={'X-CSRF-Token': api_token(client)},
    )
    assert confirm.status_code == 200, confirm.get_data(as_text=True)
    return secret, confirm.get_json()['recovery_codes']


def test_begin_returns_a_scannable_qr_and_secret(admin):
    response = admin.post(
        '/api/auth/totp/begin',
        json={'current_password': TEST_PASSWORD},
        headers={'X-CSRF-Token': api_token(admin)},
    )
    data = response.get_json()
    assert response.status_code == 200
    assert len(data['secret']) >= 32
    assert data['qr_png_data_uri'].startswith('data:image/png;base64,')
    assert data['otpauth_uri'].startswith('otpauth://totp/')
    assert data['secret'] in data['otpauth_uri']
    # Nothing is persisted until the code is confirmed
    assert app_config.get_auth_users()[0]['totp']['enabled'] is False


def test_begin_requires_the_current_password(admin):
    response = admin.post(
        '/api/auth/totp/begin',
        json={'current_password': 'wrong'},
        headers={'X-CSRF-Token': api_token(admin)},
    )
    assert response.status_code == 401


def test_wrong_confirm_code_leaves_totp_disabled(admin):
    admin.post(
        '/api/auth/totp/begin',
        json={'current_password': TEST_PASSWORD},
        headers={'X-CSRF-Token': api_token(admin)},
    )
    response = admin.post(
        '/api/auth/totp/confirm',
        json={'code': '000000'},
        headers={'X-CSRF-Token': api_token(admin)},
    )
    assert response.status_code == 400
    assert app_config.get_auth_users()[0]['totp']['enabled'] is False


def test_enrolment_stores_an_encrypted_secret_and_hashed_codes(admin):
    secret, codes = _enrol(admin)

    totp = app_config.get_auth_users()[0]['totp']
    assert totp['enabled'] is True
    assert totp['secret_encrypted']
    assert secret not in totp['secret_encrypted']       # encrypted at rest
    assert len(codes) == 10
    assert len(totp['recovery_codes']) == 10
    for entry, plaintext in zip(totp['recovery_codes'], codes):
        assert entry['used_at'] is None
        assert entry['code_digest'].startswith('scrypt:')
        assert plaintext not in entry['code_digest']    # hashed, not stored


def test_status_reports_totp_and_recovery_codes(admin):
    _enrol(admin)
    data = admin.get('/api/auth/status').get_json()
    assert data['totp_enabled'] is True
    assert data['recovery_codes_remaining'] == 10
    assert data['recovery_codes_total'] == 10


# ---------------------------------------------------------------------------
# Two-step login
# ---------------------------------------------------------------------------

def _password_step(client):
    token = token_from_page(client, '/login')
    return client.post('/login', data={
        'username': TEST_USERNAME, 'password': TEST_PASSWORD, 'csrf_token': token,
    })


def test_password_step_alone_does_not_authenticate(client):
    complete_setup(client)
    _enrol(client)

    fresh = client.application.test_client()
    response = _password_step(fresh)
    assert response.status_code == 302
    assert '/login/totp' in response.headers['Location']

    # The half-authenticated session must not pass the gate
    assert fresh.get('/api/settings').status_code == 401


def test_second_factor_completes_the_login(client):
    complete_setup(client)
    secret, _codes = _enrol(client)

    fresh = client.application.test_client()
    _password_step(fresh)
    token = token_from_page(fresh, '/login/totp')
    response = fresh.post('/login/totp', data={
        'code': _current_code(secret), 'csrf_token': token,
    })
    assert response.status_code == 302
    assert fresh.get('/api/settings').status_code == 200


def test_wrong_second_factor_is_rejected(client):
    complete_setup(client)
    _enrol(client)

    fresh = client.application.test_client()
    _password_step(fresh)
    token = token_from_page(fresh, '/login/totp')
    response = fresh.post('/login/totp', data={'code': '000000', 'csrf_token': token})
    assert response.status_code == 401
    assert fresh.get('/api/settings').status_code == 401


def test_totp_code_cannot_be_replayed_for_a_second_login(client):
    complete_setup(client)
    secret, _codes = _enrol(client)
    code = _current_code(secret)

    first = client.application.test_client()
    _password_step(first)
    assert first.post('/login/totp', data={
        'code': code, 'csrf_token': token_from_page(first, '/login/totp'),
    }).status_code == 302

    second = client.application.test_client()
    _password_step(second)
    response = second.post('/login/totp', data={
        'code': code, 'csrf_token': token_from_page(second, '/login/totp'),
    })
    assert response.status_code == 401
    assert second.get('/api/settings').status_code == 401


def test_totp_page_without_a_pending_session_redirects_to_login(client):
    complete_setup(client)
    fresh = client.application.test_client()
    response = fresh.get('/login/totp')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')


# ---------------------------------------------------------------------------
# Recovery codes
# ---------------------------------------------------------------------------

def test_recovery_code_signs_in_once_then_fails(client):
    complete_setup(client)
    _secret, codes = _enrol(client)
    code = codes[0]

    first = client.application.test_client()
    _password_step(first)
    assert first.post('/login/totp', data={
        'recovery_code': code, 'csrf_token': token_from_page(first, '/login/totp'),
    }).status_code == 302
    assert first.get('/api/settings').status_code == 200

    second = client.application.test_client()
    _password_step(second)
    response = second.post('/login/totp', data={
        'recovery_code': code, 'csrf_token': token_from_page(second, '/login/totp'),
    })
    assert response.status_code == 401
    assert second.get('/api/settings').status_code == 401


def test_recovery_code_accepts_loose_formatting(client):
    complete_setup(client)
    _secret, codes = _enrol(client)

    fresh = client.application.test_client()
    _password_step(fresh)
    response = fresh.post('/login/totp', data={
        'recovery_code': codes[1].replace('-', '').lower(),
        'csrf_token': token_from_page(fresh, '/login/totp'),
    })
    assert response.status_code == 302


def test_using_a_recovery_code_decrements_the_remaining_count(client):
    complete_setup(client)
    _secret, codes = _enrol(client)

    fresh = client.application.test_client()
    _password_step(fresh)
    fresh.post('/login/totp', data={
        'recovery_code': codes[0], 'csrf_token': token_from_page(fresh, '/login/totp'),
    })
    assert fresh.get('/api/auth/status').get_json()['recovery_codes_remaining'] == 9


def test_regenerating_codes_invalidates_the_old_set(client):
    complete_setup(client)
    _secret, old_codes = _enrol(client)

    response = client.post(
        '/api/auth/recovery-codes',
        json={'current_password': TEST_PASSWORD},
        headers={'X-CSRF-Token': api_token(client)},
    )
    assert response.status_code == 200
    new_codes = response.get_json()['recovery_codes']
    assert len(new_codes) == 10
    assert not set(new_codes) & set(old_codes)

    fresh = client.application.test_client()
    _password_step(fresh)
    assert fresh.post('/login/totp', data={
        'recovery_code': old_codes[0], 'csrf_token': token_from_page(fresh, '/login/totp'),
    }).status_code == 401


def test_recovery_codes_require_totp_to_be_enabled(admin):
    response = admin.post(
        '/api/auth/recovery-codes',
        json={'current_password': TEST_PASSWORD},
        headers={'X-CSRF-Token': api_token(admin)},
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Disabling
# ---------------------------------------------------------------------------

def test_disable_requires_the_current_password(admin):
    _enrol(admin)
    response = admin.post(
        '/api/auth/totp/disable',
        json={'current_password': 'wrong'},
        headers={'X-CSRF-Token': api_token(admin)},
    )
    assert response.status_code == 401
    assert app_config.get_auth_users()[0]['totp']['enabled'] is True


def test_disable_clears_the_secret_and_codes(admin):
    _enrol(admin)
    response = admin.post(
        '/api/auth/totp/disable',
        json={'current_password': TEST_PASSWORD},
        headers={'X-CSRF-Token': api_token(admin)},
    )
    assert response.status_code == 200

    totp = app_config.get_auth_users()[0]['totp']
    assert totp['enabled'] is False
    assert totp['secret_encrypted'] == ''
    assert totp['recovery_codes'] == []


def test_login_skips_the_second_step_after_disabling(admin):
    _enrol(admin)
    admin.post(
        '/api/auth/totp/disable',
        json={'current_password': TEST_PASSWORD},
        headers={'X-CSRF-Token': api_token(admin)},
    )

    fresh = admin.application.test_client()
    response = _password_step(fresh)
    assert response.status_code == 302
    assert '/login/totp' not in response.headers['Location']
    assert fresh.get('/api/settings').status_code == 200
