# Approved `main` branch ruleset configuration

Jorge authorized this single-maintainer configuration after the M0/M0.1 squash merge.
The exact required check names were verified from pull request #1 as `quality (3.12)` and
`quality (3.13)`. Record the live ruleset identifier and API receipt after application;
do not add a documentation-only commit merely to chase a workflow run produced by that
same commit.

## Live ruleset receipt

- Ruleset ID: `21658925`; enforcement status: active.
- Target branch: `refs/heads/main`.
- Pull requests require zero approving reviews; review-conversation resolution is required.
- Required checks currently visible through the supported read path: `quality (3.12)`
  and `quality (3.13)`; strict/up-to-date is `true`.
- Deletion and force pushes are blocked.
- Bypass actors: none.
- Signed commits, CODEOWNERS, and merge queue rules are absent.
- `require_extra_approval_for_unattributed_changes` is explicitly `false`.

## Approved ruleset

- Target branch: `main`; enforcement status: active (live ref: `refs/heads/main`).
- Require changes through pull requests, with **zero required approving reviews** while
  this remains a single-maintainer user-owned repository.
- Require resolution of review conversations.
- Require `quality (3.12)` and `quality (3.13)` and require the branch to be up to date
  before merge.
- Block force pushes and deletion of `main`.
- Do not require signed commits, CODEOWNERS, a merge queue, or extra approval for
  unattributed changes.
- Do not configure bypass actors.

## M1-03B.1 outstanding metadata action

Jorge authorized adding only `windows-acquisition-safety` as the third required
check. The selected GitHub integration exposes no ruleset-write operation, and the
available browser session is not authenticated to repository settings (GitHub
returns 404 for the private ruleset page). The credential boundary prohibits
inspecting helpers/tokens or constructing a private API authorization header.
Therefore the live ruleset remains unchanged pending an authenticated owner action.
This is a platform-permission blocker, not a reason to rename or weaken CI. The
exact pending action is:

1. open ruleset `21658925` (`Protect main research foundation`);
2. add exactly `windows-acquisition-safety` to required status checks;
3. save without changing any other property; and
4. verify the exact three contexts and strict/up-to-date behavior.

This file records the current live receipt, the approved target configuration, and
the single pending permission-blocked correction.
