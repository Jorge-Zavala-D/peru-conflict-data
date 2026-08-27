# Security and data handling

Never commit API keys, OAuth tokens, Dropbox/GitHub credentials, cookies, temporary
links, `.env`, private keys, raw reports, administrative workbooks, respondent-level
data, or generated databases. Use least-privilege connectors and review third-party
MCP/plugin permissions.

Agents must never invoke `git credential fill` or otherwise query or inspect OS
credential helpers, keychains, password managers, environment secrets, stored
OAuth/API tokens, or similar credential stores. Agents must never extract discovered
user secrets into process variables or manually construct an Authorization header to
circumvent an app or connector permission denial. Normal `git push` and `git fetch` through preconfigured Git
authentication are allowed when the Git action is authorized because they do not
expose credentials to the agent. If an integration cannot perform an explicitly
authorized GitHub action, use an authenticated browser UI only after explicit user
confirmation when available, or stop and ask the user. Always respect least
privilege and the selected integration's permission boundary.

Model calls require documented data-use authority and minimal source segments.
Report suspected credential or restricted-data exposure privately to the repository
owner; do not open a public issue containing the material.
