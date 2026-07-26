# Copilot instructions — Porkbun-Certificate-Sync

> Canonical standards live in the `dev-standards` repo on SOUNDWAVE/Gitea.
> Read by Copilot chat **and** inline suggestions.

## What this repo is

A standalone **Dockerised Python web app** that fetches SSL certificates from
Porkbun and distributes them to hosts over SSH. Not a Home Assistant component.

## Repo shape

- `app/` — `main.py`, `auth.py`, `certificate_manager.py`, `porkbun_api.py`,
  `sync.py`, `ssh_config.py`, `ssh_distribution.py`, `distribution_log.py`,
  `password_encryption.py`, `config.py`, plus `static/` + `templates/` web UI.
- `tests/` — pytest suite (auth gate, setup, login, TOTP, lockout, CSRF, config).
- `config.example.yaml`, `Dockerfile`, `docker-compose.yml`,
  `requirements.txt` + `requirements-dev.txt`,
  `.github/workflows/docker-publish.yml`.

## Conventions

- Python web service: no `manifest.json`/`hassfest`/HACS.
- CI runs `pytest` and only publishes the Docker image if it passes.
- **Authentication is mandatory** (`app/auth.py`): an app-wide
  `before_app_request` gate in the `auth` blueprint protects everything except
  `GET /health` and `/static/*`. New routes are protected automatically; adding
  one to `PUBLIC_ENDPOINTS` needs a deliberate reason. Endpoint names there are
  blueprint-qualified (`auth.login`, not `login`) — a typo locks everyone out.
- User passwords and recovery codes use `werkzeug.security` scrypt. Only the TOTP
  shared secret uses the reversible Fernet helper, because it must be recoverable.
- All frontend requests go through `apiFetch()` in `app.js`, which attaches the
  CSRF token and handles session expiry. Never call `fetch()` directly.
- Porkbun API keys, SSH credentials, and cert material are **highly sensitive** —
  config via env / `config.yaml` (see `.example`), never committed. Note the repo
  has its own `password_encryption.py`; don't weaken it.

## Never

- Don't commit Porkbun API keys, SSH keys, certificates/private keys, or any
  credentials.
- Don't add an auth bypass, an `AUTH_ENABLED` flag, or a "trusted network" exemption
  — authentication is mandatory by design.
- Don't log passwords, password digests, TOTP secrets or recovery codes. Log the
  username and IP for failed sign-ins, nothing more.
- Don't reuse `ssh_config.verify_password()` (reversible Fernet compare) for user
  login, and don't store user credentials under the key `password_hash` — that's a
  legacy SSH host field. User credentials use `password_digest`.
- Don't make failed-login responses distinguish "no such user" from "wrong
  password"; that enables account enumeration.
- Don't run more than one gunicorn worker: it breaks both the scheduler and the
  in-memory lockout accounting.
