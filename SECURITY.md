# Security policy

Recon is a private, single-user, local-only app. It holds the user's study notes, which are treated as private data.

## Supported versions

Only the latest release on `main` is supported. Fixes are released as `v0.<phase>.<patch>` before v1, and as normal SemVer patches after.

## Reporting a problem

The repository is private. Raise a GitHub issue with the `bug` template and the `area:security` label, or for an audit finding, the `audit-finding` template. Don't paste real notes, flags, tokens or logs into an issue; describe them.

Severity follows the audit scale: Critical and High are fixed before anything else ships; Medium before the next phase gate; Low is fixed or left open with a reason.

## Design

The threat model, assets, entry points and mitigations are in [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md). The rules it relies on are in CLAUDE.md (Hard rules; Security and privacy). In short:

- At runtime Recon talks only to Ollama on loopback. A test fails if any module other than `services/ollama.py` imports networking code.
- Anything shaped like a CTF flag is stripped before it's stored.
- Model output is untrusted data: schema-validated, sanitised before rendering, and reviewed by the user before Apply.
- Logs never contain note content; data folders are `0700`, files `0600`.
- Secrets are scanned by gitleaks on every commit and in CI.
