---
title: "What Is a Terminal?"
phase: 0
lesson: 2
duration_minutes: 25
prerequisites: ["0.1"]
skills_unlocked: []
objectives:
  - id: what-the-terminal-is
    kind: knowledge
    text: "Understand what the terminal is and why developers use it"
    about: [1, 3]
  - id: open-the-terminal
    kind: knowledge
    text: "Know how to open the terminal on your computer"
  - id: run-your-first-commands
    kind: practice
    text: "Be able to run your first terminal commands"
    about: [2]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
The **terminal** (also called the command line, shell, or console) is a text-based interface for your computer. Instead of clicking icons, you type commands.

Think of your computer as having two interfaces:
- **GUI** (Graphical User Interface): The visual one with icons and menus — what most people use
- **CLI** (Command Line Interface): The text-based one — what developers use

Why do developers prefer the terminal?
1. **Speed**: Typing a command is faster than navigating menus
2. **Power**: Many developer tools only work in the terminal
3. **Automation**: You can write scripts to do repetitive tasks automatically
4. **Remote control**: You can control servers halfway around the world via terminal

The terminal runs a **shell** — a program that interprets your commands. The most common shells are **bash** or **zsh** (on Mac/Linux) and **PowerShell** (on Windows).

## Key Terms
- **Terminal**: The application that shows the command line interface
- **Shell**: The program inside the terminal that interprets commands (bash, zsh, PowerShell)
- **Command**: An instruction you type and run by pressing Enter
- **Prompt**: The `$`, `%`, or `>` symbol indicating the terminal is ready for input
- **CLI**: Command Line Interface — text-based way to interact with your computer

## Hands-On Exercise
Let's open the terminal and run your first commands:

**On Mac:**
1. Press `Cmd + Space` to open Spotlight
2. Type "Terminal" and press Enter
3. You'll see a window with a prompt like: `your-name@MacBook ~ %`

**On Windows:**
1. Press `Windows + X` and choose **Terminal** (or search "Terminal" in the Start menu)
2. Windows Terminal opens with PowerShell by default
3. You'll see a prompt like: `PS C:\Users\yourname>`

**Your first commands:**
```
pwd
```
This prints your current directory (where you are in the filesystem).

```
ls
```
This lists files and folders in your current location.

```
echo "Hello, World!"
```
This prints text to the screen. Congratulations — you just ran your first program!

## Quick Quiz
1. What is the terminal?
   - a) A type of virus
   - b) A text-based interface for giving commands to your computer
   - c) A programming language
   - d) A type of file

   **Answer:** b) A text-based interface for giving commands to your computer — you type instructions instead of clicking, which is why so many developer tools live there.

2. What does the `pwd` command do?
   - a) Prints a file
   - b) Powers down the computer
   - c) Shows your current directory location
   - d) Deletes a file

   **Answer:** c) Shows your current directory location — pwd stands for "print working directory".

3. Why do developers use the terminal instead of clicking around?
   - a) Terminals look cool
   - b) Terminals are faster, more powerful, and many tools only work there
   - c) GUIs don't work on developer computers
   - d) Developers are required to use terminals by law

   **Answer:** b) Terminals are faster, more powerful, and many tools only work there — typing a command beats hunting through menus, and it can be scripted so you never do it by hand twice.

## Next Up
In the next lesson, we'll learn how to **navigate your filesystem** using the terminal — moving between folders, creating files, and more.
