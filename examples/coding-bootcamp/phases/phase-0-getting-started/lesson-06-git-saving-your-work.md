---
title: "Git: Saving Your Work"
phase: 0
lesson: 6
duration_minutes: 35
prerequisites: ["0.5"]
skills_unlocked: [git-basics]
objectives:
  - id: what-version-control-is
    text: "Understand what version control is and why it matters"
    tested_by: [3]
  - id: init-a-repository
    text: "Initialise a git repository"
  - id: make-your-first-commit
    text: "Make your first commit"
    tested_by: [1]
  - id: the-staging-area
    text: "Understand the staging area"
    tested_by: [2]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
**Git** is a version control system. It tracks changes to your files over time, so you can:
- Go back to any previous version of your code
- See exactly what changed and when
- Collaborate with others without overwriting each other's work
- Experiment safely — if it breaks, just revert!

Think of Git like a very sophisticated "Save" system with an unlimited undo history.

**Core Git concepts:**
- **Repository (repo)**: A project tracked by Git (the `.git` folder)
- **Commit**: A saved snapshot of your files at a point in time
- **Staging area**: Where you prepare files before committing
- **Branch**: A parallel version of your project

**The basic workflow:**
1. Make changes to files
2. `git add` — stage the changes you want to save
3. `git commit -m "message"` — save a snapshot with a description

## Key Terms
- **Git**: Version control system that tracks file changes
- **Repository**: A project folder tracked by Git
- **Commit**: A saved snapshot of your code with a message
- **Staging area**: The holding area for changes before committing
- **git add**: Stage changes for the next commit
- **git commit**: Save a snapshot of staged changes

## Hands-On Exercise
```bash
# Navigate to your projects folder
cd ~/projects

# Create a new project folder
mkdir my-first-repo
cd my-first-repo

# Initialize git (creates the .git folder)
git init

# Set your name and email (one-time setup)
git config --global user.name "Your Name"
git config --global user.email "you@example.com"

# Create a file
echo "# My First Project" > README.md

# Check status — git sees an untracked file
git status

# Stage the file
git add README.md

# Check status again — file is staged
git status

# Make your first commit!
git commit -m "Initial commit: add README"

# See your commit history
git log --oneline
```

## Quick Quiz
1. What is a git commit?
   - a) A promise to write good code
   - b) A saved snapshot of your files at a point in time
   - c) A way to share code online
   - d) A type of error

   **Answer:** b) A saved snapshot of your files at a point in time — each commit is a point you can return to, which is what makes experimenting safe.

2. What does `git add` do?
   - a) Creates a new repository
   - b) Uploads your code to GitHub
   - c) Stages changes for the next commit
   - d) Deletes a file from git

   **Answer:** c) Stages changes for the next commit — it adds files to the staging area.

3. Why is version control important?
   - a) It makes code run faster
   - b) It's required by law
   - c) It lets you track changes, revert mistakes, and collaborate safely
   - d) It automatically fixes bugs

   **Answer:** c) It lets you track changes, revert mistakes, and collaborate safely — without it, the only way back from a bad change is remembering what you typed.

## Homework Assignment
### Phase 0 Homework: Your Development Environment

**Objective:** Verify your development environment is fully set up by completing a series of tasks and documenting them.

**Requirements:**
- [ ] Open your terminal and run `node --version` — paste the output
- [ ] Run `npm --version` — paste the output
- [ ] Run `git --version` — paste the output
- [ ] Create a folder called `phase-0-homework` in `~/projects`
- [ ] Initialize a git repository in that folder
- [ ] Create a `README.md` file with your name and today's date
- [ ] Make a commit with message "Phase 0 complete: environment setup"
- [ ] Run `git log --oneline` and share what you see

**Stretch Goals:**
- [ ] Create a GitHub account at github.com (free)
- [ ] Create a new repository on GitHub named `phase-0-homework`
- [ ] Push your local repo to GitHub

**Submission:** Show Claude the output of your `git log --oneline` command and describe what you installed.

## Next Up
Phase 1: **Web Fundamentals** — HTML, CSS, and how the web actually works. You're going to build your first webpage!
