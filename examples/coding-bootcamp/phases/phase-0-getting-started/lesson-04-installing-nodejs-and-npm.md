---
title: "Installing Node.js and npm"
phase: 0
lesson: 4
duration_minutes: 30
prerequisites: ["0.3"]
skills_unlocked: [nodejs-installed]
objectives:
  - id: what-node-is
    kind: knowledge
    text: "Understand what Node.js is and why we need it"
    about: [1]
  - id: install-node-and-npm
    kind: practice
    text: "Have Node.js and npm installed on your computer"
    verify: "Both node and npm report a version number when asked for one"
    about: [3]
  - id: verify-your-install
    kind: practice
    text: "Be able to verify your installation"
    verify: "The versions node and npm report are readable and recent enough for this course"
  - id: what-npm-is
    kind: knowledge
    text: "Understand what npm is and why it matters"
    about: [2]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
**Node.js** is a JavaScript runtime — it lets you run JavaScript code outside of a browser. Before Node.js existed, JavaScript could only run in web browsers. Now it runs everywhere: servers, command lines, desktop apps.

We need Node.js for our project because:
- Astro (our framework) runs on Node.js
- npm lets us install packages (pre-built code libraries)
- The development server runs on Node.js

**npm** (Node Package Manager) is the world's largest software registry. When you need to add a feature to your project, chances are someone has already built it. npm lets you download and use their code.

**nvm** (Node Version Manager) is the recommended way to install Node.js — it lets you easily switch between Node versions.

## Key Terms
- **Node.js**: JavaScript runtime — runs JS outside the browser
- **npm**: Node Package Manager — installs and manages code packages
- **Package**: A reusable piece of code you can install into your project
- **nvm**: Node Version Manager — manages multiple Node.js versions
- **LTS**: Long Term Support — the stable, recommended Node.js version

## Hands-On Exercise
**Mac/Linux — Install nvm:**
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
```

Close and reopen your terminal, then:

```bash
# Install Node.js LTS
nvm install --lts

# Use it
nvm use --lts
```

**Windows — Install nvm-windows:**
1. Go to https://github.com/coreybutler/nvm-windows/releases
2. Download `nvm-setup.exe` from the latest release
3. Run the installer and follow the prompts
4. Close and reopen Terminal (as Administrator), then:

```powershell
# Install Node.js LTS
nvm install lts

# Use it
nvm use lts
```

**Verify your install (Mac and Windows):**
```bash
# Verify Node.js is installed
node --version

# Verify npm is installed
npm --version
```

You should see version numbers like `v20.x.x` for Node and `10.x.x` for npm.

**Test Node.js works:**
```bash
node -e "console.log('Node.js works! Hello, World!')"
```

## Quick Quiz
1. What is Node.js?
   - a) A web browser
   - b) A JavaScript runtime that runs JS outside the browser
   - c) A database
   - d) A text editor

   **Answer:** b) A JavaScript runtime that runs JS outside the browser — that is what lets build tools, package managers and servers be written in the same language as the front end.

2. What is npm used for?
   - a) Writing JavaScript code
   - b) Running websites
   - c) Installing and managing code packages
   - d) Designing user interfaces

   **Answer:** c) Installing and managing code packages — npm gives you access to millions of reusable code libraries.

3. Why use nvm instead of installing Node.js directly?
   - a) nvm is faster
   - b) nvm is the only way to install Node.js
   - c) nvm lets you easily manage and switch between Node.js versions
   - d) nvm costs less money

   **Answer:** c) nvm lets you easily manage and switch between Node.js versions — essential when different projects need different versions.

## Next Up
Next, we'll set up **VS Code** — the code editor that most professional developers use.
