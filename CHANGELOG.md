# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-08

Initial public release.

### Added

- `validate.yml` — dry-run deploy validation on every pull request into `main`/`develop`, with a
  manual `workflow_dispatch` test-level selector.
- `deploy-dev.yml` — automatic deployment to a dev/sandbox org on push to `develop`.
- `deploy-prod.yml` — automatic deployment to production when a `release-*` tag is pushed.
- `code-scan.yml` — Salesforce Code Analyzer (PMD + ESLint) scan on push/PR, publishing
  JSON/HTML/CSV reports as a build artifact plus a Markdown job summary.
- `ai-fix.yml` — AI-assisted auto-fix bot that reads Critical violations from the latest scan
  and opens a human-reviewed PR with minimal, line-scoped fixes.
- `scripts/ai_fix.py` and `scripts/summarize_scan.py` supporting the scan and auto-fix workflows.

### Fixed

- Bumped the Node.js runtime to 22 in CI to resolve a Salesforce CLI / `undici` crash on the
  previous default version.

[1.0.0]: https://github.com/mikehsin/salesforce-cicd-toolkit/releases/tag/v1.0.0
