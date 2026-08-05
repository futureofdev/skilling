---
title: "Going Live: Launch Checklist"
phase: 8
lesson: 5
duration_minutes: 30
prerequisites: ["8.4"]
skills_unlocked: [deployment-complete, portfolio-deployed]
objectives:
  - id: a-pre-launch-checklist
    kind: practice
    text: "Complete a pre-launch quality checklist"
    about: [1]
  - id: verify-across-devices
    kind: practice
    text: "Verify every section works on mobile and desktop"
    about: [2]
  - id: share-your-portfolio
    kind: practice
    text: "Share your portfolio with the world"
  - id: plan-your-next-steps
    kind: practice
    text: "Plan next steps for growing as a developer"
    about: [3]
sections:
  key_terms:
    status: none
    intent: "A launch procedure rather than new vocabulary."
  exercise: present
  next_up:
    status: none
    intent: "Last lesson of the course, so there is nothing ahead to tease."
---

## The Concept
You've built a complete portfolio. Before announcing it, run through this launch checklist.

**Technical checks:**
- [ ] `npm run build` completes without errors
- [ ] Deployed URL opens (Cloudflare Pages)
- [ ] All navigation links scroll to correct sections
- [ ] Projects filter works (click different tags)
- [ ] Contact form validates (try submitting empty)
- [ ] Site works on mobile (test on your phone or DevTools mobile view)
- [ ] No 404 errors (open DevTools → Network, refresh)

**Performance:**
- [ ] Lighthouse score ≥ 90 on Performance
- [ ] Lighthouse score ≥ 90 on Accessibility
- [ ] Lighthouse score ≥ 90 on SEO

**Content:**
- [ ] Your real name is in the Hero
- [ ] Bio is written (not placeholder text)
- [ ] Real projects listed (even if just 1-2)
- [ ] Skills updated to reflect what you actually know
- [ ] Contact form or a real email address
- [ ] Social links (GitHub, LinkedIn) work

**SEO basics:**
- [ ] Page title is your name + role
- [ ] Meta description is set
- [ ] Open Graph tags set (for social sharing)

**Congratulations — you're a developer!**
### What you have built

You started without a development environment and you now have a portfolio site that real
people can visit: written from scratch, styled by hand, made interactive, restyled with
utilities, put under version control, and deployed to a domain you control.

Every part of it is something you can explain, because you built it rather than cloned it.
That is the thing an interviewer is actually listening for.

## Hands-On Exercise
Go through the checklist above. For any item that fails, fix it before launching.

Then:
1. Post your portfolio URL on LinkedIn
2. Share it in a developer community (Twitter/X, Discord)
3. Add it to your GitHub profile README
4. Apply to jobs or internships with it!

## Quick Quiz
1. What Lighthouse score should you target before launching?
   - a) Any score is fine
   - b) 70+ for performance
   - c) 90+ for Performance, Accessibility, and SEO
   - d) 100 is the only acceptable score

   **Answer:** c) 90+ — Astro makes this achievable; below 90 suggests something needs fixing.

2. How do you test your portfolio on mobile without a real phone?
   - a) You can't — you need a real phone
   - b) Chrome DevTools → Toggle Device Toolbar (Ctrl+Shift+M) → select a device
   - c) Use Safari instead
   - d) Deploy and view on your phone

   **Answer:** b) DevTools mobile simulation — instantly test different screen sizes.

3. After launch, what's a great next step for growing as a developer?
   - a) Stop learning — you're done
   - b) Build more projects, contribute to open source, write about what you've learned
   - c) Learn a completely different field
   - d) Rewrite the portfolio in every framework

   **Answer:** b) Keep building — a portfolio grows with you. Each new project is a new opportunity.

## Homework Assignment
### Phase 8 (Final) Homework: Launch Day!

**Objective:** Deploy your complete portfolio and share it with the world.

**Requirements:**
- [ ] Portfolio is live at a public URL (Cloudflare Pages or custom domain)
- [ ] Run Lighthouse — screenshot your scores
- [ ] All placeholder text replaced with real content
- [ ] At least 2 real projects listed
- [ ] GitHub repository is public
- [ ] README has your live site URL

**Launch tasks:**
- [ ] Share your URL with Claude — describe what you built!
- [ ] Post on LinkedIn: "Just launched my developer portfolio! Built with Astro, React, and Tailwind CSS."
- [ ] Add portfolio URL to your GitHub bio

**Submission:** Send your tutor the live URL and your Lighthouse screenshot.

**Stretch Goals:**
- [ ] Set up a custom domain
- [ ] Write your first blog post: "What I learned building my portfolio"
- [ ] Open an issue on your GitHub repo for "next features to add"

**Graduation:** Once you complete this homework, you've finished the Zero to Portfolio curriculum! You are now a web developer. 🎓
