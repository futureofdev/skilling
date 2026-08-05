---
title: "Portfolio Architecture Overview"
phase: 6
lesson: 1
duration_minutes: 25
prerequisites: ["5.7"]
skills_unlocked: []
objectives:
  - id: the-site-architecture
    kind: knowledge
    text: "Understand the architecture of the portfolio site"
  - id: which-parts-are-astro
    kind: knowledge
    text: "Know which parts of the site are Astro and which are React"
    about: [1, 2, 3]
  - id: plan-the-build-order
    kind: practice
    text: "Plan the build order"
sections:
  key_terms:
    status: none
    intent: "Build lesson: the vocabulary was established in the phases this section draws on."
  exercise:
    status: none
    intent: "Project phase: the exercise is the learner's own portfolio, built section by section as the lesson goes."
  next_up: present
---

## The Concept
The portfolio uses Islands Architecture:

**Static (Astro) — zero JavaScript:**
- Navigation (`Nav.astro`) — scroll-aware via vanilla JS
- Hero section (`Hero.astro`) — animated terminal, CSS only
- About section (`About.astro`) — static content
- Skills grid (`Skills.astro`) — data-driven, no state needed
- Footer (`Footer.astro`) — static links

**Interactive (React) — JavaScript islands:**
- Projects grid (`Projects.tsx`) — filter by tag using `useState`
- Contact form (`ContactForm.tsx`) — validation, submit state

**The file structure:**
```
src/
├── components/
│   ├── Nav.astro         ← static + vanilla JS scroll
│   ├── Hero.astro        ← static
│   ├── About.astro       ← static
│   ├── Skills.astro      ← data-driven static
│   ├── Projects.tsx      ← React island
│   ├── ContactForm.tsx   ← React island
│   └── Footer.astro      ← static
├── data/
│   ├── projects.ts       ← typed project data
│   └── skills.ts         ← typed skill data
├── layouts/
│   └── BaseLayout.astro  ← HTML shell
├── pages/
│   └── index.astro       ← assembles everything
└── types/
    └── index.ts          ← TypeScript interfaces
```

## Quick Quiz
1. Why is the Navigation built as an Astro component instead of React?
   - a) Astro is always faster
   - b) The nav is mostly static — the scroll effect uses vanilla JS, no React state needed
   - c) React can't build navbars
   - d) Navigation requires Astro

   **Answer:** b) Vanilla JS is sufficient — no need for React's overhead for a simple scroll effect.

2. Why is the Projects section a React island?
   - a) Astro can't render cards
   - b) It needs `useState` for the tag filter — users click buttons that change what's shown
   - c) React cards look better
   - d) Projects require TypeScript

   **Answer:** b) `useState` for filtering — clicking filter buttons changes which projects show, requiring React state.

3. What does `client:load` do on a React component in the index page?
   - a) Loads the component from a CDN
   - b) Hydrates the React component with JavaScript immediately on page load
   - c) Loads the component asynchronously
   - d) Enables server-side rendering

   **Answer:** b) Hydrates immediately — the component becomes interactive as soon as JavaScript loads.

## Next Up
**Building the Navigation** — the first component we'll create.
