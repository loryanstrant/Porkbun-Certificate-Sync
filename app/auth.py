"""
Authentication for Porkbun Certificate Sync

Provides a mandatory single-admin login (username + password, optional TOTP
second factor), CSRF protection for the JSON API, brute-force lockout and
persisted session signing keys.

Design notes:
  * Credentials live in the `auth` section of config.yaml, managed exclusively
    through app/config.py's auth accessors.
  * Passwords and recovery codes are hashed with werkzeug's scrypt. The
    reversible Fernet helper in password_encryption.py is only used for the TOTP
    shared secret (which must be recoverable to verify codes) -- never for
    passwords.
  * There is deliberately no way to disable authentication.
"""
import base64
import hashlib
import hmac
import io
import logging
import os
import re
import secrets
import struct
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit, urlunsplit

import segno
from flask import (
    Blueprint,
    current_app,
    g,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.sessions import SecureCookieSessionInterface
from werkzeug.security import check_password_hash, generate_password_hash

from .password_encryption import get_password_encryption

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS', 'TRACE'})

# Endpoints reachable without a session. These are Flask ENDPOINT NAMES, not URL
# paths -- request.endpoint is already resolved when the gate runs, so it cannot
# be fooled by "/api/../login", trailing slashes or casing.
#
# WARNING: a typo here (e.g. "login" instead of "auth.login") makes the login
# page itself redirect to the login page forever, locking everyone out. If that
# ever happens: stop the container, delete the `auth:` block from config.yaml,
# restart, and the app returns to /setup with all other settings intact.
PUBLIC_ENDPOINTS = frozenset({
    'static',
    'health',
    'auth.setup',
    'auth.login',
    'auth.login_totp',
    'auth.logout',
})

SECRET_KEY_FILENAME = '.secret_key'
SESSION_COOKIE_NAME = 'pbcs_session'

PASSWORD_HASH_METHOD = 'scrypt:32768:8:1'   # pinned so a werkzeug bump can't change it silently
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 1024                  # cheap DoS guard on the KDF input
USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9._@-]{3,64}$')

ABSOLUTE_SESSION_LIFETIME = timedelta(days=7)
PENDING_TOTP_SECONDS = 300
PENDING_ENROLMENT_SECONDS = 600

TOTP_DIGITS = 6
TOTP_PERIOD = 30
TOTP_WINDOW = 1                             # +/- one 30s step
TOTP_ISSUER = 'Porkbun Certificate Sync'

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'   # no 0/O/1/I
RECOVERY_CODE_GROUP = 5

# Lockout: never permanent. A self-hosted tool with no out-of-band reset must
# not be able to lock its only administrator out for good.
FREE_ATTEMPTS = 3
IP_FREE_ATTEMPTS = 10                       # looser: a proxy can collapse every client into one bucket
SENSITIVE_FREE_ATTEMPTS = 5
BASE_LOCKOUT = 5                            # seconds
MAX_LOCKOUT = 900                           # 15 minutes
ATTEMPT_WINDOW = 1800                       # a bucket idle this long is forgotten

CSRF_SESSION_KEY = 'csrf'
CSRF_HEADER_NAMES = ('X-CSRF-Token', 'X-CSRFToken')
CSRF_FORM_FIELD = 'csrf_token'


class TOTPUnavailable(Exception):
    """The stored TOTP secret could not be decrypted (encryption key changed)."""


# ---------------------------------------------------------------------------
# Secret key persistence
# ---------------------------------------------------------------------------

def load_or_create_secret_key(config_dir: str) -> str:
    """
    Resolve the Flask session signing key.

    Priority:
      1. SECRET_KEY environment variable (must be at least 32 characters)
      2. <config_dir>/.secret_key
      3. Generate one and persist it with mode 0600

    Rotating or deleting the key invalidates every session, which is also the
    intended "sign everybody out" lever for an operator with shell access.
    """
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        if len(env_key) >= 32:
            logger.info("Using Flask secret key from SECRET_KEY environment variable")
            return env_key
        logger.warning("SECRET_KEY is shorter than 32 characters; ignoring it")

    key_file = os.path.join(config_dir, SECRET_KEY_FILENAME)
    if os.path.exists(key_file):
        try:
            with open(key_file, 'r') as handle:
                stored = handle.read().strip()
            if len(stored) >= 32:
                logger.info(f"Using Flask secret key from {key_file}")
                return stored
            logger.warning(f"Secret key file {key_file} is too short; regenerating")
        except OSError as exc:
            logger.warning(f"Could not read secret key file: {exc}")

    key = secrets.token_hex(32)
    try:
        os.makedirs(config_dir, exist_ok=True)
        # os.open with an explicit mode avoids the brief world-readable window
        # that open()-then-chmod leaves behind.
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(key)
        logger.info(f"Generated a new Flask secret key and saved it to {key_file}")
    except OSError as exc:
        logger.warning(
            f"Failed to persist the Flask secret key ({exc}). Sessions will not "
            "survive a restart; set SECRET_KEY to fix this."
        )
    return key


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_DUMMY_DIGEST = None
_DUMMY_LOCK = threading.Lock()


def hash_secret(value: str) -> str:
    """Hash a password or recovery code with scrypt"""
    return generate_password_hash(value, method=PASSWORD_HASH_METHOD, salt_length=16)


def verify_secret(digest: str, value: str) -> bool:
    """Verify a value against a stored scrypt digest"""
    if not digest or not value:
        return False
    try:
        return check_password_hash(digest, value)
    except (ValueError, TypeError):
        logger.warning("Stored credential digest is malformed")
        return False


def dummy_digest() -> str:
    """
    A throwaway digest used to equalise timing for unknown usernames, so login
    response time cannot be used to enumerate accounts. Built lazily: doing it
    at import would add ~80ms to container start.
    """
    global _DUMMY_DIGEST
    with _DUMMY_LOCK:
        if _DUMMY_DIGEST is None:
            _DUMMY_DIGEST = hash_secret(secrets.token_urlsafe(32))
        return _DUMMY_DIGEST


def log_safe(value, limit: int = 64) -> str:
    """
    Make an untrusted value safe to put in a log line.

    Newlines and control characters would otherwise let an unauthenticated caller
    forge extra log entries -- a fabricated "signed in" record, or padding to bury
    a real brute-force run -- which then reach `docker logs` and any log shipper
    as if they were genuine.
    """
    text = str(value or '').strip()
    scrubbed = re.sub(r'[^\x20-\x7e]', '?', text)
    return scrubbed[:limit] if scrubbed else '<empty>'


def validate_username(username: str) -> str:
    """Normalise and validate a username, raising ValueError if unacceptable"""
    candidate = (username or '').strip()
    if not USERNAME_PATTERN.match(candidate):
        raise ValueError(
            "Usernames must be 3-64 characters and may contain letters, numbers, "
            "dots, dashes, underscores and @"
        )
    return candidate


def validate_password_policy(password: str) -> None:
    """Raise ValueError if the password does not meet the minimum policy"""
    if not password or len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Passwords must be at least {PASSWORD_MIN_LENGTH} characters long"
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError("Password is too long")


# ---------------------------------------------------------------------------
# Redirect safety
# ---------------------------------------------------------------------------

def safe_next(candidate, fallback: str = '/') -> str:
    """
    Sanitise a `next` target so it can only ever point back into this app.

    Rejects absolute URLs, scheme-relative "//evil.com", backslash tricks and
    embedded control characters. Applied both when generating the link and again
    before redirecting.
    """
    if not candidate or not isinstance(candidate, str):
        return fallback
    if len(candidate) > 512:
        return fallback
    if not candidate.startswith('/') or candidate.startswith('//'):
        return fallback
    if '\\' in candidate or any(ch in candidate for ch in '\r\n\t'):
        return fallback
    parts = urlsplit(candidate)
    if parts.scheme or parts.netloc:
        return fallback
    return urlunsplit(('', '', parts.path, parts.query, '')) or fallback


# ---------------------------------------------------------------------------
# TOTP (RFC 6238) -- implemented on the standard library
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    """Generate a 160-bit base32 TOTP secret (RFC 4226 recommended length)"""
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def _decode_base32(secret_b32: str) -> bytes:
    padded = (secret_b32 or '').strip().upper().replace(' ', '')
    return base64.b32decode(padded + '=' * (-len(padded) % 8))


def hotp(key: bytes, counter: int, digits: int = TOTP_DIGITS) -> str:
    """RFC 4226 HOTP"""
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10 ** digits)).zfill(digits)


def verify_totp(secret_b32, code, at=None, period=TOTP_PERIOD, digits=TOTP_DIGITS,
                window=TOTP_WINDOW, last_counter=None):
    """
    Verify a TOTP code.

    Returns:
        (ok, counter) -- persist `counter` as last_counter so each code can only
        be used once, even inside its validity window.
    """
    digits_only = re.sub(r'\D', '', code or '')
    if len(digits_only) != digits:
        return False, None

    try:
        key = _decode_base32(secret_b32)
    except Exception:
        logger.error("Stored TOTP secret is not valid base32")
        return False, None

    now = time.time() if at is None else at
    base = int(now // period)
    drifts = [0]
    for step in range(1, window + 1):
        drifts.extend([-step, step])

    for drift in drifts:
        counter = base + drift
        if counter < 0:
            continue
        if last_counter is not None and counter <= last_counter:
            continue                    # replay, or a code already spent
        if hmac.compare_digest(hotp(key, counter, digits), digits_only):
            return True, counter
    return False, None


def build_otpauth_uri(username: str, secret_b32: str) -> str:
    """Build the otpauth:// URI an authenticator app scans"""
    label = quote(f"{TOTP_ISSUER}:{username}", safe='')
    return (
        f"otpauth://totp/{label}"
        f"?secret={secret_b32}"
        f"&issuer={quote(TOTP_ISSUER, safe='')}"
        f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD}"
    )


def build_qr_data_uri(otpauth_uri: str) -> str:
    """
    Render the otpauth URI as a PNG data URI.

    A data URI set via img.src means no server-generated markup is ever injected
    into the page.
    """
    buffer = io.BytesIO()
    segno.make(otpauth_uri, error='m').save(buffer, kind='png', scale=5, border=2)
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


# ---------------------------------------------------------------------------
# Recovery codes
# ---------------------------------------------------------------------------

def generate_recovery_code() -> str:
    """Generate a single XXXXX-XXXXX recovery code (~50 bits)"""
    raw = ''.join(
        secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(RECOVERY_CODE_GROUP * 2)
    )
    return f"{raw[:RECOVERY_CODE_GROUP]}-{raw[RECOVERY_CODE_GROUP:]}"


def normalise_recovery_code(code: str) -> str:
    """Strip formatting so users can type codes with or without the dash"""
    return re.sub(r'[^A-Z0-9]', '', (code or '').upper())


# ---------------------------------------------------------------------------
# Session interface
# ---------------------------------------------------------------------------

def request_is_https() -> bool:
    """
    Whether the request reached the user over HTTPS.

    X-Forwarded-Proto is consulted here even when TRUST_PROXY_HEADERS is off, and
    deliberately so. This decides only whether to mark the session cookie Secure,
    and the recommended deployment is behind a TLS-terminating reverse proxy --
    tying it to the opt-in ProxyFix would hand out a cookie without the Secure
    flag in exactly that setup, so an attacker who can see or induce one plain
    HTTP request would capture a working session.

    Spoofing the header can only cost the spoofer their own session (a Secure
    cookie their plain-HTTP browser then refuses to send back); it cannot
    downgrade anybody else. TRUST_PROXY_HEADERS still governs the client IP used
    for lockout, where spoofing WOULD affect other users.
    """
    if request.is_secure:
        return True
    forwarded_proto = request.headers.get('X-Forwarded-Proto', '')
    if forwarded_proto.split(',')[0].strip().lower() == 'https':
        return True
    # RFC 7239: Forwarded: for=...;proto=https
    forwarded = request.headers.get('Forwarded', '')
    return 'proto=https' in forwarded.replace(' ', '').lower()


class SchemeAwareSessionInterface(SecureCookieSessionInterface):
    """
    Sets the cookie's Secure flag based on how the request actually arrived.

    Forcing Secure=True breaks every plain-HTTP LAN deployment in the least
    debuggable way possible: the login POST succeeds, the browser refuses to
    send the cookie back over HTTP, and the next request bounces to /login with
    no error anywhere. Forcing False downgrades HTTPS users. So: decide per
    request, with an explicit override.
    """

    def get_cookie_secure(self, app):
        mode = app.config.get('SESSION_COOKIE_SECURE_MODE', 'auto')
        if mode is True or str(mode).lower() in ('1', 'true', 'yes', 'on'):
            return True
        if mode is False or str(mode).lower() in ('0', 'false', 'no', 'off'):
            return False
        return has_request_context() and request_is_https()


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


class AuthManager:
    """Owns credential storage, session state, lockout accounting and CSRF"""

    def __init__(self, config):
        self.config = config
        # Lockout counters live in process memory. The container runs a single
        # gunicorn worker by design, so this is the whole application's view.
        # Counters reset on restart; the per-attempt scrypt cost is the floor
        # that survives one.
        self._attempts = {}
        self._attempts_lock = threading.Lock()
        # In-progress TOTP enrolments, keyed by user id. Held server-side rather
        # than in the session: the session cookie is signed but NOT encrypted, so
        # a cookie captured in transit would otherwise hand over the permanent
        # second-factor seed -- which outlives the session, the password and
        # credential_version invalidation.
        self._pending_enrolments = {}
        self._enrolment_lock = threading.Lock()

    # -- account state ---------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.config.get_auth_users())

    def find_user(self, username):
        return self.config.get_auth_user(username)

    def create_user(self, username: str, password: str) -> dict:
        """
        Create the admin account. Raises ValueError on policy violations or if an
        account already exists.
        """
        if self.is_configured():
            raise ValueError("An account already exists")

        clean_username = validate_username(username)
        validate_password_policy(password)

        now = _utc_now_iso()
        record = {
            'id': 'usr_' + secrets.token_hex(6),
            'username': clean_username,
            'password_digest': hash_secret(password),
            'password_updated_at': now,
            'credential_version': 1,
            'roles': ['admin'],
            'created_at': now,
            'last_login_at': None,
            'totp': self._empty_totp(),
        }
        self.config.add_auth_user(record)
        logger.info(f"Created admin account '{clean_username}'")
        return record

    @staticmethod
    def _empty_totp() -> dict:
        return {
            'enabled': False,
            'secret_encrypted': '',
            'algorithm': 'SHA1',
            'digits': TOTP_DIGITS,
            'period': TOTP_PERIOD,
            'confirmed_at': None,
            'last_counter': None,
            'recovery_codes': [],
        }

    def maybe_seed_from_environment(self):
        """
        Pre-seed the admin account from ADMIN_USERNAME plus ADMIN_PASSWORD or
        ADMIN_PASSWORD_HASH, for unattended deployments. First run only -- env
        vars must never resurrect an old password on restart.
        """
        if self.is_configured():
            return

        username = os.environ.get('ADMIN_USERNAME')
        password = os.environ.get('ADMIN_PASSWORD')
        password_hash = os.environ.get('ADMIN_PASSWORD_HASH')
        if not username or not (password or password_hash):
            return

        try:
            clean_username = validate_username(username)
            if password_hash:
                now = _utc_now_iso()
                record = {
                    'id': 'usr_' + secrets.token_hex(6),
                    'username': clean_username,
                    'password_digest': password_hash,
                    'password_updated_at': now,
                    'credential_version': 1,
                    'roles': ['admin'],
                    'created_at': now,
                    'last_login_at': None,
                    'totp': self._empty_totp(),
                }
                self.config.add_auth_user(record)
            else:
                validate_password_policy(password)
                self.create_user(clean_username, password)
            logger.info(
                f"Seeded admin account '{clean_username}' from environment variables"
            )
        except ValueError as exc:
            logger.error(f"Could not seed the admin account from the environment: {exc}")

    def verify_user_password(self, user, password: str) -> bool:
        """
        Verify a password. Unknown users are still checked against a dummy digest
        so the work done -- and therefore the response time -- is the same.
        """
        digest = (user or {}).get('password_digest') or dummy_digest()
        matched = verify_secret(digest, password or '')
        return bool(user) and matched

    def bump_credential_version(self, user_id: str) -> int:
        """Invalidate every existing session for this user"""
        user = self.config.get_auth_user_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        new_version = int(user.get('credential_version', 1)) + 1
        self.config.update_auth_user(user_id, {'credential_version': new_version})
        return new_version

    def change_password(self, user_id: str, new_password: str) -> int:
        validate_password_policy(new_password)
        user = self.config.get_auth_user_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        new_version = int(user.get('credential_version', 1)) + 1
        self.config.update_auth_user(user_id, {
            'password_digest': hash_secret(new_password),
            'password_updated_at': _utc_now_iso(),
            'credential_version': new_version,
        })
        logger.info(f"Password changed for '{user.get('username')}'")
        return new_version

    # -- session ---------------------------------------------------------

    def start_session(self, user):
        """Sign a user in. Clears any prior session state first."""
        session.clear()
        session['uid'] = user['id']
        session['cv'] = int(user.get('credential_version', 1))
        session['auth_at'] = int(time.time())
        session.permanent = True
        self.config.update_auth_user(user['id'], {'last_login_at': _utc_now_iso()})

    def refresh_session_credentials(self, user_id: str, credential_version: int):
        """Keep the acting session valid after a credential_version bump"""
        if session.get('uid') == user_id:
            session['cv'] = int(credential_version)

    def current_user(self):
        """
        The authenticated user, or None.

        Returns None for pending-TOTP sessions: only `uid` is consulted, and the
        first login step never sets it.
        """
        user_id = session.get('uid')
        if not user_id:
            return None

        user = self.config.get_auth_user_by_id(user_id)
        if user is None:
            session.clear()
            return None

        if session.get('cv') != int(user.get('credential_version', 1)):
            session.clear()             # credentials changed elsewhere
            return None

        auth_at = session.get('auth_at')
        if not isinstance(auth_at, int) or \
                time.time() - auth_at > ABSOLUTE_SESSION_LIFETIME.total_seconds():
            session.clear()
            return None

        return user

    def logout(self):
        session.clear()

    # -- pending second factor -------------------------------------------

    def start_pending_totp(self, user, next_url: str):
        session.clear()
        session['pending_uid'] = user['id']
        session['pending_cv'] = int(user.get('credential_version', 1))
        session['pending_exp'] = int(time.time()) + PENDING_TOTP_SECONDS
        session['pending_next'] = safe_next(next_url)
        session.permanent = False

    def get_pending_user(self):
        """The user awaiting a second factor, or None if absent/expired/stale"""
        user_id = session.get('pending_uid')
        if not user_id:
            return None
        if int(session.get('pending_exp') or 0) < int(time.time()):
            self.clear_pending_totp()
            return None
        user = self.config.get_auth_user_by_id(user_id)
        if user is None:
            self.clear_pending_totp()
            return None
        if session.get('pending_cv') != int(user.get('credential_version', 1)):
            # Password changed mid-flow
            self.clear_pending_totp()
            return None
        return user

    def clear_pending_totp(self):
        for key in ('pending_uid', 'pending_cv', 'pending_exp', 'pending_next'):
            session.pop(key, None)

    # -- TOTP ------------------------------------------------------------

    @staticmethod
    def totp_enabled(user) -> bool:
        return bool((user or {}).get('totp', {}).get('enabled'))

    @staticmethod
    def get_totp_secret(user) -> str:
        """
        Decrypt the stored TOTP secret.

        Raises TOTPUnavailable if the Fernet key has changed since enrolment --
        the caller should offer a recovery code rather than reporting a bad code.
        """
        encrypted = (user or {}).get('totp', {}).get('secret_encrypted') or ''
        if not encrypted:
            raise TOTPUnavailable("No TOTP secret stored")
        try:
            return get_password_encryption().decrypt_password(encrypted)
        except Exception as exc:
            logger.error(
                f"Could not decrypt the stored TOTP secret ({exc}). The encryption "
                "key has probably changed -- sign in with a recovery code."
            )
            raise TOTPUnavailable(str(exc))

    def verify_totp_for_user(self, user, code) -> bool:
        """Verify a TOTP code and persist last_counter so it cannot be replayed"""
        totp = user.get('totp', {})
        secret = self.get_totp_secret(user)
        ok, counter = verify_totp(
            secret,
            code,
            period=int(totp.get('period') or TOTP_PERIOD),
            digits=int(totp.get('digits') or TOTP_DIGITS),
            last_counter=totp.get('last_counter'),
        )
        if not ok:
            return False
        updated = dict(totp)
        updated['last_counter'] = counter
        self.config.update_auth_user(user['id'], {'totp': updated})
        return True

    # -- in-progress enrolment (server-side) -----------------------------

    def start_enrolment(self, user_id: str, secret_b32: str):
        with self._enrolment_lock:
            self._prune_enrolments()
            self._pending_enrolments[user_id] = {
                'secret': secret_b32,
                'exp': time.time() + PENDING_ENROLMENT_SECONDS,
            }

    def get_enrolment_secret(self, user_id: str):
        """The pending secret for this user, or None if absent or expired"""
        with self._enrolment_lock:
            self._prune_enrolments()
            entry = self._pending_enrolments.get(user_id)
            return entry['secret'] if entry else None

    def clear_enrolment(self, user_id: str):
        with self._enrolment_lock:
            self._pending_enrolments.pop(user_id, None)

    def _prune_enrolments(self):
        now = time.time()
        for user_id in [k for k, v in self._pending_enrolments.items()
                        if v.get('exp', 0) < now]:
            del self._pending_enrolments[user_id]

    def enable_totp(self, user_id: str, secret_b32: str):
        """
        Persist a confirmed TOTP secret, issue recovery codes and invalidate
        other sessions. Returns (plaintext_recovery_codes, credential_version).
        """
        user = self.config.get_auth_user_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        codes = [generate_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
        totp = self._empty_totp()
        totp.update({
            'enabled': True,
            'secret_encrypted': get_password_encryption().encrypt_password(secret_b32),
            'confirmed_at': _utc_now_iso(),
            'recovery_codes': [
                {'code_digest': hash_secret(normalise_recovery_code(c)), 'used_at': None}
                for c in codes
            ],
        })
        new_version = int(user.get('credential_version', 1)) + 1
        self.config.update_auth_user(user_id, {
            'totp': totp,
            'credential_version': new_version,
        })
        logger.info(f"Two-factor authentication enabled for '{user.get('username')}'")
        return codes, new_version

    def disable_totp(self, user_id: str) -> int:
        user = self.config.get_auth_user_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        new_version = int(user.get('credential_version', 1)) + 1
        self.config.update_auth_user(user_id, {
            'totp': self._empty_totp(),
            'credential_version': new_version,
        })
        logger.info(f"Two-factor authentication disabled for '{user.get('username')}'")
        return new_version

    def regenerate_recovery_codes(self, user_id: str):
        user = self.config.get_auth_user_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        if not self.totp_enabled(user):
            raise ValueError("Two-factor authentication is not enabled")

        codes = [generate_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
        totp = dict(user.get('totp', {}))
        totp['recovery_codes'] = [
            {'code_digest': hash_secret(normalise_recovery_code(c)), 'used_at': None}
            for c in codes
        ]
        new_version = int(user.get('credential_version', 1)) + 1
        self.config.update_auth_user(user_id, {
            'totp': totp,
            'credential_version': new_version,
        })
        logger.info(f"Recovery codes regenerated for '{user.get('username')}'")
        return codes, new_version

    def consume_recovery_code(self, user, code: str) -> bool:
        """Spend a single-use recovery code. Returns True if one matched."""
        normalised = normalise_recovery_code(code)
        if not normalised:
            return False

        totp = dict(user.get('totp', {}))
        entries = totp.get('recovery_codes') or []
        for entry in entries:
            if entry.get('used_at'):
                continue
            if verify_secret(entry.get('code_digest', ''), normalised):
                entry['used_at'] = _utc_now_iso()
                totp['recovery_codes'] = entries
                self.config.update_auth_user(user['id'], {'totp': totp})
                logger.warning(
                    f"Recovery code used to sign in as '{user.get('username')}'"
                )
                return True
        return False

    @staticmethod
    def recovery_codes_remaining(user) -> int:
        entries = (user or {}).get('totp', {}).get('recovery_codes') or []
        return sum(1 for e in entries if not e.get('used_at'))

    # -- lockout ---------------------------------------------------------

    @staticmethod
    def _free_attempts(kind: str) -> int:
        if kind == 'ip':
            return IP_FREE_ATTEMPTS
        if kind == 'sensitive':
            return SENSITIVE_FREE_ATTEMPTS
        return FREE_ATTEMPTS

    def login_buckets(self, username: str):
        """The two buckets guarding a login attempt: the account and the client"""
        return [
            ('user', (username or '').strip().lower()),
            ('ip', client_ip()),
        ]

    def check_locked(self, buckets) -> int:
        """Seconds remaining until the caller may retry (0 if not locked)"""
        now = time.time()
        remaining = 0
        with self._attempts_lock:
            self._prune(now)
            for bucket in buckets:
                state = self._attempts.get(bucket)
                if not state:
                    continue
                wait = int(state.get('locked_until', 0) - now)
                remaining = max(remaining, wait)
        return max(remaining, 0)

    def register_failure(self, buckets) -> int:
        """Record a failed attempt against each bucket; returns the lock seconds"""
        now = time.time()
        remaining = 0
        with self._attempts_lock:
            for bucket in buckets:
                state = self._attempts.setdefault(
                    bucket, {'failures': 0, 'locked_until': 0.0, 'last_attempt': now}
                )
                state['failures'] += 1
                state['last_attempt'] = now
                free = self._free_attempts(bucket[0])
                if state['failures'] > free:
                    delay = min(
                        BASE_LOCKOUT * (2 ** (state['failures'] - free - 1)), MAX_LOCKOUT
                    )
                    state['locked_until'] = now + delay
                    remaining = max(remaining, int(delay))
        return remaining

    def reset_attempts(self, buckets=None):
        """Clear lockout state. With no argument, clears everything."""
        with self._attempts_lock:
            if buckets is None:
                self._attempts.clear()
                return
            for bucket in buckets:
                self._attempts.pop(bucket, None)

    def _prune(self, now: float):
        stale = [
            bucket for bucket, state in self._attempts.items()
            if now - state.get('last_attempt', 0) > ATTEMPT_WINDOW
            and state.get('locked_until', 0) < now
        ]
        for bucket in stale:
            del self._attempts[bucket]

    # -- CSRF ------------------------------------------------------------

    def get_csrf_token(self) -> str:
        """The session's CSRF token, creating one on first use"""
        token = session.get(CSRF_SESSION_KEY)
        if not token:
            token = secrets.token_urlsafe(32)
            session[CSRF_SESSION_KEY] = token
        return token

    @staticmethod
    def _origin_check_enabled() -> bool:
        return os.environ.get('CSRF_ORIGIN_CHECK', '1').lower() not in ('0', 'false', 'no')

    def validate_csrf(self, req):
        """Returns None when the request is acceptable, else a short reason"""
        if self._origin_check_enabled():
            origin = req.headers.get('Origin')
            if origin and origin.rstrip('/') != req.host_url.rstrip('/'):
                return 'origin_mismatch'

        expected = session.get(CSRF_SESSION_KEY)
        if not expected:
            return 'no_session_token'

        submitted = ''
        for name in CSRF_HEADER_NAMES:
            if req.headers.get(name):
                submitted = req.headers[name]
                break
        if not submitted:
            try:
                submitted = req.form.get(CSRF_FORM_FIELD, '') or ''
            except Exception:
                submitted = ''
        if not submitted:
            return 'missing'

        # Compare as bytes: werkzeug decodes headers as latin-1, and
        # compare_digest raises TypeError on non-ASCII str input, which would turn
        # a crafted header into a 500 instead of a clean rejection.
        matched = hmac.compare_digest(
            expected.encode('utf-8', 'replace'),
            submitted.encode('utf-8', 'replace'),
        )
        return None if matched else 'mismatch'


# ---------------------------------------------------------------------------
# Module singleton (mirrors get_password_encryption())
# ---------------------------------------------------------------------------

_auth_manager = None


def get_auth() -> AuthManager:
    if _auth_manager is None:
        raise RuntimeError("init_auth() has not been called")
    return _auth_manager


def client_ip() -> str:
    """
    The client address used for lockout keying and audit logging.

    Sanitised because it becomes attacker-influenced once TRUST_PROXY_HEADERS is
    set and ProxyFix starts reading X-Forwarded-For.
    """
    if not has_request_context():
        return 'unknown'
    return log_safe(request.remote_addr or 'unknown', limit=64)


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def _wants_json() -> bool:
    return (
        request.path.startswith('/api/')
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
    )


def _auth_required_response():
    if _wants_json():
        # The marker matters: POST /api/distribution/test already answers 401
        # {"error": "Invalid password"} for a wrong SSH host password, and the
        # frontend must not treat that as an expired session.
        return jsonify({'error': 'Authentication required', 'auth_required': True}), 401

    if not request.cookies.get(SESSION_COOKIE_NAME) and \
            (request.referrer or '').rstrip('/').endswith('/login'):
        logger.warning(
            "Sign-in appeared to succeed but no session cookie came back. Check "
            "SESSION_COOKIE_SECURE and TLS termination -- see the Security Notes "
            "in README.md."
        )

    target = request.full_path if request.query_string else request.path
    return redirect(url_for('auth.login', next=safe_next(target)))


def _setup_required_response():
    if _wants_json():
        return jsonify({
            'error': 'Initial setup has not been completed',
            'setup_required': True,
        }), 503
    return redirect(url_for('auth.setup'))


def _csrf_failure_response(reason: str):
    logger.warning(f"Rejected {request.method} {request.path}: CSRF {reason}")
    if _wants_json():
        return jsonify({
            'error': 'CSRF token missing or invalid',
            'csrf_failed': True,
        }), 403
    # HTML forms: bounce back to the GET version of the page with a flag, so the
    # form can be re-rendered with a fresh token and a friendly message.
    endpoint = request.endpoint
    if endpoint in ('auth.setup', 'auth.login', 'auth.login_totp'):
        return redirect(url_for(endpoint, csrf_error=1), code=303)
    return redirect(url_for('auth.login', csrf_error=1), code=303)


@auth_bp.before_app_request
def _gate():
    """Application-wide authentication, setup and CSRF gate"""
    endpoint = request.endpoint

    if endpoint in ('static', 'health'):
        return None                     # always open; GET-only, so no CSRF check

    auth = get_auth()

    # 1. First-run setup
    if not auth.is_configured():
        if endpoint != 'auth.setup':
            return _setup_required_response()
    elif endpoint == 'auth.setup':
        return redirect(url_for('index'))

    # 2. Session. `endpoint is None` (unmatched URL) lands here too, so anonymous
    #    probing cannot enumerate which routes exist.
    if endpoint not in PUBLIC_ENDPOINTS:
        user = auth.current_user()
        if user is None:
            return _auth_required_response()
        g.current_user = user

    # 3. CSRF for unsafe methods, including the public POSTs (login CSRF is real)
    if request.method not in SAFE_METHODS:
        problem = auth.validate_csrf(request)
        if problem:
            return _csrf_failure_response(problem)

    return None


# ---------------------------------------------------------------------------
# Helpers for the views
# ---------------------------------------------------------------------------

def _lockout_message(seconds: int) -> str:
    if seconds >= 120:
        return (
            "Too many failed sign-in attempts. Try again in about "
            f"{max(1, round(seconds / 60))} minutes."
        )
    return f"Too many failed sign-in attempts. Try again in {max(1, seconds)} seconds."


def _json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _require_current_password(auth, user, password):
    """
    Re-check the current password for a sensitive account action, rate-limited
    separately so a hijacked browser cannot brute-force it.

    Returns None when the password is correct, otherwise a Flask response.
    """
    buckets = [('sensitive', user['id'])]
    locked = auth.check_locked(buckets)
    if locked:
        return jsonify({'error': _lockout_message(locked)}), 429, {'Retry-After': str(locked)}

    if not auth.verify_user_password(user, password or ''):
        delay = auth.register_failure(buckets)
        logger.warning(
            f"Incorrect password for a sensitive action by '{user.get('username')}' "
            f"from {client_ip()}"
        )
        if delay:
            return jsonify({'error': _lockout_message(delay)}), 429, \
                {'Retry-After': str(delay)}
        return jsonify({'error': 'Current password is incorrect'}), 401

    auth.reset_attempts(buckets)
    return None


# ---------------------------------------------------------------------------
# HTML routes
# ---------------------------------------------------------------------------

@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """First-run admin account creation"""
    auth = get_auth()

    # Checked in the gate as well. Duplicated deliberately: if this guard is ever
    # missing, anybody can reset the admin password.
    if auth.is_configured():
        if _wants_json():
            return jsonify({'error': 'Setup has already been completed'}), 409
        return redirect(url_for('index'))

    if request.method == 'GET':
        return render_template(
            'setup.html',
            error='Your session expired, please try again.' if request.args.get('csrf_error') else None,
            username='',
            min_length=PASSWORD_MIN_LENGTH,
        )

    username = request.form.get('username', '')
    password = request.form.get('password', '')
    confirm = request.form.get('password_confirm', '')

    error = None
    if password != confirm:
        error = 'The two passwords do not match.'
    else:
        try:
            validate_username(username)
            validate_password_policy(password)
        except ValueError as exc:
            error = str(exc)

    if error:
        return render_template(
            'setup.html', error=error, username=username.strip(),
            min_length=PASSWORD_MIN_LENGTH,
        ), 400

    try:
        user = auth.create_user(username, password)
    except ValueError as exc:
        return render_template(
            'setup.html', error=str(exc), username=username.strip(),
            min_length=PASSWORD_MIN_LENGTH,
        ), 400

    logger.info(f"Initial admin account created from {client_ip()}")
    auth.start_session(user)
    return redirect(url_for('index'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Password step"""
    auth = get_auth()
    next_url = safe_next(request.values.get('next'))

    if request.method == 'GET':
        if auth.current_user() is not None:
            return redirect(next_url)
        message = None
        if request.args.get('logged_out'):
            message = 'You have been signed out.'
        return render_template(
            'login.html',
            stage='password',
            next_url=next_url,
            message=message,
            error='Your session expired, please try again.' if request.args.get('csrf_error') else None,
        )

    username = request.form.get('username', '')
    password = request.form.get('password', '')
    buckets = auth.login_buckets(username)

    locked = auth.check_locked(buckets)
    if locked:
        return render_template(
            'login.html', stage='password', next_url=next_url,
            error=_lockout_message(locked),
        ), 429, {'Retry-After': str(locked)}

    user = auth.find_user(username)
    # Runs the same KDF work for unknown users, so timing reveals nothing.
    if not auth.verify_user_password(user, password):
        delay = auth.register_failure(buckets)
        logger.warning(
            f"Failed sign-in for '{log_safe(username)}' from {client_ip()}"
        )
        if delay:
            # This attempt is the one that tripped the lock -- say so now rather
            # than letting the next attempt be the first to mention it.
            return render_template(
                'login.html', stage='password', next_url=next_url,
                error=_lockout_message(delay),
            ), 429, {'Retry-After': str(delay)}
        return render_template(
            'login.html', stage='password', next_url=next_url,
            error='Invalid username or password.',
        ), 401

    auth.reset_attempts(buckets)

    if auth.totp_enabled(user):
        auth.start_pending_totp(user, next_url)
        return redirect(url_for('auth.login_totp'))

    auth.start_session(user)
    logger.info(f"'{user['username']}' signed in from {client_ip()}")
    return redirect(next_url)


@auth_bp.route('/login/totp', methods=['GET', 'POST'])
def login_totp():
    """Second factor step. The session is not authenticated until this passes."""
    auth = get_auth()
    user = auth.get_pending_user()
    if user is None:
        return redirect(url_for('auth.login'))

    next_url = safe_next(session.get('pending_next'))

    if request.method == 'GET':
        return render_template(
            'login.html', stage='totp', next_url=next_url,
            error='Your session expired, please try again.' if request.args.get('csrf_error') else None,
        )

    code = request.form.get('code', '')
    recovery_code = request.form.get('recovery_code', '')
    buckets = auth.login_buckets(user.get('username', ''))

    locked = auth.check_locked(buckets)
    if locked:
        return render_template(
            'login.html', stage='totp', next_url=next_url,
            error=_lockout_message(locked),
        ), 429, {'Retry-After': str(locked)}

    verified = False
    error = 'That code is not valid.'

    if recovery_code:
        verified = auth.consume_recovery_code(user, recovery_code)
        if not verified:
            error = 'That recovery code is not valid, or has already been used.'
    elif code:
        try:
            verified = auth.verify_totp_for_user(user, code)
        except TOTPUnavailable:
            error = (
                'Two-factor codes cannot be checked right now because the '
                'encryption key has changed. Sign in with a recovery code.'
            )
    else:
        error = 'Enter the code from your authenticator app.'

    if not verified:
        delay = auth.register_failure(buckets)
        logger.warning(
            f"Failed second factor for '{user.get('username')}' from {client_ip()}"
        )
        if delay:
            return render_template(
                'login.html', stage='totp', next_url=next_url,
                error=_lockout_message(delay),
            ), 429, {'Retry-After': str(delay)}
        return render_template(
            'login.html', stage='totp', next_url=next_url, error=error,
        ), 401

    auth.reset_attempts(buckets)
    # Re-read: consume_recovery_code / verify_totp_for_user just wrote to the record
    user = auth.config.get_auth_user_by_id(user['id'])
    auth.start_session(user)
    logger.info(f"'{user['username']}' signed in with a second factor from {client_ip()}")
    return redirect(next_url)


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """POST only -- a GET logout could be triggered by any <img src>"""
    get_auth().logout()
    return redirect(url_for('auth.login', logged_out=1))


# ---------------------------------------------------------------------------
# JSON routes
# ---------------------------------------------------------------------------

@auth_bp.route('/api/csrf-token', methods=['GET'])
def csrf_token_endpoint():
    return jsonify({'csrf_token': get_auth().get_csrf_token()})


@auth_bp.route('/api/auth/status', methods=['GET'])
def auth_status():
    auth = get_auth()
    user = g.current_user
    totp = user.get('totp', {})
    return jsonify({
        'username': user.get('username'),
        'totp_enabled': auth.totp_enabled(user),
        'totp_confirmed_at': totp.get('confirmed_at'),
        'recovery_codes_total': len(totp.get('recovery_codes') or []),
        'recovery_codes_remaining': auth.recovery_codes_remaining(user),
        'password_updated_at': user.get('password_updated_at'),
    })


@auth_bp.route('/api/auth/password', methods=['POST'])
def change_password():
    auth = get_auth()
    user = g.current_user
    data = _json_body()

    problem = _require_current_password(auth, user, data.get('current_password'))
    if problem is not None:
        return problem

    new_password = data.get('new_password') or ''
    if new_password == (data.get('current_password') or ''):
        return jsonify({'error': 'The new password must be different'}), 400

    try:
        new_version = auth.change_password(user['id'], new_password)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    auth.refresh_session_credentials(user['id'], new_version)
    return jsonify({
        'status': 'success',
        'message': 'Password updated. Any other signed-in sessions have been ended.',
    })


@auth_bp.route('/api/auth/totp/begin', methods=['POST'])
def totp_begin():
    auth = get_auth()
    user = g.current_user
    data = _json_body()

    if auth.totp_enabled(user):
        return jsonify({'error': 'Two-factor authentication is already enabled'}), 409

    problem = _require_current_password(auth, user, data.get('current_password'))
    if problem is not None:
        return problem

    secret = generate_totp_secret()
    # Held server-side, not in config and not in the session: no half-configured
    # state reaches config.yaml, and the seed never travels in a cookie.
    auth.start_enrolment(user['id'], secret)
    otpauth_uri = build_otpauth_uri(user.get('username', 'admin'), secret)
    return jsonify({
        'secret': secret,
        'otpauth_uri': otpauth_uri,
        'qr_png_data_uri': build_qr_data_uri(otpauth_uri),
        'digits': TOTP_DIGITS,
        'period': TOTP_PERIOD,
    })


@auth_bp.route('/api/auth/totp/confirm', methods=['POST'])
def totp_confirm():
    auth = get_auth()
    user = g.current_user
    data = _json_body()

    if auth.totp_enabled(user):
        return jsonify({'error': 'Two-factor authentication is already enabled'}), 409

    secret = auth.get_enrolment_secret(user['id'])
    if not secret:
        return jsonify({
            'error': 'Enrolment timed out. Start again to get a fresh QR code.',
        }), 409

    ok, _counter = verify_totp(secret, data.get('code'))
    if not ok:
        return jsonify({'error': 'That code is not valid. Check your device clock and try again.'}), 400

    codes, new_version = auth.enable_totp(user['id'], secret)
    auth.clear_enrolment(user['id'])
    auth.refresh_session_credentials(user['id'], new_version)
    return jsonify({
        'status': 'success',
        'message': 'Two-factor authentication is now enabled.',
        'recovery_codes': codes,
    })


@auth_bp.route('/api/auth/totp/disable', methods=['POST'])
def totp_disable():
    auth = get_auth()
    user = g.current_user
    data = _json_body()

    if not auth.totp_enabled(user):
        return jsonify({'error': 'Two-factor authentication is not enabled'}), 409

    problem = _require_current_password(auth, user, data.get('current_password'))
    if problem is not None:
        return problem

    new_version = auth.disable_totp(user['id'])
    auth.clear_enrolment(user['id'])
    auth.refresh_session_credentials(user['id'], new_version)
    return jsonify({
        'status': 'success',
        'message': 'Two-factor authentication has been disabled.',
    })


@auth_bp.route('/api/auth/recovery-codes', methods=['POST'])
def regenerate_recovery_codes():
    auth = get_auth()
    user = g.current_user
    data = _json_body()

    if not auth.totp_enabled(user):
        return jsonify({'error': 'Two-factor authentication is not enabled'}), 409

    problem = _require_current_password(auth, user, data.get('current_password'))
    if problem is not None:
        return problem

    codes, new_version = auth.regenerate_recovery_codes(user['id'])
    auth.refresh_session_credentials(user['id'], new_version)
    return jsonify({
        'status': 'success',
        'message': 'New recovery codes generated. The previous codes no longer work.',
        'recovery_codes': codes,
    })


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning(f"{name} is not a number; using {default}")
        return default
    if value < minimum or value > maximum:
        logger.warning(f"{name}={value} is out of range; using {default}")
        return default
    return value


def init_auth(app, config):
    """Configure sessions, register the auth blueprint and the app-wide gate"""
    global _auth_manager

    app.secret_key = load_or_create_secret_key(config.config_dir)

    lifetime_hours = _env_int('SESSION_LIFETIME_HOURS', 12, minimum=1, maximum=720)
    app.config.update(
        SESSION_COOKIE_NAME=SESSION_COOKIE_NAME,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE_MODE=os.environ.get('SESSION_COOKIE_SECURE', 'auto'),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=lifetime_hours),
        SESSION_REFRESH_EACH_REQUEST=True,
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    app.session_interface = SchemeAwareSessionInterface()

    if os.environ.get('TRUST_PROXY_HEADERS', '').lower() in ('1', 'true', 'yes', 'on'):
        # Opt-in only: trusting X-Forwarded-For unconditionally would let a direct
        # client spoof the IP that lockout is keyed on.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        logger.info("Trusting X-Forwarded-* headers (TRUST_PROXY_HEADERS is set)")

    _auth_manager = AuthManager(config)
    _auth_manager.maybe_seed_from_environment()

    app.jinja_env.globals['csrf_token'] = _auth_manager.get_csrf_token
    app.register_blueprint(auth_bp)

    if not _auth_manager.is_configured():
        logger.warning(
            "No administrator account exists yet. Open the web interface to "
            "create one at /setup."
        )
    return _auth_manager
