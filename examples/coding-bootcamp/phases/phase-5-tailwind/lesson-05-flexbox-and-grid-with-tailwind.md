---
title: "Flexbox and Grid with Tailwind"
phase: 5
lesson: 5
duration_minutes: 30
prerequisites: ["5.4"]
skills_unlocked: []
objectives:
  - id: flex-and-grid-utilities
    text: "Create flex and grid layouts using Tailwind utilities"
    tested_by: [1, 2]
  - id: alignment-and-gap
    text: "Apply alignment and gap utilities"
    tested_by: [3]
  - id: a-responsive-card-grid
    text: "Build a responsive card grid"
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Utilities are practised directly on the portfolio as it is restyled, so there is no separate exercise to attempt."
  next_up: present
---

## The Concept
Tailwind wraps flexbox and grid as utilities:

**Flexbox:**
```html
<div class="flex items-center justify-between gap-4">
  <div>Left</div>
  <div>Right</div>
</div>
```
- `flex` = `display: flex`
- `items-center` = `align-items: center`
- `justify-between` = `justify-content: space-between`
- `gap-4` = `gap: 1rem`
- `flex-col` = `flex-direction: column`
- `flex-1` = `flex: 1`
- `flex-wrap` = `flex-wrap: wrap`

**Grid:**
```html
<div class="grid grid-cols-3 gap-6">
  <div>Card 1</div>
  <div>Card 2</div>
  <div>Card 3</div>
</div>

<!-- Responsive auto-fill grid -->
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
```

- `grid` = `display: grid`
- `grid-cols-3` = `grid-template-columns: repeat(3, 1fr)`
- `col-span-2` = `grid-column: span 2`

## Key Terms
- **`flex`**: Enable flexbox on container
- **`items-*`**: `align-items` (cross-axis)
- **`justify-*`**: `justify-content` (main-axis)
- **`gap-*`**: Gap between flex/grid items
- **`grid`**: Enable grid on container
- **`grid-cols-{n}`**: Define n equal columns

## Quick Quiz
1. What does `flex items-center justify-center` create?
   - a) A flex container with items at the start
   - b) A flex container with items centered both horizontally and vertically
   - c) A centered block element
   - d) Three flex columns

   **Answer:** b) `items-center` = vertical center, `justify-center` = horizontal center in a row layout.

2. How do you create a 3-column grid with Tailwind?
   - a) `columns-3`
   - b) `grid grid-cols-3`
   - c) `flex flex-3`
   - d) `display-grid col-3`

   **Answer:** b) `grid grid-cols-3` — `grid` enables grid, `grid-cols-3` creates 3 equal columns.

3. What does `gap-6` do?
   - a) Creates 6 columns
   - b) Adds 6px gap
   - c) Adds 1.5rem (24px) gap between grid/flex items
   - d) Creates 6 rows

   **Answer:** c) `gap-6` = 6 × 0.25rem = 1.5rem = 24px gap between items.

## Next Up
**Responsive Design with Tailwind** — mobile-first breakpoints.
