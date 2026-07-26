"""
Shared pytest fixtures.

Everything at module scope here runs BEFORE any test module imports app.main --
pytest imports conftest.py first. That matters because importing app.main builds
a Config() and a DistributionLog(), both of which mkdir their config directory;
without CONFIG_PATH pointed at a temp dir they would try to create /app/config
and fail on a dev box or in CI.
"""
import os
import re
import shutil
import tempfile

import pytest

_CONFIG_DIR = tempfile.mkdtemp(prefix='pbcs-test-')

os.environ['CONFIG_PATH'] = os.path.join(_CONFIG_DIR, 'config.yaml')
os.environ['DISABLE_SCHEDULER'] = '1'
os.environ['SECRET_KEY'] = 'test-secret-key-' + '0' * 32
os.environ['SESSION_COOKIE_SECURE'] = 'false'
# A stray value in the developer's shell must not seed an account mid-suite.
os.environ.pop('ADMIN_USERNAME', None)
os.environ.pop('ADMIN_PASSWORD', None)
os.environ.pop('ADMIN_PASSWORD_HASH', None)
os.environ.pop('TRUST_PROXY_HEADERS', None)
os.environ.pop('CSRF_ORIGIN_CHECK', None)

from app import auth as auth_module            # noqa: E402
from app.main import app as flask_app          # noqa: E402
from app.main import config as app_config      # noqa: E402

TEST_USERNAME = 'admin'
TEST_PASSWORD = 'correct-horse-battery'


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_CONFIG_DIR, ignore_errors=True)


@pytest.fixture(scope='session')
def app():
    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture(autouse=True)
def clean_state(app):
    """
    app.main's module-level singletons make per-test re-import impractical, so
    reset the state they hold instead: wipe the config back to defaults and clear
    the in-memory lockout counters.
    """
    app_config.config = app_config._default_config()
    app_config.save()
    auth_module.get_auth().reset_attempts()
    yield


@pytest.fixture
def auth_manager():
    return auth_module.get_auth()


@pytest.fixture
def client(app):
    return app.test_client()


def token_from_page(client, path):
    """Scrape the csrf_token hidden field out of a rendered form"""
    response = client.get(path)
    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"', response.get_data(as_text=True)
    )
    assert match, f"No csrf_token field found on {path} (status {response.status_code})"
    return match.group(1)


def complete_setup(client, username=TEST_USERNAME, password=TEST_PASSWORD):
    """Run the first-run setup flow and leave the client signed in"""
    token = token_from_page(client, '/setup')
    response = client.post('/setup', data={
        'username': username,
        'password': password,
        'password_confirm': password,
        'csrf_token': token,
    })
    assert response.status_code == 302, response.get_data(as_text=True)
    return response


def api_token(client):
    """The CSRF token for an authenticated JSON client"""
    response = client.get('/api/csrf-token')
    assert response.status_code == 200
    return response.get_json()['csrf_token']


@pytest.fixture
def admin(client):
    """An authenticated test client with setup already completed"""
    complete_setup(client)
    return client


@pytest.fixture
def admin_headers(admin):
    """CSRF headers for the authenticated client"""
    return {'X-CSRF-Token': api_token(admin)}
