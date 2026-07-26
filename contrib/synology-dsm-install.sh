#!/bin/bash
# ---------------------------------------------------------------------------
# synology-dsm-install.sh
#
# Installs certificates fetched by Porkbun-Certificate-Sync into the Synology
# DSM certificate store, replacing an existing certificate *in place* so that
# every service already bound to it (reverse-proxy hosts, MailServer, FTPS, ...)
# keeps working without being re-bound.
#
# Intended to run ON the DSM box (root, via Control Panel > Task Scheduler)
# when the container writes its output to a local folder. It is idempotent:
# if the synced certificate is the one already installed, it does nothing.
#
# Modelled on acme.sh's deploy/synology_dsm.sh hook, which established the
# shape of the (undocumented) SYNO.Core.Certificate import call.
#
# Dependencies: bash, curl, openssl. Deliberately NO jq -- DSM does not ship it.
#
#   Usage: synology-dsm-install.sh [--dry-run] [--force] [--domain <domain>]
#
#   --dry-run        report what would happen; make no write calls
#   --force          import even when the certificate is already current
#   --domain <d>     only process this one domain (default: all in CERT_MAP)
#
# Exit: 0 = success (including "nothing to do"), 1 = failure.
# ---------------------------------------------------------------------------
set -euo pipefail

CONF="${CERTSYNC_CONF:-/volume1/docker/certsync-dsm/certsync-dsm.env}"
if [ -r "$CONF" ]; then
  # shellcheck source=/dev/null
  . "$CONF"
elif [ -e "$CONF" ]; then
  # Guard: `[ -r x ] && . x` under `set -e` would exit 1 here with no output at all.
  echo "ERROR: config file exists but is not readable: $CONF (run as root?)" >&2
  exit 1
else
  echo "ERROR: config file not found: $CONF (set \$CERTSYNC_CONF to override)" >&2
  exit 1
fi

DSM_URL="${DSM_URL:-http://127.0.0.1:5000}"
CERT_DIR="${CERT_DIR:-/volume1/certshare}"
LOG_FILE="${LOG_FILE:-/volume1/docker/certsync-dsm/install.log}"
# Space/newline separated "<domain>=<DSM cert id>" pairs, e.g.
#   CERT_MAP="strant.casa=NVlrGh strant.com=cqL39M"
CERT_MAP="${CERT_MAP:-}"

DRY_RUN=0
FORCE=0
ONLY_DOMAIN=""

SID=""
TOKEN=""
CERT_LIST=""
TMPDIR_=""
CHANGED=0
FAILED=0

# ---------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------

log() {
  local line
  line="$(date '+%Y-%m-%d %H:%M:%S') $*"
  printf '%s\n' "$line"
  # Best-effort logging: never let an unwritable log file abort the run.
  if [ -n "$LOG_FILE" ]; then
    printf '%s\n' "$line" >>"$LOG_FILE" 2>/dev/null || true
  fi
}

die() { log "ERROR: $*"; exit 1; }

cleanup() {
  [ -n "$TMPDIR_" ] && rm -rf "$TMPDIR_"
  [ -n "$SID" ] && api_logout
  return 0
}
trap cleanup EXIT

usage() { sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

# Pull one scalar field out of a single-line JSON record.
json_field() { # <record> <field>
  printf '%s' "$1" | sed -n "s/.*\"$2\" *: *\"\([^\"]*\)\".*/\1/p"
}

# ---------------------------------------------------------------------------
# DSM API
# ---------------------------------------------------------------------------

api_login() {
  local resp
  resp="$(curl -sS --max-time 30 -c "$TMPDIR_/cookies" -G "$DSM_URL/webapi/entry.cgi" \
    --data-urlencode 'api=SYNO.API.Auth' \
    --data-urlencode 'version=7' \
    --data-urlencode 'method=login' \
    --data-urlencode "account=$DSM_USER" \
    --data-urlencode "passwd=$DSM_PASS" \
    --data-urlencode 'session=CertMgr' \
    --data-urlencode 'format=cookie' \
    --data-urlencode 'enable_syno_token=yes')" || die "login request failed"

  SID="$(json_field "$resp" sid)"
  TOKEN="$(json_field "$resp" synotoken)"

  if [ -z "$SID" ]; then
    local code
    code="$(printf '%s' "$resp" | sed -n 's/.*"code" *: *\([0-9]*\).*/\1/p')"
    case "$code" in
      400|401) die "login failed: bad DSM_USER/DSM_PASS (error $code)" ;;
      403|404) die "login failed: account requires 2FA/OTP (error $code) -- use an account with 2FA disabled" ;;
      *)       die "login failed (error ${code:-unknown})" ;;
    esac
  fi
  [ -n "$TOKEN" ] || die "login succeeded but DSM returned no SynoToken; cannot make write calls"
  log "authenticated to DSM as $DSM_USER"
}

api_logout() {
  curl -sS --max-time 15 -b "$TMPDIR_/cookies" -H "X-SYNO-TOKEN: $TOKEN" \
    -G "$DSM_URL/webapi/entry.cgi" \
    --data-urlencode 'api=SYNO.API.Auth' --data-urlencode 'version=7' \
    --data-urlencode 'method=logout' --data-urlencode "_sid=$SID" >/dev/null 2>&1 || true
  SID=""
}

# Fetch the certificate list once and split it into one line per certificate.
# Each top-level certificate object starts with {"desc": (DSM emits the keys
# alphabetically), so that string is a safe record separator; nested objects
# such as issuer/subject/services never begin with it.
#
# NB: once a session is created with enable_syno_token=yes, DSM requires the
# X-SYNO-TOKEN header on EVERY call including reads -- omitting it returns 119.
api_cert_list() {
  local resp
  resp="$(curl -sS --max-time 30 -b "$TMPDIR_/cookies" -H "X-SYNO-TOKEN: $TOKEN" \
    -G "$DSM_URL/webapi/entry.cgi" \
    --data-urlencode 'api=SYNO.Core.Certificate.CRT' \
    --data-urlencode 'version=1' \
    --data-urlencode 'method=list' \
    --data-urlencode "_sid=$SID")" || die "certificate list request failed"

  printf '%s' "$resp" | grep -q '"success" *: *true' \
    || die "certificate list failed: $(printf '%s' "$resp" | head -c 200)"

  CERT_LIST="$(printf '%s' "$resp" | tr -d '\n' | sed 's/{"desc":/\n{"desc":/g' | grep '"id"')"
}

cert_record() { printf '%s\n' "$CERT_LIST" | grep -F "\"id\":\"$1\"" | head -1; }

# ---------------------------------------------------------------------------
# certificate helpers
# ---------------------------------------------------------------------------

# The app names Porkbun's `publickey` field <domain>.cert.pem, but that file is
# an RSA PUBLIC KEY, not a certificate -- so the leaf must come from the first
# PEM block of fullchain.pem instead.
extract_leaf() { # <fullchain> <out>
  awk '/-----BEGIN CERTIFICATE-----/{n++} n==1{print} /-----END CERTIFICATE-----/{if(n==1) exit}' \
    "$1" >"$2"
  grep -q 'BEGIN CERTIFICATE' "$2" || die "no certificate found in $1"
}

cert_enddate() { openssl x509 -noout -enddate -in "$1" | sed 's/^notAfter=//'; }

# Refuse to import material that would break TLS for every bound service.
preflight() { # <leaf> <key> <chain> <domain>
  local leaf="$1" key="$2" chain="$3" domain="$4" cmod kmod

  openssl x509 -noout -in "$leaf" >/dev/null 2>&1 || die "$domain: leaf is not a valid certificate"
  openssl pkey -noout -in "$key" >/dev/null 2>&1 || die "$domain: private key is not a valid key"
  openssl x509 -noout -in "$chain" >/dev/null 2>&1 || die "$domain: chain is not a valid certificate"

  # The key must belong to the certificate, or DSM will happily serve a broken pair.
  cmod="$(openssl x509 -noout -pubkey -in "$leaf" | openssl md5)"
  kmod="$(openssl pkey -pubout -in "$key" | openssl md5)"
  [ "$cmod" = "$kmod" ] || die "$domain: private key does not match the certificate -- refusing to import"

  openssl x509 -checkend 0 -noout -in "$leaf" >/dev/null 2>&1 \
    || die "$domain: new certificate is already expired -- refusing to import"

  # Guard against a mis-typed CERT_MAP pointing at the wrong domain's cert.
  openssl x509 -noout -text -in "$leaf" | grep -qF "$domain" \
    || die "$domain: certificate does not mention this domain -- check CERT_MAP"
}

# ---------------------------------------------------------------------------
# main per-domain routine
# ---------------------------------------------------------------------------

process_domain() { # <domain> <cert_id>
  local domain="$1" id="$2"
  local fullchain="$CERT_DIR/$domain.fullchain.pem"
  local chain="$CERT_DIR/$domain.chain.pem"
  local key="$CERT_DIR/$domain.private.key"
  local work="$TMPDIR_/$domain"
  local record desc installed_till new_till is_default as_default resp

  log "--- $domain (DSM cert id $id)"

  for f in "$fullchain" "$chain" "$key"; do
    [ -r "$f" ] || { log "ERROR: $domain: missing or unreadable $f"; FAILED=1; return 1; }
  done

  record="$(cert_record "$id")"
  if [ -z "$record" ]; then
    log "ERROR: $domain: no certificate with id $id exists in DSM -- check CERT_MAP"
    FAILED=1; return 1
  fi

  desc="$(json_field "$record" desc)"
  installed_till="$(json_field "$record" valid_till)"
  is_default=no
  printf '%s' "$record" | grep -q '"is_default" *: *true' && is_default=yes

  mkdir -p "$work"
  extract_leaf "$fullchain" "$work/cert.pem"
  preflight "$work/cert.pem" "$key" "$chain" "$domain"
  new_till="$(cert_enddate "$work/cert.pem")"

  log "$domain: installed expires '$installed_till' / synced expires '$new_till'"

  if [ "$installed_till" = "$new_till" ] && [ "$FORCE" -eq 0 ]; then
    log "$domain: already current -- nothing to do"
    return 0
  fi
  [ "$FORCE" -eq 1 ] && log "$domain: --force given, importing regardless"

  if [ "$DRY_RUN" -eq 1 ]; then
    log "$domain: DRY RUN -- would import into id $id (is_default=$is_default, desc='$desc')"
    return 0
  fi

  # Replacing by id is the whole point: DSM re-binds the existing services and
  # reloads nginx itself. as_default must be preserved or DSM will demote it.
  as_default=false
  [ "$is_default" = yes ] && as_default=true

  resp="$(curl -sS --max-time 120 -b "$TMPDIR_/cookies" \
    -H "X-SYNO-TOKEN: $TOKEN" \
    -F "key=@$key" \
    -F "cert=@$work/cert.pem" \
    -F "inter_cert=@$chain" \
    -F "id=$id" \
    -F "desc=$desc" \
    -F "as_default=$as_default" \
    "$DSM_URL/webapi/entry.cgi?api=SYNO.Core.Certificate&method=import&version=1&SynoToken=$TOKEN&_sid=$SID")" \
    || { log "ERROR: $domain: import request failed"; FAILED=1; return 1; }

  if printf '%s' "$resp" | grep -q '"error"'; then
    log "ERROR: $domain: import rejected: $(printf '%s' "$resp" | head -c 300)"
    FAILED=1; return 1
  fi

  CHANGED=1
  if printf '%s' "$resp" | grep -q '"restart_httpd" *: *true'; then
    log "$domain: imported into id $id; DSM restarted its HTTP services"
  else
    log "$domain: imported into id $id (no HTTP restart required)"
  fi
}

# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --force)   FORCE=1 ;;
    --domain)  shift; ONLY_DOMAIN="${1:-}"; [ -n "$ONLY_DOMAIN" ] || die "--domain needs a value" ;;
    -h|--help) usage ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
  shift
done

# Log the start line before any validation, so that a run which dies in the
# checks below still leaves a trace -- Task Scheduler discards stdout/stderr
# unless an output path is configured.
log "=== run start (dry_run=$DRY_RUN force=$FORCE${ONLY_DOMAIN:+ domain=$ONLY_DOMAIN})"

for bin in curl openssl awk sed; do
  command -v "$bin" >/dev/null 2>&1 || die "required command not found: $bin"
done

[ -n "${DSM_USER:-}" ] || die "DSM_USER is not set (expected in $CONF)"
[ -n "${DSM_PASS:-}" ] || die "DSM_PASS is not set (expected in $CONF)"
[ -n "$CERT_MAP" ]     || die "CERT_MAP is not set (expected in $CONF)"
[ -d "$CERT_DIR" ]     || die "certificate directory not found: $CERT_DIR"

TMPDIR_="$(mktemp -d)"
chmod 700 "$TMPDIR_"

api_login
api_cert_list

for pair in $CERT_MAP; do
  domain="${pair%%=*}"
  id="${pair#*=}"
  [ -n "$domain" ] && [ -n "$id" ] && [ "$domain" != "$id" ] \
    || die "malformed CERT_MAP entry: '$pair' (expected domain=certid)"
  [ -n "$ONLY_DOMAIN" ] && [ "$ONLY_DOMAIN" != "$domain" ] && continue
  process_domain "$domain" "$id" || true
done

if [ "$FAILED" -ne 0 ]; then
  log "=== run finished WITH ERRORS"
  exit 1
fi
log "=== run finished OK (changed=$CHANGED)"
exit 0
