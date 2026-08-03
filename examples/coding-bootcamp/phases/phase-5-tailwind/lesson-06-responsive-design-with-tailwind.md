---
title: "Responsive Design with Tailwind"
phase: 5
lesson: 6
duration_minutes: 30
prerequisites: ["5.5"]
skills_unlocked: []
objectives:
  - id: responsive-prefixes
    text: "Use Tailwind's responsive prefixes"
    tested_by: [1, 2]
  - id: mobile-first-with-tailwind
    text: "Apply mobile-first design with Tailwind"
    tested_by: [3]
  - id: adapt-mobile-to-desktop
    text: "Build layouts that adapt from mobile to desktop"
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Utilities are practised directly on the portfolio as it is restyled, so there is no separate exercise to attempt."
  next_up: present
---

## The Concept
Tailwind is mobile-first. No prefix = mobile. Add prefix = applies at that size and above.

**Breakpoints:**
- `sm:` = ≥ 640px
- `md:` = ≥ 768px
- `lg:` = ≥ 1024px
- `xl:` = ≥ 1280px

```html
<!-- Single column on mobile, 2 on tablet, 3 on desktop -->
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

<!-- Hidden on mobile, visible on desktop -->
<div class="hidden lg:block">Desktop only content</div>

<!-- Different text sizes per breakpoint -->
<h1 class="text-3xl md:text-5xl lg:text-7xl font-black">
  Big Heading
</h1>

<!-- Different padding per breakpoint -->
<section class="px-4 md:px-8 lg:px-16 py-12 lg:py-24">
```

**Pattern:** Write mobile styles first, then add `md:` and `lg:` prefixes to override for larger screens.

## Key Terms
- **Breakpoint prefix**: `sm:`, `md:`, `lg:`, `xl:` — apply class at this width and above
- **Mobile-first**: Default styles for mobile, enhanced for larger screens
- **`hidden`**: `display: none`
- **`block`**: `display: block`

## Quick Quiz
1. What does `text-xl lg:text-4xl` do?
   - a) Sets text to 4xl on mobile, xl on desktop
   - b) Sets text to xl by default (mobile), and 4xl on large screens and above
   - c) Creates a text animation
   - d) Sets two different text elements

   **Answer:** b) Mobile-first — `text-xl` is the base, `lg:text-4xl` overrides at 1024px+.

2. What does `hidden md:block` do?
   - a) Hides the element on all screens
   - b) Hides on mobile, shows as block on medium screens and above
   - c) Shows on mobile, hides on desktop
   - d) Makes the element transparent

   **Answer:** b) `hidden` hides it by default; `md:block` shows it on 768px+.

3. In Tailwind's mobile-first approach, which breakpoint applies to the smallest screens?
   - a) `sm:`
   - b) `xs:`
   - c) No prefix — mobile styles have no breakpoint prefix
   - d) `mobile:`

   **Answer:** c) No prefix — utilities without a breakpoint apply to all sizes (mobile first).

## Next Up
**Hover, Focus, and State Variants** — interactive styling with Tailwind.
