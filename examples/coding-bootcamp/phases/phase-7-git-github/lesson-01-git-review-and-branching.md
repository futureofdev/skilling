---
title: "Git Review and Branching"
phase: 7
lesson: 1
duration_minutes: 35
prerequisites: ["6.8"]
skills_unlocked: []
objectives:
  - id: review-git-basics
    text: "Review the git basics: init, add, commit, log"
  - id: create-and-switch-branches
    text: "Create and switch branches"
    tested_by: [1]
  - id: why-branching-matters
    text: "Understand why branching matters"
    tested_by: [2]
  - id: merge-a-feature-branch
    text: "Merge a feature branch"
    tested_by: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
**Branches** let you work on features without affecting your main code. It's like working on a copy — when it's done, you merge it back.

```bash
# Current state
git log --oneline
# a1b2c3 Previous commit

# Create and switch to a new branch
git checkout -b feature/add-blog-page
# Or: git switch -c feature/add-blog-page

# Check your branch
git branch
# * feature/add-blog-page
#   main

# Work on your feature, then commit
git add src/pages/blog.astro
git commit -m "feat: add blog page"

# Switch back to main
git checkout main

# Merge the feature in
git merge feature/add-blog-page

# Delete the branch (it's been merged)
git branch -d feature/add-blog-page
```

**Why branch?**
- Isolate work-in-progress from stable code
- Work on multiple features simultaneously
- Easy to abandon a branch if the approach doesn't work

## Key Terms
- **Branch**: A parallel version of your repository
- **`git checkout -b`**: Create and switch to a new branch
- **`git merge`**: Incorporate changes from one branch into another
- **HEAD**: Pointer to your current position in the git history
- **`main` (or `master`)**: The primary branch of your project

## Hands-On Exercise
```bash
cd ~/projects/zero-to-portfolio

# See current branches
git branch

# Create a feature branch
git checkout -b feature/update-bio

# Make a change (update About section)
# ... edit src/components/About.astro ...
git add src/components/About.astro
git commit -m "feat: update bio text in About section"

# Switch back and merge
git checkout main
git merge feature/update-bio
git log --oneline --graph  # see the merge
```

## Quick Quiz
1. What does `git checkout -b feature/new-page` do?
   - a) Checks out an existing branch
   - b) Creates a new branch AND switches to it
   - c) Deletes a branch
   - d) Lists all branches

   **Answer:** b) Creates and switches — `-b` means "new branch".

2. What is the purpose of the `main` branch?
   - a) It's the fastest branch
   - b) It represents the stable, production-ready version of your code
   - c) It's where all commits go by default
   - d) It's automatically deployed

   **Answer:** b) Stable code — feature branches merge INTO main when they're ready.

3. After merging a feature branch, what should you do with it?
   - a) Keep it permanently for history
   - b) Delete it — it's been merged and is no longer needed
   - c) Archive it
   - d) Convert it to main

   **Answer:** b) Delete it — `git branch -d branch-name` keeps things clean.

## Next Up
**Merging and Resolving Conflicts** — what to do when two branches change the same code.
