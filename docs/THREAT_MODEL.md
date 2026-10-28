# Threat model

Recon is a single-user desktop app on the user's own machine. This model lists what's worth protecting, where untrusted data comes in, what could go wrong, and what stops it. It's reviewed at every phase audit and in full at the release audit; any change to an entry point or mitigation updates this file in the same pull request.

## Assets

| Asset | Why it matters |
| --- | --- |
| A1 Study notes (`app.db`, vault, raw notes, backups) | Private; loss means lost work; leak exposes room answers |
| A2 Integrity of the user's own text and of `00 Raw notes/` | The spec promises the user's words are never changed |
| A3 CTF flags | Must never be stored anywhere (TryHackMe asks that answers to active rooms aren't shared) |
| A4 Voice recordings and screenshots | May contain personal audio, desktop contents, EXIF/GPS metadata |
| A5 The vault's structure | A broken note or a write outside the vault damages the user's library |
| A6 the user's machine and accounts | Code execution, KDE config, GitHub token, other files in `$HOME` |
| A7 Repository | Must never contain real notes, data or secrets |

## Trust boundaries and entry points

| Entry point | Trust |
| --- | --- |
| E1 Typed and pasted text in blocks | Untrusted content (pasted from anywhere) from a trusted user |
| E2 Pasted or dropped images | Untrusted files |
| E3 Microphone audio → Whisper transcript | Untrusted content |
| E4 Every Ollama response (extraction, fact-check, quiz, answers, vision) | Untrusted; may be wrong or shaped by prompt injection in E1/E2 |
| E5 Vault files the user edits in Obsidian | Trusted author, but may change between staging and Apply |
| E6 Settings file and settings UI (vault path, backup folder) | Trusted user, unvalidated input |
| E7 D-Bus (portal via jeepney, notifications via QtDBus), KWin config | Local session services; portal replies are validated like any other input |
| E8 Dependencies, CI actions, hook repos | Third-party code |
| E9 Network | Only Ollama on loopback at runtime |

## Threats and mitigations

| ID | Threat | Mitigations | Verified by |
| --- | --- | --- | --- |
| T1 | Flag stored in db, vault, cards, backups or logs (A3) | `engine/flags_filter.py` enforced in the repositories on every text field (block text, answers, task titles, room details), including flags still being typed; `FlagGuard` clears them from the editor; voice transcripts and screenshot text go through it too (Phase 5); only lone hex lookalikes can be kept ("Not a flag, keep it"), never braced flags; flag text is never logged ([ADR 0005](adr/0005-flag-filter-rules.md)) | `tests/engine/test_flags_filter.py` (unit and property), `tests/db/test_flags_never_stored.py` (raw database bytes, key-by-key typing), mutation testing 111/111 |
| T2 | Prompt injection in pasted text steers the model to add links, embeds, HTML or scripts to notes (E1, E4 → A5) | Delimited data in prompts; schema validation; length limits; sanitising of `[[`, `![[`, HTML, `%%`, frontmatter fences, non-http(s) URLs; review screen before Apply | `tests/engine/test_sanitise.py` (hostile strings, exact replacements, property tests; 119/119 mutants killed), `tests/engine/test_notes.py` (hostile model output in every field), `tests/engine/test_extract.py` (delimiters can't be closed) |
| T3 | Model output overwrites or edits the user's text (A2) | Model returns data only; jinja2 renders; the user's commands, tables and raw notes rendered by code; updates only between `%% recon:start/end %%` markers (`engine/stage.merge`); notes with damaged markers or that aren't UTF-8 are skipped, never rewritten; raw notes never updated (a re-run gets a new raw-notes file) | Golden tests, `tests/engine/test_stage.py` (merge property test, damaged markers, raw notes), hard-rule tests |
| T4 | Path traversal via room or concept names (`../../etc`, control chars) (A5, A6) | Filename sanitiser (`engine/names.file_name`: no separators, `..`, control or bidi characters, reserved or hidden names; length-limited); every resolved write path checked to stay inside the vault, data folder or chosen export folder (`UnsafePathError`; `engine/stage.inside` resolves symlinks, so a symlinked folder leading out is refused); Markdown exports never overwrite (hard-link create, then `(2)`, `(3)`…) | Hostile-name and property tests (`tests/engine/test_names.py`, `test_export.py`, `test_notes.py`, `test_stage.py`) |
| T5 | Lost work from a crash or kill (A1) | Autosave with at most 0.5 s latency for block text and task titles alike (max-latency debounce, retried on failure); at quit, queued room jobs drain before the final saves and before the database closes; SQLite WAL with `synchronous=FULL`; atomic writes (temp, fsync, replace, fsync folder); migrations in one transaction each; daily online-backup snapshot of `app.db`, keeping 14; off-machine backups (task 5.7) | `tests/db/test_crash.py` (`kill -9` mid-typing loses 0.5 s); `tests/bridge/test_session.py` (a steadily typed title saves within 1 s); `tests/test_quit.py` (title, Next, quit keeps the title); `tests/engine/test_stage_crash.py` (SIGKILL mid-Apply, then start-up recovery leaves the vault fully applied; killed before the first write, untouched) |
| T6 | Apply clobbers a note the user edited meanwhile (E5 → A1) | Staging records each target's SHA-256; Apply re-hashes every target first and aborts on any change, creation or deletion (`ApplyConflict`), writing nothing; backups of every overwritten file before the first write (newest 20 runs kept); new notes created with a hard link, never overwriting; crash recovery never writes over a file changed since staging; restore from History (2.8) | `tests/engine/test_stage.py` (edited, created and deleted conflicts; backups; 448/448 mutants killed), `tests/test_processing.py` |
| T7 | Note content leaks via logs (A1) | `RedactingFilter`, `RedactingFormatter` (never reuses cached exception text), literal-only log messages for any logger receiver, literal or `__name__` logger names, no `LoggerAdapter`, ruff `G` rules; content only in private `runs/` (30-day expiry) | `tests/test_logging.py` (runtime probes plus static checks with detector self-tests) |
| T8 | Other local users read data (A1, A4) | Folders `0700` at every level Recon creates, files `0600`; at launch every folder and file under the data and config folders is brought to those modes (symlinks skipped, never followed); Qt's QML cache kept in Recon's private cache folder; SQLite `secure_delete` | Permission tests; `tests/test_fresh_profile.py` (real start-up on a fresh profile, and a profile with older 0644 files) |
| T9 | Data leaves the machine (A1) | No telemetry or update checks. Only `services/ollama.py` imports networking, and it refuses non-loopback hosts. Hugging Face libraries only in `services/whisper.py` (loaded offline, #30). `subprocess` and URL openers only in named modules. No dynamic imports. QML can't contain remote URLs or network APIs. QML's network access manager refuses non-local schemes (`services/qml_network.py`) | `tests/test_network_imports.py` (static, with detector self-tests), `tests/test_qml_network.py`, `tests/services/test_ollama.py` (loopback hosts, with a property test over every IP address) |
| T10 | Malicious image (decompression bomb, parser bug, metadata leak) (E2, A4) | Pillow bomb limit; size limit; re-encode to PNG; strip EXIF/GPS | EXIF/GPS and oversize tests |
| T11 | Recordings kept longer than needed (A4) | Deleted after transcription unless "Keep recordings" is on | Recording deletion test |
| T12 | Command injection via subprocess (A6) | Subprocesses only where unavoidable, argument lists, no `shell=True`, allowlisted binaries by full path; ruff `S` rules | Lint, review |
| T13 | KDE config damaged by the KWin rule (A6) | Opt-in (asked once at first launch); only Recon's own `recon-panel` group is written; removal deletes its keys and its `rules`/`Order` entries and drops `count` when empty, leaving every other rule alone; allowlisted KDE tools by full path, no shell; checked against a backup on the development desktop (ADR 0004) | `tests/test_kwin.py` (fake KDE store pre-filled with the user's real config) |
| T14 | Compromised dependency, action or hook (E8) | `uv.lock` pinning; `UV_MALWARE_CHECK`; `uv audit` in CI and at gates; actions and hooks pinned by commit SHA; least-privilege tokens; Dependabot PRs reviewed by hand with a cooldown | CI |
| T15 | Secrets or real data committed (A7) | gitleaks in pre-commit and CI; `.gitignore` for `*.db` and audio; fixtures are invented | CI |
| T16 | Model wrong but confident (E4) | Code checks override the model; flags are suggestions; `unsure` dropped; generated content labelled | Fact-check tests |
| T17 | Contacting tryhackme.com (policy) | No networking outside the Ollama service; loopback-only; no URL openers or browsers outside `services/open_url.py` (obsidian:// only) | Network tests |

## Out of scope

- An attacker who already runs code as the user: they can read everything Recon can. Recon doesn't encrypt at rest; full-disk encryption is the right layer.
- The security of Ollama, Obsidian, KDE and the NVIDIA driver themselves.
- Multi-user or networked use; Recon is single-user and local by design.
