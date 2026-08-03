---
title: "What Is Astro and Why It's Different"
phase: 4
lesson: 1
duration_minutes: 25
prerequisites: ["3.9"]
skills_unlocked: []
objectives:
  - id: ship-less-javascript
    text: "Understand Astro's ship-less-JavaScript philosophy"
    tested_by: [1]
  - id: astro-vs-react-frameworks
    text: "Know the difference between Astro and React or Next.js"
    tested_by: [3]
  - id: what-islands-are
    text: "Understand what Islands Architecture is"
    tested_by: [2]
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Conceptual phase: Astro's ideas are practised on the portfolio build rather than in isolation."
  next_up: present
---

## The Concept
Astro is a web framework that generates **pure HTML** at build time. Unlike React (which ships JavaScript to run in the browser), Astro ships HTML with zero JavaScript by default.

**The problem Astro solves:** React apps ship JavaScript for EVERYTHING — even static content that never changes. This makes sites slow.

**Astro's approach:**
- Render to HTML at build time (fast!)
- Only add JavaScript where you actually need interactivity
- Interactive bits = "islands" — isolated React/Vue/Svelte components

**When to use Astro:** Content-heavy sites (portfolios, blogs, docs) where most content is static.

**Astro vs Next.js:** Next.js is full-stack React. Astro is content-first with optional React islands.

## Key Terms
- **Static Site Generation (SSG)**: Generating HTML at build time
- **Islands Architecture**: Hydrating only interactive components, not the whole page
- **Hydration**: Adding JavaScript behavior to server-rendered HTML
- **Zero JavaScript by default**: Astro's core principle

## Quick Quiz
1. What does Astro do by default with JavaScript?
   - a) Ships all JavaScript to the browser
   - b) Ships zero JavaScript — generates pure HTML
   - c) Converts JavaScript to CSS
   - d) Requires JavaScript for everything

   **Answer:** b) Ships zero JavaScript — you explicitly opt-in with `client:load`.

2. What is an "island" in Islands Architecture?
   - a) A standalone page
   - b) An isolated interactive component surrounded by static HTML
   - c) A server-only component
   - d) A database island

   **Answer:** b) An isolated interactive component — only the island gets hydrated with JavaScript.

3. What type of site is Astro best suited for?
   - a) Real-time chat applications
   - b) Content-heavy sites like portfolios, blogs, and documentation
   - c) Mobile apps
   - d) Database-heavy web apps

   **Answer:** b) Content-heavy sites — Astro excels at shipping fast static content.

## Next Up
**Astro Files** — the `.astro` file format and frontmatter.
