---
title: "Installing Tailwind v4 with Astro"
phase: 5
lesson: 2
duration_minutes: 30
prerequisites: ["5.1"]
skills_unlocked: []
objectives:
  - id: install-tailwind
    kind: practice
    text: "Install Tailwind CSS v4 correctly with Astro"
    about: [2]
  - id: v4-versus-v3
    kind: knowledge
    text: "Understand the differences between Tailwind v4 and v3"
    about: [1]
  - id: configure-the-vite-plugin
    kind: practice
    text: "Configure the Vite plugin rather than the Astro integration"
    about: [2]
  - id: the-import-statement
    kind: practice
    text: "Use the Tailwind @import statement in CSS"
    about: [3]
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Utilities are practised directly on the portfolio as it is restyled, so there is no separate exercise to attempt."
  next_up: present
---

## The Concept
Tailwind v4 is a MAJOR change from v3. The most common mistake is using the wrong setup method.

**Correct Tailwind v4 setup for Astro:**

1. Install packages:
```bash
npm install @tailwindcss/vite
```

2. `astro.config.mjs` — use the Vite plugin, NOT `@astrojs/tailwind`:
```js
import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  integrations: [react()],
  vite: {
    plugins: [tailwindcss()],
  },
});
```

3. `src/styles/global.css`:
```css
@import "tailwindcss";
/* No tailwind.config.js needed in v4! */
```

4. Import in `BaseLayout.astro`:
```astro
---
import "../styles/global.css";
---
```

**v4 vs v3 key differences:**
- v4: `@import "tailwindcss"` / v3: `@tailwind base; @tailwind components; @tailwind utilities;`
- v4: No `tailwind.config.js` needed / v3: Required
- v4: CSS variables for themes / v3: Config file for themes
- v4: Vite plugin / v3: PostCSS plugin or Astro integration

## Key Terms
- **`@tailwindcss/vite`**: The Tailwind v4 Vite plugin
- **`@import "tailwindcss"`**: How to include Tailwind v4 in CSS
- **`@theme`**: CSS block for defining custom design tokens in v4

## Quick Quiz
1. In Tailwind v4, where do you define custom colors?
   - a) `tailwind.config.js`
   - b) In `@theme {}` block in CSS, using CSS custom properties
   - c) In `astro.config.mjs`
   - d) In a separate `colors.json` file

   **Answer:** b) `@theme {}` in CSS — v4 moved configuration to CSS custom properties.

2. Which package do you install for Tailwind v4 with Astro?
   - a) `@astrojs/tailwind`
   - b) `tailwindcss` and `@tailwindcss/vite`
   - c) `tailwind-astro`
   - d) `tailwindcss` only

   **Answer:** b) `@tailwindcss/vite` (which brings in tailwindcss as a dependency).

3. What is the correct `@import` statement for Tailwind v4?
   - a) `@import "tailwind/base"`
   - b) `@tailwind base; @tailwind utilities;`
   - c) `@import "tailwindcss";`
   - d) `@use tailwindcss;`

   **Answer:** c) `@import "tailwindcss"` — single import, no directives needed.

## Next Up
**Typography and Colors** — Tailwind's system for text and color utilities.
