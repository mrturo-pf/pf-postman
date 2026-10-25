#!/usr/bin/env bash
set -euo pipefail

# Run mutating integration fixtures against a disposable local database only.
# This deliberately resets the local pf-db database before and after the run;
# it must never be pointed at GCP, Neon, or production.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DB_ROOT="$REPO_ROOT/modules/pf-db"
INCOME_ROOT="$REPO_ROOT/modules/pf-svc-income"
BACKUP_PATH="${PF_LOCAL_BACKUP_PATH:-/tmp/pf-local-integration-$(date -u +%Y%m%dT%H%M%SZ).dump}"

[[ -d "$DB_ROOT" && -d "$INCOME_ROOT" ]] || {
  printf 'Expected local pf-db and pf-svc-income checkouts under %s\n' "$REPO_ROOT" >&2
  exit 2
}

case "${PF_INCOME_BASE_URL:-http://localhost:8000}" in
  http://localhost:*|http://127.0.0.1:*|http://\[::1\]:*) ;;
  *) printf 'Refusing non-loopback PF_INCOME_BASE_URL\n' >&2; exit 2 ;;
esac

backup_database() {
  nerdctl --address /var/run/docker/containerd/containerd.sock \
    compose -f "$DB_ROOT/docker-compose.yml" exec -T db \
    pg_dump -U pf_db -d pf_db --format=custom >"$BACKUP_PATH"
  chmod 600 "$BACKUP_PATH"
  printf 'Local database backup: %s\n' "$BACKUP_PATH"
}

reset_database() {
  make -C "$DB_ROOT" db-reset
  make -C "$DB_ROOT" local-up-test
}

cleanup() {
  printf 'Resetting local integration database...\n'
  reset_database
}

backup_database
reset_database
trap cleanup EXIT

income_key="${PF_INCOME_API_KEY:?PF_INCOME_API_KEY is required}"
PF_INCOME_API_KEY="$income_key" \
  python3 "$SCRIPT_DIR/run-postman-integration.py" \
  --base-url "${PF_INCOME_BASE_URL:-http://localhost:8000}" \
  --defer-cleanup
