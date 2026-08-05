---
title: "What Is Utility-First CSS?"
phase: 5
lesson: 1
duration_minutes: 25
prerequisites: ["4.7"]
skills_unlocked: []
objectives:
  - id: utility-first-philosophy
    kind: knowledge
    text: "Understand the utility-first CSS philosophy"
    about: [2]
  - id: tradeoffs-vs-plain-css
    kind: knowledge
    text: "Know the tradeoffs against traditional CSS"
    about: [3]
  - id: classes-map-to-properties
    kind: knowledge
    text: "See how Tailwind classes map to CSS properties"
    about: [1]
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Utilities are practised directly on the portfolio as it is restyled, so there is no separate exercise to attempt."
  next_up: present
---

## The Concept
Traditional CSS: write CSS classes, apply to HTML.
```css
.btn { padding: 12px 24px; background: blue; color: white; border-radius: 8px; }
```
```html
<button class="btn">Click me</button>
```

Tailwind (utility-first): use tiny, single-purpose classes.
```html
<button class="px-6 py-3 bg-blue-500 text-white rounded-lg">Click me</button>
```

Each class does ONE thing:
- `px-6` = `padding-left: 1.5rem; padding-right: 1.5rem`
- `py-3` = `padding-top: 0.75rem; padding-bottom: 0.75rem`
- `bg-blue-500` = `background-color: #3b82f6`
- `text-white` = `color: white`
- `rounded-lg` = `border-radius: 0.5rem`

**Advantages:** No naming CSS classes, no context switching, styles co-located with HTML, tiny final CSS bundle (only used classes shipped).

**The "concern":** "My HTML will be ugly!" — In practice, components hide the complexity.

## Key Terms
- **Utility class**: A single CSS property in class form (`p-4`, `text-lg`)
- **Utility-first**: Composing styles from utility classes rather than semantic CSS
- **Purging/Tree-shaking**: Removing unused classes at build time (automatic in v4)

## Quick Quiz
1. What does `p-4` do in Tailwind?
   - a) Sets font size to 4
   - b) Sets padding to 1rem on all sides
   - c) Sets position to relative
   - d) Adds 4px margin

   **Answer:** b) `p-4` = `padding: 1rem` (4 × 0.25rem = 1rem).

2. What's the main advantage of utility-first CSS?
   - a) Less HTML
   - b) Styles co-located with HTML, no CSS file context switching, tiny bundles
   - c) Requires no CSS knowledge
   - d) Works without JavaScript

   **Answer:** b) Co-location and productivity — you never leave your HTML to style something.

3. Does Tailwind ship all its classes to production?
   - a) Yes — it's one big CSS file
   - b) No — it tree-shakes and only includes classes actually used
   - c) Only premium classes are included
   - d) You manually include which classes you want

   **Answer:** b) Tree-shaking — the production CSS file only contains classes you actually use.

## Next Up
**Installing Tailwind v4 with Astro** — the correct setup (it's different from v3!).
