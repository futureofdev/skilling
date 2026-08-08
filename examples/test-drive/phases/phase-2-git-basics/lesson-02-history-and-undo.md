---
title: History and Undo
phase: 2
lesson: 2
duration_minutes: 15
prerequisites: ["2.1"]
skills_unlocked: [time-traveller]
objectives:
  - id: how-history-protects
    kind: knowledge
    text: Explain how an append-only history makes experiments safe
    about: [1, 3]
  - id: read-and-restore
    kind: practice
    text: Read a file's history and restore an earlier version of it
    verify: >
      The learner brought back an earlier committed version of a file using git, without
      retyping its contents
    about: [2]
  - id: commit-in-small-steps
    kind: practice
    text: Commit in steps small enough that each message can honestly say why
sections:
  key_terms: present
  exercise:
    status: none
    intent: >
      The homework is the exercise: you'll practise reading history and restoring files on
      a repository of your own work.
  next_up:
    status: none
    intent: "Last lesson of the course — there is nothing after this to tease."
---

## The Concept

A commit is not a backup you hope never to need. It is a **save point you can build on** —
and that changes how boldly you can work.

History in git is append-only: committing never overwrites an earlier commit, it adds a new
one on top. So the moment something works, commit it. From then on, any experiment is safe,
because the working version is permanent and the experiment is just the difference on top.

Three commands turn that history from a comfort into a tool:

```bash
git log --oneline            # the story so far: every commit, newest first
git diff                     # what has changed since the last commit
git restore notes.txt        # throw away uncommitted changes to a file
```

And when the bad version has already been committed, reach further back:

```bash
git restore --source HEAD~1 notes.txt   # bring back the previous committed version
```

`HEAD` names the latest commit; `HEAD~1` the one before it. Restore copies that old version
into your working tree — nothing is deleted, no history is rewritten, and you can commit
the restoration like any other change.

One habit makes all of this work: **commit in small steps**. A commit that changes one
thing gets a message that says why, and a history of such commits reads like a logbook. A
commit that changes everything gets a message like "stuff", and a history of those protects
nothing, because no old version is one you'd want back.

## Key Terms

- **Log**: The list of commits that led to the current state, newest first
- **Diff**: The line-by-line difference between two versions
- **Restore**: Copying a chosen committed version of a file back into the working tree
- **HEAD**: Git's name for the latest commit on the current branch

## Quick Quiz

1. Why does committing before an experiment make the experiment safe?
   - a) Git stops you from editing committed files
   - b) The committed version is permanent, so anything after it can be undone
   - c) Experiments run faster inside a repository
   - d) Git automatically fixes mistakes

   **Answer:** b) The committed version is permanent, so anything after it can be undone —
   history is append-only, which makes every commit a save point nothing later can
   overwrite.

2. You broke `notes.txt` and want yesterday's committed version back. Which approach works?
   - a) Retype it from memory
   - b) Delete the `.git` directory
   - c) Restore the file from the commit that has the good version
   - d) Make a new empty file with the same name

   **Answer:** c) Restore the file from the commit that has the good version — git keeps
   every committed version, so getting one back is a command, not an act of memory.

3. What does `git log` show?
   - a) The commits that led to the current state, newest first
   - b) Only files that have never been committed
   - c) Errors in your code
   - d) The contents of every file

   **Answer:** a) The commits that led to the current state, newest first — the log is the
   repository's story: who changed what, when, and why the message says.

## Homework Assignment

### A Repo of Your Own

**Objective:** Put a real folder of your work under version control and prove you can
travel its history.

Use the folder you organised for the Shipshape homework, or any small project of your own.

- [ ] A repository initialised in a folder of your own work
- [ ] A history of commits whose messages each say why the change was made
- [ ] One file deliberately changed for the worse, then restored from an earlier commit
- [ ] The output of `git log --oneline`, captured for your tutor

**Stretch Goals:**
- [ ] A `.gitignore` that keeps clutter out of `git status`
- [ ] An experiment tried on a branch and merged back

**Submission:** Tell your tutor when it's ready and share the log output and the restore
commands you used.
