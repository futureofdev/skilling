---
title: "Merging and Resolving Conflicts"
phase: 7
lesson: 2
duration_minutes: 35
prerequisites: ["7.1"]
skills_unlocked: []
objectives:
  - id: what-conflicts-are
    text: "Understand what merge conflicts are"
    tested_by: [1]
  - id: resolve-conflicts-manually
    text: "Resolve conflicts manually"
    tested_by: [2]
  - id: the-vs-code-merge-ui
    text: "Use VS Code's merge conflict interface"
  - id: prevent-conflicts
    text: "Prevent conflicts with good practices"
    tested_by: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
A **merge conflict** happens when two branches change the same lines of the same file. Git can't automatically choose which change to keep — you must decide.

```
<<<<<<< HEAD (your current branch)
color: #00D4AA;
=======
color: #FF6B35;
>>>>>>> feature/new-colors (incoming branch)
```

You must edit the file to resolve: keep one, keep both, or write something new. Then:
```bash
git add the-resolved-file.css
git commit -m "resolve: merge conflict in global.css"
```

**In VS Code:** When a conflict exists, VS Code shows "Accept Current Change" / "Accept Incoming Change" / "Accept Both Changes" buttons — click the right one.

**Avoiding conflicts:**
- Communicate with teammates about who's working on what
- Merge/pull `main` into your branch frequently
- Make branches short-lived

## Key Terms
- **Merge conflict**: Two branches changed the same lines — git needs human decision
- **Conflict markers**: `<<<<<<<`, `=======`, `>>>>>>>` — git inserts these to mark conflicting sections
- **Resolution**: Manually editing the file to the correct final state

## Hands-On Exercise
Create a deliberate conflict to practice:
```bash
# Branch A changes line 5 of a file
git checkout -b branch-a
# edit file.txt line 5 → "Branch A was here"
git add file.txt && git commit -m "branch a change"

# Branch B also changes line 5
git checkout main
git checkout -b branch-b
# edit file.txt line 5 → "Branch B was here"
git add file.txt && git commit -m "branch b change"

# Merge branch-a into main
git checkout main
git merge branch-a

# Now try to merge branch-b — CONFLICT!
git merge branch-b
# Edit the conflict, then:
git add file.txt
git commit -m "resolve: merge branches a and b"
```

## Quick Quiz
1. What does `<<<<<<< HEAD` mark in a conflict?
   - a) The start of your file
   - b) Your current branch's version of the conflicting code
   - c) The incoming branch's changes
   - d) A git error

   **Answer:** b) Your current branch's version — between `<<<` and `===`.

2. After resolving a conflict manually, what must you do?
   - a) Run `git conflict --resolved`
   - b) `git add` the resolved file, then `git commit`
   - c) Delete the conflict markers and nothing else
   - d) Run `git merge --continue`

   **Answer:** b) Stage the resolved file then commit — git sees the conflict is resolved when you commit.

3. What's the best way to prevent merge conflicts?
   - a) Never branch
   - b) Communicate about who's working on which files, keep branches short-lived, pull main frequently
   - c) Only one person commits at a time
   - d) Conflicts are unavoidable — there's no way to prevent them

   **Answer:** b) Communication + short branches + frequent syncing — conflicts happen but can be minimized.

## Next Up
**GitHub** — pushing your code to the cloud and collaborating with others.
