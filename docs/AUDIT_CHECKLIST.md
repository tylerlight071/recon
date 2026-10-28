# Audit checklist

Used by the independent audit at every phase gate (scope: that phase's changes) and by the release audit (scope: everything). The auditor is a fresh agent that didn't write the code. Findings go to `docs/audits/phase-N.md` (or `release.md`), one per heading, each with:

- **ID** (`F-01`…), **severity** (Critical / High / Medium / Low), **area** (from the list below), **location** (`file:line`), **finding**, **fix**.

Severity guide: **Critical** breaks a hard rule, loses or leaks data, or stops the app starting. **High** blocks a main flow or a gate's acceptance check. **Medium** is a real defect with a workaround, a missing test for a risky path, or a standards gate not met. **Low** is minor.

Critical, High and Medium are fixed before the gate. Every finding becomes an issue (`audit-finding` template).

## 1. Correctness

- [ ] Behaviour matches SPEC.md and the phase's acceptance checks in BUILD_PLAN.md.
- [ ] Edge cases: empty input, very long input, Unicode, zero tasks, last task, rapid repeated actions.
- [ ] Concurrency: worker threads don't touch QML objects; one writer connection; queue order holds.
- [ ] Cancellation leaves nothing half-written.

## 2. Hard rules (CLAUDE.md)

- [ ] 1 No contact with tryhackme.com; no network outside `services/ollama.py`; loopback only.
- [ ] 2 Flags stripped before db, vault, cards, backups, logs; "Not a flag, keep it" restores one string only.
- [ ] 3 Only `stage.apply()` writes into the vault.
- [ ] 4 `00 Raw notes/` never changed after writing; the user's text never edited.
- [ ] 5 Generated content labelled.
- [ ] 6 Backups before overwrite; last 20 runs kept.
- [ ] 7 Autosave ≤ 1 s.
- [ ] 8 Edits only between `%% recon:start %%` / `%% recon:end %%` markers.
- [ ] 9 Apply aborts on hash mismatch.
- [ ] 10 One room processes at a time.
- [ ] Each hard rule touched by this phase has a test that fails when the rule is broken.

## 3. Security and privacy (THREAT_MODEL.md)

- [ ] Every threat touched by this phase still has its mitigation and test.
- [ ] Model output validated, length-limited and sanitised before rendering.
- [ ] Paths built from names are sanitised and checked to stay inside their root.
- [ ] Permissions: folders `0700`, files `0600`.
- [ ] No note content, prompts, transcripts or model output in `app.log`; log messages are literals.
- [ ] Subprocesses: argument lists, allowlisted binaries by full path, no `shell=True`.
- [ ] Images re-encoded and stripped of metadata.
- [ ] No secrets or real data in the diff; gitleaks clean.
- [ ] Dependency audit clean; each new dependency justified in its PR; licences compatible.
- [ ] THREAT_MODEL.md updated for new entry points.

## 4. Error handling

- [ ] Errors derive from `ReconError`; no bare `except`; `except Exception` only at thread/process boundaries.
- [ ] Every user-visible error has plain copy and a next step; no stack traces in the UI.
- [ ] Ollama down, model missing, vault missing, disk full and conflict paths are handled and tested.

## 5. Tests and coverage

- [ ] Branch coverage ≥ 90% for engine, db, revision, services; ≥ 80% overall; not lower than before without a written reason.
- [ ] Mutation score ≥ 85% on flags_filter, stage, sanitising, factcheck; survivors killed or explained.
- [ ] Property tests where CLAUDE.md requires them; golden files for every note type touched.
- [ ] Migration tests for every new schema version; crash tests for save and Apply paths.
- [ ] Tests test behaviour, not implementation details; no sleeps or flaky timing.

## 6. Engineering standards

- [ ] `mypy --strict` clean; every `Any`, `cast` or `type: ignore` has a reason.
- [ ] Ruff clean with no new blanket ignores.
- [ ] Functions small (≤ ~50 lines, ≤ 3 nesting levels) or justified.
- [ ] Dependencies injected; no global clients.
- [ ] Pydantic at every boundary.
- [ ] No dead code, commented-out code or untracked TODOs.
- [ ] Atomic writes; parameterised SQL; WAL; `foreign_keys=ON`.

## 7. Performance budgets

- [ ] Launch to Home < 2 s; keystroke to saved < 1 s; task switch < 100 ms; 60 fps panel animations; idle memory < 300 MB with no models loaded. Measured, with numbers recorded.
- [ ] No blocking work on the UI thread.

## 8. Accessibility

- [ ] Every control reachable and usable by keyboard with a visible focus ring.
- [ ] Every interactive item has `Accessible.name` and `Accessible.role`.
- [ ] Text contrast ≥ 4.5:1 (test passes); reduce motion makes durations 0.

## 9. ADHD rules

- [ ] Exactly one accent button per screen.
- [ ] Only what's needed now; nothing that can be lost; Undo with 10 s toast for deletions.
- [ ] Same thing, same place: buttons and shortcuts consistent.
- [ ] No shame: no red, no overdue counts, no broken-streak copy; time never shown as a threat.
- [ ] Calm by default: no sounds or pop-ups unless enabled.

## 10. Copy

- [ ] British English, plain words, short sentences.
- [ ] Says what happened and what to do next; never blames.
- [ ] No emoji in UI.

## 11. Docs

- [ ] README, ARCHITECTURE, THREAT_MODEL, ADRs and CHANGELOG updated with the change.
- [ ] BUILD_PLAN tasks ticked in the PR that completed them.
