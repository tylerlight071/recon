---
type: "raw"
platform: "TryHackMe"
path: "Foundations"
module: "Computer Basics"
room: "Linux Basics"
captured_on: 2026-10-28
time_spent: 35
---
# Linux Basics (raw notes)

## Task 1: The shell

**Key idea**
The terminal runs a shell (bash here) that reads what I type and runs programs.

## Task 2: Moving around

**Command**
```sh
pwd  # print the folder I'm in
```

**Command**
```sh
cd /var/log  # go into the logs folder
```

**Command**
```sh
ls -la  # long list, including hidden files
```

## Task 3: Reading files

**Command**
```sh
cat notes.txt  # print a file
```

**Command**
```sh
cat -l notes.txt  # same but with line numbers
```

**Command**
```sh
grep -i error app.log  # lines containing error, any case
```

**Command**
```sh
find / -name '*.conf' 2>/dev/null  # look for config files, hide permission errors
```

**Key idea**
Files whose names start with a dot are hidden from a plain ls.

## Task 4: Permissions

**Key idea**
chmod 600 means only the owner can read and write the file.

**Command**
```sh
chmod +x backup.sh  # make the script runnable
```

**Key idea**
Got the answer for this task: 

**Key idea**
md5sum prints a 32 character hex hash, e.g.  for the word hello

**Room question**
What does -h do in df -h?

> [!question]- Answer
> Shows sizes in human-readable units like G and M
