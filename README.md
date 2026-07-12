# Salesforce CI/CD Toolkit

GitHub Actions workflows for Salesforce DX projects: PR validation, dev/prod
deployment, static code analysis (Salesforce Code Analyzer), and an
AI-assisted auto-fix bot for Critical PMD/ESLint violations.

## What's included

| File | Purpose |
|---|---|
| `.github/workflows/validate.yml` | Dry-run deploy validation on every PR |
| `.github/workflows/deploy-dev.yml` | Deploy to a dev org on push to `develop` |
| `.github/workflows/deploy-prod.yml` | Deploy to production on `release-*` tags |
| `.github/workflows/code-scan.yml` | Run Salesforce Code Analyzer (PMD + ESLint), publish reports as artifacts |
| `.github/workflows/ai-fix.yml` | Pull the latest scan report, ask an LLM to fix Critical violations line-by-line, open a PR |
| `scripts/ai_fix.py` | Core auto-fix logic — batches violations, calls an OpenAI-compatible API, splices fixes back into source |
| `scripts/summarize_scan.py` | Renders a scan report as a Markdown table for the GitHub Actions job summary |

## Requirements

- A Salesforce DX project (`sfdx-project.json`, `force-app/`, `manifest/package.xml`)
- `sf` (Salesforce CLI) — installed automatically by the workflows
- An OpenAI-compatible LLM API (NVIDIA NIM, OpenAI, or any compatible endpoint) for `ai-fix.yml`

## Setup

1. Copy the `.github/workflows/` and `scripts/` directories into your Salesforce DX repo.
2. Copy `.env.example` to `.env` for local testing (never commit `.env`).
3. Add these as **GitHub Actions Secrets** (Settings → Secrets and variables → Actions):

   | Secret | Used by |
   |---|---|
   | `SF_AUTH_URL` | `validate.yml` |
   | `SF_AUTH_URL_DEV` | `deploy-dev.yml` |
   | `SF_AUTH_URL_PROD` | `deploy-prod.yml` |
   | `AI_API_KEY` | `ai-fix.yml` |

   Get a Salesforce auth URL with:
   ```
   sf org display --verbose --json --target-org <alias> | jq -r '.result.sfdxAuthUrl'
   ```

4. (Optional) Add repo **variables** `AI_BASE_URL` / `AI_MODEL` to point at a different
   OpenAI-compatible provider or model. Defaults to NVIDIA's `meta/llama-3.1-8b-instruct`.

5. Adjust the Apex test class(es) run by `validate.yml`/`deploy-prod.yml` — this repo defaults
   to `RunLocalTests`; tighten to `RunSpecifiedTests --tests <YourTestClass>` if you want faster
   PR validation.

## How ai-fix.yml works

1. Trigger manually (`workflow_dispatch`) with a `batch_size` (how many Critical violations to
   attempt) and `base_branch` (where the fix PR should land).
2. Downloads the most recent successful `code-scan.yml` artifact.
3. For each Critical violation, sends the single offending line + rule + message to the LLM and
   asks for a minimal replacement.
4. Re-runs the scanner after fixes, opens a PR with a before/after summary and token usage.

**This does not auto-merge.** All fixes land in a PR for human review — treat LLM-generated Apex
fixes as a first draft, not a trusted patch.

## Security notes

- Never commit `.env` — it's gitignored by default.
- Secrets are read from GitHub Actions Secrets at runtime, never hardcoded.
- The bot only modifies files under `force-app/` and only opens PRs — it never pushes directly to
  a protected branch and never auto-merges.

## License

MIT — see `LICENSE`.
