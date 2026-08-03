---
title: "GitHub: Remote Repositories"
phase: 7
lesson: 3
duration_minutes: 35
prerequisites: ["7.2"]
skills_unlocked: []
objectives:
  - id: create-a-repository
    text: "Create a GitHub repository"
  - id: connect-a-remote
    text: "Connect a local repository to GitHub"
    tested_by: [1]
  - id: push-code
    text: "Push code to GitHub"
    tested_by: [2]
  - id: pull-changes
    text: "Pull changes from GitHub"
    tested_by: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
GitHub is a cloud hosting service for git repositories. Your local git repo lives on your computer — GitHub hosts a copy online.

```bash
# After creating a repo on github.com:

# Connect your local repo to GitHub
git remote add origin https://github.com/yourusername/your-repo.git

# Push your code for the first time (-u sets tracking)
git push -u origin main

# After that, just:
git push

# Pull changes from GitHub (others' commits, or your own from another machine)
git pull
```

**Workflow:**
1. Create repo on github.com
2. `git remote add origin <url>`
3. `git push -u origin main`
4. Now `git push` and `git pull` work normally

**SSH vs HTTPS:** SSH is more secure for frequent use (no password prompts). Set it up with `ssh-keygen` and adding your public key to GitHub.

## Key Terms
- **Remote**: A version of your repository on a server (GitHub)
- **`origin`**: The conventional name for your primary remote
- **`git push`**: Send local commits to the remote
- **`git pull`**: Fetch and merge remote changes
- **`git clone`**: Download a remote repository locally

## Hands-On Exercise
```bash
# 1. Create a new repo on github.com (no README)
# 2. In your portfolio project:
cd ~/projects/zero-to-portfolio

git init  # if not already
git add .
git commit -m "Initial commit: portfolio site"

git remote add origin https://github.com/YOURUSERNAME/zero-to-portfolio.git
git push -u origin main

# Check GitHub — your code is online!
```

## Quick Quiz
1. What does `git remote add origin <url>` do?
   - a) Downloads the remote repository
   - b) Connects your local repository to a remote location named "origin"
   - c) Creates a new GitHub repository
   - d) Renames your branch to origin

   **Answer:** b) Creates a named connection to the remote — "origin" is the conventional name.

2. What does `git push -u origin main` do?
   - a) Pushes to GitHub and sets `origin/main` as the tracking branch (so future `git push` just works)
   - b) Pushes all branches
   - c) Creates a new branch on GitHub
   - d) Pulls from main

   **Answer:** a) Push and set upstream tracking — `-u` (or `--set-upstream`) means future pushes only need `git push`.

3. What does `git pull` do?
   - a) Removes changes from the remote
   - b) Fetches remote changes and merges them into your current branch
   - c) Uploads your changes
   - d) Downloads the repository for the first time

   **Answer:** b) Fetch + merge — it combines `git fetch` and `git merge origin/branch`.

## Next Up
**Pull Requests** — the collaboration workflow on GitHub.
