"""First-run setup: creating the one admin account, and never doing it twice."""
import os

import pytest

from app import auth as auth_module
from app.main import config as app_config
from tests.conftest import TEST_PASSWORD, TEST_USERNAME, complete_setup, token_from_page


def test_setup_page_renders_when_unconfigured(client):
    response = client.get('/setup')
    assert response.status_code == 200
    assert 'csrf_token' in response.get_data(as_text=True)


def test_setup_creates_a_single_user_and_signs_in(client):
    complete_setup(client)

    users = app_config.get_auth_users()
    assert len(users) == 1
    user = users[0]
    assert user['username'] == TEST_USERNAME
    assert user['password_digest'].startswith('scrypt:')
    # password_hash is a legacy SSH host field; user credentials must not use it.
    assert 'password_hash' not in user
    assert TEST_PASSWORD not in str(user)

    # The client is now authenticated
    assert client.get('/api/settings').status_code == 200


def test_second_setup_attempt_is_rejected_and_leaves_the_digest_alone(client):
    """If this ever regresses, anybody can reset the admin password."""
    complete_setup(client)
    original_digest = app_config.get_auth_users()[0]['password_digest']

    # The gate redirects an already-configured GET away from /setup
    assert client.get('/setup').status_code == 302

    response = client.post('/setup', data={
        'username': 'attacker',
        'password': 'attacker-password-1',
        'password_confirm': 'attacker-password-1',
        'csrf_token': 'irrelevant',
    })
    assert response.status_code in (302, 400, 403, 409)
    assert app_config.get_auth_users()[0]['password_digest'] == original_digest
    assert len(app_config.get_auth_users()) == 1


def test_short_password_is_rejected(client):
    token = token_from_page(client, '/setup')
    response = client.post('/setup', data={
        'username': 'admin', 'password': 'short', 'password_confirm': 'short',
        'csrf_token': token,
    })
    assert response.status_code == 400
    assert app_config.get_auth_users() == []


def test_mismatched_passwords_are_rejected(client):
    token = token_from_page(client, '/setup')
    response = client.post('/setup', data={
        'username': 'admin',
        'password': 'a-long-enough-password',
        'password_confirm': 'a-different-password',
        'csrf_token': token,
    })
    assert response.status_code == 400
    assert 'do not match' in response.get_data(as_text=True)
    assert app_config.get_auth_users() == []


@pytest.mark.parametrize('username', ['ab', 'has space', 'bad!char', 'x' * 65])
def test_invalid_usernames_are_rejected(client, username):
    token = token_from_page(client, '/setup')
    response = client.post('/setup', data={
        'username': username,
        'password': TEST_PASSWORD,
        'password_confirm': TEST_PASSWORD,
        'csrf_token': token,
    })
    assert response.status_code == 400
    assert app_config.get_auth_users() == []


def test_environment_seed_creates_the_account(auth_manager, monkeypatch):
    monkeypatch.setenv('ADMIN_USERNAME', 'seeded')
    monkeypatch.setenv('ADMIN_PASSWORD', 'seeded-password-123')

    auth_manager.maybe_seed_from_environment()

    assert auth_manager.is_configured()
    assert app_config.get_auth_user('seeded') is not None


def test_environment_seed_is_ignored_once_configured(client, auth_manager, monkeypatch):
    complete_setup(client)
    original_digest = app_config.get_auth_users()[0]['password_digest']

    monkeypatch.setenv('ADMIN_USERNAME', 'seeded')
    monkeypatch.setenv('ADMIN_PASSWORD', 'seeded-password-123')
    auth_manager.maybe_seed_from_environment()

    assert len(app_config.get_auth_users()) == 1
    assert app_config.get_auth_users()[0]['password_digest'] == original_digest


def test_environment_seed_rejects_a_weak_password(auth_manager, monkeypatch):
    monkeypatch.setenv('ADMIN_USERNAME', 'seeded')
    monkeypatch.setenv('ADMIN_PASSWORD', 'short')

    auth_manager.maybe_seed_from_environment()

    assert not auth_manager.is_configured()


def test_secret_key_file_is_created_with_mode_600(tmp_path, monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)

    key_file = tmp_path / '.secret_key'
    key = auth_module.load_or_create_secret_key(str(tmp_path))

    assert len(key) >= 32
    assert key_file.exists()
    assert oct(os.stat(key_file).st_mode & 0o777) == '0o600'
    # A second call reuses the persisted key
    assert auth_module.load_or_create_secret_key(str(tmp_path)) == key


def test_secret_key_environment_variable_wins(tmp_path, monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'e' * 40)
    assert auth_module.load_or_create_secret_key(str(tmp_path)) == 'e' * 40
    assert not (tmp_path / '.secret_key').exists()


def test_short_secret_key_environment_variable_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'too-short')
    key = auth_module.load_or_create_secret_key(str(tmp_path))
    assert key != 'too-short'
    assert (tmp_path / '.secret_key').exists()
