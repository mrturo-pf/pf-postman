#!/usr/bin/env bash
# Configure pf-postman Actions secrets without exposing values in shell history.
# GitHub does not provide an API to read existing secret values, so this script
# accepts them interactively and writes them directly to the target repository.

set -euo pipefail

readonly TARGET_REPOSITORY="mrturo-pf/pf-postman"
readonly SECRET_NAMES=(
  POSTMAN_API_KEY
  POSTMAN_COLLECTION_UID
  POSTMAN_ENV_UID_LOCAL
  POSTMAN_ENV_UID_GCP
  PF_RATES_API_KEY_LOCAL
  PF_SVC_INCOME_API_KEY_LOCAL
  PF_RATES_API_KEY_GCP
  PF_SVC_INCOME_API_KEY_GCP
  PF_SHEETS_API_KEY
)

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  }
}

require_command gh

if ! gh auth status >/dev/null 2>&1; then
  printf 'GitHub CLI is not authenticated. Run: gh auth login\n' >&2
  exit 1
fi

printf 'Configuring %s secrets. Values are hidden while typing.\n' "$TARGET_REPOSITORY"
printf 'Press Ctrl-C to stop.\n\n'

for secret_name in "${SECRET_NAMES[@]}"; do
  while true; do
    read -r -s -p "${secret_name}: " secret_value
    printf '\n'
    if [[ -n "$secret_value" ]]; then
      break
    fi
    printf 'A blank value is not allowed. Try again.\n' >&2
  done

  printf '%s' "$secret_value" | gh secret set "$secret_name" --repo "$TARGET_REPOSITORY"
  unset secret_value
  printf 'Stored %s.\n' "$secret_name"
done

printf '\nConfigured secret names (values remain unreadable):\n'
gh secret list --repo "$TARGET_REPOSITORY"
printf '\nTrigger the workflow with:\n'
printf 'gh workflow run "CI / Sync Postman Collection" --repo %s --ref main\n' "$TARGET_REPOSITORY"
