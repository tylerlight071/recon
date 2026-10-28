# ADR 0007: How the pipeline turns a room into vault notes

- **Status:** Accepted
- **Date:** 2026-10-28
- **Context task:** 2.3 (issue #121)

## Context

Task 2.3 builds pipeline steps 1, 3 and 6 (parse, extract and render) for text blocks. SPEC.md fixes the note types, their sections and their properties. It leaves open how far to trust a 9B model's reply, how to name files, and how to write properties safely. Running the three fixture rooms through `qwen3.5:9b` showed what goes wrong in practice:
- with thinking off, it sometimes returned no tasks at all;
- it never copied the user's own sentences into `own_words`;
- it restated the user's questions and confusions as facts ("There is a quick way to do decimal to hex in your head");
- it gave concepts tool names as aliases (`cat` as an alias of "Reading files").

## Decision

1. **The model returns data; code decides what's true about the user's notes.** After schema validation, `engine/extract.check`:
   - keeps a task point only if it names a Key idea, Command, Table or Voice block in its own task, so questions and confusions can never become points;
   - drops concepts and tools the notes never mention, merges duplicates, and keeps aliases to four words or fewer;
   - keeps `own_words` only if the sentence is really in the notes. If it isn't, the first Key idea sentence that names the concept within its first four words is used; otherwise the definition is generated and labelled;
   - keeps a tool's flags only if they appear in the user's commands for that tool (parsed in `engine/commands.py`);
   - keeps answers for Question blocks only, explanations for Confused by blocks only, and `related` links only to concepts from this room;
   - removes tool names from concept names and aliases, so a tool's name always links to its tool note;
   - strips flags from every string again.
2. **Commands, tables, raw notes and room questions are the user's text, rendered by code.** The Commands table and the tool notes' examples come from the user's Command blocks, and their `# comment` is "What it does". The model never rewrites them.
3. **The schema forces the shape.**
   - `summary` needs at least 3 lines and `tasks` at least one entry. With these minimums, the empty replies stopped and replies became repeatable at temperature 0.
   - Lengths are capped, and names can't contain link or markup characters.
4. **Every call sets `num_ctx` to 16,384** (`services.ollama.CONTEXT_TOKENS`). Ollama defaults to a 4k context on cards under 24 GB and truncates silently, which is too small for a room plus its schema. Thinking stays off by default (`model_thinking` in settings). With thinking on, one room gave noticeably richer replies, but took about 77 s instead of about 28 s; the bake-off (2.9) decides.
5. **File names and links.**
   - Room notes go in `01 Rooms/<platform>/<path>/<room>.md`.
   - Raw notes go in `00 Raw notes/<room> (raw notes).md`, so `[[<room>]]` always means the room note and is never ambiguous.
   - Concepts and tools are `02 Concepts/<name>.md` and `03 Tools/<name>.md`.
   - Every name goes through `names.file_name`.
   - Links in the room note are the first mention of a concept or tool in each line, matched by its name or aliases. Longest match wins, and inline code is skipped. Phase 3's linking replaces this matching with embeddings and the index.
6. **Properties are JSON scalars and lists**, which YAML reads exactly, so a room name containing quotes, newlines or `---` can't break out of the frontmatter. `time_spent` is whole minutes, so Bases can sort and sum it.
7. **Sections.**
   - Each generated section sits under its heading, between `%% recon:start <name> %%` and `%% recon:end %%`. Section names are fixed words, or `from-<room>` for a concept's per-room notes.
   - Empty sections (no commands, tables, questions or related concepts) are left out.
   - "Check this" is left out until fact-checking (Phase 3) has flags to show.

## Consequences

- Recorded replies for the three fixture rooms live in `tests/fixtures/responses/`, and are re-recorded with `scripts/record_responses.py` whenever the prompt or schema changes. Golden notes in `tests/golden/notes/` are rewritten with `tests/engine/make_golden.py`, and every diff is read before committing.
- `sanitise.py` is mutation-tested, and all 119 of its mutants are killed.
- Word-matched links can be wrong: "Network layer" links to a "Network" concept. These links are visible on the review screen (2.6), and Phase 3's linking replaces the matching.
- Points can still miss something the user wrote. The raw notes are always kept in full, and the bake-off scores what's missed.
