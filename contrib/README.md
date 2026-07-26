# contrib/synology-dsm-install.sh

Installs certificates fetched by Porkbun-Certificate-Sync into the **Synology DSM
certificate store**, replacing an existing certificate *in place* so that every service
already bound to it (reverse-proxy hosts, MailServer, FTPS, …) keeps working without being
re-bound.

This covers the case where the container runs **on the NAS itself** and writes its output to
a local folder, so the built-in SSH Distribution feature isn't involved at all. It also fills
a gap that Distribution can't: DSM needs an *API call* to adopt a new certificate, and there
is no post-distribution hook to make one.

Modelled on [acme.sh's `deploy/synology_dsm.sh`](https://github.com/acmesh-official/acme.sh/blob/master/deploy/synology_dsm.sh),
which established the shape of the undocumented `SYNO.Core.Certificate` import call.

## Requirements

* Runs **on the DSM box as root** (Control Panel → Task Scheduler → *User-defined script*).
* `bash`, `curl`, `openssl` — all present on DSM 7. **`jq` is deliberately not used**, since
  DSM does not ship it.
* A DSM account in the **administrators** group with **2FA disabled** (the login flow here
  does not do OTP). Verified against DSM 7.3.2.

## Configuration

The script reads a shell-sourced env file, by default
`/volume1/docker/certsync-dsm/certsync-dsm.env` (override with `$CERTSYNC_CONF`).
It contains a password, so it must be `root:root` and `chmod 600`.

```sh
DSM_URL=http://127.0.0.1:5000          # DSM web API, loopback when run on the NAS
DSM_USER=<dsm admin account>
DSM_PASS=<password>
CERT_DIR=/volume1/certshare            # host path the container writes into
LOG_FILE=/volume1/docker/certsync-dsm/install.log
CERT_MAP="example.com=AbCdEf other.net=GhIjKl"
```

`CERT_MAP` maps each configured domain to the **DSM certificate ID** it should replace. Find
the IDs by listing the store:

```sh
# after logging in (see the script's api_login) --
curl -s -b cookies -H "X-SYNO-TOKEN: $TOKEN" \
  "$DSM_URL/webapi/entry.cgi?api=SYNO.Core.Certificate.CRT&version=1&method=list&_sid=$SID"
```

Replacing **by ID** is the whole point: DSM re-binds the existing services and reloads its
HTTP stack itself, which is far safer than hand-writing into
`/usr/syno/etc/certificate/_archive/<id>/` and running `synow3tool --gen-all`.

## Usage

```
synology-dsm-install.sh [--dry-run] [--force] [--domain <domain>]
```

| Flag | Effect |
|---|---|
| `--dry-run` | Report what would happen; make no write calls. |
| `--force` | Import even when the installed certificate is already current. |
| `--domain <d>` | Process only this domain instead of everything in `CERT_MAP`. |

Idempotent: it compares the synced leaf's `notAfter` against the installed certificate's
`valid_till` and does nothing when they match, so a **daily** schedule is safe and
self-healing. Exit code is `0` on success (including "nothing to do") and `1` on any failure,
so Task Scheduler's "notify on abnormal termination" will catch problems.

## Two gotchas this script exists to handle

1. **`<domain>.cert.pem` is not a certificate.** The app writes Porkbun's `publickey` API
   field to that name, but it is an RSA *public key* (`-----BEGIN PUBLIC KEY-----`). Feeding
   it to DSM fails. The leaf is therefore taken from the **first PEM block of
   `<domain>.fullchain.pem`**; `<domain>.chain.pem` supplies `inter_cert`.
2. **`X-SYNO-TOKEN` is required on every call, not just writes.** Once a session is created
   with `enable_syno_token=yes`, omitting the header on even a read returns error `119`.

## DSM API notes (learned the hard way against DSM 7.3.2)

Useful if you extend this or automate the Task Scheduler entry:

* **`X-SYNO-TOKEN` on every call.** Once you log in with `enable_syno_token=yes`, *all*
  subsequent calls need the header — even reads. Omitting it returns `119`.
* **Never import in "create" mode from automation.** With an empty `id`, DSM creates a new
  certificate **and promotes it to default**, ignoring `as_default=false`. This script always
  requires an existing ID and aborts if it isn't found, so it can't do that.
* **DSM will not delete the default certificate** — `method=delete` returns
  `{"success":true}` and silently does nothing. Reassign the default first.
* **Setting the default** is `SYNO.Core.Certificate.CRT` `method=set` with `id=<id>`,
  `desc=<desc>` and `as_default=true`. Note `set` takes `id` (singular) while `delete` takes
  `ids=["..."]`; using the wrong one returns `5503`.
* **Root-owned scheduled tasks** must be created via **`SYNO.Core.TaskScheduler.Root`**
  (`SYNO.Core.TaskScheduler` returns `4800 "Root need run on ..."`), and that requires an
  elevated session: POST `SYNO.Core.User.PasswordConfirm` v2 `method=auth` to get a
  `SynoConfirmPWToken` and pass it along. Omit `monthly_week` from `schedule` or you get
  `4800 "monthly_week not supported"`. `.Root` implements only `create`/`set` — and
  `run`/`delete` on the non-Root API **report success but silently no-op** on root-owned
  tasks, so trigger and delete those from the DSM UI.
* Import errors worth recognising: `5511` missing/invalid certificate data, `5517` the
  supplied `inter_cert` does not actually sign the leaf.

## Safety checks before any import

The script refuses to proceed — rather than break TLS for every bound service — if:

* the private key does not match the leaf certificate (public-key digest comparison);
* the leaf is already expired;
* the leaf does not mention the domain it is mapped to (catches a mis-typed `CERT_MAP`);
* the mapped certificate ID does not exist in DSM;
* any of the leaf/key/chain files are missing, unreadable, or not valid PEM.

It also preserves the existing `desc` and `is_default` flag, so a default certificate is not
silently demoted on re-import.
