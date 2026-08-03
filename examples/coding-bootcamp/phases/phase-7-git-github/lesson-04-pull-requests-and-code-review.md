---
title: "Pull Requests and Code Review"
phase: 7
lesson: 4
duration_minutes: 30
prerequisites: ["7.3"]
skills_unlocked: []
objectives:
  - id: open-a-pull-request
    text: "Create a pull request on GitHub"
    tested_by: [1]
  - id: write-good-descriptions
    text: "Write good pull request descriptions"
    tested_by: [2]
  - id: the-review-process
    text: "Understand the code review process"
    tested_by: [3]
  - id: merge-a-pull-request
    text: "Merge a pull request on GitHub"
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Pull requests need a repository and a reviewer, so the phase's homework covers the whole flow end to end instead."
  next_up: present
---

## The Concept
A **Pull Request (PR)** is a request to merge your branch into another branch. It's where code review happens.

**The PR workflow:**
1. Create a feature branch locally
2. Push the branch to GitHub
3. Open a PR on GitHub (from your branch → main)
4. Teammates review and comment
5. You address feedback with new commits
6. PR is approved and merged

```bash
# Create and push a feature branch
git checkout -b feature/add-projects-filter
# ... make changes ...
git add .
git commit -m "feat: add tag filter to projects section"
git push origin feature/add-projects-filter

# Then open github.com → your repo → you'll see a "Compare & pull request" button
```

**Good PR description:**
- What did you change and why?
- How to test it
- Screenshots for visual changes

Even for solo projects (like your portfolio), PRs are good practice.

## Key Terms
- **Pull Request (PR)**: Request to merge changes from one branch into another
- **Code review**: Examination of code changes before merging
- **Reviewer**: Person checking the code quality
- **`Squash and merge`**: Combine all PR commits into one before merging

## Quick Quiz
1. What is the purpose of a pull request?
   - a) To download code
   - b) To request merging a branch and enable code review before the merge
   - c) To delete a branch
   - d) To pull changes from the server

   **Answer:** b) Merge request + code review — it's the collaboration checkpoint before code enters main.

2. What makes a good PR description?
   - a) Just the commit messages
   - b) What changed, why it changed, how to test it, and screenshots for visual changes
   - c) A list of files changed
   - d) The branch name

   **Answer:** b) Context for reviewers — what, why, and how to verify.

3. Can you add more commits to a PR after opening it?
   - a) No — PRs are locked once opened
   - b) Yes — push new commits to the same branch and they automatically appear in the PR
   - c) Only if you close and reopen
   - d) Only the repo owner can add commits

   **Answer:** b) Yes — push to the same branch; GitHub updates the PR automatically.

## Next Up
**GitHub Actions** — automating builds and deployments with CI/CD.
