# Recon: TryHackMe Study Companion — Design Spec

As of 23 October 2026

## Overview and goals

Recon is a desktop app for CachyOS (KDE Plasma) that sits as a slim panel beside the browser while the user does a TryHackMe room. It says exactly what to write and where, one task at a time, then turns those rough notes into a tidy, linked Obsidian vault and short flashcard sessions. It is built for an ADHD brain: low friction to start, nothing to remember, nothing lost, small wins along the way. All AI runs locally through Ollama and Whisper; nothing leaves the PC.

It succeeds when:

- Starting a room takes under ten seconds, and the user always knows what to type next without thinking about it.
- Closing the app mid-room loses nothing, and reopening it shows where you left off in one line.
- Finishing a room takes one button, a quick quiz and a short review, ending in a finished Obsidian note.
- A concept learned in one room has exactly one note, which every later room adds to and links to.
- Wrong facts are caught and explained, never silently changed.
- Revision happens in short sessions that feel manageable, with one daily nudge.
- It works for any room or path and can take HackTheBox later without a redesign.

## Decisions locked in

These came out of two rounds of Q&A on 23 October and drive everything below.

| Area | Decision |
| --- | --- |
| Name | Recon |
| Form | Desktop GUI app, not a command; PySide6 with Qt Quick (QML) for a polished, animated UI |
| Desktop | CachyOS on KDE Plasma (Wayland), one 2560×1440 monitor; rooms done on CachyOS with TryHackMe's in-browser AttackBox |
| Where writing happens | In the app; Obsidian becomes the finished library to read and browse |
| Window | Slim side panel beside the browser, plus a normal main window for review, revision and dashboards |
| Capture | Typed blocks per task (Key idea, Command, Table, Screenshot, Question, Confused by, Room question, Voice) with a hint in each |
| Room questions and flags | Optional Room question block for knowledge questions worth keeping; flags are never stored |
| Generated content | Allowed only as short definitions when notes are thin, always labelled as generated and fact-checked |
| Voice | Local Whisper transcription into a block |
| ADHD supports | One task at a time, flexible focus timer, "Where was I?" resume, subtle progress and rewards |
| Look | Researched professional dark UI (Linear and Raycast style); no gimmicks |
| Scope | TryHackMe now; designed to take HackTheBox later without changes |
| Fact-checking | Flag and suggest; the user's original text is never changed |
| Review | Preview first, in the app, with Apply and Discard |
| Re-runs | Reopen a finished room in the app; changes merge, keeping the user's edits |
| Flashcards | Suggested from notes, quick keep or skip; stored in concept notes; reviewed in the app |
| Nudges | One daily desktop notification when cards are due |
| Timer | Flexible 15, 25 or 45 minutes, soft chime, break nudge after 90 minutes |
| Extras | End-of-room quiz, Ask my notes, weekly recap |
| Vault | Owned by the app, in the user's home folder, on CachyOS only; no sync needed |
| Backup | Daily copy of vault and app data to a folder or drive the user picks, last 14 kept |
| Screenshots | Embedded, with text and tables read by a local vision model |
| Dashboards | In the app, with matching Obsidian Bases views in the vault |
| Linking | Embedding search plus model confirmation |
| Concept notes | One idea per note |
| Terminal logging | Not for now |
| Paths | Nothing hardcoded to one path or room |

Also settled: Recon is developed with Claude Code as the coding agent, in a private GitHub repo, and earlier rooms are back-filled with a From memory mode.

## Ground rules

The tool only ever reads what the user wrote or pasted; it never touches tryhackme.com. TryHackMe's [Terms of Service](https://tryhackme.com/legal/terms-of-use) ban automated or programmatic extraction from the site, and its [Acceptable Use Policy](https://tryhackme.com/r/legal/acceptable-use-policy) bans systematically copying or compiling its content into an archive.

- **No fetching, scraping or browser automation** against TryHackMe, ever. While running, the app talks only to the local Ollama server. One-off setup downloads (packages, fonts, models) happen once, with the user told first.
- **Notes in the user's own words.** Pasting the odd table or snippet is normal note-taking; pasting whole tasks is not. The capture panel shows this as a quiet one-line reminder.
- **Private vault.** It is never published or shared. TryHackMe discourages sharing answers to active rooms, so answers stay out of anything public.
- **Honest output.** The tool never invents content the user didn't write. Additions it makes (a definition, a diagram) are marked as generated so they can be told apart from the user's own notes.

## The app

Two windows. While a room is open, a slim panel window is docked to the right of the browser, showing only the current task. Everything else opens in a normal main window with a left sidebar; the panel stays put. (On Wayland a pinned window can't also resize itself to full screen, so the two views are separate windows sharing the same data.) The user does rooms on CachyOS using TryHackMe's in-browser AttackBox, so the browser and Recon share one 2560×1440 screen: the panel defaults to 420 px (adjustable from 360 to 520), leaving about 2,100 px for the room and the AttackBox split. Review, revision and the library always open in the main window.

| Screen | Window | What it's for |
| --- | --- | --- |
| Home | Main | One big "Start a room" or "Carry on with <room>" button, cards due today, this week's progress |
| Room session | Panel | Writing notes for the current task, one task at a time |
| Finish | Panel | End-of-room quiz, then processing with a progress indicator |
| Review | Main | Everything the room will add to the vault; flags; Apply or Discard |
| Cards | Main | Keep or skip suggested flashcards, then the celebration screen |
| Revise | Main | Short flashcard sessions |
| Ask my notes | Main | Search or ask questions, answered only from the vault |
| Library | Main | Rooms, concepts and tools, with open flags; "Open in Obsidian" on everything |
| Settings | Main | Vault, models, timer, nudge time, theme accent |

**A room from start to finish:**

1. **Start.** Type the room name and number of tasks (path and module are remembered from last time). Ten seconds, then the first task is on screen.
2. **Capture.** One task at a time. Add blocks, paste screenshots, hold a key to talk. Everything saves as you type.
3. **Next task.** A single button moves on, with a small tick animation. The progress ring fills.
4. **Finish.** A quiz of three to five questions from what was just written. Then processing runs in the background; the user can close the panel.
5. **Review.** A notification says the room is ready. Review the changes and any flags, then Apply.
6. **Cards.** Flick through suggested flashcards: keep, edit or skip.
7. **Done.** A short completion animation, the room added to the path's progress, and an "Open in Obsidian" button.

**Rooms already done: From memory mode.** For back-filling earlier rooms, Start offers "From memory". Recon first shows one blank Key idea block per task and asks the user to write whatever they remember, without looking. Then it switches to the normal flow with the room open, and everything added in this second pass is quietly tagged as "filled in". The finished room note marks those points, and they get priority as flashcards, because they are exactly what didn't stick.

## Room session: what to write and where

The panel shows one task at a time and never an empty page: every task opens with one Key idea block already in place and its hint showing, so there is always an obvious first thing to type.

**Panel layout, top to bottom:**

1. **Header:** room name, "Task 3 of 7", progress ring, timer.
2. **Task title:** typed once, or left as "Task 3".
3. **Blocks:** the notes for this task, each a card with a coloured edge showing its type.
4. **Add bar:** one button per block type, always in the same place, each with a keyboard shortcut.
5. **Footer:** "Next task" as the one primary button; "Finish room" appears on the last task. A quiet "Previous task" button (Alt+Left) goes back to add or fix something; it never changes a task's status, and it's greyed out on the first task rather than hidden, so nothing moves.

**Block types:**

| Block | Shortcut | Hint shown in the empty block | What the app does with it |
| --- | --- | --- | --- |
| Key idea | Ctrl+1 | "What's the one thing this task is teaching? Your words, one line is fine." | Becomes a point in the room note; concepts in it get linked |
| Command | Ctrl+2 | "Paste or type the command. Add what it does after a #." | Command table; tool notes |
| Table | Ctrl+3 | "Paste a table, or type rows like: 80, HTTP, web" | Cleaned table; conversions checked in code |
| Screenshot | Ctrl+4 or paste | "Paste an image. Add a line on why it matters." | Embedded; text read by the vision model |
| Question | Ctrl+5 | "Something you want answered later." | Suggested answer, marked as generated |
| Confused by | Ctrl+6 | "What didn't click? Even 'no idea what X is'." | Explained in the review; added to revision |
| Room question | Ctrl+7 | "Copy a room question worth remembering, then your answer. Skip flags." | Answer kept hidden in a collapsed callout; offered as a flashcard |
| Voice | Hold F9 | "Talk it through: what was this task about?" | Transcribed, then shown as an editable Key idea |

**Flags are never stored.** Anything shaped like a flag (`THM{...}`, `flag{...}` or a long hash on its own) is left out of every note, card and backup, with a small notice saying it was skipped. Rooms about hashing show example hashes on purpose, so the notice has a "Not a flag, keep it" button that restores that one string. Flags carry no learning value, and keeping them around is how answers to active rooms leak.

Hints fade once typing starts and come back if a block is cleared. Blocks can be dragged to reorder, and Ctrl+Z works across the whole session. A tiny "Skip this task" link exists for tasks that are just "press the button", so a blank task never feels like failure.

## ADHD design rules

Every screen follows these rules; a design that breaks one gets changed, not excused. They draw on the usual guidance for ADHD-friendly interfaces: predictable layouts, small chunks, minimal distraction ([St Andrews](https://digitalcommunications.wp.st-andrews.ac.uk/2025/02/12/designing-for-users-with-adhd/)), progressive disclosure and autosave ([friction guide](https://claudeskills.info/skills/curiositech/some_claude_skills/ux-friction-analyzer/)), and forgiving recovery ([Design Monks](https://www.designmonks.co/blog/ui-ux-and-adhd)).

| Rule | How the app does it |
| --- | --- |
| One obvious next step | Every screen has exactly one primary button; everything else is quieter |
| Show only what's needed now | One task at a time; future tasks, settings and stats tucked away until asked for |
| Never a blank page | Pre-placed first block with a hint; room setup is two fields |
| Nothing can be lost | Autosave on every keystroke; Undo everywhere; nothing deletes without a 10-second Undo toast |
| Same thing, same place | Buttons and shortcuts never move between screens or rooms |
| Remember for the user | "Where was I?" card on open: "Task 4 of 7 in DNS in Detail, 2 days ago. Last note: 'TXT records hold text'." One click resumes |
| Small wins, often | Tick on each task, ring filling, a calm completion moment per room; no pressure mechanics |
| No shame | No red overdue counts, no "you broke your streak". A missed day just shows as a gap; copy is always kind and plain |
| Short sessions | Revision capped at 10 minutes by default; "Stop here" always visible and always fine |
| Time made visible | Timer and time-on-task shown quietly in the header, for time blindness, never as a countdown threat |
| Calm by default | No badges, pop-ups or sounds unless chosen; motion can be reduced in settings |

## Look and feel

The target is the restrained dark style of tools like Linear and Raycast: a near-black canvas, surfaces separated by tiny steps in lightness and hairline borders, mostly greyscale with one accent colour, crisp small type and quick, quiet motion ([Linear-style kit](https://cdn.jsdelivr.net/npm/@wrongstack/core@0.295.1/design-kits/linear-dark/KIT.md), [Linear tokens](https://open-design.ai/plugins/design-system-linear-app/)). It looks expensive through restraint, not decoration.

| Element | Choice |
| --- | --- |
| Background | Near-black with a faint cool tint; panels and cards one or two small steps lighter |
| Borders | 1 px hairlines, low contrast |
| Accent | One colour, used only for the primary button (with near-black text on it, since white fails contrast on these accents), focus and progress; default muted violet, with cyan or green as alternatives in settings |
| Status colours | Amber for flags, green for done; never red for anything the user did |
| Block types | A thin coloured left edge per type, muted, so type is visible at a glance without noise |
| Type | Inter for UI (13 to 15 px, medium weights); JetBrains Mono for commands and code |
| Spacing | 4 px grid; generous padding in the panel so it never feels cramped |
| Corners | 6 px small, 8 px cards, 12 px dialogs |
| Motion | 150 to 200 ms ease-out fades and slides; the progress ring and completion moment are the only "showy" animations; a Reduce motion setting makes all of it instant |
| Contrast | All text, hints included, at least 4.5:1 against its background, checked by a test |

**Toolkit: PySide6 with Qt Quick (QML).** QML is GPU-accelerated and built around animation, and it keeps the whole app in Python alongside the engine, Ollama and Whisper. Plain Qt Widgets look dated without a lot of styling work; Tauri with React would look just as good but needs a second language and a bridge to the Python engine. The app gets its own small component set (button, card, block, ring, toast) built on Qt Quick Templates, so every control matches the design rather than the system theme.

**Installing.** Packaged so it launches from the app menu like any other program, with its own icon; no terminal needed to run it.

## Vault structure

The app owns a vault folder in the user's home folder and creates it on first launch; Obsidian simply opens it. Folders are by note type rather than by path. Path and room live in each note's properties, so any path, module or room works with no setup.

`text
~/Cyber Vault/
├── Home.md                 Bases dashboard for browsing in Obsidian
├── 00 Raw notes/           the user's original capture per room, saved on Apply
├── 01 Rooms/
│   └── TryHackMe/
│       └── <Path>/         created from the room's path
├── 02 Concepts/            one idea per note: Hexadecimal, TCP handshake…
├── 03 Tools/               nmap, Wireshark, Burp: usage and flags
├── Attachments/            screenshots, named <room>-<task>-<n>.png
├── Recaps/                 weekly recaps the user chooses to save
└── Bases/                  .base files behind the Obsidian dashboards
`

- In-progress rooms live in the app's own database (autosaved), not the vault, so the vault only ever holds finished, reviewed notes.
- Rooms sit under a platform folder (`TryHackMe/`) so `HackTheBox/` can sit beside it later. Concepts and tools are shared across platforms.
- The app's index, backups, revision history and settings live outside the vault (see State and safety nets), so nothing clutters Obsidian's graph.

## Note types

Five note types in the vault, each with a fixed property set so Bases can query them and the tool knows what it owns. Generated sections sit between hidden markers (`%% recon:start summary %%` … `%% recon:end %%`) so the tool can update its own parts without touching anything the user adds outside them.

### Raw notes (saved from the app)

On Apply, the user's capture for the room is written to `00 Raw notes/` exactly as typed, block by block, with the room's properties at the top. It is never changed afterwards, so the original is always there to compare against.

### Room note (generated)

One per room in `01 Rooms/<Platform>/<Path>/`. Sections, in order:

1. **Summary**: three to five lines on what the room taught.
2. **Tasks**: one heading per task, the user's points tidied, with `[[links]]` to concepts and tools.
3. **Commands**: table of command, what it does, example, from anything in code blocks.
4. **Tables and diagrams**: The user's pasted tables cleaned up, screenshots embedded, Mermaid diagrams where a process was described.
5. **Check this**: warning callouts for flagged claims (see Fact-checking).
6. **Open questions**: The user's questions, each with a suggested answer marked as generated.
7. **Source notes**: a link to the raw notes in `00 Raw notes/`.

### Concept note (generated, then shared)

One idea per note in `02 Concepts/`, e.g. `Hexadecimal`, `Two's complement`, `TCP three-way handshake`. Sections: plain-English definition (the user's own; if the notes are too thin, one or two generated lines in a labelled "Generated definition" callout, fact-checked like everything else), explanation, tables and examples, gotchas, related concepts, flashcards. Later rooms append under a dated "From <room>" sub-heading rather than rewriting earlier text.

### Tool note (generated, then shared)

One per tool in `03 Tools/`: what it is for, a flags and usage table that grows each time a room uses it, and example commands with the room they came from.

### Flashcards (inside concept notes)

Kept cards sit at the end of their concept note in a format the Obsidian Spaced Repetition plugin also understands (`Question::Answer`, `?` for multi-line, `==cloze==`), so they remain usable outside the app. Each card carries a short hidden id so the app can track its review history.

### Home (set up once)

A Bases dashboard for browsing in Obsidian: rooms done by path, notes with open flags, recently touched concepts. The app has its own richer version of this.

### Properties

| Note type | Key properties |
| --- | --- |
| Raw notes | type, platform, path, module, room, captured_on, time_spent |
| Room | type, platform, path, module, room, date_done, time_spent, concepts, tools, open_flags, raw_notes |
| Concept | type, aliases, topic, seen_in (list of room links), open_flags, card_count, last_updated |
| Tool | type, aliases, category, seen_in, last_updated |

`open_flags` is a count the tool keeps up to date, so Bases can list every note with something left to check.

## Processing pipeline

Finishing a room starts eight steps that run in the background and end at the review screen; only Apply writes to the vault. The user can close the panel while it runs and gets a notification when it is ready.

*Diagram in the design doc (processing pipeline · 8 steps, 1 approval gate); the steps are listed below.*

Discard returns to the room session exactly as it was, so the user can add more and finish again.

1. **Parse (Python).** Read the room's blocks straight from the app's database: their types already say what is a command, a table, a screenshot or a question, so nothing has to be guessed.
2. **Read screenshots.** Each screenshot goes to the vision model, which returns any text and tables as structured data. Skipped when there are none.
3. **Extract.** The model reads the whole room and fills a fixed schema: summary, points per task, concepts, tools, commands, factual claims, answers to the user's questions, explanations for "Confused by" blocks, flashcard suggestions.
4. **Link.** Concepts and tools are matched to existing notes (see Linking).
5. **Fact-check.** Code checks, then the model review pass (see Fact-checking).
6. **Render.** Python templates turn the validated data into Markdown in a staging area, never the vault.
7. **Review screen.** Opens in the app with every change listed.
8. **Apply or Discard.** Covered in Preview, apply and re-runs.

A progress indicator in the panel shows which step is running, with a plain-English line ("Linking 6 concepts to your notes") rather than a spinner.

## Linking and duplicate prevention

Every concept or tool the model pulls out is matched against what already exists before anything new is created, so "TCP handshake", "three-way handshake" and "SYN/SYN-ACK/ACK" all land on one note.

1. **Index.** Every concept and tool note's title, aliases and definition are embedded and stored in the tool's index. The index refreshes on each run for any note whose file has changed, including ones the user edited by hand.
2. **Exact match.** A candidate whose name or alias exactly matches an existing note (case-insensitive) links straight to it.
3. **Similarity search.** Otherwise its name plus one-line definition is embedded and the closest five notes are retrieved.
4. **Model decision.** The model sees the candidate and the five neighbours and answers in a fixed format: same as an existing note, related to one, or new. Same → link and add the new wording as an alias. New → create the note.
5. **Thresholds.** Very close matches skip the model and link directly; distant ones are created as new without asking. The two cut-offs are config values, tuned in the build on the user's own notes.

Every merge or new note appears in the review note, so a wrong "same as" is caught before it is applied. Links inside a room note use the concept's canonical title with display text where the user's wording differs, e.g. `[[TCP three-way handshake|the handshake]]`.

## Fact-checking

Flags are suggestions, never edits: The user's sentence stays as written, and a warning callout beside it says what looks wrong and why. Checks run in two layers, and the deterministic layer always wins where it applies.

**Layer 1: checked in code, never by the model**

- Number conversions (binary, decimal, hex, octal) and anything that is arithmetic, such as subnet sizes from CIDR, worked out in Python and compared with what the user wrote.
- Well-known port numbers and protocols against a fixed reference table shipped with the tool.
- Command syntax only where it can be checked offline (e.g. a flag that doesn't exist in the tool's reference table). Unknown commands are left alone, not flagged.

**Layer 2: reviewed by the model**

A separate pass, with its own prompt, reads each factual claim and returns one of: looks right, likely wrong (with the correction and a one-line reason), or unsure. Only "likely wrong" becomes a flag; "unsure" is dropped rather than shown, to keep noise down.

**What a flag looks like**

`markdown
> [!warning] Check this
> You wrote: HTTPS runs on port 80.
> Likely: HTTPS uses port 443; port 80 is plain HTTP.
> Checked by: port reference table
`

**Resolving.** Flags appear as cards on the review screen with three buttons: "Fix my note" (opens that block to edit), "I was right" (dismisses it) and "Later" (writes the callout into the vault and lists it under Library > Open flags). A fixed or dismissed flag never comes back for the same sentence. Dismissals are logged so patterns of false flags can be tuned out.

## Preview, apply and re-runs

Nothing touches the vault until the user presses Apply. The review screen opens full-window and is split into short sections to work through top to bottom, each collapsible, with a count in its header.

1. **The room note:** rendered as Obsidian will show it.
2. **New notes:** concepts and tools it will create, marked New.
3. **Additions:** existing notes it will add to, showing only the added parts.
4. **Links:** every merge it made ("treating 'three-way handshake' as TCP three-way handshake"), each with an Undo.
5. **Flags:** as cards (see Fact-checking).

**Apply** writes everything, saves the raw notes, updates the index, then moves on to keeping or skipping flashcards. **Discard** throws away the staged changes and returns to the room session as it was. A sticky footer keeps both buttons visible however far the page scrolls.

**Re-runs on a finished room.** Library > the room > "Add more notes" reopens it in the panel with its blocks intact. Finishing again:

- Rebuilds generated sections that are unchanged since the last Apply, with the new material folded in.
- Leaves sections the user has edited in Obsidian alone, and shows the new material as "Suggested additions" for that section instead.
- Keeps resolved flags resolved, and keeps anything outside the generated markers untouched.

**Safety nets:** before Apply overwrites any file, the previous version is copied to the app's backup folder; the last 20 runs are kept, and Library > History can restore any of them with one click.

## Revision and extras

### Keeping flashcards

After Apply, suggested cards appear one at a time, large and centred: **Keep** (Enter), **Edit** (E) or **Skip** (S), with a counter ("4 of 9"). A room rarely suggests more than ten, so this takes about a minute.

### Revising

- Scheduling uses FSRS, the modern spaced-repetition algorithm, through the [py-fsrs](https://pypi.org/project/fsrs/) library.
- FSRS has four ratings; the app shows three to keep decisions quick: **Forgot**, **Got it**, **Easy** (mapped to Again, Good, Easy).
- Space flips a card; 1, 2, 3 rate it. A thin bar shows cards left, not time.
- Sessions default to 10 minutes or 20 cards, whichever comes first, with "Stop here" always visible. Leftover cards just wait; nothing turns red.
- Revision can be filtered by topic (networking, Linux, web) or by path.

### Daily nudge

One desktop notification at a time the user picks, only on days with cards due: "12 cards ready, about 5 minutes." Clicking it opens straight into revision. It is sent by a tiny background job, so it works even when the app is closed. Skipping it does nothing; there is no follow-up nag.

### End-of-room quiz

Pressing Finish room brings up three to five quick questions written from the notes just made, before processing starts. Answers are typed in a line or picked from options; the model marks them generously and shows the right answer either way. It never blocks finishing, and anything answered wrongly becomes the first flashcards for that room. A "Skip quiz" link is always there.

### Ask my notes

A search box that also takes questions ("what's the difference between TCP and UDP?"). The app finds the most relevant notes with the same embedding index used for linking, and the model answers only from them, with links to each note it used. If the vault doesn't cover it, it says so rather than answering from general knowledge.

### Weekly recap

Every week on a day the user picks, Home shows a recap card: rooms finished, time spent, new concepts, the hardest cards, and open flags. It is written in plain, encouraging language with no comparison to previous weeks unless asked for. A "Save to vault" button keeps a copy as a note.

## Obsidian setup

Obsidian needs no community plugins: the app does the writing, processing and revision, and Obsidian is where the user reads, browses and follows links. The app creates the vault with these core settings already in place.

| Feature | Type | Job |
| --- | --- | --- |
| [Bases](https://help.obsidian.md/bases) | Core | Home dashboard for browsing: rooms by path, open flags, recent concepts |
| Callouts, Mermaid, Graph view | Core | Flags, diagrams, seeing links grow |
| Properties | Core | Room, concept and tool metadata |
| [Spaced Repetition](https://community.obsidian.md/plugins/obsidian-spaced-repetition) | Community, optional | Only if the user ever wants to revise inside Obsidian; the card format already suits it |

**Why Bases over Dataview.** Bases is maintained by the Obsidian team and is faster; Dataview's latest release is still beta and development has slowed ([guide](https://www.dsebastien.net/the-complete-guide-to-dataview-in-obsidian/)). The dashboard only needs filtering and grouping on properties, which Bases covers.

**Settings set on creation.** Wikilinks on; "Automatically update internal links" on, so renaming a concept doesn't break rooms; new attachments to `Attachments/`.

**Opening notes from the app.** Every room, concept and tool in the app has "Open in Obsidian", which uses Obsidian's own `obsidian://open` link, so no plugin is needed for the two to work together. Obsidian only follows these links for vaults it already knows, so after creating the vault Recon asks the user to open the folder in Obsidian once, and shows the buttons only after that.

## Models and hardware

Default: Qwen 3.5 9B for the thinking work and screenshots, Qwen3 Embedding 0.6B for linking and search, and Whisper large-v3-turbo for voice, all local on the RTX 5070 Ti (16 GB). The 9B leaves VRAM spare for a long context, so a whole room's notes go in one pass.

| Role | Default | Fallback | Why |
| --- | --- | --- | --- |
| Structuring, fact-check, quiz, Ask my notes | `qwen3.5:9b` | `gemma4:12b` | Both are listed as strong general picks for 16 GB cards ([cheat sheet](https://computingforgeeks.com/ollama-models-cheat-sheet/)); the 9B leaves more room for context |
| Screenshots | `qwen3.5:9b` (vision is built into the standard tag) | `qwen3-vl:8b` | One model avoids swapping; Qwen3-VL is the fallback for hard screenshots ([guide](https://bestllmfor.com/guide/llm-multimodal-vision-local-ollama/)) |
| Embeddings | `qwen3-embedding:0.6b` | `nomic-embed-text` | Small (about 640 MB) with a 32K-token window ([comparison](https://localaimaster.com/blog/best-ollama-embedding-models)) |
| Voice | Whisper `large-v3-turbo` via faster-whisper | `distil-large-v3` | Much faster than large-v3 with close accuracy in English; about 3.5 GB of VRAM ([benchmarks](https://gigagpu.com/whisper-turbo-v3-self-hosted/), [VRAM](https://pypi.org/project/speakerscribe/0.1.0/)) |

**Bake-off before committing.** Phase 2 runs both text candidates on three of the user's real rooms and compares them on schema errors, missed concepts, wrong merges and false flags. The winner goes in the config; switching later is a one-line change.

**How the model is used.** Every call uses Ollama's [structured outputs](https://docs.ollama.com/capabilities/structured-outputs): a JSON schema in the `format` field and temperature 0. Responses are validated with Pydantic and retried once on failure. The model never writes Markdown directly; Python templates render every note, so formatting is identical every time and a bad model response can't break a note.

**Hardware notes.** Ollama runs one large model at a time; the embedding model is small enough to sit alongside it. Whisper loads only while a voice clip is being transcribed and unloads after a minute idle, so it never competes with processing. Ollama needs a recent version for the newer model families; the app checks this on first launch and says plainly what to update. Maya shares the same Ollama server, so running both at once slows each but breaks neither.

## State and safety nets

Everything the app needs to remember lives in its data folder (`~/.local/share/`, the standard Linux place), outside the vault. The vault stays clean Markdown, and the search index can be rebuilt from it at any time.

| Store | Holds | If lost |
| --- | --- | --- |
| `app.db` (SQLite) | Rooms in progress and their blocks, card review history, sessions, time spent, settings | The serious one: backed up automatically each day, last 14 kept |
| `index.db` | Embeddings, aliases, section hashes, flag states, which run wrote what | Rebuilt from the vault with one button in Settings |
| `audio/` | Voice clips until transcribed | Deleted after transcription unless "Keep recordings" is on |
| `runs/<run id>/` | Staged changes, raw model responses, timings | Nothing; kept for debugging, cleared after 30 days |
| `backups/<run id>/` | Previous version of every vault file Apply changed | Last 20 runs kept |
| `app.log` | One line per action: room, result, flags, duration | Nothing |

Screenshots for rooms still in progress sit in a `media/` folder in the same place, already cleaned of hidden data (location, camera details), and are copied into the vault's `Attachments/` on Apply.

**Rules that can't be broken:**

- Every keystroke in a room session is saved within a second; a crash or power cut loses at most that second.
- Nothing in `00 Raw notes/` is ever changed after it is written.
- Only one room processes at a time; finishing a second room queues it and says so.
- If the vault changed between review and Apply (the user edited a concept in Obsidian meanwhile), Apply stops and offers to re-check rather than overwriting.

**Off-machine backup.** Settings has one field: a backup folder, ideally on another drive. Each day Recon copies the vault and `app.db` there and keeps the last 14 copies. If the folder is missing (drive unplugged), Home shows a quiet note, never a warning pop-up.

## Build phases

Recon is developed in a private GitHub repo called `recon`, with Claude Code as the coding agent, running locally on CachyOS so the app can be launched and tested against the real GPU, Ollama and KDE. Its first job is checking how Ollama is installed and whether it is recent enough, before any model choices are relied on. Before any code, the repo gets this spec, a phased build plan with acceptance checks, and a CLAUDE.md holding the design rules, stack and conventions, so every session starts from the same ground. Production standards apply throughout: strict typing, high test coverage, mutation testing on the safety-critical parts, a security and privacy threat model, and an independent code audit at every phase gate. Then five phases, each leaving something usable, so the user is taking notes in the app after phase 1 and can start back-filling earlier Pre Security rooms as a refresher straight away.

1. **Shell and capture.** Design system and components, Home, start a room, the side panel with blocks and hints, autosave, "Where was I?", timer. Finished rooms export as plain Markdown for now. *Done when:* a real room is captured comfortably start to finish without touching the mouse more than needed.
2. **Processing and review.** Vault creation, the pipeline, review screen, Apply and Discard, backups. Model bake-off happens here. *Done when:* three real rooms produce clean room and concept notes with no hand fixes to formatting.
3. **Linking and fact-checking.** Embedding index, matching and appending, code checks, model review, flag cards. *Done when:* rooms that share concepts create no duplicates, and a seeded set of deliberate mistakes is caught with no more than one false flag per room.
4. **Cards and revision.** Keep or skip, FSRS revision sessions, daily nudge, end-of-room quiz, From memory mode, completion moment and progress. *Done when:* a week of real use with daily sessions under 10 minutes.
5. **Voice, screenshots and extras.** Whisper, vision pass, Ask my notes, weekly recap, re-runs on finished rooms. *Done when:* adding to a finished room merges without losing any edits made in Obsidian.

## Risks and limitations

| Risk | Effect | Mitigation |
| --- | --- | --- |
| Wayland stops apps placing their own windows | The panel can't dock itself beside the browser | Recon writes a KDE window rule (in `kwinrulesrc`, then asks KWin to reload) that pins the panel to the right edge at full height; if a reload doesn't take, a tiny KWin script does the same job ([KDE forum](https://discuss.kde.org/t/applying-window-rule-via-command-line/37452)). Switchable in Settings |
| Global hotkeys on Wayland | Hold F9 to talk may not work while the browser has focus | Register F9 through the global shortcuts portal (called directly over D-Bus), which on Plasma 6 reports both press and release, so true hold-to-talk works while the browser is focused ([global-shortcut-portal](https://pypi.org/project/global-shortcut-portal/)). A mic button in the panel is the fallback |
| Scope is large | Motivation dips before it's useful | Phase 1 is useful on its own; each phase is small enough to finish in a few sessions |
| A 9B model is confidently wrong | Bad flag, quiz answer or suggested answer | Code checks override it; flags are suggestions; "unsure" is dropped; dismissed flags are logged |
| Very thin notes | Thin room note | It structures what's there and never pads with invented content; hints nudge for a little more |
| Wrong concept merge | Two ideas end up in one note | Every merge shows on the review screen with Undo |
| Screenshot text misread | Wrong value in a table | Vision text sits in a collapsed callout under the image, never merged into the user's tables without review |
| Whisper mishears jargon ("nmap" as "in map") | Odd words in a voice block | Transcripts land as editable text; a short custom vocabulary of tool names is passed to Whisper |
| Speed | A long room could take a few minutes | Runs in the background with a notification when ready |

## Open questions

None. The last six were settled on 23 October: KDE Plasma, room questions kept hidden with flags never stored, labelled generated definitions allowed, CachyOS only with no sync, a daily off-machine backup, and the name Recon. Each is folded into the sections above.
