# Copilot instructions — Porkbun-Certificate-Sync

> Canonical standards live in the `dev-standards` repo on SOUNDWAVE/Gitea.
> Read by Copilot chat **and** inline suggestions.

## What this repo is

A standalone **Dockerised Python web app** that fetches SSL certificates from
Porkbun and distributes them to hosts over SSH. Not a Home Assistant component.

## Repo shape

- `app/` — `main.py`, `certificate_manager.py`, `porkbun_api.py`, `sync.py`,
  `ssh_config.py`, `ssh_distribution.py`, `distribution_log.py`,
  `password_encryption.py`, `config.py`, plus `static/` + `templates/` web UI.
- `config.example.yaml`, `Dockerfile`, `docker-compose.yml`,
  `.github/workflows/docker-publish.yml`.

## Conventions

- Python web service: no `manifest.json`/`hassfest`/HACS.
- CI publishes the Docker image.
- Porkbun API keys, SSH credentials, and cert material are **highly sensitive** —
  config via env / `config.yaml` (see `.example`), never committed. Note the repo
  has its own `password_encryption.py`; don't weaken it.

## Never

- Don't commit Porkbun API keys, SSH keys, certificates/private keys, or any
  credentials.
