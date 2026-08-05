---
title: "GitHub Actions (CI/CD Basics)"
phase: 7
lesson: 5
duration_minutes: 30
prerequisites: ["7.4"]
skills_unlocked: [git-and-github]
objectives:
  - id: what-ci-cd-is
    kind: knowledge
    text: "Understand what CI/CD is"
    about: [1]
  - id: create-a-workflow
    kind: practice
    text: "Create a basic GitHub Actions workflow"
    verify: "A workflow file exists under .github/workflows and its YAML parses"
    about: [2, 3]
  - id: checks-on-every-push
    kind: practice
    text: "Run automated checks on every push"
    about: [2]
  - id: the-link-to-deployment
    kind: knowledge
    text: "Understand the connection to deployment"
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
**CI/CD** = Continuous Integration / Continuous Deployment.
- **CI**: Automatically run tests and checks on every push
- **CD**: Automatically deploy when checks pass

GitHub Actions lets you define workflows in YAML files:

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          
      - name: Install dependencies
        run: npm install
        
      - name: Build site
        run: npm run build
```

This runs on every push to main and every PR — if the build fails, you know immediately.

**For your portfolio:** Cloudflare Pages handles CD automatically (deploys on every push). CI is optional for a solo project but good practice.

## Key Terms
- **CI (Continuous Integration)**: Automatically test/build on every push
- **CD (Continuous Deployment)**: Automatically deploy when CI passes
- **GitHub Actions**: GitHub's built-in CI/CD system
- **Workflow**: A YAML file defining automated steps
- **Runner**: The virtual machine that executes your workflow

## Hands-On Exercise
Create a CI workflow for your portfolio:
```bash
mkdir -p .github/workflows
# Create the ci.yml file above
git add .github/workflows/ci.yml
git commit -m "ci: add build check workflow"
git push
```

Go to github.com → your repo → Actions tab — you'll see your workflow running!

## Quick Quiz
1. What does "Continuous Integration" mean?
   - a) The code integrates continuously with the database
   - b) Automatically running builds and tests on every code change
   - c) Continuous deployment to production
   - d) Integrating third-party services

   **Answer:** b) Automated testing on every change — catch bugs before they reach production.

2. When does the workflow `on: push: branches: [main]` trigger?
   - a) When anyone views the main branch
   - b) When code is pushed to the main branch
   - c) When a PR is opened
   - d) Every day at midnight

   **Answer:** b) On push to main — you can also add `pull_request` to check PRs before they merge.

3. What does `actions/checkout@v4` do in a workflow step?
   - a) Checks out a payment
   - b) Downloads your repository code onto the runner VM so subsequent steps can access it
   - c) Creates a checkout page
   - d) Verifies the repository is public

   **Answer:** b) Downloads your code — every workflow starts by checking out the repo.

## Homework Assignment
### Phase 7 Homework: GitHub Setup

**Objective:** Get your portfolio repository on GitHub with a working CI workflow.

**Requirements:**
- [ ] Create a GitHub repository named `zero-to-portfolio` (or your chosen name)
- [ ] Push your complete portfolio code to GitHub
- [ ] Create `.github/workflows/ci.yml` that builds your Astro site
- [ ] Verify the CI workflow passes (green check in Actions tab)
- [ ] Create a feature branch, make a change, open a PR
- [ ] Merge the PR on GitHub

**Stretch Goals:**
- [ ] Add a README badge showing CI status
- [ ] Set up branch protection on `main` (require CI to pass before merge)
- [ ] Tag a release: `git tag v1.0.0 && git push origin v1.0.0`

**Submission:** Share your GitHub repository URL with Claude.

## Next Up
Phase 8: **Deployment** — pushing your portfolio live to Cloudflare Pages!
