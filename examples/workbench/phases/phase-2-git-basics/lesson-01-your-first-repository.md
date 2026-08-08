---
title: Your First Repository
phase: 2
lesson: 1
duration_minutes: 15
prerequisites: ["1.2"]
skills_unlocked: [repo-keeper]
objectives:
  - id: what-a-commit-is
    kind: knowledge
    text: Say what a commit is and what the staging area is for
    about: [1, 2]
  - id: init-and-commit
    kind: practice
    text: Turn a directory into a git repository and commit work to it
    verify: A git repository exists whose log shows at least one commit made by the learner
    check: git log --oneline
    about: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept

Everything you did in the shell so far shares one weakness: there is only ever the current
version. Overwrite a good line with a bad one and the good one is simply gone.

Git fixes that. A **repository** is an ordinary directory that git has been asked to watch:

```bash
git init
```

That single command creates a hidden `.git` directory, and from then on git can remember
every version of every file — but only when you ask it to. The unit of remembering is the
**commit**: a snapshot of chosen files at a chosen moment, stamped with an author, a date,
and a message saying *why*.

Committing is deliberately a two-step act:

```bash
git add notes.txt        # stage: choose what the snapshot will contain
git commit -m "Add the harbor meeting note"   # commit: take the snapshot
```

The **staging area** between them is what lets a commit say one thing. Your directory may
contain three half-finished changes; `git add` picks out just the one that belongs in this
snapshot, and the message can then honestly describe it.

Between commands, `git status` tells you where everything stands — which files are changed,
which are staged, which git has never seen. When in doubt, run it. It is the `ls` of git.

## Key Terms

- **Repository**: A directory whose history git is tracking, marked by a hidden `.git` folder
- **Commit**: A recorded snapshot of the staged files, with an author, a date, and a message
- **Staging area**: The waiting room where `git add` gathers exactly what the next commit will contain
- **Working tree**: The ordinary files you see and edit — the current version of everything

## Hands-On Exercise

Put your `practice` directory under version control.

1. `cd practice`, then `git init` — watch it announce the new repository.
2. `git status` — everything is "untracked": git can see the files but remembers nothing yet.
3. `git add notes.txt`, then `git status` again — notes.txt has moved to "to be committed".
4. `git commit -m "Add harbor notes"` — the first snapshot. If git asks who you are, follow
   the two `git config` lines it prints, then commit again.
5. Change something: `echo "bring the rope" >> notes.txt`, then `git add notes.txt` and
   `git commit -m "Add packing reminder"`.
6. `git log --oneline` — a history, newest first, in your own words.

## Quick Quiz

1. What is a commit?
   - a) A backup of the whole computer
   - b) A recorded snapshot of the staged files, with a message and an author
   - c) A copy of the repository on another machine
   - d) A command that deletes history

   **Answer:** b) A recorded snapshot of the staged files, with a message and an author —
   each commit captures exactly what was staged at that moment, and history keeps it
   permanently.

2. What is the staging area for?
   - a) Choosing exactly which changes the next commit will contain
   - b) Storing deleted files
   - c) Sharing files with other people
   - d) Running programs in isolation

   **Answer:** a) Choosing exactly which changes the next commit will contain — `git add`
   gathers changes there, so a commit can say one clear thing even when the directory holds
   several unrelated edits.

3. What does `git init` do?
   - a) Downloads a repository from the internet
   - b) Commits every file in the directory
   - c) Creates a new, empty repository in the current directory
   - d) Installs git

   **Answer:** c) Creates a new, empty repository in the current directory — it writes the
   hidden `.git` directory where history will live. Nothing is committed until you commit.

## Next Up

A history now exists. Next you'll read it, compare versions, and bring an older one back —
the part that makes every experiment safe.
