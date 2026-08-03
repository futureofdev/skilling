---
title: "Building the Skills Section"
phase: 6
lesson: 5
duration_minutes: 30
prerequisites: ["6.4"]
skills_unlocked: []
objectives:
  - id: a-data-driven-skills-grid
    text: "Build a data-driven skills grid from a TypeScript data file"
    tested_by: [2]
  - id: astro-templates-with-typed-data
    text: "Use Astro's template syntax with typed data"
    tested_by: [1, 3]
  - id: a-dot-indicator-display
    text: "Create a dot-indicator skill level display"
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
The Skills section reads from `src/data/skills.ts` and renders a grid — no React needed because there's no interactivity.

```astro
---
import { skills } from "../data/skills";
const categories = ["Frontend", "Backend", "Tools"] as const;
const levelDots = { beginner: 1, intermediate: 2, advanced: 3 };
---

<section id="skills" class="py-24">
  <div class="max-w-6xl mx-auto px-6">
    <div class="grid md:grid-cols-3 gap-8">
      {categories.map(category => (
        <div class="rounded-xl p-6 border" style="background: var(--color-surface)">
          <h3 class="font-mono text-lg font-bold mb-6">{category}</h3>
          {skills
            .filter(s => s.category === category)
            .map(skill => (
              <div class="flex items-center justify-between mb-3">
                <span>{skill.name}</span>
                <div class="flex gap-1">
                  {[1,2,3].map(dot => (
                    <div class={`w-2 h-2 rounded-full`} style={`background: ${dot <= levelDots[skill.level] ? "var(--color-accent)" : "var(--color-border)"}`} />
                  ))}
                </div>
              </div>
            ))}
        </div>
      ))}
    </div>
  </div>
</section>
```

## Quick Quiz
1. Why is this section Astro instead of React?
   - a) React can't render grids
   - b) The data is static — no user interaction, no state changes needed
   - c) Astro is always better for grids
   - d) TypeScript doesn't work in React

   **Answer:** b) Static data display — Astro renders it to pure HTML at build time, zero JavaScript.

2. What does `.filter(s => s.category === category)` do?
   - a) Removes skills with the given category
   - b) Returns only skills matching the current category being rendered
   - c) Counts skills in the category
   - d) Sorts skills alphabetically

   **Answer:** b) Filters the skills array to only those matching the current category column.

3. What TypeScript feature ensures only valid categories are used?
   - a) `interface Category`
   - b) `as const` on the array, ensuring Astro knows the exact string values
   - c) `typeof categories`
   - d) Generic types

   **Answer:** b) `as const` narrows the type from `string[]` to a readonly tuple of literal types.
