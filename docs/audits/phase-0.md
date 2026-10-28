# Phase 0 audit

- **Date:** 2026-10-24
- **Scope:** everything on `main` at commit `6caf0cb` (PRs #8–#18 plus the direct setup commits): `recon/`, `scripts/`, `packaging/recon-launch`, `tests/`, `.github/`, `.pre-commit-config.yaml`, `pyproject.toml`, `uv.lock` and the docs.
- **Auditor:** independent agent; did not write the code.
- **Checklist:** `docs/AUDIT_CHECKLIST.md`. Phase 0 has no UI, database, vault or model code, so checklist areas 7–10 (performance, accessibility, ADHD rules, copy) apply only to the error copy in `recon/errors.py`.

## How the audit was done

Read every file in scope, plus CLAUDE.md, BUILD_PLAN, SPEC (relevant parts), THREAT_MODEL, ARCHITECTURE, ADRs 0001–0003 and `docs/environment.md`. Reproduced each finding with a script in the session scratchpad, not by reading alone. No repository file was changed apart from this report.

| Command | Result |
| --- | --- |
| `uv run pytest -m "not ollama and not gpu" --cov --cov-branch` | **187 passed**, 8 deselected, 2.2 s. Coverage of `recon/`: **100%** (122 statements, 18 branches) |
| `uv run coverage json` + `uv run python scripts/coverage_gates.py` | `per-package coverage gates: OK`, exit 0. All four gated packages (`engine/`, `db/`, `revision/`, `services/`) have 0 measurable statements, so no gate was actually checked (see F-05) |
| Same tests with `--cov=scripts` added (separate data file) | `scripts/` total 85%: `check_env.py` 99%, `kwin_rule.py` 38%, `whisper.py` 70%, `structured.py` 72% |
| `uv run mypy` | Success: no issues in 24 source files |
| `uv run ruff check .` / `uv run ruff format --check .` | All checks passed / 56 files already formatted |
| `uv lock --check` | OK |
| `uv audit --preview-features audit-command --frozen` | No known vulnerabilities in 74 packages. `uv audit` covers optional extras by default (it only has `--no-extra`), so the `voice` extra is included |
| `gh run list` | CI green on `main` at `6caf0cb` |
| `gh issue list`, milestones API | Phase 0 issues all closed; **Phase 1 milestone has 0 issues** |
| Pre-push hook, scratch repo with a bare remote and pre-commit 4.7.0 | Single push to `main`: blocked. `git push origin <existing-branch> main`: **main updated**. `git push --all`: **main updated**. `git push origin --delete main`: **deleted** (F-02) |
| Logging probes against `configure_logging` | Content reached `app.log` by 3 paths (F-03) |
| Network-detector probes using the test's own `_imported_modules`/`_is_network` | 16 of 17 bypass forms not detected (F-04) |
| `check_env` probes with a fake runner | Reports "Ollama service: OK" when `ollama --version` times out or errors; crashes on empty `nvidia-smi` output (F-07, F-16) |
| Headless QML timing test, 12 runs with 32 busy loops on 16 cores | 12/12 passed |

## Summary

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 1 |
| Medium | 6 |
| Low | 11 |

No hard rule is broken by the code as it stands: there's no app code yet that touches notes, flags, the vault or the network. The Medium findings are mostly guards (network test, log redaction, coverage gate, pre-push hook) that pass while the thing they guard could still be broken.

---

## F-01 — Gate 0 step 4 can't be done: no Phase 1 issues exist

- **Severity:** High
- **Area:** Docs
- **Location:** `docs/BUILD_PLAN.md:77`
- **Finding:** Gate 0's manual test step 4 asks for a review of "the Phase 1 issues" on GitHub. The Phase 1 milestone has 0 open and 0 closed issues (`gh api repos/tylerlight071/recon/milestones`). So that gate step can't be done as written. The plan also contradicts itself: line 8 says issues are created "at the start of each phase", while Gate 0 expects them before Phase 1 starts.
- **Fix:** Before the Gate 0 handover, create the Phase 1 issues (tasks 1.1–1.15, `task` template, labels, `Phase 1` milestone). Or, if they should only be created once the gate is approved, change step 4 to drop "the Phase 1 issues". Either way, make lines 8 and 77 agree.

## F-02 — The pre-push hook (main's only protection) misses deletes and multi-ref pushes

- **Severity:** Medium
- **Area:** Security and privacy
- **Location:** `scripts/hooks/no-push-to-main:2-5`; `.pre-commit-config.yaml:73-79`
- **Finding:** The hook checks only `PRE_COMMIT_REMOTE_BRANCH`. pre-commit 4.7.0 (`pre_commit/commands/hook_impl.py`, `_pre_push_ns`) sets that from the **first** ref in git's push list that has commits, and skips the hooks altogether when every ref is a deletion. Reproduced in a scratch repo:
  - `git push origin aaa main`, where `aaa` already exists on the remote: git lists `aaa` first, the hook sees `refs/heads/aaa`, and `main` is updated. Every branch name the conventions allow (`build/`, `chore/`, `ci/`, `docs/`, `feat/`, `fix/`, `perf/`, `refactor/`, `test/`) sorts before `main`.
  - `git push --all origin`: `main` is updated.
  - `git push origin --delete main`: the hooks don't run and `main` is deleted. The hook's own comment says it "refuse[s] any push that updates or deletes main". GitHub normally refuses to delete the default branch, which limits this case.

  On GitHub Free this hook is the only thing standing in for the ruleset (CLAUDE.md, Branch protection). The single-ref case the PR #8 test covered does work.
- **Fix:** Use a hook that reads git's pre-push stdin itself and rejects any line whose remote ref is `refs/heads/main`, deletions included. For example, install a native `.git/hooks/pre-push` as pre-commit's legacy hook (pre-commit passes stdin through to `pre-push.legacy`), or ship it as a `scripts/install_hooks` step. Add a test that runs the hook against the multi-ref, `--all` and delete stdin forms. Correct the comment, and ARCHITECTURE.md:68, to say what the hook really covers.

## F-03 — Log redaction has holes: content as the message, cached exception text, logger names

- **Severity:** Medium
- **Area:** Security and privacy
- **Location:** `recon/logging_setup.py:58-67` (filter), `recon/logging_setup.py:70-87` (formatter), `recon/logging_setup.py:32`; `tests/test_logging.py:129-152`
- **Finding:** Reproduced with runtime-built strings (so the traceback's source lines couldn't cause false positives). Three ways content reaches `app.log`:
  1. **Content as the message.** `RedactingFilter` trusts any `str` `record.msg`, so `log.info(note_text)` writes the note verbatim. The only guard is the static test, and that test only looks at calls whose receiver is a bare name in `{log, logger, logging, _log, _logger}`. `self.log.info(text)`, `self._logger.info(text)`, `LOGGER.info(text)` and `logging.getLogger(__name__).warning(text)` are all skipped (checked by feeding them to `_logging_calls`). There are no logging calls in `recon/` yet, so the test passes without checking anything. Unlike the network test, it has no self-test proving the detector catches a violation. A `LoggerAdapter.process()` that adds content to `msg` gets past both guards.
  2. **Cached exception text.** `logging.Formatter.format` reuses `record.exc_text` if an earlier handler set it. `RedactingFormatter` only overrides `formatException`. Any handler that formats the record before Recon's (one on a child logger such as `recon.engine.x`, or one added to `recon` before `configure_logging`) caches the full message, e.g. `ValueError: <note text>`, and `app.log` then gets it unredacted.
  3. **Logger names.** `%(name)s` is logged as-is, so `getLogger(f"recon.room.{name}")` writes the room name.

  ARCHITECTURE.md:56 and THREAT_MODEL T7 say these guards make content in `app.log` impossible. They don't yet.
- **Fix:** (1) Widen `_logging_calls` to every `ast.Call` whose `func` is an `Attribute` with a logging method name, whatever the receiver (allowlist known non-logging receivers if needed). Add a detector self-test with the forms above. Also ban `LoggerAdapter` subclasses in `recon/`, or test them. (2) Override `RedactingFormatter.format` to set `record.exc_text = None` before calling `super().format`, so the redacted text is always rebuilt, and add a test with a second handler on a child logger. (3) Add a test that every `getLogger` argument in `recon/` is `__name__` or a literal, or have the formatter print only names under `recon.` that match a module path.

## F-04 — The network-import test is easy to get round and can't see QML or libraries that use the network indirectly

- **Severity:** Medium
- **Area:** Hard rules
- **Location:** `tests/test_network_imports.py:8-22`, `:25-33`, `:64-72`
- **Finding:** This test is hard rule 1's only automated guard (THREAT_MODEL T9, T17). Running the test's own `_imported_modules`/`_is_network` over sample sources, these all passed undetected:
  - `from importlib import import_module; import_module("socket")`, and `builtins.__import__ ("socket")` (the text check needs `__import__(` with no space before the bracket).
  - stdlib network clients not on the list: `asyncio` (`open_connection`), `smtplib`, `ftplib`, `xmlrpc.client`, `socketserver`, `multiprocessing.connection`.
  - `webbrowser.open(...)`, `subprocess` running `curl`, and `PySide6.QtGui.QDesktopServices.openUrl`, all of which can open tryhackme.com.
  - `PySide6.QtWebEngineCore` and `PySide6.QtHttpServer`.
  - Libraries that use the network themselves: `faster_whisper` and `huggingface_hub`. `WhisperModel("large-v3-turbo")` downloads from Hugging Face at runtime unless `local_files_only=True` (README.md:84 says "first voice use").
  - **QML**: only `*.py` files are scanned. Recon's UI is QML, where `XMLHttpRequest`, `Image { source: "https://…" }`, `FontLoader` and `Qt.openUrlExternally` reach the network through the engine's network access manager, with no Python import at all.
- **Fix:** Add the stdlib modules above, `webbrowser`, `PySide6.QtWebEngine*` and `PySide6.QtHttpServer` to the banned list. Flag every `import_module`/`__import__`/`importlib` use through the AST, not by searching the text. Allow `faster_whisper` only in `services/whisper.py`, and add a test that its model loads with `local_files_only=True` (also set `HF_HUB_OFFLINE=1` in `recon-launch` once the model has been fetched in a setup step). Add a QML scan for `http:`/`https:`, `XMLHttpRequest` and `openUrlExternally`, and in `app.py` install a `QQmlNetworkAccessManagerFactory` that refuses every scheme except `file:` and `qrc:`, allowlisted in the test as its one necessary QtNetwork import. Make `subprocess` allowed only in modules on a list, matching CLAUDE.md's subprocess rule.

## F-05 — The per-package coverage gate passes when it has nothing to measure

- **Severity:** Medium
- **Area:** Tests and coverage
- **Location:** `scripts/coverage_gates.py:35`, `:39`, `:57`, `:79`
- **Finding:** `package_percent` returns `None` when no file matches a prefix or all matching files have 0 statements, and `check` then skips that package. As a result:
  - Today all four gated packages are empty, and CI prints `per-package coverage gates: OK` without checking any of them. Nothing in the output says so.
  - Matching is by `startswith("recon/engine/")` on the report's keys. If the keys are ever absolute (running from another directory, `coverage combine` without `relative_files`, a changed `source`), every gate silently passes. Reproduced: `{"/home/runner/work/recon/recon/recon/db/x.py": 0% of 100 lines}` and `{"./recon/db/x.py": 0%}` both give `[]`.
  - The script that enforces the gate isn't measured itself (`source = ["recon"]`, `pyproject.toml:102`).
- **Fix:** Normalise keys (`Path(name).resolve().relative_to(repo_root)`), and fail when a gated package's folder contains `.py` files with statements but no report entry matched. Print one line per package (`recon/engine/: 93.4% (gate 90%)` or `recon/engine/: no code yet`), so "OK" means something. Set `relative_files = true` under `[tool.coverage.run]`. Add tests for absolute and `./` keys.

## F-06 — The first launch after a plain `uv sync` (or on a fresh clone) has no CUDA libraries on the loader path

- **Severity:** Medium
- **Area:** Correctness
- **Location:** `packaging/recon-launch:27-33`, `:44`; `docs/adr/0002-voice-runtime.md:34`
- **Finding:** The launcher builds `LD_LIBRARY_PATH` by globbing `.venv/.../nvidia/*/lib` **before** it runs `uv run --frozen --extra voice`. `uv sync` without `--extra voice` removes those wheels (it's an exact sync, as ADR 0002 says), and CLAUDE.md's Commands section says to run plain `uv sync` and then `./packaging/recon-launch`. On the next launch the glob finds nothing, `uv run` (an inexact sync by default, per `uv help run`) reinstalls the voice extra, and Python starts with no cuBLAS on the loader path. Whisper then fails with "libcublas.so.12 is not found" for that whole session. The next launch works. ADR 0002 says the launcher "restores them". It does reinstall them, but too late for the launch that did it. The launcher tests use a fake repo that already has the lib folders, so they don't cover this.
- **Fix:** Before the glob, run `"$uv_bin" sync --frozen --extra voice --inexact` (or `"$uv_bin" run --frozen --extra voice true`), so the wheels are in place before the paths are computed. Add a launcher test where the fake `uv` creates the `nvidia/*/lib` folders on its first call, and check that `LD_LIBRARY_PATH` still includes them. Correct ADR 0002's consequence line.

## F-07 — `check_env` says the Ollama service is OK when `ollama --version` times out or errors

- **Severity:** Medium
- **Area:** Correctness
- **Location:** `scripts/check_env.py:238-255` (line 246)
- **Finding:** When systemd doesn't report `active`, the check passes as long as `ollama --version` returned anything that doesn't contain "could not connect". A hung server gives the runner's timeout result `Output(124, "", "ollama timed out")`, and any other failure (non-zero exit, `Error: …`) also passes. Both were reproduced as `Status.OK, "A server is answering, though not via the systemd service."` The exit code isn't checked. This is the case task 0.5 hit (a failing service). `check_ollama_gpu` reads journal lines from the whole boot, so it can still report "Using CUDA" from an earlier successful start, and the report reads all-green.
- **Fix:** Require `version.code == 0` and a parsed server version (`ollama version is X` without the "client version" warning) before reporting OK. Treat code 124 as "Ollama didn't answer within 15 s". Add tests for timeout and non-zero exit. Optionally, only use GPU journal lines from after the service's current `ActiveEnterTimestamp`.

---

## F-08 — `scripts/` is outside coverage, so the reported 100% leaves out most of the tested code

- **Severity:** Low
- **Area:** Tests and coverage
- **Location:** `pyproject.toml:100-102`
- **Finding:** CI's "Total coverage: 100.00%" covers 122 statements in `recon/`. The 858 statements in `scripts/` (85% when measured) aren't counted, including `coverage_gates.py` (which enforces the gates) and `kwin_rule.py` at 38% (it writes the user's KDE config). For one-off smoke scripts that's acceptable. For `check_env.py` and `coverage_gates.py`, which stay in use, it isn't.
- **Fix:** Measure `scripts/check_env.py` and `scripts/coverage_gates.py` (add them to `source` or a separate report). Leave `scripts/smoke/` out, saying why in `pyproject.toml`.

## F-09 — The documented "fast tests" command runs the real GPU Whisper test

- **Severity:** Low
- **Area:** Docs
- **Location:** `README.md:64`, `CLAUDE.md:356`
- **Finding:** `uv run pytest -m "not ollama"` collects `test_real_whisper_on_cuda_through_the_launcher` (marked `gpu` and `slow`, 600 s timeout, downloads about 1.6 GB from Hugging Face on the first run). CI and pre-commit use `not ollama and not gpu`, but the docs don't.
- **Fix:** Change both lines to `uv run pytest -m "not ollama and not gpu"`.

## F-10 — The audit-finding issue template has no "Engineering standards" area

- **Severity:** Low
- **Area:** Docs
- **Location:** `.github/ISSUE_TEMPLATE/audit-finding.yml:24-35`
- **Finding:** The Area dropdown lists 10 of the checklist's 11 areas. "Engineering standards" (checklist §6) is missing, so findings in that area can't be filed accurately.
- **Fix:** Add `Engineering standards` between "Tests and coverage" and "Performance budgets".

## F-11 — ADR 0001 still names QtDBus for the shortcut portal

- **Severity:** Low
- **Area:** Docs
- **Location:** `docs/adr/0001-stack.md:21`, `:29`
- **Finding:** ADR 0003 replaced QtDBus with jeepney for the GlobalShortcuts portal, and CLAUDE.md was updated. ADR 0001's decision table and reasons still say the portal goes over QtDBus, with no note that this has changed.
- **Fix:** Add "Partly superseded by ADR 0003 (portal via jeepney)" to ADR 0001's status and on line 21.

## F-12 — README's network claims don't quite match

- **Severity:** Low
- **Area:** Docs
- **Location:** `README.md:5`, `README.md:84`, README "Check your machine"
- **Finding:** Line 5 says the only service Recon talks to at runtime is Ollama, and line 84 says the Whisper model downloads on "first voice use", which is at runtime. CLAUDE.md allows the Whisper download as a one-off setup download, but nothing makes it happen at setup. The model is also fetched by name without a pinned Hugging Face revision (`scripts/smoke/whisper.py:121`). README also says `check_env` "makes no network calls", but `ollama --version` queries the local server over HTTP on loopback.
- **Fix:** In Phase 5, fetch the model in an explicit setup step pinned to a revision, then load it with `local_files_only=True` (see F-04), and update line 84. Change "makes no network calls" to "makes no network calls beyond asking local Ollama for its version".

## F-13 — `Any` and `type: ignore` without reasons; the ignores in tests are never type-checked

- **Severity:** Low
- **Area:** Engineering standards
- **Location:** `scripts/smoke/shortcut.py:154`; `tests/test_smoke_desktop.py:113`, `:120`, `:128`, `:146`; `tests/test_smoke_desktop.py:96`, `:102`, `:105`
- **Finding:** `tuple[Any, ...]` at shortcut.py:154 has no reason comment. CLAUDE.md asks for one; line 46's `Variant` docstring explains its own `Any`. The four `# type: ignore[arg-type]` in tests have no reason, and they do nothing because mypy's `files` is `["recon", "scripts"]`. The `noqa: ARG002` lines have no reason either.
- **Fix:** Add one-line reasons. Either type-check `tests/`, or make `_FakeConnection` satisfy a `Protocol` that `PortalSession` accepts, so the ignores aren't needed.

## F-14 — `ensure_private_dir` doesn't re-check after chmod, and an existing `app.log` keeps its mode

- **Severity:** Low
- **Area:** Security and privacy
- **Location:** `recon/paths.py:62-76`; `recon/logging_setup.py:90-104`
- **Finding:** If `chmod` "succeeds" without effect (filesystems that ignore Unix modes, some FUSE/NTFS mounts, a folder owned by someone else with ACLs), no error is raised and the folder stays open. `private_opener` only sets the mode on new files, so an `app.log` created earlier with 0644 stays 0644. CLAUDE.md asks for files to be "checked at launch"; that's Phase 1 work, but nothing exists for it yet.
- **Fix:** Re-`stat` after `chmod` and raise `InsecurePermissionsError` if the mode is still wrong. Add `ensure_private_file()` (fix or raise), and call it on `app.log` in `configure_logging`. Test both.

## F-15 — CI cancels runs on `main`, and the release workflow trusts any version tag

- **Severity:** Low
- **Area:** Security and privacy
- **Location:** `.github/workflows/ci.yml:13`; `.github/workflows/release.yml:5`, `:30-34`
- **Finding:** `cancel-in-progress: true` applies to `refs/heads/main` too. Two quick merges cancel the first merge's run, so that commit never gets a CI result ("main always green" can't be shown for it). `release.yml` publishes a Release for any `v*.*.*` tag, on any commit, without checking that the commit is on `main` or that CI passed there. The version is also used as an awk regex, so its dots match any character. Neither is exploitable in a private single-user repo.
- **Fix:** `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}`. In the release job, check `git merge-base --is-ancestor "$GITHUB_SHA" origin/main` (with `fetch-depth: 0`), and either check the CI result for that SHA through `gh api` or require the tag to point at a commit whose CI passed. Escape the dots in the version, or compare with `index()`.

## F-16 — `check_env` crashes or checks the wrong place in some edge cases

- **Severity:** Low
- **Area:** Correctness
- **Location:** `scripts/check_env.py:307`, `:115-125`, `:475`, `:39`
- **Finding:** Empty `nvidia-smi` output with exit 0 raises `IndexError` (reproduced), and a short CSV line raises `ValueError`. Either aborts the whole report. `run_command` doesn't catch `OSError` (a binary found but not executable) or `UnicodeDecodeError`. When no `OLLAMA_MODELS` is set, the models folder defaults to `~tyler/.ollama/models`, but a system service runs as user `ollama` with its own home, so free space is checked on the wrong filesystem. `busctl` is on the allowlist but never used.
- **Fix:** Guard the `nvidia-smi` parse (fewer than 4 fields means ATTENTION, "couldn't read nvidia-smi"). Catch `OSError` in `run_command` and return `Output(126, …)`. Use `errors="replace"`. Read the service user's home from `systemctl show ollama -p User`, or say "models folder unknown". Remove `busctl`.

## F-17 — The fast-test hook doesn't run for shell or QML changes

- **Severity:** Low
- **Area:** Tests and coverage
- **Location:** `.pre-commit-config.yaml:62`
- **Finding:** `pytest-fast` runs only for `python, pyi, toml, json, yaml, markdown` files. A commit that changes only `packaging/recon-launch` or a `.qml` file skips the launcher and QML tests that cover them. CI still runs them.
- **Fix:** Add `shell` and a `files:` pattern for `\.qml$` (or use `always_run: true`, since the suite takes about 2 s).

## F-18 — The headless QML test depends on wall-clock timing in CI

- **Severity:** Low
- **Area:** Tests and coverage
- **Location:** `tests/test_smoke_qml.py:83-92`; `scripts/smoke/qml_window.py:28-30`
- **Finding:** `test_headless_window_renders_inter_and_animates` runs in CI and needs the 200 ms animation to finish in 180–400 ms with at least 8 frames under the software renderer. The checklist rules out flaky timing. It passed 12 of 12 times here with 2× CPU oversubscription on 16 cores, but CI runners have 4 vCPUs and noisy neighbours.
- **Fix:** In CI (`QT_QPA_PLATFORM=offscreen`), assert only that the animation finished and the screenshot rendered in Inter. Keep the timing and frame thresholds for the on-desktop run (`--expect-platform wayland`), or mark the timing part `slow`.

---

## Checked and fine

- **Subprocesses:** `check_env.run_command` and `kwin_rule._run` use an allowlist, resolve by full path on a fixed `PATH`, pass argument lists (no `shell=True`), set timeouts and use a minimal environment. `check_env` runs only read-only commands. Tests cover allowlist refusal, a missing program and timeouts.
- **`recon-launch` shell safety:** every expansion is quoted. `set -eu` and the `[ … ] &&` lines in the loops don't abort early. An empty or unset inherited `LD_LIBRARY_PATH` doesn't add an empty (current-folder) entry. It works through symlinks (`readlink -f`, tested) and handles repo paths with spaces. `exec` passes arguments through intact.
- **Downloads:** the Whisper clip is https, pinned to a commit, SHA-256 checked, and the partial file is removed on a mismatch (tested). Gitleaks in CI is fetched over https at a pinned version and checked with `sha256sum --strict`. pre-commit hook repos are pinned by commit SHA.
- **CI and supply chain:** top-level `permissions: contents: read`; only the release job gets `contents: write`. Every action is pinned by full SHA with a version comment. `persist-credentials: false` everywhere. Timeouts on every job. uv cache enabled. Untrusted values (`pull_request.title`, `ref_name`) reach `run:` only through `env:`; there is no `${{ }}` inside a script. `uv lock --check` runs, and `UV_LOCKED=1` is set. `UV_MALWARE_CHECK=1` works without the preview flag (uv 0.13.5 only warns). `uv audit` is clean and includes the `voice` extra. Dependabot config is valid (uv and github-actions, weekly, grouped, 7-day cooldown, every label exists). Repo settings match CLAUDE.md: squash only, branches auto-deleted, wiki and projects off, default token read-only.
- **pre-commit:** covers everything CLAUDE.md lists (ruff check, ruff format check, mypy strict, fast tests, gitleaks on staged changes, Conventional Commits with the allowed types). If gitleaks isn't installed, the hook fails rather than being skipped. `default_install_hook_types` installs all three hooks.
- **Logging basics:** string, bytes, mapping and non-allowlisted arguments are redacted (property test included). Exception messages are dropped along the whole cause/context chain, including cycles. `add_note` notes, `stack_info` and `extra=` don't reach the file (probed). Log files are created 0600, rotated ones too. Rotation is 5 MB × 5.
- **Paths:** XDG resolution ignores empty and relative values as the spec requires. Folders are created 0700 with an atomic `mkdir(mode=…)`, and too-open folders are tightened (tested).
- **Errors:** every class derives from `ReconError`, each has its own plain British-English `user_message` with a next step, and none of the copy blames the user. Each `noqa: N818` has a reason.
- **Engineering standards:** mypy strict and ruff are clean. The ruff selection includes every family CLAUDE.md requires, plus `G`, `LOG` and `T20`. Per-file ignores have reasons. No function is over 50 lines (the longest is 46). No TODOs, no dead code apart from `busctl` (F-16). mutmut 3.8 config keys (`source_paths`, `only_mutate`) are valid.
- **Fixture rooms (0.8):** original text with no URLs. The two conversion mistakes, one port mistake and one flag mistake are proven wrong in code. `THM{this_is_a_test}` and the MD5 lookalike are declared and are the only flag-shaped strings. A strict pydantic loader rejects unknown fields.
- **Smoke scripts (0.7a–c):** Ollama is pinned to `127.0.0.1`. The shortcut log is written 0600 in a 0700 folder. The KWin rule matches the app ID and title exactly, and removal also cleans `Order`. The temporary KWin script is deleted in `finally`.
- **Docs:** `environment.md` matches what `check_env` reports (10 checks). ADRs 0002 and 0003 match the code, apart from F-06's "restores them". CHANGELOG follows Keep a Changelog. The THREAT_MODEL threat IDs match CLAUDE.md.
- **No app entry point** (`recon/__main__.py`): expected for Phase 0. README says "There's no app to run yet". Gate 1 is the first gate that needs a launchable app.

## Gate 0 readiness

**Not ready.** Fix F-01 (create the Phase 1 issues, or change Gate 0 step 4) and the six Medium findings (F-02 to F-07), and keep CI green. The rest is in place: CI is green on `6caf0cb`, the dependency audit is clean, and coverage gates and mutation testing are not applicable yet (no gated or safety-critical modules exist, so there's no mutation score). The environment report, models, smoke tests and fixture rooms are done. `main` is protected by the local pre-push hook (GitHub Free), which has the gaps in F-02.

## Follow-up

Every finding became a GitHub issue (`audit-finding` label). All Critical, High and Medium findings are fixed; ten of the eleven Lows are fixed, and one is left open with a reason.

| Finding | Severity | Issue | Resolution |
| --- | --- | --- | --- |
| F-01 | High | #19 | Fixed in #52: Phase 1 issues created (#37–#51); the plan says when task issues are made |
| F-02 | Medium | #20 | Fixed in #53: a git pre-push hook reads every ref (multi-ref, `--all`, delete); tested against a real bare remote |
| F-03 | Medium | #21 | Fixed in #54: static checks for any logger receiver, logger names and `LoggerAdapter`, with self-tests; the formatter never reuses cached exception text |
| F-04 | Medium | #22 | Fixed in #55: wider banned list, dynamic imports, restricted names and a QML scan, each with self-tests. The QML network access manager factory is noted on task 1.3 (#39) |
| F-05 | Medium | #23 | Fixed in #56: the gate reports per package, normalises paths and fails on unmeasured code |
| F-06 | Medium | #24 | Fixed in #57: the launcher syncs the voice extra before building `LD_LIBRARY_PATH`; verified after a plain `uv sync` |
| F-07 | Medium | #25 | Fixed in #58: the service is OK only when a server answers; the GPU check reads the current invocation only |
| F-08 | Low | #26 | Fixed in #56: `scripts/` is measured (smoke probes excepted, with the reason given) |
| F-09 | Low | #27 | Fixed in #52 |
| F-10 | Low | #28 | Fixed in #52 |
| F-11 | Low | #29 | Fixed in #52 |
| F-12 | Low | #30 | **Open, Phase 5:** wording fixed in #52; the pinned, offline Whisper model needs the Phase 5 voice code |
| F-13 | Low | #31 | Fixed in #59: reasons on the `Any`, ignore and noqa comments |
| F-14 | Low | #32 | Fixed in #54: re-check after chmod; an existing `app.log` is locked to 0600 |
| F-15 | Low | #33 | Fixed in #59: CI keeps runs on `main`; releases need a tag on `main` with passing CI; literal CHANGELOG matching |
| F-16 | Low | #34 | Fixed in #58 |
| F-17 | Low | #35 | Fixed in #53: the fast-test hook runs on every commit |
| F-18 | Low | #36 | Fixed in #59: headless QML tests skip the timing budget; the desktop run keeps it |
