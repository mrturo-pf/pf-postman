# Postman collection — pf ecosystem

Single Postman collection covering all `pf-*` services with an HTTP surface (`pf-rates`,
`pf-svc-income`, and `pf-sheets` — `pf-db` has no HTTP API; it is DDL/migrations only),
plus two environments (`LOCAL`, `GCP`). After an authorized push to `main`, the workflow
syncs the repository assets to Postman. Everything lives here as plain JSON so it can be
edited like any other file in this repo (by hand or by code-puppy).

## Contribution workflow

Commit collection or environment changes directly to `main`. The `Postman assets
validation` check runs on the push and must pass before synchronization. The same
push to `main` triggers the Postman synchronization workflow.

```
edit pf-ecosystem.postman_collection.json
  or pf-ecosystem.postman_environment.{local,gcp}.json
        │
        ▼
   push to main → Validate → Synchronize
        │
        ▼
   .github/workflows/sync-postman.yml
  ├─ sync-collection      → PUT .../collections/{POSTMAN_COLLECTION_UID}
  └─ sync-environments    → PUT .../environments/{POSTMAN_ENV_UID_LOCAL|GCP}
        │                    (api-key values injected from GitHub Secrets
        │                     right before the PUT -- see "Secrets" below)
        ▼
Your Postman workspace shows the update -- no manual import needed.
```

This is a **one-way sync: repo → Postman.** Edits made directly in the Postman app are
**not** pulled back automatically -- if you change something in the Postman UI (other
than an api-key value, see below), export it and overwrite the matching JSON file here,
or it gets clobbered on the next push.

## CI trigger policy

The policy below is the execution contract for this repository. It separates
repository validation from requests that can mutate a service, call an external
provider, or create a Google Drive artifact.

| Change or operation | Automatic trigger | Manual trigger | Safety boundary |
|---|---|---|---|
| Collection, environment, or validation-workflow JSON/YAML | `validate.yml` on pull requests and pushes to `main` | `workflow_dispatch` for an intentional rerun | JSON/whitespace checks only; no HTTP calls |
| Collection publication to Postman | Push to `main` after validation | `sync-postman.yml` dispatch for an approved retry | Secrets are injected into throwaway files; repository JSON stays sanitized |
| OpenAPI or service-contract changes | Owning service CI remains authoritative; the Postman repository does not guess a target | Dispatch `run-api-coverage.yml` with explicit read-only OpenAPI URLs | Fetch only HTTPS/read-only `/openapi.json`; no API key or mutation |
| Disposable fixtures or Postman runner changes | No remote execution | Dispatch `run-postman-integration-local.yml` | Loopback services, disposable database, synthetic identifiers, cleanup in `finally` |
| Read-only smoke against LOCAL/GCP | No automatic remote execution | Dispatch `run-postman-smoke.yml` with explicit target and URLs | Bounded read-only subset; GCP requires explicit target selection and secrets |
| Expected GCP error contracts | No automatic remote execution | Dispatch `run-gcp-error-contracts.yml` with explicit HTTPS URLs | Read-only `401/403`, `404`, and validation cases only |
| Provider refresh, create/update/delete, destructive requests, async exports | Never automatic | Separate approved operator workflow only | Explicit non-production target, bounded timeout/window, synthetic fixture, cleanup evidence |

A pull request that changes collection assets must pass validation before merge.
A change to a service OpenAPI or contract must run the owning service checks and
then the explicit Postman coverage workflow before release evidence is accepted.
Cross-repository CI is intentionally not triggered by untrusted remote URLs or by
committed API keys. Manual workflows must not be added to the default smoke subset
without updating this policy and the IMP-011 safety checklist.

### Rerun and retention rules

- Rerun a failed automatic validation from the failed workflow; do not republish
  manually edited Postman JSON.
- Rerun a manual test only after confirming the target, fixture state, and failure
  classification; never retry a mutating request automatically after an ambiguous
  timeout.
- Upload JUnit/CLI reports as workflow artifacts using sanitized output. Retain
  them according to the repository's GitHub artifact policy; reports must not
  contain API keys, authorization headers, payroll data, or raw provider payloads.
- The workflow owner triages runner/fixture failures; the owning service team
  triages contract or runtime failures; `pf-postman` owns collection mapping,
  assertion, and environment wiring failures.

### Operations and failure triage

Use the workflow file names, not copied run URLs, so reruns remain reproducible:

```bash
# Rerun safe repository validation after confirming the target commit.
gh workflow run validate.yml --repo mrturo-pf/pf-postman

# Compare explicit read-only OpenAPI targets.
gh workflow run run-api-coverage.yml --repo mrturo-pf/pf-postman \
  -f pf_rates_openapi_url=https://<approved-target>/openapi.json \
  -f pf_svc_income_openapi_url=https://<approved-target>/openapi.json

# Run the bounded read-only smoke subset.
gh workflow run run-postman-smoke.yml --repo mrturo-pf/pf-postman \
  -f environment=gcp \
  -f pf_rates_url=https://<approved-rates-target> \
  -f pf_svc_income_url=https://<approved-income-target>
```

Before any `gh` command, use the repository's required proxy cleanup. Never
paste API keys into workflow inputs; the workflows resolve them from GitHub
Secrets. For a failed run, classify the first failure before rerunning:

| Symptom | Owner | Classification and action |
|---|---|---|
| JSON, YAML, ordering, or whitespace failure | `pf-postman` | Collection/runner defect; fix the repository asset, then rerun validation |
| OpenAPI mapping missing, stale, or duplicate | `pf-postman` plus owning service | Contract drift; compare the service OpenAPI and collection, then update the owner of the stale side |
| Fixture setup or cleanup failure | Integration workflow owner | Quarantine synthetic identifiers; do not rerun mutations until cleanup is confirmed |
| HTTP schema/status or runtime failure | Owning service team | Reproduce with the same target and sanitized request; do not hide it with a weaker assertion |
| Authentication, URL, or secret materialization failure | Workflow/environment owner | Check target wiring and secret presence without printing values |
| Timeout after a mutating or external request | Operator and owning service | Inspect job/resource state first; never blindly retry or send stop automatically |

JUnit and CLI reports are uploaded as sanitized GitHub Actions artifacts. The
standard retention is **14 days**; evidence needed for IMP closure must also be
recorded in the improvement plan with run ID, target, counts, and sanitized
failures. Artifacts must never contain API keys, authorization headers, payroll
payloads, personal data, or raw provider responses.

> Postman Team/Enterprise plans also offer a native bidirectional Git sync (no custom
> workflow needed) -- if you upgrade later, you can drop `sync-postman.yml` and use that
> instead. This setup works on **any** Postman plan, including Free.

## Environments: LOCAL vs GCP

Both environments share the same four variable names (matching the collection's
requests): `pf-rates-url`, `pf-rates-api-key`, `pf-svc-income-url`, `pf-svc-income-api-key`.
Whichever environment is active in the Postman UI overrides the collection's own
(harmless localhost) defaults, so switching target just means picking a different
environment from the dropdown -- no request needs editing.

| | `pf-ecosystem.postman_environment.local.json` | `pf-ecosystem.postman_environment.gcp.json` |
|---|---|---|
| `*-url` values | `http://localhost:8001` / `:8000` | real Cloud Run URLs |
| `*-api-key` values in the committed file | always `""` | always `""` |
| Real key comes from | GitHub Secret `PF_RATES_API_KEY_LOCAL` / `PF_SVC_INCOME_API_KEY_LOCAL` | GitHub Secret `PF_RATES_API_KEY_GCP` / `PF_SVC_INCOME_API_KEY_GCP` |

**Why the api-key fields are always empty in git:** a Postman `"type": "secret"` variable
only *masks* the value in the UI -- the raw value is still plain text in the exported
JSON. Committing a real key (even a local dev one) would put it in git history forever.
Instead, the real values live only as GitHub Secrets and get injected into a throwaway
copy of the file inside the GitHub Actions runner, by variable key name (via `jq`,
never blind text substitution), right before the `PUT` to Postman -- then that copy is
deleted. The repo itself never sees a real key.

Practical effect: editing `*-url` values here and pushing updates Postman immediately.
Editing an `*-api-key` value here does **nothing** (it always gets overwritten with the
GitHub Secret's value on sync) -- to rotate a key, update the GitHub Secret instead
(`gh secret set PF_RATES_API_KEY_GCP --repo mrturo-pf/pf-postman`) and re-run the workflow
(push any change under `this repository`, or `gh workflow run "CI / Sync Postman Collection" --repo mrturo-pf/pf-postman`).

## One-time setup

1. **Get a Postman API key**: go to
   [`https://web.postman.co/settings/me/api-keys`](https://web.postman.co/settings/me/api-keys)
   (the UI hides this outside of general Settings) → **Generate API Key**. Copy it, you
   won't see it again.

2. **Find the collection's and each environment's UID**: open it in the Postman **web
   app** (not desktop) — the URL looks like
   `https://<workspace>.postman.co/workspace/.../collection/<UID>` or `.../environment/<UID>`.
   If something doesn't exist in Postman yet, create it first (**Import** in the Postman
   app using the matching JSON here), then read its UID off the URL.

3. **Add every secret** in `pf-postman` (Settings → Secrets and variables → Actions →
   New repository secret):

   | Secret | Value |
   |---|---|
   | `POSTMAN_API_KEY` | from step 1 |
   | `POSTMAN_COLLECTION_UID` | the collection's UID |
   | `POSTMAN_ENV_UID_LOCAL` | the `LOCAL` environment's UID |
   | `POSTMAN_ENV_UID_GCP` | the `GCP` environment's UID |
   | `PF_RATES_API_KEY_LOCAL` | pf-rates dev API key (from `modules/pf-rates/.env`) |
   | `PF_SVC_INCOME_API_KEY_LOCAL` | pf-svc-income dev API key (from `modules/pf-svc-income/.env`) |
   | `PF_RATES_API_KEY_GCP` | pf-rates production API key (GCP Secret Manager, secret `PF_RATES_API_KEY`) |
   | `PF_SVC_INCOME_API_KEY_GCP` | pf-svc-income production API key (GCP Secret Manager, secret `PF_SVC_INCOME_API_KEY`) |
   | `PF_SHEETS_API_KEY` | pf-sheets `GET_CLP_API_KEY` Script Property -- Apps Script editor → Project Settings → Script Properties (no CLI/file access, it's cloud-only) |

   Prefer piping values into `gh secret set` over pasting them anywhere they'd be
   echoed/logged, e.g.:
   ```bash
   grep '^PF_RATES_API_KEY=' modules/pf-rates/.env | cut -d'=' -f2- \
     | gh secret set PF_RATES_API_KEY_LOCAL --repo mrturo-pf/pf-postman
   ```
   Production values living in GCP Secret Manager may be blocked from direct CLI access
   by VPC Service Controls, depending on org policy -- fetch them via the GCP Console
   or an already-authorized path instead if `gcloud secrets versions access` is denied.

4. After pushing a validated change to `main`, check the **Actions** tab — the
   validation and both sync jobs (`sync-collection`, `sync-environments`) should
   turn green. For a manual operational retry, use `gh workflow run`.

## Automated endpoint coverage

[`scripts/check-api-coverage.py`](scripts/check-api-coverage.py) compares the
OpenAPI operations exported by `pf-rates` and `pf-svc-income` with the requests
in this collection. It reports missing and stale method/path pairs without
calling an API or mutating data.

Generate sanitized OpenAPI snapshots from the running services, then run:

```bash
python3 scripts/check-api-coverage.py \
  --openapi pf-rates=/tmp/pf-rates-openapi.json \
  --openapi pf-svc-income=/tmp/pf-svc-income-openapi.json
```

The command exits non-zero when a service folder is missing, an OpenAPI operation
has no Postman request, a Postman request no longer exists in OpenAPI, or an
an undocumented operation appears more than once in the collection. The current
intentional duplicates are refresh operations with different modes and the two
JSON import workflows; they are listed in `INTENTIONAL_DUPLICATES` in the checker.
Snapshots are runtime inputs and must not contain credentials, authorization headers, or
production payloads. The checker can also fetch the documents directly with GET:

```bash
python3 scripts/check-api-coverage.py \
  --openapi-url pf-rates=https://example-rates/openapi.json \
  --openapi-url pf-svc-income=https://example-income/openapi.json
```

The manual workflow
[`run-gcp-error-contracts.yml`](.github/workflows/run-gcp-error-contracts.yml)
checks expected `403`, `404`, and `400/422` responses against explicitly supplied
HTTPS GCP URLs using the GCP API-key secrets. It is read-only.

The manual [`run-gcp-pdf-validation.yml`](.github/workflows/run-gcp-pdf-validation.yml)
uses a synthetic PDF against GCP, asserts template/row resolution, and sends the
result to `mode=validate` only. It does not persist data or upload response bodies.

The manual workflow
[`run-api-coverage.yml`](.github/workflows/run-api-coverage.yml) accepts those
read-only URLs, stores snapshots only in the ephemeral Actions runner directory,
and fails when coverage differs. This coverage check is the first layer of
`IMP-011`; Newman execution and mutating fixture workflows remain separate safety
tiers.

### Read-only Newman smoke tests

[`scripts/run-postman-smoke.py`](scripts/run-postman-smoke.py) creates a temporary
collection containing only `GET`, `HEAD`, and `OPTIONS` requests, then runs it with
Newman and produces a JUnit report. It excludes `pf-sheets` by default because its
committed URL is an external Web App; pass `--include-sheets` only when that call is
explicitly approved. Specific export-job status requests are also excluded by
default because job IDs are not stable fixtures; pass `--include-job-status` only
when a valid job ID is prepared. Specific payroll period IDs are also excluded by
default; pass `--include-payroll-period` only with a valid fixture ID. Specific
template IDs are also excluded by default; pass `--include-template` only with a
valid fixture ID. It never changes the committed collection.

Install Newman and run locally with a materialized environment:

```bash
npm install --global newman
python3 scripts/run-postman-smoke.py \
  --environment /tmp/postman-environment.json \
  --report test-results/postman-smoke.xml
```

Use `--include-sheets` only for an explicitly approved external Web App check.

[`scripts/generate-synthetic-payroll-pdf.py`](scripts/generate-synthetic-payroll-pdf.py)
generates the stable local PDF fixture used by the preview → JSON validation flow:

```bash
python3 scripts/generate-synthetic-payroll-pdf.py \
  --output /tmp/pf-synthetic-payroll.pdf
```

The fixture contains no real payroll data and is written to a temporary path.

The manual [`run-postman-smoke.yml`](.github/workflows/run-postman-smoke.yml)
workflow injects API keys into an ephemeral environment file and supports LOCAL or
GCP targets. It is intentionally read-only; imports, refreshes, creates, updates,
deletes, and stop-job requests require a separate safety boundary.

The [`run-postman-integration-local.yml`](.github/workflows/run-postman-integration-local.yml)
workflow is the disposable LOCAL gate. It checks out the PF services, boots a
PostgreSQL test database, runs OpenAPI coverage and read-only smoke tests, executes
synthetic mutations, resets the database on exit, and uploads JUnit/log artifacts.
It has no GCP, Neon, or production target. It also runs the loopback-only
`check-local-error-contracts.py` cases for invalid auth, missing resources, and
invalid import payloads.

### Local integration fixtures

[`scripts/run-postman-integration.py`](scripts/run-postman-integration.py) runs a
synthetic `pf-svc-income` employer → contract → template create/update workflow.
It rejects non-loopback URLs, requires an explicit local API key, generates unique
fixture identifiers, and always attempts cleanup in `finally`:

```bash
PF_INCOME_API_KEY="..." \
  python3 scripts/run-postman-integration.py
```

Use `--dry-run` to inspect the workflow without mutation. For the full disposable
local run, use:

```bash
PF_INCOME_API_KEY="..." \
  scripts/run-local-integration.sh
```

That wrapper backs up the local database, rebuilds it with `local-up-test`, runs the
integration workflow, and rebuilds the test database again on exit. It rejects
non-loopback targets. Never point either runner at GCP, Neon, or production.

## Structure

- `pf-ecosystem.postman_collection.json` — the collection itself (requests, folders per
  service, example bodies). Edit this directly.
- `pf-ecosystem.postman_environment.local.json` / `.gcp.json` — the two environments.
  Edit `*-url` values freely; `*-api-key` values are always overwritten at sync time
  (see above).

pf-sheets has no local/gcp split (one Apps Script deployment, one Web App URL) so its
two values (`pf_sheets_webapp_url`, `pf_sheets_api_key`) live as plain collection
variables instead of a third environment. `pf_sheets_webapp_url` is committed with its
real value (an Apps Script deployment URL isn't a secret by itself); `pf_sheets_api_key`
follows the same empty-in-git / injected-at-sync-time pattern as every other api-key.

### Collection ordering

Keep the collection deterministically ordered at every level: top-level service
folders, nested folders, subfolders, and requests must be sorted alphabetically by
`name`, using case-insensitive comparison. When adding or moving an item, reorder
its containing `item` array before committing so the JSON remains easy to review
and diffs do not depend on insertion history.

## Request selection policy

The committed Postman collection is an **operational contract catalog**, not a
negative-test or regression-test suite. Every request should represent a real
operation that a user or integration may intentionally perform.

Include:

- supported happy-path operations;
- supported modes that are useful in normal workflows, such as
  `mode="validate"` when validation-before-commit is an actual product
  capability;
- chained operational workflows, such as PDF preview followed by JSON import;
- CRUD operations for real resources;
- documented request/response examples using variables or clearly synthetic
  values where the operation is still intended to be executed.

Do not add requests whose primary purpose is to demonstrate failure or prove a
regression, including:

- natural-key conflicts;
- `404`, `409`, or `422` demonstrations;
- rollback-only scenarios;
- invalid or unresolved payloads;
- duplicate requests that differ only by a validation/error expectation;
- fake IDs or incomplete bodies that cannot represent an intentional operation.

Those cases belong in automated unit/integration tests and in the service's
API documentation when they define the public error contract. A request may
mention expected error statuses in its description when that information helps
explain the real operation, but the collection should not contain a standalone
request solely to trigger that error.

Before adding a request, ask: **would a real consumer intentionally send this
request to perform a supported operation, or is it only a test fixture?** If it
is only a fixture, keep it in tests instead.


Just edit the JSON by hand, or ask code-puppy to add it (e.g. "add a POST to
/payroll/import/json under the pf-svc-income folder, with this example body"). Keep requests
grouped in a top-level folder per service (`pf-rates`, `pf-svc-income`, `pf-sheets`),
matching each service's `docs/api.md`, so this collection never drifts further from
reality than those docs do.

## Chained requests (pf-svc-income: preview → import)

`Payroll/Preview/Preview a PDF payslip` and `Payroll/Import/Import
JSON (from last Preview)` requests are wired together with Postman scripts so you
never have to copy/paste a preview response by hand:

1. Run **Preview a PDF payslip** with one or more PDFs attached under the `files`
   form-data key. Its **Tests** script stashes the raw response array into the
   collection variable `last_pdf_preview_response`.
2. Run **Import JSON (from last Preview)**. Its **Pre-request Script** reads that
   variable, wraps it as `{ "mode": <import_json_mode>, "periods": [...] }`, and overwrites the
   request's raw JSON body with it before sending -- no manual editing needed.

`last_pdf_preview_response` is declared (empty) as a top-level collection variable
purely so it shows up in the Postman UI's variable list; never edit it by hand, and
never commit a real value into it (it's request/response scratch space, not config).

The request's `mode` comes from a second collection variable, `import_json_mode`,
committed with the value `"validate"`. To persist a chained import, set
`import_json_mode` to `"commit"` in the collection's variable list (Postman UI, or the
request-level/environment override) -- no script editing required. The default stays
`"validate"` on purpose: a chained import must never silently persist real payroll data
just because someone forgot to flip a variable back after testing a commit.

If you add more chained pairs like this in the future, follow the same shape: a
`Tests` script on the producer request writing one collection variable, a
`Pre-request Script` on the consumer request reading it and mutating
`pm.request.body.raw` -- keep the two requests next to each other in the JSON and name
the consumer `"<Thing> (from last <Producer>)"` so the relationship is obvious just
from the sidebar.

## Async export lifecycle

The `pf-rates` export folder contains assertions for the supported async contract:

```text
Trigger financial-data export (async)
  → job_id collection variable
  → Get export job status
  → terminal status
  → file_id on success or error_message on failure/cancellation
```

The trigger and status requests are intentionally not part of the default smoke
workflow. They can start a Google Drive export and therefore require an explicit
manual workflow, approved target, bounded date window, and cleanup/ownership plan.
The `Stop one export job` request remains a separate operator action and is never
invoked automatically.
