---
title: "Building the About Section"
phase: 6
lesson: 4
duration_minutes: 30
prerequisites: ["6.3"]
skills_unlocked: []
objectives:
  - id: a-two-column-about
    text: "Build a two-column about section"
    tested_by: [1]
  - id: a-terminal-stats-panel
    text: "Use a decorative terminal stats panel"
  - id: apply-the-design-system
    text: "Apply the design system consistently"
    tested_by: [2, 3]
sections:
  key_terms:
    status: none
    intent: "Build lesson: the vocabulary was established in the phases this section draws on."
  exercise:
    status: none
    intent: "Project phase: the exercise is the learner's own portfolio, built section by section as the lesson goes."
  next_up:
    status: none
    intent: "Build lessons run straight into the next section of the portfolio, so the teaser is generated rather than written."
---

## The Concept
The About section uses a two-column layout: bio text on the left, a decorative "developer stats" terminal on the right.

```astro
<section id="about" class="py-24" style="background: var(--color-surface)">
  <div class="max-w-6xl mx-auto px-6">
    <div class="grid lg:grid-cols-2 gap-16 items-center">
      <!-- Bio -->
      <div>
        <p class="text-sm font-mono mb-3" style="color: var(--color-accent)">01. about_me</p>
        <h2 class="text-4xl font-mono font-black mb-6">Who I Am</h2>
        <p style="color: var(--color-text-muted)">Your bio here...</p>
      </div>
      <!-- Terminal stats panel -->
      <div class="rounded-xl p-8 border font-mono" style="background: var(--color-bg); border-color: var(--color-border)">
        <div class="text-xs mb-4" style="color: var(--color-text-muted)">$ cat stats.json</div>
        <!-- Stats rows -->
      </div>
    </div>
  </div>
</section>
```

The stats panel is decorative but reinforces the "Terminal Scholar" aesthetic — it looks like a JSON file in a terminal.

## Quick Quiz
1. What does `items-center` do on the grid container?
   - a) Centers the grid horizontally
   - b) Vertically aligns grid items to center when they're different heights
   - c) Centers text in each grid item
   - d) Adds centered items animation

   **Answer:** b) Vertical alignment — on a grid/flex container, `items-center` vertically centers items.

2. Why use CSS custom properties (`var(--color-surface)`) instead of Tailwind classes for colors?
   - a) Tailwind doesn't have dark colors
   - b) Our custom design system colors aren't in Tailwind's default palette
   - c) CSS variables are faster
   - d) Tailwind can't use background colors

   **Answer:** b) Custom design tokens — our exact hex values need to be defined and referenced via CSS variables.

3. What is the purpose of the section numbering (`01. about_me`)?
   - a) Required by HTML
   - b) Visual design element that gives the site a structured, editorial feel
   - c) Accessibility requirement
   - d) Used for navigation

   **Answer:** b) Design aesthetic — numbered sections give a sense of structured documentation.
