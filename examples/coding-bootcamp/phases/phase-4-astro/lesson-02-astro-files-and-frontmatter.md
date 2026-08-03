---
title: "Astro Files and Frontmatter"
phase: 4
lesson: 2
duration_minutes: 35
prerequisites: ["4.1"]
skills_unlocked: []
objectives:
  - id: write-astro-files
    text: "Write valid .astro files"
  - id: the-frontmatter-script
    text: "Use the frontmatter script section"
    tested_by: [1, 2]
  - id: frontmatter-to-template
    text: "Pass data from frontmatter to the template"
  - id: import-components
    text: "Import and use other components"
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Conceptual phase: Astro's ideas are practised on the portfolio build rather than in isolation."
  next_up: present
---

## The Concept
`.astro` files have two sections:

```astro
---
// FRONTMATTER: runs on the server at build time
// This is regular JavaScript/TypeScript
import OtherComponent from './OtherComponent.astro';

const title = "My Page";
const items = ["a", "b", "c"];
const data = await fetch('/api/data').then(r => r.json());
---

<!-- TEMPLATE: HTML with expressions -->
<html>
  <body>
    <h1>{title}</h1>
    <ul>
      {items.map(item => <li>{item}</li>)}
    </ul>
    <OtherComponent />
  </body>
</html>

<style>
  /* Scoped CSS — only affects this component */
  h1 { color: var(--color-accent); }
</style>
```

**Key differences from React:**
- Frontmatter runs at BUILD TIME (not in the browser)
- No `useState`, `useEffect` in `.astro` files (they're static)
- Scoped `<style>` — styles don't leak to other components
- Can `await` data fetching at the top level

## Key Terms
- **Frontmatter**: The `---` fenced section at the top — server-side JS
- **Template**: The HTML section below frontmatter
- **Scoped styles**: CSS in `<style>` tags that only applies to this component
- **Build time**: When Astro generates HTML (before deployment)

## Quick Quiz
1. When does the Astro frontmatter code run?
   - a) In the browser when the page loads
   - b) At build time on the server
   - c) Every time a user visits the page
   - d) Only in development

   **Answer:** b) At build time — Astro frontmatter runs once when building the site, not in the browser.

2. Can you use `useState` in an `.astro` file?
   - a) Yes, works the same as React
   - b) No — Astro components are static; use `client:load` React components for interactivity
   - c) Yes, but with different syntax
   - d) Only in the `<script>` tag

   **Answer:** b) No — `.astro` files are static. For interactivity, create a React component and use `client:load`.

3. How is `<style>` in an Astro component different from global CSS?
   - a) It's identical
   - b) Astro scopes styles — they only apply to elements in that component
   - c) Scoped styles only work in production
   - d) Astro converts scoped styles to inline styles

   **Answer:** b) Scoped — Astro adds unique class names to prevent style leaking.

## Next Up
**Layouts and Slots** — sharing HTML structure across pages.
