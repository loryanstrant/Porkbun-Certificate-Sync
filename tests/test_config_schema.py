"""Config storage: the auth block, legacy files, and save() hardening."""
import os

import yaml

from app.config import Config
from app.ssh_config import SSHConfig
from tests.conftest import TEST_PASSWORD, TEST_USERNAME, complete_setup


def _legacy_config(path):
    """A config.yaml as written by a release that predates authentication."""
    data = {
        'api': {'api_key': 'pk1_test', 'secret_key': 'sk1_test'},
        'domains': [{'domain': 'example.com', 'custom_name': 'example',
                     'separator': '_', 'alt_file_names': []}],
        'certificates': {'output_dir': '/app/certificates',
                         'naming_format': '{domain}', 'formats': ['pem']},
        'schedule': {'enabled': False, 'cron': '0 2 * * *'},
    }
    with open(path, 'w') as handle:
        yaml.safe_dump(data, handle)
    return data


def test_default_config_contains_an_empty_auth_section(tmp_path):
    config = Config(str(tmp_path / 'config.yaml'))
    assert config.get_auth_config() == {'version': 1, 'users': []}
    assert config.get_auth_users() == []


def test_legacy_config_loads_and_reports_no_users(tmp_path):
    path = tmp_path / 'config.yaml'
    _legacy_config(path)

    config = Config(str(path))
    assert 'auth' not in config.config
    assert config.get_auth_users() == []
    assert config.get_auth_user('admin') is None
    assert config.get_auth_user_by_id('usr_x') is None


def test_adding_a_user_preserves_every_other_section(tmp_path):
    path = tmp_path / 'config.yaml'
    original = _legacy_config(path)

    config = Config(str(path))
    config.add_auth_user({'id': 'usr_1', 'username': 'admin',
                          'password_digest': 'scrypt:32768:8:1$x$y',
                          'credential_version': 1})

    reloaded = yaml.safe_load(path.read_text())
    assert reloaded['api'] == original['api']
    assert reloaded['domains'] == original['domains']
    assert reloaded['certificates'] == original['certificates']
    assert reloaded['schedule'] == original['schedule']
    assert reloaded['auth']['users'][0]['username'] == 'admin'


def test_auth_block_round_trips_through_safe_dump(tmp_path):
    """yaml.safe_dump raises on bytes, so nothing in the block may be binary."""
    path = tmp_path / 'config.yaml'
    config = Config(str(path))
    record = {
        'id': 'usr_1', 'username': 'admin',
        'password_digest': 'scrypt:32768:8:1$salt$hash',
        'password_updated_at': '2026-07-26T00:00:00Z',
        'credential_version': 2, 'roles': ['admin'],
        'created_at': '2026-07-26T00:00:00Z', 'last_login_at': None,
        'totp': {'enabled': True, 'secret_encrypted': 'abc==', 'algorithm': 'SHA1',
                 'digits': 6, 'period': 30, 'confirmed_at': '2026-07-26T00:00:00Z',
                 'last_counter': 12345,
                 'recovery_codes': [{'code_digest': 'scrypt:...', 'used_at': None}]},
    }
    config.add_auth_user(record)

    assert yaml.safe_load(path.read_text())['auth']['users'][0] == record


def test_username_lookup_is_case_insensitive(tmp_path):
    config = Config(str(tmp_path / 'config.yaml'))
    config.add_auth_user({'id': 'usr_1', 'username': 'Admin'})

    assert config.get_auth_user('admin')['id'] == 'usr_1'
    assert config.get_auth_user('ADMIN')['id'] == 'usr_1'
    assert config.get_auth_user('  admin  ')['id'] == 'usr_1'


def test_duplicate_username_is_rejected(tmp_path):
    import pytest

    config = Config(str(tmp_path / 'config.yaml'))
    config.add_auth_user({'id': 'usr_1', 'username': 'admin'})
    with pytest.raises(ValueError):
        config.add_auth_user({'id': 'usr_2', 'username': 'ADMIN'})


def test_update_auth_user_merges_and_persists(tmp_path):
    path = tmp_path / 'config.yaml'
    config = Config(str(path))
    config.add_auth_user({'id': 'usr_1', 'username': 'admin', 'credential_version': 1})

    config.update_auth_user('usr_1', {'credential_version': 5})

    stored = yaml.safe_load(path.read_text())['auth']['users'][0]
    assert stored['credential_version'] == 5
    assert stored['username'] == 'admin'      # untouched keys survive


def test_save_writes_mode_600(tmp_path):
    path = tmp_path / 'config.yaml'
    config = Config(str(path))
    config.save()
    assert oct(os.stat(path).st_mode & 0o777) == '0o600'


def test_save_leaves_no_temporary_files_behind(tmp_path):
    config = Config(str(tmp_path / 'config.yaml'))
    config.save()
    config.save()
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith('.config-')]
    assert leftovers == []


def test_ssh_host_passwords_still_work_alongside_auth(tmp_path):
    """The SSH credential path must be untouched by the auth changes."""
    path = tmp_path / 'config.yaml'
    config = Config(str(path))
    ssh_config = SSHConfig(config)

    ssh_config.add_ssh_host('before', 'host.invalid', 22, 'root', 'sshpass', '/tmp/c')
    config.add_auth_user({'id': 'usr_1', 'username': 'admin',
                          'password_digest': 'scrypt:32768:8:1$x$y'})
    ssh_config.add_ssh_host('after', 'host2.invalid', 22, 'root', 'sshpass2', '/tmp/c')

    assert ssh_config.verify_password('before', 'sshpass')
    assert ssh_config.verify_password('after', 'sshpass2')
    assert not ssh_config.verify_password('before', 'wrong')
    assert config.get_auth_user('admin') is not None


def test_setup_persists_the_auth_block_to_disk(client):
    complete_setup(client)

    from app.main import config as app_config
    on_disk = yaml.safe_load(open(app_config.config_path).read())
    user = on_disk['auth']['users'][0]

    assert user['username'] == TEST_USERNAME
    assert user['password_digest'].startswith('scrypt:')
    assert TEST_PASSWORD not in open(app_config.config_path).read()
