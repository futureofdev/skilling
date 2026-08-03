---
title: "Islands Architecture"
phase: 4
lesson: 5
duration_minutes: 25
prerequisites: ["4.4"]
skills_unlocked: []
objectives:
  - id: islands-in-depth
    text: "Understand Islands Architecture in depth"
    tested_by: [1, 3]
  - id: islands-vs-spa
    text: "See how it differs from React's single-page-app model"
  - id: performance-implications
    text: "Understand the performance implications"
    tested_by: [2]
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Conceptual phase: Astro's ideas are practised on the portfolio build rather than in isolation."
  next_up: present
---

## The Concept
Traditional React apps ship ALL JavaScript to the browser. Astro flips this.

**Traditional SPA (React/Next.js):**
- HTML is minimal — just `<div id="root"></div>`
- ALL rendering happens in the browser with JavaScript
- User waits for JS to download, parse, execute before seeing content

**Astro's Islands Architecture:**
```
┌─────────────────────────────────────────┐
│  Static HTML (no JS)     │   Nav (no JS) │
├─────────────────────────────────────────┤
│  Hero section (no JS — Astro component)  │
├─────────────────────────────────────────┤
│  About (no JS)                           │
├──────────────┬──────────────────────────┤
│ 🏝 Projects  │  ← React Island (JS!)   │
│ (client:load)│  filter buttons work     │
├──────────────┴──────────────────────────┤
│ 🏝 Contact Form ← React Island (JS!)   │
│ (client:load) validation, submit state  │
└─────────────────────────────────────────┘
```

The browser gets HTML immediately. Only the islands (React components with `client:*`) load JavaScript. Each island is isolated — one doesn't affect another.

**Result:** Faster load times, better Core Web Vitals, same rich interactivity where needed.

## Key Terms
- **Island**: An isolated interactive component in a sea of static HTML
- **Progressive enhancement**: Static content first, enhance with JS where needed
- **Core Web Vitals**: Google's performance metrics (FCP, LCP, CLS)
- **Partial hydration**: Only hydrating interactive parts, not the whole page

## Quick Quiz
1. What is an "island" in Astro's Islands Architecture?
   - a) A page
   - b) An isolated interactive React component in a sea of static HTML
   - c) A CSS layout system
   - d) A server-side route

   **Answer:** b) An isolated interactive component — surrounded by static HTML.

2. What's the performance advantage of Islands Architecture?
   - a) Less CSS
   - b) Only interactive components ship JavaScript — static parts ship zero JS
   - c) Faster database queries
   - d) Smaller images

   **Answer:** b) Less JavaScript shipped — most content is pure HTML, only islands add JS.

3. Are islands isolated from each other?
   - a) No — they share a global state
   - b) Yes — each island is independent with its own hydration
   - c) Only React islands are isolated
   - d) Islands communicate through the Astro runtime

   **Answer:** b) Yes — each island independently hydrates. They don't share state by default.

## Next Up
**Static Pages and Routing** — how Astro's file-based routing works.
