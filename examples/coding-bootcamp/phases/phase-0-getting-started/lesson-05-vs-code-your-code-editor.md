---
title: "VS Code: Your Code Editor"
phase: 0
lesson: 5
duration_minutes: 25
prerequisites: ["0.4"]
skills_unlocked: [vs-code-setup]
objectives:
  - id: install-vs-code
    text: "Have VS Code installed and configured"
  - id: keyboard-shortcuts
    text: "Know the key VS Code keyboard shortcuts"
  - id: essential-extensions
    text: "Have essential extensions installed"
  - id: open-a-project
    text: "Know how to open a project in VS Code"
    tested_by: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
**VS Code** (Visual Studio Code) is a free, open-source code editor made by Microsoft. It's the most popular code editor in the world — over 70% of developers use it.

A code editor is like Microsoft Word, but for code. It has:
- **Syntax highlighting**: Colors that make code readable
- **IntelliSense**: Smart autocomplete that suggests code as you type
- **Extensions**: Add-ons that add features (like Astro support)
- **Integrated terminal**: Run commands without switching windows
- **Git integration**: See file changes, commit code, all without leaving VS Code

The difference between a text editor and an IDE (Integrated Development Environment) is blurry, but VS Code sits in the middle — lightweight like an editor, powerful like an IDE.

## Key Terms
- **Code editor**: Software for writing code (not Word/Notepad!)
- **Syntax highlighting**: Color-coding that makes code structure visible
- **IntelliSense**: VS Code's autocomplete and code intelligence feature
- **Extension**: A plugin that adds features to VS Code
- **Integrated terminal**: Terminal built directly into VS Code

## Hands-On Exercise
**Step 1: Install VS Code**
Download from https://code.visualstudio.com/ and install it.

**Step 2: Install the `code` command**

*Mac:* Press `Cmd+Shift+P`, type "Shell Command: Install 'code' command in PATH", press Enter.

*Windows:* The `code` command is added automatically by the installer. If it's not working, open a new Terminal window and try again.

Now you can open any folder from the terminal with `code .`

**Step 3: Install essential extensions**
Press `Cmd+Shift+X` (Mac) or `Ctrl+Shift+X` (Windows) to open Extensions, then install:
- **Astro** (by Astro Technology Company)
- **Tailwind CSS IntelliSense** (by Tailwind Labs)
- **ESLint** (by Microsoft)
- **Prettier** (by Prettier)

**Step 4: Learn the key shortcuts**

| Action | Mac | Windows |
|--------|-----|---------|
| Quick file open | `Cmd+P` | `Ctrl+P` |
| Command palette | `Cmd+Shift+P` | `Ctrl+Shift+P` |
| Toggle terminal | `Cmd+`` ` `` | `Ctrl+`` ` `` |
| Comment/uncomment | `Cmd+/` | `Ctrl+/` |
| Move line up/down | `Alt+Up/Down` | `Alt+Up/Down` |
| Select next occurrence | `Cmd+D` | `Ctrl+D` |

**Step 5: Try it**
```bash
mkdir ~/projects/test-project
cd ~/projects/test-project
code .
```

VS Code opens with your folder!

## Quick Quiz
1. What is VS Code?
   - a) A web browser
   - b) A free, open-source code editor for writing code
   - c) A programming language
   - d) A cloud storage service

   **Answer:** b) A free, open-source code editor for writing code — it is an editor rather than a whole toolchain, which is why extensions matter so much.

2. What is IntelliSense?
   - a) An AI assistant
   - b) VS Code's smart autocomplete and code intelligence
   - c) A security tool
   - d) A debugging feature

   **Answer:** b) VS Code's smart autocomplete and code intelligence — it suggests completions as you type.

3. How do you open a folder in VS Code from the terminal?
   - a) `vscode .`
   - b) `open .`
   - c) `code .`
   - d) `editor .`

   **Answer:** c) `code .` — the dot means "current directory".

## Next Up
The final lesson in Phase 0: **Git** — the version control system that saves your work and lets you collaborate with others.
