# Manual tests

These are run once, on the finished app, as one session (decided at Gate 1). Each phase gate adds its steps here instead of waiting for them. Tick them off in the final test; note anything fiddly, slow, cluttered or unclear beside the step.

Launch Recon the way it will really be used: from the KDE app menu (`uv run python -m scripts.install_desktop` installs the entry).

## Phase 1: shell and capture (v0.1.0)

- [ ] Launch Recon from the app menu and time it to Home (budget: under 2 seconds). Start a real room you've done before.
- [ ] Write notes for at least three tasks, using four different block types. Along the way, use Tab, Ctrl+Z / Ctrl+Shift+Z, delete a block and press its Undo, and go back with Previous task.
- [ ] Close Recon mid-sentence, and once mid-title. Reopen it: check the "Where was I?" card, then carry on with nothing lost.
- [ ] Paste `THM{test}` into a block and into the task title: both are skipped with a "Flag skipped" notice.
- [ ] Paste an example MD5 into a block: "Not a flag, keep it" brings it back.
- [ ] Settings: turn pinning on (the panel docks to the right edge at full height), then off (it's a normal window again). Drag the panel width. Press "Play" on the chime and hear it. Try the cyan accent and Reduce motion.
- [ ] With Recon open, launch it again from the menu: it says "Recon is already open".
- [ ] Start a 15-minute focus block from the timer chip and let it finish (chime on): you get the notice and the sound.
- [ ] Finish the room and press "Export as Markdown". Check the folder picker is KDE's own, then open the file in Obsidian. Is anything missing or odd (including a line that starts with `%%` or `<`)?
- [ ] Press Done, then click the room on Home: its Finish screen comes back, and "Back to the room" reopens it at the last task.
- [ ] Anything that felt fiddly, slow, cluttered or unclear:

## Phase 2: processing and review (in progress)

- [ ] On first launch, `~/Cyber Vault` appears with its folders, `Home.md` and `Bases/`. Home in Recon shows "Open your vault in Obsidian, once": press Copy path, open the folder in Obsidian ("Open folder as vault"), then press "I've done that". The card goes and doesn't come back.
- [ ] In Obsidian, `Home.md` shows the three dashboards (empty until rooms are applied), and Settings → Files and links shows wikilinks on, "Automatically update internal links" on, and new attachments in `Attachments`.
- [ ] Settings → Models with Ollama running: the three models are listed and the dot is green. Stop Ollama (`systemctl stop ollama`, or quit it) and press Check again: an amber dot and "Couldn't reach Ollama…". Start it again and press Check again.
- [ ] In `settings.toml`, set `embedding_model = "nomic-embed-text"` (or any model you don't have) and reopen Settings: it names the model and shows `ollama pull …` with Copy. Put the setting back afterwards.
- [ ] After applying a room (once 2.4–2.7 land), open its room note, a concept note and a tool note in Obsidian. The properties panel shows every property, callouts fold, and the Mermaid diagram draws. No `%% recon` marker is visible in reading view. Note any point that misses or twists something you wrote.
- [ ] Edit a concept note in Obsidian (outside and inside its `%% recon` markers), then process another room that touches it. Before Apply, edit it again: Recon stops and offers to re-check rather than overwriting. After Apply, your text outside the markers is untouched and the old version is in `~/.local/share/recon/backups/<run>/`.
- [ ] Finish a room and watch the panel's processing line move through its steps. Close the panel while it runs: a notification says the room is ready (silently). Click it: the room opens in the panel.
- [ ] Finish two rooms quickly: the second says it's waiting, then processes after the first.
- [ ] Stop Ollama, finish a room: the panel says what went wrong with Retry, and a notification says so too. Start Ollama, press Retry.
- [ ] Quit Recon mid-processing, then reopen it: the room processes again without being asked.
- [ ] Open a room's review from the notification, from Home and from the panel. Read it top to bottom: is anything confusing, too long or missing? Fold and unfold each section from the keyboard (Tab, Space).
- [ ] Press Discard, then "Keep reviewing": nothing changes. Press Discard again and confirm: the room reopens in the panel exactly as you left it.
- [ ] Apply: a toast says how many notes were written, and they're in the vault.
