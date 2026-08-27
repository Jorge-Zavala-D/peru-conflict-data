# Proposed `main` branch protection (not applied)

The repository currently reports `main` as unprotected. Do not apply these settings
without Jorge's explicit repository-administrator approval. Confirm the exact check names
from the first M0.1 pull request before saving a rule.

## Recommended ruleset

- Target branch: `main`.
- Require a pull request before merging; require at least one approving review, dismiss
  stale approvals after new commits, and require resolution of review conversations.
- Require the repository quality checks for both supported Python versions (the matrix
  checks currently appear as `quality (3.12)` and `quality (3.13)`; verify their exact
  names in GitHub after the PR run).
- Require branches to be up to date before merge if the repository is small enough for the
  queue cost; otherwise use merge queue after a measured need.
- Block force-push and branch deletion on `main`; allow ordinary pushes only through the
  pull-request rule.
- Keep the ruleset in “evaluate” mode for a short dry period if GitHub exposes that mode,
  then enforce after review. Do not require signed commits or CODEOWNERS until ownership
  and signing workflows are explicitly agreed.

This proposal is a governance recommendation only. No GitHub-admin setting, ruleset,
branch protection, merge queue, or auto-merge configuration was changed during M0.1.
