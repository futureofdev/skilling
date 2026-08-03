---
title: "Astro Components vs React Components"
phase: 4
lesson: 4
duration_minutes: 30
prerequisites: ["4.3"]
skills_unlocked: []
objectives:
  - id: astro-or-react-component
    text: "Know when to use an Astro component and when to use a React one"
    tested_by: [2]
  - id: the-tradeoffs
    text: "Understand the tradeoffs of each"
  - id: client-directives
    text: "Use client:* directives correctly"
    tested_by: [1, 3]
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Conceptual phase: Astro's ideas are practised on the portfolio build rather than in isolation."
  next_up: present
---

## The Concept
Astro lets you use both `.astro` components (static) and React components (interactive). Knowing when to use each is key.

**Use Astro (`.astro`) when:**
- Content is static (header, footer, nav, about section)
- No need for React state
- Maximum performance is priority

**Use React (`.tsx`) when:**
- Component has state (filter buttons, form validation)
- Component responds to user interactions
- You need React hooks (`useState`, `useEffect`)

**`client:*` directives** tell Astro how to hydrate a React component:
```astro
<!-- Hydrate immediately when page loads -->
<Projects client:load />

<!-- Hydrate when component becomes visible -->
<Comments client:visible />

<!-- Hydrate when browser is idle -->
<Analytics client:idle />

<!-- Never hydrate — server only -->
<StaticWidget />
```

**The rule**: Use `client:load` for components above the fold that need immediate interactivity. Use `client:visible` for below-fold interactive components.

## Key Terms
- **`client:load`**: Hydrate the React component immediately
- **`client:visible`**: Hydrate when the component enters the viewport
- **`client:idle`**: Hydrate when the browser is not busy
- **Static**: No JavaScript sent to browser

## Quick Quiz
1. Which directive should you use for a contact form that needs immediate interactivity?
   - a) No directive — Astro handles it
   - b) `client:visible`
   - c) `client:load`
   - d) `client:interactive`

   **Answer:** c) `client:load` — for components that need to be interactive right away.

2. What happens if you use a React component in Astro WITHOUT a `client:*` directive?
   - a) React throws an error
   - b) It renders as static HTML — no JavaScript, no interactivity
   - c) It uses `client:load` automatically
   - d) It fails to build

   **Answer:** b) Static HTML only — React renders to HTML at build time, no client-side JS.

3. When would you choose `client:visible` over `client:load`?
   - a) Never — always use `client:load`
   - b) For components below the fold that don't need to be interactive until scrolled to
   - c) For forms
   - d) For navigation bars

   **Answer:** b) Below the fold — delay hydrating until the user can actually see the component.

## Next Up
**Islands Architecture** — the deep dive into how Astro's model works.
