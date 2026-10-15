# Postman collection — pf ecosystem

Single Postman collection covering all `pf-*` services with an HTTP surface (`pf-rates`,
`pf-payroll`, and `pf-sheets` — `pf-db` has no HTTP API; it is DDL/migrations only),
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

> Postman Team/Enterprise plans also offer a native bidirectional Git sync (no custom
> workflow needed) -- if you upgrade later, you can drop `sync-postman.yml` and use that
> instead. This setup works on **any** Postman plan, including Free.

## Environments: LOCAL vs GCP

Both environments share the same four variable names (matching the collection's
requests): `pf-rates-url`, `pf-rates-api-key`, `pf-payroll-url`, `pf-payroll-api-key`.
Whichever environment is active in the Postman UI overrides the collection's own
(harmless localhost) defaults, so switching target just means picking a different
environment from the dropdown -- no request needs editing.

| | `pf-ecosystem.postman_environment.local.json` | `pf-ecosystem.postman_environment.gcp.json` |
|---|---|---|
| `*-url` values | `http://localhost:8001` / `:8000` | real Cloud Run URLs |
| `*-api-key` values in the committed file | always `""` | always `""` |
| Real key comes from | GitHub Secret `PF_RATES_API_KEY_LOCAL` / `PF_PAYROLL_API_KEY_LOCAL` | GitHub Secret `PF_RATES_API_KEY_GCP` / `PF_PAYROLL_API_KEY_GCP` |

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
   | `PF_PAYROLL_API_KEY_LOCAL` | pf-payroll dev API key (from `modules/pf-payroll/.env`) |
   | `PF_RATES_API_KEY_GCP` | pf-rates production API key (GCP Secret Manager, secret `PF_RATES_API_KEY`) |
   | `PF_PAYROLL_API_KEY_GCP` | pf-payroll production API key (GCP Secret Manager, secret `PF_PAYROLL_API_KEY`) |
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
/payroll/import/json under the pf-payroll folder, with this example body"). Keep requests
grouped in a top-level folder per service (`pf-rates`, `pf-payroll`, `pf-sheets`),
matching each service's `docs/api.md`, so this collection never drifts further from
reality than those docs do.

## Chained requests (pf-payroll: preview → import)

`Periods/Preview/Preview a PDF payslip` and `Periods/Import/Import
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
