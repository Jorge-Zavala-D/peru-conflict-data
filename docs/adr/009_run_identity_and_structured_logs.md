# ADR 009: Reproducible run identity and JSON Lines logs

Status: accepted, 2026-08-27.

## Context

Scientific results cannot be audited from a timestamp and code version alone.

## Decision

Every run captures Git commit/dirty state, collision-safe config/schema/lock/input hashes, parser versions, Python/platform/package identity, and model/prompt metadata when used. Logs are one standards-compliant JSON object per line, serialize non-finite diagnostic floats as explicit strings, and are written only to caller-approved derived destinations.

## Consequences

Run metadata is a first-class artifact. M0 provides capture/formatting but does not execute corpus pipelines.
