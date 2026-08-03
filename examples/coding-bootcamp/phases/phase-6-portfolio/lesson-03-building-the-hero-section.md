---
title: "Building the Hero Section"
phase: 6
lesson: 3
duration_minutes: 35
prerequisites: ["6.2"]
skills_unlocked: []
objectives:
  - id: a-full-viewport-hero
    text: "Build a full-viewport hero section"
    tested_by: [3]
  - id: a-terminal-snippet
    text: "Create a terminal code snippet with CSS animations"
    tested_by: [2]
  - id: apply-the-aesthetic
    text: "Apply the site's visual aesthetic consistently"
    tested_by: [1]
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
The hero showcases the "Terminal Scholar" design: dark background, monospace fonts, syntax-colored code block.

Key pieces:
1. Full-viewport section (`min-h-screen flex items-center`)
2. Two-column grid on desktop (text left, terminal right)
3. Animated terminal with CSS `@keyframes`
4. CSS-only blinking cursor

The terminal window is just stylized HTML/CSS — no JavaScript needed. The syntax colors are inline styles using CSS custom properties.

```astro
<section class="min-h-screen flex items-center pt-20">
  <div class="max-w-6xl mx-auto px-6 grid lg:grid-cols-2 gap-16 items-center">
    <!-- Text -->
    <div>
      <p class="text-sm font-mono mb-4" style="color: var(--color-accent)">Hello, world! I'm</p>
      <h1 class="text-5xl lg:text-7xl font-mono font-black mb-4">Your Name</h1>
      <!-- ... -->
    </div>
    <!-- Terminal -->
    <div class="hidden lg:block">
      <!-- Terminal window markup -->
    </div>
  </div>
</section>
```

## Quick Quiz
1. Why use `hidden lg:block` on the terminal window?
   - a) Terminals don't work on mobile
   - b) The terminal is hidden on mobile (no space) but shown on large screens
   - c) It's a Tailwind requirement
   - d) Hidden elements still load their content

   **Answer:** b) Responsive — no room on mobile, show on desktop.

2. How is the blinking cursor animated?
   - a) JavaScript setInterval
   - b) CSS `@keyframes` animation on the cursor element
   - c) A GIF image
   - d) React state toggling visibility

   **Answer:** b) Pure CSS animation — `animation: blink 1s step-end infinite` toggles opacity.

3. What does `pt-20` on the hero section do?
   - a) Sets padding top to 20px
   - b) Adds top padding of 80px to avoid the fixed navbar overlapping content
   - c) Sets font size to 20
   - d) Creates 20rem top padding

   **Answer:** b) 20 × 4px = 80px padding — enough to clear the fixed navbar height.
