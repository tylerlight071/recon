# Phase 1 audit

- **Date:** 2026-10-27
- **Scope:** everything Phase 1 added or changed on `main`, `v0.0.0..e155d9b` (16 squash-merged PRs, #62–#80: tasks 1.1–1.15 and 1.9b). Covers `recon/` (bridge, db, engine, services, QML, `app.py`, `__main__.py`, `config.py`, `fs.py`), `scripts/screenshots.py`, `scripts/install_desktop.py`, `scripts/make_chime.py`, `packaging/`, `tests/`, `.github/workflows/ci.yml` and the docs those PRs changed.
- **Auditor:** independent agent; did not write the code.
- **Checklist:** `docs/AUDIT_CHECKLIST.md`, all eleven areas.

## How the audit was done

Read every Python and QML file in scope, plus CLAUDE.md, BUILD_PLAN (Phase 1), SPEC (room session, ADHD rules, look and feel), ARCHITECTURE, THREAT_MODEL, ADRs 0004–0005 and the Phase 0 audit. Each finding below was reproduced with a script or a scratch pytest file in the session scratch folder (`/tmp/claude-1000/-data-projects-Recon/audit-phase1/`), driving the real repositories, bridges and QML windows headless (`QT_QPA_PLATFORM=offscreen`, `QT_QUICK_BACKEND=software`). Scratch tests reuse the project's own fixtures (`tests/bridge/test_session.py::_world`, `tests/ui/test_windows.py::running`). Nothing touched Tyler's real data, config, vault or KDE settings; every app launch used throwaway `XDG_*` folders. No repository file was changed apart from this report.

| Command | Result |
| --- | --- |
| `uv run pytest -m "not ollama and not gpu" --cov --cov-branch` | **1073 passed**, 8 deselected, 36.6 s. Total branch coverage **98.60%** (3321 statements, 540 branches, `recon/` plus measured `scripts/`) |
| `uv run coverage json` + `uv run python scripts/coverage_gates.py coverage.json` (report written to the scratch folder) | `recon/engine/` 99.1%, `recon/db/` 98.0%, `recon/services/` 100.0% (gate 90%); `recon/revision/` "no code yet". `per-package coverage gates: OK` |
| `uv run mypy --strict recon` | Success: no issues in 44 source files |
| `uv run ruff check .` / `uv run ruff format --check .` | All checks passed / 143 files already formatted |
| `uv lock --check` | OK (78 packages) |
| `uv audit --preview-features audit-command --frozen` | No known vulnerabilities and no adverse project statuses in 77 packages |
| `gh run list --branch main --limit 3` | CI **success** on `e155d9b` (1 m 20 s); two Dependabot update runs also green |
| `gitleaks git --log-opts="v0.0.0..main"` | 16 commits scanned, no leaks |
| `gh issue list --milestone "Phase 1"` | 16 task issues (#37–#51, #71), all closed |
| Headless launch of the real `recon.__main__.main()` on a fresh profile, 3 runs | Both windows loaded and the event loop running **0.17–0.22 s** after process start; RSS **116 MB**. File modes: `backups/` **0755** (F-09) |
| `RoomSession.next()` through the real QML panel, 8 switches | 1.5–2.3 ms each (synchronous worker, offscreen) |
| `RoomSession.edit` and `Editors.tablePreview` on a 500 KB Table block | 9.9 ms and 10.8 ms per keystroke (fine) |
| Repository probes with flag-shaped text | Rest of the line deleted from storage (F-03); typed hex prefix stored (F-07); filter gaps (F-15) |
| Undo probes (`_world` fixture) | Toast Undo after Finish destroys the block (F-01); reused block ID sends Ctrl+Z to the wrong block (F-04) |
| Title typed at 4 keys/s through `setTitle` with a real event loop | Nothing stored after 9.3 s of typing (F-02) |
| Mutation testing | **Not re-run** by the auditor: a separate `mutmut` run was in progress in the working tree during the audit. ADR 0005 records 111/111 on `flags_filter` (see F-25) |

## Summary

| Severity | Count |
| --- | --- |
| Critical | 2 |
| High | 2 |
| Medium | 8 |
| Low | 13 |

The tooling gates are all green and the code is careful in most places. But two paths lose Tyler's text outright: the delete toast's Undo after Finish, and a task title typed without pausing. Two more lose or misplace it in common situations: the unfinished-flag rule eats the rest of a line, and Undo goes to the wrong block once a block ID has been reused. The Mediums are mostly guarantees the docs make that the code doesn't fully keep: the UI thread never blocks, nothing is lost at quit, files are 0600, and every error has plain copy.

---

## F-01 — The delete toast's Undo, pressed after Finish, permanently destroys the deleted block

- **Severity:** Critical
- **Area:** Correctness (ADHD rule 4, "nothing can be lost")
- **Location:** `recon/bridge/session.py:431-437` (`undoDelete`), `:464-467` (`_insert_block` returns early when no room is open), `:510-517` (`_forget`), `:519-534` (`closeRoom` keeps the history)
- **Finding:** `undoDelete` takes the step off the history, calls `_forget` (which deletes its `undo_log` row on the worker), and only then calls `_apply`. `_insert_block` returns without doing anything when `self._room` is `None`. After "Finish room", `closeRoom()` sets the room to `None` but leaves the history in place, and the panel's 10 s "Block deleted. Undo" toast is still showing over the Finish screen. Pressing Undo there removes the only record of the deleted block and restores nothing. "Back to the room" reloads the history from `undo_log`, so it's gone for good. The same early-`_forget` ordering also drops a step from the session whenever `take_insert` finds it while `_busy` is true (`:434-435` pops before checking busy).
- **Reproduced:** `tests_audit/test_undo_after_finish.py`: add a Command block, type, delete it, Finish (last task), press the toast's Undo, then reopen the room and press Ctrl+Z twice.
  ```
  block restored: False | insert_block steps left in undo_log: 0
  after reopening and Ctrl+Z twice: [('key_idea', '')]
  ```
- **Fix:** Delete the `undo_log` row in the same worker job as the restore, and only after it succeeds. Don't make `_insert_block` depend on the open room: it needs only `block.task_id`, plus the room ID for remapping, which can come from the step. Check `_busy` before `take_insert`. On `closeRoom`, clear the panel's toast action, or keep it working against the stored block. Add a test for "delete, Finish, toast Undo".

## F-02 — A task title typed steadily is never saved until a 0.5 s pause (hard rule 7)

- **Severity:** Critical
- **Area:** Hard rules (7)
- **Location:** `recon/bridge/session.py:50` (`TITLE_SAVE_MS`), `:299-306` (`setTitle` restarts the timer on every keystroke); `docs/ARCHITECTURE.md:89`
- **Finding:** `setTitle` calls `QTimer.start()` on each keystroke, which restarts the single-shot timer. That's a trailing debounce, so continuous typing keeps putting the save off. Hard rule 7 says a crash may lose at most one second. Block text gets this right (`AutosaveQueue` uses a max-latency debounce); the title doesn't. A `kill -9`, power cut or SIGTERM at logout loses everything typed since the last half-second pause, which can be the whole title. The `kill -9` acceptance test only drives `AutosaveQueue`, so it doesn't cover this. The scope is one short, optional field, but it is a hard-rule breach.
- **Reproduced:** `tests_audit/test_title_debounce.py`: 37 characters, one every 250 ms, through `RoomSession.setTitle` with a live event loop.
  ```
  typed 37 chars over 9.3s; stored title = ''
  after 0.7 s pause: 'How DNS resolution works step by step'
  ```
- **Fix:** Start the timer only when it isn't already active (max-latency, the same as `AutosaveQueue`), or put titles through the autosave queue. Add a test that steady typing is saved within 1 s, and extend `tests/db/test_crash.py` (or a bridge-level crash test) to cover the title.

## F-03 — The unfinished-flag rule silently deletes the rest of Tyler's line from storage

- **Severity:** High
- **Area:** Hard rules (2 and 4), Correctness
- **Location:** `recon/engine/flags_filter.py:31` (`UNFINISHED`), `:111-118` (repeat rounds); `recon/db/repositories.py:122-134`; `docs/adr/0005-flag-filter-rules.md` decision 2
- **Finding:** On save, everything from an unclosed `THM{`/`flag{`/`HTB{` to the end of its line is removed. ADR 0005 accepted this as "rare". In CTF notes it isn't rare: `grep -r "flag{" .` and `strings x | grep THM{` are standard commands, and prose about flag formats is common. The editor doesn't apply this rule, so Tyler sees his full line and gets no "Flag skipped" notice. The truncated text appears on the next task switch, "Previous task" or restart. Because stripping repeats, one removal can expose another unclosed prefix, and the whole line goes. The undo log stores the truncated text too, so Undo can't bring it back.
- **Reproduced:** `repro_flags.py` (real `BlockRepository.update_content`):
  ```
  'grep -ri "flag{" /home  # find flags' -> 'grep -ri "'
  'strings dump.bin | grep THM{ | head' -> 'strings dump.bin | grep '
  'HTB{ is the HackTheBox prefix, THM{ is TryHackMe' -> ''
     editor-side strip (what Tyler sees): unchanged in all three
  ```
  High rather than Critical because the trade-off was recorded in an ADR. Tyler should decide whether, given these examples, it counts as data loss.
- **Fix:** Narrow the rule to what a flag being typed looks like. The body can't contain whitespace, quotes or pipes (`(?:thm|htb|flag)\{[^{}\s"'`|]{0,200}$`), and it has to be at the end of the text or the line. Better still, strip only at the cursor (pass the cursor position from the editor). Show the notice whenever storage strips something the editor didn't. Add the three examples above as regression tests, and update ADR 0005.

## F-04 — After a block ID is reused, Undo acts on the wrong block

- **Severity:** High
- **Area:** Correctness (undo)
- **Location:** `recon/db/migrations/0001_initial.sql:33` (`id INTEGER PRIMARY KEY`, no `AUTOINCREMENT`); `recon/db/repositories.py:372-403` (`restore`), `:500-510` (`UndoRepository.remap`); `recon/bridge/undo.py:142-148` (`UndoHistory.remap`)
- **Finding:** SQLite reuses the highest deleted rowid. Delete block A (the newest), then add block B, and B gets A's ID. When A is then restored (toast Undo, or Ctrl+Z), its ID is taken, so it comes back with a new ID. `remap(old, new)` then rewrites *every* step about the old ID, including B's add and B's typing, to point at A. The next Ctrl+Z puts B's earlier content into A, and the one after deletes A. B's own typing is never undone. If Tyler types again after that, redo is cleared and A's text is gone. The same thing happens across tasks: a task's new starter block can reuse a deleted block's ID, and remap then moves steps between tasks, where they're silently dropped.
- **Reproduced:** `tests_audit/test_undo_reuse.py`:
  ```
  A id 2 B id 2
  after toast Undo: {1: ('key_idea', ''), 3: ('command', 'nmap -sV target  '), 2: ('question', 'why is UDP slower? ')}
  after Ctrl+Z: {1: ('key_idea', ''), 3: ('command', ''), 2: ('question', 'why is UDP slower? ')}
  after 2nd Ctrl+Z: {1: ('key_idea', ''), 2: ('question', 'why is UDP slower? ')}
  ```
- **Fix:** Migration 0003: rebuild `blocks` with `INTEGER PRIMARY KEY AUTOINCREMENT`, so an ID is never reused (copy the rows, keep the IDs, and seed `sqlite_sequence` from `max(id)`). `restore` then always gets its old ID back, and the remap code and its failure modes can go. Add migration and regression tests, including the cross-task case.

## F-05 — The UI thread still reads and writes storage

- **Severity:** Medium
- **Area:** Performance budgets, Engineering standards ("the UI thread never blocks")
- **Location:** `recon/bridge/flags.py:55` (`keep` → `BlockRepository.keep_lookalike`, a transaction with fsync); `recon/bridge/settings.py:166-170` (`flush` → atomic write plus two fsyncs, run from a `QTimer` on the UI thread); `recon/bridge/home.py:96`, `:164`; `recon/bridge/start.py:75`; `recon/db/connection.py:72-95` (reads take the same lock that writers hold through `COMMIT`)
- **Finding:** CLAUDE.md and ARCHITECTURE.md:25 say file writes never run on the UI thread. "Not a flag, keep it" writes to the database there, and every settings change (including each step of a panel-width drag, once it settles) writes and fsyncs `settings.toml` there. `HomeModel.refresh` runs on every `RoomSession.changed`, so on every task switch, and it does three reads under the single `Database` lock. A `synchronous=FULL` commit by the autosave or room worker holds that lock through its fsync, so the UI thread waits as long as the commit takes. WAL readers don't need to wait for a writer; only Recon's Python lock makes them.
- **Reproduced:** `ui_thread_io.py` instruments `Database.read`/`transaction` by thread:
  ```
  HomeModel.refresh on UI thread: ['read', 'read', 'read']
  StartRoom.refresh on UI thread: ['read']
  HomeModel.resume on UI thread: ['read']
  FlagGuard.keep on UI thread: ['read', 'WRITE']
  HomeModel.refresh waited 200 ms behind a 200 ms write
  ```
  (The 200 ms commit stands in for an fsync on a busy disk. Real fsync times on Tyler's btrfs NVMe couldn't be measured inside the allowed folders, because `/tmp` is tmpfs.)
- **Fix:** Run `keep_lookalike` and `save_settings` on a worker (the room worker for the first, a small serial worker for settings). Move Home and Start refreshes to a worker and deliver the results by signal. Give reads their own connection (WAL lets readers run alongside the writer), so a reader never waits on the writer's lock. Add a test that fails if any bridge slot touches `Database` on the UI thread (the instrumentation above works as a fixture).

## F-06 — Room-worker jobs still queued at quit run after the database is closed

- **Severity:** Medium
- **Area:** Correctness (data safety at quit)
- **Location:** `recon/__main__.py:76-81` (`db.close()` in `main`'s `finally`), `:161` (`serial_submit(app)`), `:189-191` (the `aboutToQuit` savers don't wait for the worker); `recon/bridge/workers.py:16-28`
- **Finding:** `aboutToQuit` saves the title, the time and the autosave queue, but never waits for the serial room worker. `main()` then closes the database while jobs may still be queued: "Next task" (its title and status), a block delete or move, undo-log pushes. They fail with `ProgrammingError`, which is logged and dropped. For example, if Tyler types a title, presses Ctrl+Return and quits straight away, the title is lost, because `_move` has already taken it from `_pending_title`, so `session.close` has nothing to save.
- **Reproduced:** `quit_drain.py` mirrors `main()`'s order (queue a slow job and a delete, `app.quit()`, then `db.close()`):
  ```
  db closed (main's finally)
  delete job failed: ProgrammingError Cannot operate on a closed database.
  block still in app.db after quit: True
  ```
- **Fix:** Return the `QThreadPool` from `serial_submit` (or a `drain()` with it), and call `pool.waitForDone(5000)` at `aboutToQuit` after `session.close`/`focus.close` and before `autosave.close`. Do the same for the global pool used by Start and Pinning. Add a test that queues a job, quits, and checks the job's write landed.

## F-07 — A hex answer typed key by key reaches app.db and its WAL until the 32nd character

- **Severity:** Medium
- **Area:** Hard rules (2)
- **Location:** `recon/engine/flags_filter.py:32` (`LONE_HEX`), `:82-87` (the unfinished rule covers braced flags only)
- **Finding:** ADR 0005 added the "unfinished" rule so a braced flag can't be stored a few characters at a time. A lone hex flag has no such rule. Typing an MD5 answer into a Room question saves 31 of its 32 characters on the way (one autosave every 0.5 s). The 32nd character strips the whole string, but the earlier frames stay in `app.db-wal` until they're overwritten. Pasting, the usual case, is safe. Medium rather than Critical because what's stored is a prefix and only hand-typed hashes are affected. It's a gap in a hard rule that has no test.
- **Reproduced:** `repro_hex_typed.py`:
  ```
  stored answer now: ''
  31-char prefix present in app.db + WAL bytes: True
  ```
- **Fix:** On save, also strip a hex run of, say, 20–31 characters that ends the text or a line (a hash still being typed), with the same "hold, don't store" rule as braced prefixes. Add the key-by-key test for hex that `test_flags_never_stored.py` already has for `THM{`.

## F-08 — In the Markdown export, a line of Tyler's text can hide the rest of the note

- **Severity:** Medium
- **Area:** Security and privacy (sanitising Tyler's text), Correctness
- **Location:** `recon/engine/render.py:35` (`_STRUCTURE`), `:117-120` (`escape_lines`)
- **Finding:** CLAUDE.md asks that Tyler's own text is "escaped where needed so it can't break the note's structure". `escape_lines` covers headings, quotes, fences, rules and `%%`, but not raw HTML. A line starting with `<script`, `<style`, `<pre`, `<textarea` or `<!--` opens a CommonMark HTML block, and these can interrupt a paragraph. Unclosed, the block runs to the end of the document. Notes for web rooms (XSS, HTML comments) contain exactly these lines, so whole later tasks vanish from the rendered note. Obsidian also drops `<script>` content.
- **Reproduced:** `repro_export_html.py` renders a four-task room through `render_export` and parses it with markdown-it (CommonMark):
  ```
  --- headings CommonMark sees: ['XSS Basics', 'Task 1: Reflected XSS']
  --- html_block tokens: ['<script> runs whatever the page reflects back.\nAlways encode output.\n\n']
  ```
  Tasks 2–4 are inside the HTML block. Obsidian's reading view wasn't checked (no GUI), but it follows the same block rules.
- **Fix:** Escape a leading `<` (`\<`) in `escape_lines` and in table cells. Also consider four-space-indented lines (which become code blocks) and a leading `[!`. Add golden and property tests: any `ExportBlock` text renders to the same number of headings as tasks. Phase 2's vault renderer should reuse this.

## F-09 — `backups/` is created 0755, and older files aren't checked at launch

- **Severity:** Medium
- **Area:** Security and privacy (permissions); Phase 1 acceptance
- **Location:** `recon/paths.py:88` (`mkdir(mode=…, parents=True)`: Python applies `mode` only to the last folder); `recon/db/backup.py:47`; `recon/__main__.py:69-77`
- **Finding:** `ensure_private_dir(data/backups/db)` creates `backups/` with the umask's 0755. Only the leaf gets 0700. Files that already exist aren't checked at launch: an existing `settings.toml` or an older snapshot keeps whatever mode it has (CLAUDE.md: "set on creation and checked at launch"; THREAT_MODEL T8). The parent data folder is 0700, so nothing is exposed today, but the acceptance check ("Data and config folders are 0700 and their files 0600; a test checks this on a fresh profile") isn't met, and no fresh-profile test exists.
- **Reproduced:** `launch_probe.py` runs the real `main()` on throwaway XDG folders:
  ```
  0o755 recon/backups
  0o700 recon/backups/db
  0o644 recon/settings.toml            (pre-existing at 0644; unchanged after launch)
  0o644 recon/backups/db/app-2026-10-20.db   (pre-existing; unchanged)
  ```
- **Fix:** Create each missing level of the path with 0700 (walk the parents under the data root). At launch, walk the data and config folders and fix, or refuse, anything that isn't 0700/0600. Add the fresh-profile acceptance test, which runs `main()` headless as above and asserts every mode.

## F-10 — Nothing stops two copies of Recon running, and two writers lose edits

- **Severity:** Medium
- **Area:** Correctness (one writer connection), Data safety
- **Location:** `recon/__main__.py:58-82` (no single-instance check)
- **Finding:** Launching Recon again while it's running starts a second process with its own connection, autosave queue and in-memory copy of the room. That's easy to do with the panel hidden and the app-menu entry one click away. "Carry on" in both windows means each autosaves its own full text of a block, and the last write wins. Undo logs also interleave across the two processes.
- **Reproduced:** Two `python -m recon` processes on one profile both started and ran together (`pgrep` showed both). `tests_audit/test_two_instances.py`, two sessions on two connections to one `app.db`:
  ```
  stored: 'TXT records hold text.'      (the other window's 'DNS uses UDP 53 for queries.' is gone)
  ```
- **Fix:** Take a `QLockFile` in the data folder at start-up. If it's held, raise the running instance's windows over D-Bus (or a `QLocalServer`) and exit. Test that a second `main()` exits without opening the database.

## F-11 — Once Finish is closed, or Recon restarts on it, the room can't be exported or reopened

- **Severity:** Medium
- **Area:** Correctness (task 1.13; Gate 1 step 5); ADHD rule 4
- **Location:** `recon/bridge/finish.py:129-138` (`open` marks the room `done` straight away), `:216-219`; `recon/bridge/home.py:118` (`canResume` only while capturing)
- **Finding:** "Finish room" marks the room `done` before Tyler exports. Export and "Back to the room" exist only on the Finish screen. Press "Done" without exporting, or quit or crash there, and the room shows on Home as an inert "Done" row: no export and no reopen until Phase 2's Library. The notes are safe in `app.db`, but Tyler can't reach them.
- **Reproduced:** `tests_audit/test_finish_done.py` (real QML windows):
  ```
  recent rooms: [{'canResume': False, 'detail': 'Done', 'id': 1, 'name': 'DNS in Detail', 'when': 'just now'}]
  hasCurrent: False | room status: done
  panel shows Finish: False | session has room: False
  ```
- **Fix:** Make a done room's row on Home open the Finish screen again (export, back to the room). Or keep the room `capturing` until Tyler presses "Done", and on launch reopen Finish for a room left there.

## F-12 — Start-up failures are invisible from the app menu, and the copy is wrong

- **Severity:** Medium
- **Area:** Error handling
- **Location:** `recon/__main__.py:69` (`paths.ensure()`, uncaught), `:74-77` (stderr only)
- **Finding:** If the database can't be opened or migrated, Recon prints `StorageError.user_message` to stderr and exits 1. Launched from the KDE menu, nothing appears at all. The copy also says "Check there's free disk space", which is wrong for the common causes: a database from a newer Recon (logged as such), or a corrupt file. A data path that can't be created (`FileExistsError`) or locked down (`InsecurePermissionsError`) escapes as a traceback. The checklist asks for plain copy and a next step for every user-visible error.
- **Reproduced:**
  ```
  $XDG_DATA_HOME/recon is a file   -> traceback ending "FileExistsError: [Errno 17] File exists: …/recon"
  app.db with user_version=99      -> stderr "Couldn't save to Recon's data folder. Check there's free disk space, then retry."; exit 1
                                      app.log: "database schema 99 is newer than this recon (2)"
  ```
- **Fix:** Catch `ReconError` and `OSError` in `main()` and show a minimal QML (or `notify-send`-style) message window with specific copy per cause. Give the newer schema its own error ("This data is from a newer Recon. Update Recon, then open it again."). Test each start-up failure path.

---

## F-13 — Tab in a block types a tab character, so forward keyboard navigation stops at the first block

- **Severity:** Low
- **Area:** Accessibility
- **Location:** `recon/ui/components/TextArea.qml` (no Tab handling); `recon/ui/editors/BlockEditor.qml:85-105`
- **Finding:** Pressing Tab inside a block inserts `\t` and focus stays put. Shift+Tab does go round every control (Home, timer chip, Next, Skip, add bar, editors, delete buttons). Most actions also have shortcuts, so this isn't a trap, but forward Tab from the title only reaches the first block.
- **Reproduced:** `tests_audit/test_panel_keyboard.py`: `Tab path: [editor, editor, editor, editor, editor]`, `editor text after 4 Tabs: '\t\t\t\t'`. The Shift+Tab cycle reached every control.
- **Fix:** In non-Table blocks, Tab and Shift+Tab move focus (`KeyNavigation`, or `Keys.onTabPressed` → `nextItemInFocusChain().forceActiveFocus()`). Keep a literal tab for Table blocks, with Ctrl+Tab to leave them.

## F-14 — Flags in task titles and Start fields are dropped silently, and the title keeps showing the flag

- **Severity:** Low
- **Area:** Hard rules (2: "the UI shows a small 'Flag skipped' notice")
- **Location:** `recon/ui/screens/Session.qml:297`; `recon/bridge/session.py:299-306`; `recon/db/repositories.py:122-124`
- **Finding:** Titles, room names, paths and modules are cleaned only in the repository. No notice is shown, and the title field keeps showing `THM{…}` until the task is reopened.
- **Reproduced:** `tests_audit/test_title_flag.py`: `stored title: 'Answer was ' | Flag skipped notices: []`.
- **Fix:** Pass the title and Start fields through `FlagGuard.clean` in QML, as blocks are, so the text disappears with the notice.

## F-15 — Flag-shaped strings the filter misses

- **Severity:** Low
- **Area:** Hard rules (2)
- **Location:** `recon/engine/flags_filter.py:30-31`
- **Finding:** These survive storage: `THM{a{b}c}` (a brace inside), a body of more than 200 characters, `TH​M{secret}` (zero-width space), `THM｛secret｝` (full-width braces) and `THM {secret}`. `THM{multi\nline}` leaves `\nline}` behind. Most are unlikely in real rooms. They're listed so Tyler can decide which to cover.
- **Reproduced:** `repro_flags.py` ("flag-shaped strings that survive" section).
- **Fix:** NFKC-normalise and drop zero-width characters before matching (only for detection, mapping positions back). Allow optional whitespace before `{`. Document the 200-character and nested-brace limits in ADR 0005, or lift them.

## F-16 — Turning pinning on then quickly off can leave the KWin rule in place

- **Severity:** Low
- **Area:** Correctness (T13)
- **Location:** `recon/bridge/pinning.py:90-108` (pin and unpin run on Qt's multi-threaded global pool)
- **Finding:** Pin (about 20 `kwriteconfig6`/`qdbus6` calls) and unpin (fewer) can run at the same time. If unpin finishes first, the rule is written after it, and Settings says "off" while the panel stays pinned.
- **Reproduced:** `pin_race.py` with a fake pinner using the real bridge and global pool: `setting: off | KWin rule present: True`.
- **Fix:** Run pin and unpin on one serial worker, and have each job read the current setting before acting.

## F-17 — A failing save shows a new toast every second, and its copy asks for a retry that isn't needed

- **Severity:** Low
- **Area:** Copy, ADHD rule 11 (calm)
- **Location:** `recon/__main__.py:167`; `recon/db/autosave.py:23`, `:141`; `recon/errors.py` (`StorageError`)
- **Finding:** `on_error` fires on every retry of every block. Both `on_error` and the retry are per block, once a second. The copy ends "then retry", but autosave already retries by itself, and nothing says when saving works again.
- **Reproduced:** An `AutosaveQueue` whose save always fails, with 2 unsaved blocks: `failed-save notices in 3.2 s with 2 unsaved blocks: 6`.
- **Fix:** Report once per failure episode, plus a quiet "Saved again" when it recovers. Copy along the lines of: "Couldn't save your notes just now. Recon keeps trying; check there's free disk space."

## F-18 — Several example hashes pasted at once can't be kept

- **Severity:** Low
- **Area:** Hard rules (2, "Not a flag, keep it")
- **Location:** `recon/bridge/flags.py:48`; `recon/ui/PanelWindow.qml:54-60`
- **Finding:** Keeping is offered only when exactly one string was removed. A pasted hash table (common in hashing rooms) loses every hash, with the notice "Flag skipped. Recon never saves flags." Tyler has to paste them one at a time.
- **Reproduced:** `FlagGuard.clean` with two 32-hex strings emits `keepable == ""` (also covered by the project's own `test_several_findings_offer_no_keep`).
- **Fix:** Offer "Not a flag, keep them" when every removal is hex (still never for braced flags), and say "Skipped 3 things that look like flags."

## F-19 — `undo_log` keeps deleted and overwritten note text indefinitely

- **Severity:** Low
- **Area:** Security and privacy (deletion)
- **Location:** `recon/db/repositories.py:465`, `:488-493` (pruned only when a room is opened); `recon/db/migrations/0001_initial.sql` (`sessions` is never written)
- **Finding:** Every word-sized undo step stores the block's whole previous content. Steps are pruned to 300 only when a room opens, so a finished room keeps its whole last session's history, deleted blocks included. That works against `secure_delete` and "deleted … removed promptly". The `sessions` table from the Phase 1 data model is created but never written.
- **Reproduced:** `tests_audit/test_undo_log_retention.py` (type in a block, delete it, finish, mark done): `undo_log rows holding the deleted block's text after the room is done: 1`. Nothing removes it while the room is done.
- **Fix:** Clear a room's `undo_log` when it's finished (or after Phase 2's Apply), and prune by age as well. Write `sessions` rows (open/close, focus minutes), or drop the table in a migration and note it in the plan.

## F-20 — A relative or `~` vault path resolves inside the git checkout

- **Severity:** Low
- **Area:** Security and privacy (path safety), latent until Phase 2
- **Location:** `recon/config.py:55`, `:62-64`; `packaging/recon-launch:28` (`cd "$repo"`)
- **Finding:** `vault_path` isn't validated. `~/Cyber Vault` or `Vault` (hand-edited in `settings.toml`, E6) is resolved against the working directory, which the launcher sets to the repo. When Phase 2 starts writing, notes would land in the checkout and could be committed.
- **Reproduced:** `vault_folder(Settings(vault_path="~/Cyber Vault"), home)` → `/data/projects/Recon/~/Cyber Vault`.
- **Fix:** Validate in `Settings`: expand `~`, require an absolute path, and refuse paths inside the repo or Recon's data folder.

## F-21 — Any later notice replaces the delete toast, so its Undo goes early

- **Severity:** Low
- **Area:** ADHD rules (4: a 10 s Undo for deletions)
- **Location:** `recon/ui/PanelWindow.qml:47-50`
- **Finding:** `notify` replaces both the message and the action. A "Flag skipped" notice, a focus-block notice or a save error during the 10 seconds removes the delete's Undo button. Ctrl+Z still works.
- **Reproduced:** `tests_audit/test_toast_replaced.py`: `after a flag notice: Flag skipped. Recon never saves flags. | action:` (empty); `toastAction` is `None`.
- **Fix:** Queue notices behind an open Undo toast, or show actionless notices separately.

## F-22 — Qt's QML disk cache sits outside Recon's private cache folder

- **Severity:** Low
- **Area:** Security and privacy (permissions)
- **Location:** `recon/app.py:45-47` (application name `Recon` → `~/.cache/Recon/qmlcache`)
- **Finding:** Qt writes compiled QML to `$XDG_CACHE_HOME/Recon/qmlcache` (0755 folders, 0644 files), next to Recon's own 0700 `~/.cache/recon`. The cache holds compiled UI code only, never notes, so this is tidiness rather than a leak.
- **Reproduced:** `launch_probe.py` listing: `0o755 Recon`, `0o644 Recon/qmlcache/*.qmlc`.
- **Fix:** Set `QML_DISK_CACHE_PATH` to `paths.cache / "qmlcache"` before the engine is created (or set the organisation and app names so it lands in `recon/`).

## F-23 — `install_desktop.py`: `%` isn't escaped in Exec, and install overwrites someone else's entry

- **Severity:** Low
- **Area:** Correctness (task 1.15)
- **Location:** `scripts/install_desktop.py:51-62`, `:70-77`
- **Finding:** The Desktop Entry spec says a literal `%` in Exec must be written `%%`. A checkout path with `%` in it becomes a field code. `install` also overwrites an existing `io.github.tylerlight071.Recon.desktop` that it didn't write, although `uninstall` carefully checks for its marker.
- **Reproduced:** `render_entry(Path('/home/t/100%done/…/recon-launch'))` → `desktop-file-validate`: `contains a deprecated field code "%d"`.
- **Fix:** Escape `%` as `%%` in `exec_quote`. Refuse, or ask before, overwriting an entry without the marker.

## F-24 — Docs say things the code doesn't do

- **Severity:** Low
- **Area:** Docs
- **Location:** `README.md:12`; `CHANGELOG.md` (Database layer entry); `docs/THREAT_MODEL.md` T5 and T8; `docs/ARCHITECTURE.md:25`, `:89`, `:187`
- **Finding:** README still says "Phase 0 (foundations). There's no app to run yet." The CHANGELOG and T5 say a `kill -9` loses at most half a second of typing, which isn't true for titles (F-02). T8 says permissions are "checked at launch" (F-09). ARCHITECTURE:25 says file writes never run on the UI thread (F-05).
- **Reproduced:** By reading, against the reproductions above.
- **Fix:** Update each of these with the fixes above.

## F-25 — Phase 1's escaping and file-name code isn't in the committed mutation set

- **Severity:** Low
- **Area:** Tests and coverage
- **Location:** `pyproject.toml` `[tool.mutmut] only_mutate` (committed version)
- **Finding:** CLAUDE.md requires mutation testing on sanitising. Phase 1's sanitising is `engine/render.py` (`escape_lines`, `fenced`, `_cell`) and its path-safety code is `engine/names.py`. Neither is in the committed `only_mutate` list, so the 85% gate has only been shown for `flags_filter`. During the audit, an uncommitted working-tree change adding both, and a `mutmut` run, were in progress (not made by the auditor). The score wasn't re-measured here.
- **Reproduced:** `git show HEAD:pyproject.toml` lists only `flags_filter`, `stage`, `sanitise` and `factcheck/*`.
- **Fix:** Commit the wider list with its test selection, and record the scores for all three modules in the gate summary.

---

## What's good

- The flag filter is enforced at the last stop before SQLite, for every text field and the undo log, and is backed by raw-bytes tests that type key by key. Braced flags can't be kept, at any layer.
- Storage is careful: STRICT tables with CHECKs, parameterised literal SQL only, WAL with `synchronous=FULL` and `secure_delete`, migrations in one transaction each with an upgrade test, atomic writes with folder fsync, and an online-backup daily snapshot.
- The block autosave is a real max-latency debounce with retry, and the `kill -9` test proves it for block text.
- Logging is clean: every Phase 1 log call is a literal with IDs, counts or exception type names only. QML warnings log line numbers only, and QML can't reach the network.
- Gates are green: mypy strict, ruff, 98.6% branch coverage, a clean dependency audit, gitleaks, one accent button per screen (tested), no literal colours or sizes in QML (tested with a detector self-test), and contrast checked from `Theme.qml`.

## Mutation testing (after the audit, before the gate)

Run on the gate branch once the audit was written, with `engine/render.py` and `engine/names.py` added to `[tool.mutmut]` (F-25):

| Module | Killed |
| --- | --- |
| `recon/engine/flags_filter.py` | 111 / 111 |
| `recon/engine/render.py` | 220 / 230 |
| `recon/engine/names.py` | 64 / 68 |
| **Total** | **395 / 409 (96.6%)** |

The first run had 46 survivors. New tests killed every one that showed a real gap: strip and cut edges, a multibyte cut, lone surrogates, the unknown-type label, answer callouts, `%%` in titles and cells, backslashes in cells, and keeping Tyler's own spacing. The 14 left are equivalent mutants:

- **`render_export` (9):** the Jinja `Environment` options (`autoescape=False` versus `None` or removed, `StrictUndefined` removed, `keep_trailing_newline`, `lstrip_blocks`) and the `\n{3,}` collapse. The template has no indented tags or undefined names, and the final `rstrip() + "\n"` makes trailing-newline handling irrelevant.
- **`names._cut` (4):** `"utf-8"` versus `"UTF-8"` or Python's default (the same codec), and `<=` versus `<` at exactly the limit (the slice is the whole string either way).
- **`render.fenced` (1):** `default=0` versus `1`, since the fence is `max(3, longest + 1)` either way.

## Couldn't check

- **On Tyler's desktop:** launch time through the app menu on Wayland with the GPU renderer, 60 fps panel animations, idle memory with the real RHI backend, the KWin rule's behaviour, and the chime through PipeWire. Headless numbers are in the table above.
- **Real fsync latency** on Tyler's btrfs disks (scratch is tmpfs), so F-05's wait was shown with a stand-in commit.
- **Obsidian's rendering** of the export (F-08 used a CommonMark parser).
- **Mutation scores** (a separate run was in progress; see F-25).
- **Screen-reader output:** the accessible names and roles were checked in the tree, not with Orca.
