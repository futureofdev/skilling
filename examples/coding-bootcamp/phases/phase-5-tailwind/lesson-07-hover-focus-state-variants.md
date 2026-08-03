---
title: "Hover, Focus, and State Variants"
phase: 5
lesson: 7
duration_minutes: 25
prerequisites: ["5.6"]
skills_unlocked: [tailwind-fundamentals]
objectives:
  - id: hover-styles
    text: "Add hover styles with the hover: prefix"
    tested_by: [1]
  - id: focus-states
    text: "Style focus states with the focus: prefix"
  - id: transitions
    text: "Use transition for smooth animations"
    tested_by: [2]
  - id: group-variants
    text: "Apply group for parent-triggered child styles"
    tested_by: [3]
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Utilities are practised directly on the portfolio as it is restyled, so there is no separate exercise to attempt."
  next_up: present
---

## The Concept
Tailwind's state variants work like breakpoints — prefix any utility to apply it on a state.

**Hover:**
```html
<button class="bg-blue-500 hover:bg-blue-600 transition-colors">
  Click me
</button>
```

**Focus:**
```html
<input class="border border-gray-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none">
```

**Transitions:**
```html
<button class="transition-all duration-200 hover:scale-105 hover:shadow-lg">
  Hover me
</button>
```
- `transition` or `transition-all` = adds transition to properties
- `duration-200` = 200ms transition
- `ease-in-out` = easing function

**Group hover** — style children when parent is hovered:
```html
<div class="group cursor-pointer">
  <h3 class="text-gray-800 group-hover:text-blue-500">Title</h3>
  <p class="text-gray-500 group-hover:text-gray-700">Description</p>
</div>
```

## Key Terms
- **`hover:`**: Apply styles on hover
- **`focus:`**: Apply styles when element is focused
- **`transition`**: Enable smooth transitions
- **`duration-*`**: Transition duration
- **`group`**: Mark parent so children can use `group-hover:` etc.
- **`group-hover:`**: Style child when parent is hovered

## Quick Quiz
1. How do you make a button darken on hover in Tailwind?
   - a) `darken-hover`
   - b) Add `hover:bg-{darker-color}` alongside the base `bg-{color}`
   - c) `:hover` CSS selector in a `<style>` tag
   - d) JavaScript mouse events

   **Answer:** b) `bg-blue-500 hover:bg-blue-700` — Tailwind generates the hover CSS.

2. What does adding `transition-colors duration-200` do?
   - a) Changes color every 200ms automatically
   - b) Animates color changes over 200ms when triggered (e.g., on hover)
   - c) Sets 200 color transitions
   - d) Limits transitions to color properties only

   **Answer:** b) Smooth color transitions on state changes — hover effects feel polished.

3. What does the `group` class enable?
   - a) Grouping elements visually with a border
   - b) Allowing children to use `group-hover:` to style themselves when the parent is hovered
   - c) Creating a flexbox group
   - d) Grouping animations

   **Answer:** b) Parent-child hover coordination — child responds to parent being hovered.

## Homework Assignment
### Phase 5 Homework: Style the Portfolio

**Objective:** Apply Tailwind CSS utilities throughout the portfolio site.

**Requirements:**
- [ ] Use Tailwind utilities for ALL layout (no separate custom CSS for layout)
- [ ] Apply responsive breakpoints — single column on mobile, multi-column on desktop
- [ ] Add hover states to navigation links and project cards
- [ ] Add `transition` for smooth hover effects
- [ ] Use `max-w-6xl mx-auto` for content width limiting
- [ ] Apply at least 3 different text size utilities
- [ ] Use `gap-*` for consistent spacing in grids/flex containers

**Stretch Goals:**
- [ ] Use `group` and `group-hover:` for card hover effects
- [ ] Add `focus:` styles to form inputs
- [ ] Create a `dark:` variant (Tailwind v4 supports this natively)

**Submission:** Show Claude a screenshot of the portfolio on mobile and desktop sizes.

## Next Up
Phase 6: **Building the Portfolio** — putting everything together to build the actual portfolio sections!
