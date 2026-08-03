---
title: "Typography and Colors"
phase: 5
lesson: 3
duration_minutes: 30
prerequisites: ["5.2"]
skills_unlocked: []
objectives:
  - id: text-utilities
    text: "Use Tailwind text utilities for size, weight, colour and alignment"
    tested_by: [1, 2]
  - id: background-and-border-colours
    text: "Apply background and border colours"
    tested_by: [3]
  - id: css-custom-properties
    text: "Use CSS custom properties alongside Tailwind"
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Utilities are practised directly on the portfolio as it is restyled, so there is no separate exercise to attempt."
  next_up: present
---

## The Concept
**Text utilities:**
```html
<h1 class="text-4xl font-black tracking-tight text-white">
  Heading
</h1>
<p class="text-base text-gray-400 leading-relaxed">
  Body text
</p>
```

**Size scale:** `text-xs` (12px) → `text-sm` → `text-base` (16px) → `text-lg` → `text-xl` → `text-2xl` → ... → `text-9xl`

**Weight:** `font-thin` → `font-light` → `font-normal` → `font-medium` → `font-semibold` → `font-bold` → `font-extrabold` → `font-black`

**Color utilities:**
```html
<div class="bg-slate-900 text-white border border-slate-700">
  Dark card
</div>
```

**With CSS variables (your design system):**
```html
<!-- In Tailwind v4, CSS custom properties work directly -->
<h1 style="color: var(--color-accent)">
  Or use inline styles for custom properties
</h1>
```

## Key Terms
- **`text-{size}`**: Font size utility
- **`font-{weight}`**: Font weight utility  
- **`text-{color}-{shade}`**: Text color (e.g., `text-blue-500`)
- **`bg-{color}-{shade}`**: Background color
- **`leading-{value}`**: Line height

## Quick Quiz
1. What class makes text bold in Tailwind?
   - a) `text-bold`
   - b) `bold`
   - c) `font-bold`
   - d) `weight-bold`

   **Answer:** c) `font-bold` — Tailwind uses the `font-{weight}` pattern.

2. What does `text-lg` do?
   - a) Sets text color to light gray
   - b) Sets font size to large (18px / 1.125rem)
   - c) Makes text lowercase
   - d) Sets line height to large

   **Answer:** b) Font size large — `text-lg` = `font-size: 1.125rem`.

3. How do you set a background color in Tailwind?
   - a) `background-blue`
   - b) `color-bg-blue`
   - c) `bg-blue-500`
   - d) `background: blue-500`

   **Answer:** c) `bg-{color}-{shade}` — e.g., `bg-blue-500`, `bg-gray-900`, `bg-white`.

## Next Up
**Spacing, Sizing, and Layout** — Tailwind's padding, margin, and width utilities.
