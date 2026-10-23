<!-- Title: Conventional Commits, e.g. "feat(capture): room session panel" -->

## What and why

<!-- What changed and why. Mention any decision Tyler should know about. -->

Closes #

## How it was tested

<!-- Tests added or changed; manual checks; commands run. -->

## Screenshots

<!-- Required for UI changes. Delete for non-UI work. -->

## Checklist

- [ ] Tests added or updated alongside the code
- [ ] Coverage gates hold (90% engine/db/revision/services, 80% overall)
- [ ] `uv run pre-commit run --all-files` passes
- [ ] Hard rules in CLAUDE.md still hold (flags, Apply-only vault writes, raw notes, markers, backups)
- [ ] No note content, prompts or model output logged to `app.log`
- [ ] Docs updated (README, ARCHITECTURE, THREAT_MODEL, ADR) where affected
- [ ] `CHANGELOG.md` Unreleased section updated
- [ ] Task ticked in `docs/BUILD_PLAN.md`
- [ ] No new dependency, or the reason for it is given above
- [ ] Self-reviewed with `gh pr diff`
