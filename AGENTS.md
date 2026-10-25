# AGENTS.md — pf-postman

`pf-postman` owns the PF ecosystem's Postman collections and environments.
It is the single source of truth for Postman request catalogs, examples,
environment URLs, and the repository-to-Postman synchronization workflow.

## Scope

This repository owns:

- Postman collections for `pf-rates`, `pf-svc-income`, and `pf-sheets`;
- LOCAL and GCP Postman environments;
- sanitized request examples and chained request scripts;
- the GitHub Actions workflow that syncs these files to Postman.

Service repositories remain the source of truth for HTTP implementation and API
contracts. When an endpoint changes, update the owning service's API documentation
and then update the matching Postman request here.

## Security

- Never commit API keys, passwords, tokens, connection strings, personal data,
  payroll data, or raw production payloads.
- API-key variables in committed JSON must remain empty strings or placeholders.
- Real values must be GitHub Secrets and may only be injected into throwaway files
  during the sync workflow.
- Never print secrets in workflow logs.
- Do not add Postman requests whose purpose is only to demonstrate errors; keep
  those cases in automated tests and API documentation.

## Sync contract

The workflow is one-way:

```text
repository JSON → GitHub Actions → Postman API
```

Edits made directly in Postman are not automatically pulled back. Export any
intentional UI changes and reconcile them in this repository.

Required repository secrets:

- `POSTMAN_API_KEY`;
- `POSTMAN_COLLECTION_UID`;
- `POSTMAN_ENV_UID_LOCAL`;
- `POSTMAN_ENV_UID_GCP`;
- service API keys for LOCAL/GCP environments;
- `PF_SHEETS_API_KEY`.

## Contribution workflow

Commit collection or environment changes directly to `main`. The `Postman assets
validation` workflow runs on the push before synchronization, and the same push
triggers synchronization to Postman. Pull requests may be used for discussion or
external contributions, but they are not required for the normal release path.


Before committing collection or environment changes:

```bash
jq empty pf-ecosystem.postman_collection.json
jq empty pf-ecosystem.postman_environment.local.json
jq empty pf-ecosystem.postman_environment.gcp.json
git diff --check
```

## Git

- Use English Conventional Commits.
- Never commit, push, create a PR, or create the remote repository without
  explicit owner authorization.
- Keep collection requests grouped by service and synchronized with each
  service's `docs/api.md`.
