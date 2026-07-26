# 🔐 Porkbun Certificate Sync

A Docker container with a web-based management interface for retrieving SSL certificates from Porkbun and hosting them in a mounted volume.

## Features

- 🔐 **Authentication**: Mandatory sign-in protects the interface and the API
  - First-run setup wizard creates your administrator account
  - Optional two-factor authentication (authenticator app + single-use recovery codes)
  - Brute-force lockout with exponential backoff
  - CSRF-protected API and hardened session cookies
- 🌐 **Web Interface**: Easy-to-use web UI for managing certificates, with a Security tab for your account and two-factor settings
- 🔑 **API Configuration**: Securely store and manage Porkbun API credentials
- 📦 **Domain Management**: Add, edit, and remove domains for certificate retrieval
- 📝 **Custom Naming**: Define custom naming structures for certificate files with multiple options
  - Custom base names for certificates
  - Configurable file name separators (underscore, hyphen, dot)
  - Alternative file name variants for flexibility
- 🔗 **Intermediary Certificate Split**: Automatically extracts and saves intermediary certificates as separate files
  - Full chain certificate (leaf + intermediates + root)
  - Individual leaf certificate
  - Separate intermediary chain file (intermediates + root only)
  - Private key
- 🔄 **Format Conversion**: Support for multiple certificate formats (PEM, CRT, KEY, PFX/PKCS12)
- 🚀 **SSH Distribution**: Automatically distribute certificates to remote servers via SSH
  - Configure multiple remote hosts with friendly display names
  - Secure password storage with encryption
  - Automatic distribution after successful certificate sync
  - Sudo support for deploying to protected directories
  - **Per-host file name overrides** for custom remote file naming (e.g., cert.pem, chain.pem, privkey.pem)
  - Specify custom certificate paths on remote servers
  - Collapsible host cards for clean interface
  - Alphabetically sorted host list
- 📋 **Distribution Logging**: Comprehensive logging of all sync and distribution events
  - Track certificate sync events
  - Monitor distribution success/failure per host
  - Filter logs by event type
  - View statistics dashboard
- ⏰ **Human-Friendly Scheduling**: Intuitive schedule configuration with:
  - Easy-to-use frequency selectors (Hourly, Daily, Weekly, Specific Days, Monthly)
  - Visual time pickers for hour and minute selection
  - Real-time cron expression preview
- 🌓 **Dark Mode**: Toggle between light and dark themes for comfortable viewing
- 💾 **YAML Configuration**: All settings stored in a YAML configuration file
- 🐳 **Docker Ready**: Fully containerized with Docker Compose support

## Screenshots

### Light Mode
<img src="https://github.com/user-attachments/assets/74143c1c-bcde-4e37-b573-497b92912579" alt="Settings Tab - Light Mode" width="800">

*Settings tab showing API configuration, certificate settings, and the intuitive schedule configuration interface*

<img src="https://github.com/user-attachments/assets/b840f1ba-d3e3-4e63-b83b-30dfacecc6a8" alt="Domains Tab - Light Mode" width="800">

*Domains tab with domain management features including custom naming and file separators*

<img src="https://github.com/user-attachments/assets/e1ad96a2-2141-42e8-bcef-ce834ce951cf" alt="Distribution Tab with File Overrides - Light Mode" width="800">

*Distribution tab for configuring SSH hosts with per-host custom file name overrides*

<img src="https://github.com/user-attachments/assets/ed0fce32-4a09-4305-b442-3a92f543abab" alt="Logs Tab - Light Mode" width="800">

*Logs tab displaying distribution events, statistics, and filtering options*

### Dark Mode
<img src="https://github.com/user-attachments/assets/37c28b18-d8d1-4da1-bd1d-d3a84d3dabc0" alt="Settings Tab - Dark Mode" width="800">

*Dark mode provides a comfortable viewing experience in low-light environments*

<img src="https://github.com/user-attachments/assets/d2093bd9-abf1-4eb1-9117-7f3ae242d99c" alt="Domains Tab - Dark Mode" width="800">

*Domain management interface in dark mode*

<img src="https://github.com/user-attachments/assets/75c43160-9dc2-4d4f-9f07-a9216d7fa224" alt="Distribution Tab with File Overrides - Dark Mode" width="800">

*Distribution tab with custom file name overrides in dark mode — properly styled for readability*

<img src="https://github.com/user-attachments/assets/6c6ff9b7-cd67-4910-928f-d72d7332c7da" alt="Logs Tab - Dark Mode" width="800">

*Distribution logs with statistics in dark mode*

<!-- TODO: add screenshots of the sign-in page, the first-run setup page and the
     Security tab (two-factor enrolment with the QR code), in both light and dark
     mode, to match the sections above. -->

## Quick Start

### Using Docker Compose

1. Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  porkbun-cert-sync:
    image: ghcr.io/loryanstrant/porkbun-certificate-sync:latest
    container_name: porkbun-cert-sync
    ports:
      - "5000:5000"
    volumes:
      - ./certificates:/app/certificates
      - ./config:/app/config
    environment:
      - CONFIG_PATH=/app/config/config.yaml
    restart: unless-stopped
```

2. Start the container:

```bash
docker-compose up -d
```

3. Access the web interface at `http://localhost:5000`

4. **Create your administrator account.** On first start you are redirected to
   `/setup`. Choose a username and a password of at least 12 characters. This is
   the only account for the installation, and there is no password reset by
   email — store the password somewhere safe.

5. Optionally enable two-factor authentication from the **Security** tab, and
   save the recovery codes it gives you.

> **Unattended deployments**: set `ADMIN_USERNAME` together with
> `ADMIN_PASSWORD` (or `ADMIN_PASSWORD_HASH`) before the first start to create
> the account without visiting `/setup`. These are read on first run only.
> Be aware that anyone who can run `docker inspect` can read environment
> variables, so `ADMIN_PASSWORD_HASH` is the safer of the two. Generate one with:
> ```bash
> python -c "from werkzeug.security import generate_password_hash; \
>   print(generate_password_hash(input(), method='scrypt:32768:8:1', salt_length=16))"
> ```

> **Monitoring**: `GET /health` is the only endpoint that does not require
> signing in. Uptime checks pointing at `/` will now receive a `302` redirect to
> the login page — point them at `/health` instead.

### Using Docker CLI

```bash
docker run -d \
  --name porkbun-cert-sync \
  -p 5000:5000 \
  -v $(pwd)/certificates:/app/certificates \
  -v $(pwd)/config:/app/config \
  -e CONFIG_PATH=/app/config/config.yaml \
  ghcr.io/loryanstrant/porkbun-certificate-sync:latest
```

## Configuration

### Web Interface

Access the web interface at `http://localhost:5000` to configure:

1. **API Settings**: Enter your Porkbun API key and secret key
2. **Domains**: Add and edit domains to retrieve certificates for
   - Set custom base names for certificate files
   - Choose file name separators (underscore, hyphen, or dot)
   - Define alternative file name variants
   - Edit existing domain configurations
3. **Distribution**: Configure SSH hosts for automatic certificate distribution
   - Add multiple remote hosts with friendly display names
   - Specify hostname/IP address, port, username, and password
   - Set the remote certificate path
   - **Override file names per host**: Use custom file names like cert.pem, chain.pem, privkey.pem, fullchain.pem for specific hosts
   - Edit or delete existing hosts
   - Hosts are displayed in collapsible cards sorted alphabetically
4. **Logs**: View distribution and sync event logs
   - See statistics for total syncs, distributions, successes, and failures
   - Filter logs by event type
   - Review detailed information for each event
5. **Certificate Settings**: 
   - Output directory
   - File naming format (use `{domain}` placeholder)
   - Certificate formats (PEM, CRT, KEY, PFX)
6. **Schedule**: Configure automatic sync schedule with user-friendly options
   - Select frequency: Hourly, Daily, Weekly, Specific Days, or Monthly
   - Choose specific time with dropdown menus
   - Preview the generated cron expression in real-time
7. **Theme**: Toggle between light and dark mode using the theme button in the header
8. **Security**: Change your password, turn two-factor authentication on or off, regenerate recovery codes, and sign out

### YAML Configuration

The configuration is stored in `/app/config/config.yaml`:

> **Note**: the `auth` section is written and maintained by the application. Do
> not hand-edit it. It holds your username, a scrypt password hash, the
> encrypted TOTP secret and hashed recovery codes — see
> [Security Notes](#security-notes) for the recovery procedure if you lose access.

```yaml
api:
  api_key: "your-api-key"
  secret_key: "your-secret-key"

domains:
  - domain: "example.com"
    custom_name: "example"  # Optional: custom base name for certificate files
    separator: "_"  # File name separator: "_", "-", or "."
    alt_names: []  # Optional: alternative file name variants

certificates:
  output_dir: "/app/certificates"
  naming_format: "{domain}"
  formats:
    - pem
    - crt
    - key

ssh_hosts:
  - display_name: "Production Server"
    hostname: "prod.example.com"
    port: 22
    username: "root"
    password_encrypted: "encrypted_password_here"  # Password is securely encrypted
    cert_path: "/etc/ssl/certs"
    use_sudo: true  # Use sudo for privileged operations
    file_overrides:  # Optional: custom file names for this host
      cert: "cert.pem"
      chain: "chain.pem"
      privkey: "privkey.pem"
      fullchain: "fullchain.pem"
  - display_name: "Staging Server"
    hostname: "staging.example.com"
    port: 22
    username: "deploy"
    password_encrypted: "encrypted_password_here"
    cert_path: "/opt/certificates"
    use_sudo: false  # No sudo required

schedule:
  enabled: true
  cron: "0 2 * * *"  # 2 AM daily (configured via user-friendly UI)
```

## Certificate Formats

- **PEM**: Full chain, private key, certificate, and intermediary chain as separate files
  - `{name}_fullchain.pem` - Complete certificate chain (leaf + intermediates + root)
  - `{name}_cert.pem` - Leaf certificate only
  - `{name}_chain.pem` - Intermediary certificate chain (intermediates + root, without leaf)
  - `{name}_private.key` - Private key
- **CRT**: Certificate chain as a single `.crt` file
- **KEY**: Private key as a separate `.key` file
- **PFX/PKCS12**: Combined certificate and private key in `.pfx` format

### File Naming Options

You have flexible control over certificate file names:

1. **Default Naming**: Uses custom base name + separator + file type
   - Example with base name "strant.casa" and separator "_": `strant.casa_fullchain.pem`, `strant.casa_cert.pem`, `strant.casa_chain.pem`, `strant.casa_private.key`

2. **Per-Host File Overrides**: Override individual file names for specific SSH hosts
   - Example: `cert.pem`, `chain.pem`, `privkey.pem`, `fullchain.pem`
   - This is useful when deploying to systems that expect specific file names (e.g., Let's Encrypt style naming)
   - Configured per SSH host so different servers can use different file naming conventions

## API Endpoints

The application provides a REST API.

**Authentication applies to every endpoint except `GET /health`:**

- All `/api/*` endpoints require an authenticated session cookie. Unauthenticated
  calls return `401 {"auth_required": true}`, or `503 {"setup_required": true}`
  before the administrator account has been created.
- Requests using an unsafe method (`POST`, `PUT`, `DELETE`) must also send the
  session's CSRF token in an `X-CSRF-Token` header, obtainable from
  `GET /api/csrf-token`. Without it the request is rejected with
  `403 {"csrf_failed": true}`.
- **There is no API token in this release**, so scripting the API means driving a
  browser session (sign in, keep the cookie jar, fetch a CSRF token). See
  [Upgrading](#upgrading-from-a-version-without-authentication).

### Authentication

- `GET /setup` / `POST /setup` - First-run administrator account creation
- `GET /login` / `POST /login` - Sign in (username and password)
- `GET /login/totp` / `POST /login/totp` - Second factor: authenticator code or recovery code
- `POST /logout` - Sign out (POST only)
- `GET /api/csrf-token` - Get the current session's CSRF token
- `GET /api/auth/status` - Account status (username, two-factor state, recovery codes remaining)
- `POST /api/auth/password` - Change the password
- `POST /api/auth/totp/begin` - Start two-factor enrolment (returns secret, `otpauth://` URI and QR code)
- `POST /api/auth/totp/confirm` - Confirm enrolment with a code; returns the recovery codes once
- `POST /api/auth/totp/disable` - Turn two-factor authentication off
- `POST /api/auth/recovery-codes` - Replace the recovery codes with a fresh set

### Application

- `GET /api/settings` - Get current settings
- `POST /api/settings/api` - Update API credentials
- `POST /api/settings/certificates` - Update certificate settings
- `POST /api/settings/schedule` - Update schedule settings
- `GET /api/domains` - List configured domains
- `POST /api/domains` - Add a new domain
- `PUT /api/domains/<domain>` - Update an existing domain
- `DELETE /api/domains/<domain>` - Remove a domain
- `GET /api/ssh-hosts` - List configured SSH hosts
- `POST /api/ssh-hosts` - Add a new SSH host
- `PUT /api/ssh-hosts/<display_name>` - Update an existing SSH host
- `DELETE /api/ssh-hosts/<display_name>` - Remove an SSH host
- `POST /api/distribution/test` - Test SSH connection to a host
- `GET /api/distribution/logs` - Get distribution logs
- `POST /api/sync` - Manually trigger certificate sync
- `GET /api/sync/status` - Get sync status
- `GET /health` - Health check endpoint (**the only endpoint that needs no sign-in**)

## Building from Source

```bash
# Clone the repository
git clone https://github.com/loryanstrant/Porkbun-Certificate-Sync.git
cd Porkbun-Certificate-Sync

# Build the Docker image
docker build -t porkbun-cert-sync .

# Run the container
docker-compose up -d
```

## Development

### Requirements

- Python 3.11+
- Docker
- Docker Compose

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export CONFIG_PATH=./config/config.yaml

# Run the application
python -m flask --app app.main run --host 0.0.0.0 --port 5000
```

Then open `http://localhost:5000` and create an account at `/setup`, or skip that
step by exporting `ADMIN_USERNAME` and `ADMIN_PASSWORD` before starting.

### Running the tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

The suite covers the authentication gate, setup, sign-in, TOTP (including the
RFC 6238 test vectors), lockout, CSRF and the config schema. It uses a temporary
config directory, so it will not touch your local `config/`. CI runs it on every
push and pull request, and the Docker image is only published if it passes.

## Environment Variables

### General

- `CONFIG_PATH`: Path to configuration file (default: `/app/config/config.yaml`)
- `FLASK_APP`: Flask application module (default: `app.main`)
- `ENCRYPTION_KEY`: (Optional) Encryption key for SSH passwords **and the TOTP secret**. If not set, a key is automatically generated and saved to `/app/config/.encryption_key`, which persists across container restarts as long as the config volume is mounted. You can manually set this if you need to use the same key across multiple instances. Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `DISABLE_SCHEDULER`: (Optional) Set to `1` to skip starting the background scheduler. Intended for development and tests.

### Authentication

- `SECRET_KEY`: (Optional) Flask session signing key. If unset, one is generated and saved to `/app/config/.secret_key` with mode `0600`, so sessions now survive container restarts without any configuration. Setting it explicitly takes precedence; it must be at least 32 characters. **Changing or deleting it signs everyone out** — which is also the deliberate way to end all sessions from the host.
- `ADMIN_USERNAME`: (Optional) Pre-seed the administrator username. **First run only.**
- `ADMIN_PASSWORD`: (Optional) Pre-seed the administrator password (minimum 12 characters). **First run only.** Visible to anyone who can run `docker inspect` — prefer `ADMIN_PASSWORD_HASH`.
- `ADMIN_PASSWORD_HASH`: (Optional) Pre-seed a werkzeug password hash instead of a plaintext password. **First run only.**
- `SESSION_COOKIE_SECURE`: `auto` (default), `true` or `false`. On `auto` the session cookie is marked `Secure` only for requests that arrived over HTTPS — including HTTPS terminated at a reverse proxy, which is detected from `X-Forwarded-Proto` or `Forwarded` regardless of `TRUST_PROXY_HEADERS`. Set to `false` if sign-in appears to succeed but immediately bounces back to the login page on a plain-HTTP deployment.
- `SESSION_LIFETIME_HOURS`: Idle session lifetime in hours (default `12`, maximum `720`). Sessions are also capped at 7 days regardless of activity.
- `TRUST_PROXY_HEADERS`: Set to `1` when running behind a reverse proxy, so `X-Forwarded-Proto` and `X-Forwarded-For` are honoured. Without it, HTTPS is not detected through the proxy and every client appears to share the proxy's IP address for lockout purposes. Do **not** enable it when the container is reachable directly, as clients could then spoof their address.
- `CSRF_ORIGIN_CHECK`: Set to `0` to disable the secondary `Origin` header check. Only needed for unusual proxy setups that rewrite the `Host` header.

## Volumes

- `/app/certificates`: Certificate storage directory
- `/app/config`: Configuration file directory. Also holds `.encryption_key` and `.secret_key` (both mode `0600`) and the app-managed `auth` section of `config.yaml`. **Keep this directory private** — anyone who can read it can forge a session or decrypt your SSH passwords.

## Ports

- `5000`: Web interface and API

## Security Notes

- Store your Porkbun API credentials securely
- **Authentication is mandatory and cannot be disabled.** A reverse proxy with TLS is still strongly recommended: without HTTPS your password and session cookie cross the network in the clear.
- Regularly update certificates and rotate credentials
- The container runs as root by default; consider using a non-root user in production
- **Important**: PFX/PKCS12 files are created without password protection by default for compatibility. Ensure the certificate directory has appropriate file permissions (e.g., `chmod 700 certificates`) to protect private keys
- Keep the config volume private. `config.yaml`, `.secret_key` and `.encryption_key` are written with mode `0600`, but the directory itself must not be world-readable.
- Only one gunicorn worker is supported. Raising the worker count breaks both the background scheduler and lockout accounting.

### Authentication Security

- **Password storage**: passwords are hashed with scrypt (`n=32768, r=8, p=1`, 16-byte salt) via `werkzeug.security`. They are never stored reversibly and never logged. This is deliberately different from SSH host passwords, which must be recoverable to be used.
- **Sessions**: the cookie is `HttpOnly`, `SameSite=Lax`, and `Secure` whenever the request arrived over HTTPS — whether directly or via a TLS-terminating reverse proxy (see `SESSION_COOKIE_SECURE`). It is signed with a key persisted to `/app/config/.secret_key`. Sessions expire after `SESSION_LIFETIME_HOURS` of inactivity and are capped at 7 days. Changing your password, or turning two-factor authentication on or off, immediately ends every other signed-in session.
- **The session cookie is signed, not encrypted.** It carries only an opaque user id, a credential version and a timestamp — never a password, a TOTP secret or a recovery code. An in-progress two-factor enrolment secret is held in the server's memory, not in the cookie.
- **CSRF**: all unsafe requests must carry the session's CSRF token, in an `X-CSRF-Token` header or a `csrf_token` form field. An `Origin` header, when present, must match the request host. This applies to sign-in and setup too, since login CSRF is a real attack.
- **Brute-force lockout**: after 3 failed attempts against an account, delays grow exponentially from 5 seconds to a 15-minute maximum; a separate, looser counter tracks the client address. A wrong password and a non-existent username produce byte-identical responses and identical lockout behaviour, so the login form cannot be used to enumerate accounts. Lockouts are never permanent and reset on container restart.
- **Two-factor authentication**: standard TOTP (RFC 6238, SHA-1, 6 digits, 30-second period) with a ±30 second tolerance, compatible with any authenticator app. **The container clock must be accurate** — configure NTP on the host, or codes will be rejected. Each accepted code is recorded so it cannot be replayed.
- **TOTP secret at rest**: encrypted with the same key as SSH passwords (`/app/config/.encryption_key`). If you rotate `ENCRYPTION_KEY`, the secret can no longer be decrypted; sign in with a recovery code and re-enrol. The app reports this as "codes cannot be checked right now" rather than as a wrong code.
- **Recovery codes**: 10 single-use codes are issued when you enable two-factor authentication, stored hashed, and displayed exactly once. Save them. The Security tab shows how many remain and warns when you are running low.
- **Lost access?** With no password and no recovery codes, recovery requires filesystem access: stop the container, delete the entire `auth:` block from `config/config.yaml`, and restart. The next request returns to `/setup` and every other setting is preserved.

### SSH Distribution Security

- **Password Storage**: SSH passwords are encrypted using Fernet symmetric encryption before storage in the configuration file. The encryption key is automatically generated and persisted to `/app/config/.encryption_key` (which is in the mounted config volume), ensuring passwords remain valid across container updates and restarts. Alternatively, you can manually set the `ENCRYPTION_KEY` environment variable if you need to use the same key across multiple instances.
- **Sudo Support**: The application supports using `sudo` for privileged operations when deploying certificates to protected directories. This is useful when certificates need to be placed in system directories like `/etc/ssl/certs`.
- **Automatic Distribution**: After successful certificate sync, certificates are automatically distributed to all configured SSH hosts. This eliminates the need for manual copying and ensures all servers have the latest certificates.
- **SSH Key Alternative**: For enhanced security, consider using SSH key-based authentication instead of passwords (future enhancement)
- **Host Key Validation**: The application uses `AutoAddPolicy` to automatically accept SSH host keys for ease of deployment. This accepts unknown host keys without validation, which could be susceptible to man-in-the-middle attacks. For production use, consider implementing SSH key-based authentication with proper known_hosts validation
- **Network Security**: Ensure SSH access is properly secured on target servers (firewall rules, fail2ban, etc.)
- **Least Privilege**: Use dedicated service accounts with minimal permissions on remote servers. Enable `use_sudo` only when necessary.
- **Audit Logs**: Review distribution logs regularly to monitor certificate deployment activities
- **Secure Transmission**: SSH connections use standard SSH protocol encryption for secure file transfer

## Upgrading from a version without authentication

Authentication was added in a release that changes behaviour for existing
installations. After pulling the new image:

1. Every page redirects to `/setup` and every `/api/*` call returns
   `503 {"setup_required": true}` until you create an administrator account.
2. Your existing settings, domains, SSH hosts and encrypted SSH passwords are
   untouched. A `.secret_key` file appears alongside `.encryption_key`, and
   `config.yaml` is rewritten with mode `0600`.
3. **Certificates keep syncing throughout**, including before setup is completed.
   The scheduled sync runs outside the web request path and is deliberately not
   gated, so nothing expires just because nobody has visited the UI.

Breaking changes to be aware of:

- **Scripted API access stops working.** Any `curl` or cron job calling `/api/*`
  now receives `401`, and unsafe methods additionally need a CSRF token. There is
  no API token in this release, and no way to disable authentication. Scripts must
  either sign in and hold a cookie jar, or be replaced by the built-in scheduler.
- **Uptime checks on `/` now get a `302`.** Point them at `GET /health`.
- **Reverse proxies already doing HTTP Basic auth** will prompt twice. You can
  drop the proxy-level authentication.
- **`POST /api/distribution/test`** now answers `403` rather than `401` for a
  wrong SSH host password, so `401` unambiguously means "sign in".
- **`config.yaml` becomes mode `0600`**, which may surprise you if you edit it as
  a non-root user on the host.

## Troubleshooting

### Sign-in Issues

**"I sign in successfully but land straight back on the login page."** The browser
is refusing to return the session cookie. This happens when the cookie is marked
`Secure` but the page is served over plain HTTP. Set `SESSION_COOKIE_SECURE=false`
if you are not using HTTPS, or `TRUST_PROXY_HEADERS=1` if a reverse proxy is
terminating TLS for you. The container logs a warning when it detects this.

**"My authenticator codes are always rejected."** The container clock has drifted.
TOTP allows only ±30 seconds. Check the host's time synchronisation, then sign in
with a recovery code.

**"I'm locked out after too many attempts."** Lockouts are temporary and never
permanent; the `Retry-After` header and the on-screen message tell you how long
to wait. Restarting the container also clears the counters.

**"I've lost my password and my recovery codes."** Stop the container, delete the
whole `auth:` block from `config/config.yaml`, and restart. The next request goes
to `/setup`; every other setting is preserved.

### API Connection Issues

Check your API credentials in the Settings tab. Use the "Test Connection" feature to verify.

### Certificate Sync Failures

- Ensure the domain is configured in Porkbun
- Verify API credentials have the correct permissions
- Check container logs: `docker logs porkbun-cert-sync`

### Permission Issues

#### Local File System

Ensure the mounted volumes have appropriate permissions:

```bash
chmod 755 certificates config
```

#### SSH Distribution

If you encounter "Permission denied" errors when distributing certificates to remote hosts:

1. Check the error message in the distribution logs
2. If the remote path requires elevated privileges (e.g., `/etc/ssl/certs`), enable `use_sudo: true` in your SSH host configuration
3. Ensure the remote user account has sudo privileges
4. Verify the remote user's password is correctly configured

Example configuration for hosts requiring sudo:

```yaml
ssh_hosts:
  - display_name: "My Server"
    hostname: "server.example.com"
    port: 22
    username: "deploy"
    password_encrypted: "..."
    cert_path: "/etc/ssl/certs"
    use_sudo: true  # Enable this for paths requiring elevated privileges
```


## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## Development Approach
<img width="256" height="256" alt="Vibe Coding with GitHub Copilot 256x256" src="https://github.com/user-attachments/assets/bb41d075-6b3e-4f2b-a88e-94b2022b5d4f" />


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Porkbun](https://porkbun.com/) for their API
- [Flask](https://flask.palletsprojects.com/) web framework
- [APScheduler](https://apscheduler.readthedocs.io/) for scheduling
