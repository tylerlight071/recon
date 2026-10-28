# ADR 0006: Vault bootstrap writes scaffolding outside Apply

- **Status:** Accepted
- **Date:** 2026-10-28
- **Context task:** 2.1 (issue #119)

## Context

Hard rule 3 says nothing reaches the vault without Apply: room output is staged, reviewed, then applied. SPEC.md also says Recon creates the vault on first launch, with its folders, a Bases `Home.md` and Obsidian's settings. That has to happen before any Apply, so the two need squaring.

## Decision

1. **Bootstrap writes only fixed scaffolding,** never room output:
   - the folders from SPEC.md's vault structure;
   - `Home.md` (rendered from `templates/vault/home.md.j2`);
   - three dashboards in `Bases/` (Rooms by path, Notes with something to check, Concepts);
   - `.obsidian/app.json`.

   Notes generated from the user's rooms still reach the vault only through Apply.
2. **It never replaces anything.**
   - Home and the dashboards are created only if missing (with a hard-link create, so even a race can't overwrite). After that they're the user's to edit.
   - `.obsidian/app.json` only gains keys it doesn't have (`useMarkdownLinks: false`, `alwaysUpdateLinks: true`, `attachmentFolderPath: "Attachments"`, checked against Obsidian 1.14.5). The user's values win, and an unreadable file is left alone.
   - It runs at every launch, and when Settings points at another folder, so a deleted folder or dashboard comes back. Nothing else changes.
3. **Obsidian has to have opened the vault once.** It refuses `obsidian://` links to vaults it doesn't know. So Home shows a one-time card ("Open your vault in Obsidian, once", with Copy path and "I've done that") until the user confirms. The confirmed folder is stored in settings (`obsidian_vault`), so choosing a different vault asks again, and a failing link can reset it (`forgetOpened`).

## Consequences

- The vault is created 0700, and its files 0600 like the rest of Recon's data.
- The Bases files use only keys in Obsidian's documented syntax (`filters`, `views` of type `table`, `order`, `groupBy`). The docs give no sort key, so sorting is left to Obsidian's own view controls.
- Tests can never create the real `~/Cyber Vault`: start-up tests use a throwaway home or vault, and a session-wide guard in `tests/conftest.py` fails the run if one appears.
