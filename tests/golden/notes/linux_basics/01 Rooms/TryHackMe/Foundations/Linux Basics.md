---
type: "room"
platform: "TryHackMe"
path: "Foundations"
module: "Computer Basics"
room: "Linux Basics"
date_done: 2026-10-28
time_spent: 35
concepts: ["[[Bash Shell]]", "[[File Permissions]]", "[[Hidden Files]]", "[[File Hashing]]", "[[Disk Usage]]"]
tools: ["[[pwd]]", "[[cd]]", "[[ls]]", "[[cat]]", "[[grep]]", "[[find]]", "[[chmod]]", "[[md5sum]]"]
open_flags: 0
raw_notes: "[[Linux Basics (raw notes)]]"
---
# Linux Basics

## Summary

%% recon:start summary %%
- The room covers basic Linux shell operations using the [[Bash Shell|bash]] terminal.
- It teaches how to navigate directories, list files, and read file contents.
- Key topics include [[Hidden Files|hidden files]], [[File Permissions|file permissions]] with [[chmod]], and calculating file hashes with [[md5sum]].
- It also explains common command flags like -h for human-readable output in [[Disk Usage|df]].
%% recon:end %%

## Tasks

%% recon:start tasks %%
### Task 1: The shell

- The terminal runs a shell ([[Bash Shell|bash]]) that reads input and executes programs.

### Task 2: Moving around

- [[pwd]] prints the current folder path.
- [[cd]] changes directory to a specified path.
- [[ls]] -la lists all files including hidden ones in long format.

### Task 3: Reading files

- [[cat]] prints the contents of a file to the screen.
- [[cat]] -l prints file contents with line numbers.
- [[grep]] -i error searches for lines containing 'error' ignoring case.
- [[find]] looks for files matching a name pattern and suppresses permission errors with redirect.
- Files starting with a dot are hidden from a plain [[ls]] command.

### Task 4: Permissions

- [[chmod]] 600 sets permissions so only the owner can read and write the file.
- [[chmod]] +x makes a script executable.
- [[md5sum]] prints a 32 character hex hash for a file or string.

**Room question:** What does -h do in df -h?

> [!question]- Answer
> Shows sizes in human-readable units like G and M
%% recon:end %%

## Commands

%% recon:start commands %%
| Command | What it does | Task |
| --- | --- | --- |
| `pwd` | print the folder I'm in | 2 |
| `cd /var/log` | go into the logs folder | 2 |
| `ls -la` | long list, including hidden files | 2 |
| `cat notes.txt` | print a file | 3 |
| `cat -l notes.txt` | same but with line numbers | 3 |
| `grep -i error app.log` | lines containing error, any case | 3 |
| `find / -name '*.conf' 2>/dev/null` | look for config files, hide permission errors | 3 |
| `chmod +x backup.sh` | make the script runnable | 4 |
%% recon:end %%

## Source notes

%% recon:start source %%
Your notes as you wrote them: [[Linux Basics (raw notes)]]
%% recon:end %%
