---
title: "Navigating the Filesystem"
phase: 0
lesson: 3
duration_minutes: 30
prerequisites: ["0.2"]
skills_unlocked: []
objectives:
  - id: filesystem-as-a-tree
    kind: knowledge
    text: "Understand how the filesystem is organised as a tree"
  - id: navigate-with-cd
    kind: practice
    text: "Navigate between directories using cd"
    about: [1]
  - id: create-and-remove-files
    kind: practice
    text: "Create, list, and remove files and folders"
    verify: "A file the learner created from the terminal exists, and one they removed is gone"
    about: [3]
  - id: absolute-vs-relative-paths
    kind: knowledge
    text: "Understand absolute versus relative paths"
    about: [2]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
Your computer's files are organized in a **tree structure**. At the top is the **root** (`/` on Mac/Linux, `C:\` on Windows). Everything branches out from there.

Think of it like a filing cabinet:
- The cabinet itself = root (`/`)
- Drawers = top-level folders (`/Users`, `/Applications`)
- Folders inside drawers = subdirectories (`/Users/yourname`)
- Files = the actual documents

**Essential commands (Mac/Linux):**
- `pwd` — where am I? (print working directory)
- `ls` — what's here? (list directory contents)
- `cd folder-name` — go into a folder
- `cd ..` — go up one level
- `cd ~` — go to home directory
- `mkdir folder-name` — create a new folder
- `touch file.txt` — create a new empty file
- `rm file.txt` — delete a file (careful! no undo)
- `rm -r folder/` — delete a folder and its contents

**Essential commands (Windows PowerShell):**
- `pwd` — where am I? (works the same)
- `ls` or `dir` — what's here?
- `cd folder-name` — go into a folder (works the same)
- `cd ..` — go up one level (works the same)
- `cd ~` — go to home directory (works the same)
- `mkdir folder-name` — create a new folder (works the same)
- `ni file.txt` — create a new empty file (`ni` = New-Item)
- `rm file.txt` — delete a file (works the same)
- `rm -r folder/` — delete a folder (works the same)

**Paths:**
- **Absolute path**: starts from root: `/Users/yourname/Documents` (Mac) or `C:\Users\yourname\Documents` (Windows)
- **Relative path**: starts from current location: `Documents/projects`

## Key Terms
- **Directory**: A folder in the filesystem
- **Root**: The top-level directory (`/` on Mac/Linux, `C:\` on Windows)
- **Home directory**: Your user's personal directory (`~` or `/Users/yourname` on Mac, `C:\Users\yourname` on Windows)
- **Path**: The address of a file or folder
- **Absolute path**: Full path from root
- **Relative path**: Path relative to your current location

## Hands-On Exercise
Practice navigating! Open your terminal and run these commands in order:

**Mac/Linux:**
```bash
# Where am I?
pwd

# What's in my home directory?
ls

# Create a projects folder
mkdir ~/projects

# Go into it
cd ~/projects

# Create a test file
touch hello.txt

# Confirm it's there
ls

# Go back home
cd ~

# Clean up: delete the test file
rm ~/projects/hello.txt

# Verify it's gone
ls ~/projects
```

**Windows (PowerShell):**
```powershell
# Where am I?
pwd

# What's in my home directory?
ls

# Create a projects folder
mkdir ~/projects

# Go into it
cd ~/projects

# Create a test file
ni hello.txt

# Confirm it's there
ls

# Go back home
cd ~

# Clean up: delete the test file
rm ~/projects/hello.txt

# Verify it's gone
ls ~/projects
```

## Quick Quiz
1. What does `cd ..` do?
   - a) Deletes the current directory
   - b) Moves up one level in the directory tree
   - c) Creates a new directory
   - d) Lists files in the parent directory

   **Answer:** b) Moves up one level — `..` always means "the parent directory".

2. What's the difference between an absolute and relative path?
   - a) Absolute paths are shorter
   - b) Absolute paths start from root (`/`); relative paths start from your current location
   - c) They're the same thing
   - d) Relative paths only work on Windows

   **Answer:** b) Absolute paths start from root; relative paths start from your current location.

3. Which command creates a new empty file?
   - a) `mkdir`
   - b) `cd`
   - c) `touch`
   - d) `new`

   **Answer:** c) `touch` — it creates an empty file on Mac/Linux (or updates the timestamp if it exists). On Windows PowerShell, use `ni` (New-Item) instead.

## Next Up
Next, we'll **install Node.js and npm** — the runtime and package manager that power modern JavaScript development.
