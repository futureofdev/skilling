---
title: "Spacing, Sizing, and Layout"
phase: 5
lesson: 4
duration_minutes: 30
prerequisites: ["5.3"]
skills_unlocked: []
objectives:
  - id: padding-and-margin
    text: "Use padding and margin utilities"
    tested_by: [1]
  - id: width-and-height
    text: "Control element width and height"
    tested_by: [3]
  - id: max-width-for-readability
    text: "Use max-width for readable content"
    tested_by: [2]
  - id: centre-with-mx-auto
    text: "Centre elements with mx-auto"
    tested_by: [2]
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Utilities are practised directly on the portfolio as it is restyled, so there is no separate exercise to attempt."
  next_up: present
---

## The Concept
Tailwind uses a **spacing scale** based on 4px (0.25rem) increments:
- `1` = 4px | `2` = 8px | `4` = 16px | `6` = 24px | `8` = 32px | `12` = 48px | `16` = 64px

**Padding:**
```html
<div class="p-4">      <!-- all sides: 16px -->
<div class="px-6 py-3"> <!-- x: 24px, y: 12px -->
<div class="pt-8">      <!-- top only: 32px -->
```

**Margin:**
```html
<div class="m-4">       <!-- all sides -->
<div class="mx-auto">   <!-- center horizontally -->
<div class="mt-8 mb-4"> <!-- top: 32px, bottom: 16px -->
```

**Width and max-width:**
```html
<div class="w-full">         <!-- 100% width -->
<div class="w-1/2">          <!-- 50% width -->
<div class="max-w-6xl mx-auto"> <!-- centered, max 72rem -->
<div class="w-64">           <!-- 256px fixed width -->
```

**Height:**
```html
<div class="h-screen">  <!-- 100vh -->
<div class="min-h-screen"> <!-- at least 100vh -->
<div class="h-16">      <!-- 64px -->
```

## Key Terms
- **Spacing scale**: 1 unit = 0.25rem (4px)
- **`p-*`**: Padding (all sides)
- **`px-*` / `py-*`**: Horizontal / vertical padding
- **`m-*`**: Margin
- **`mx-auto`**: Horizontal centering with auto margins
- **`max-w-*`**: Maximum width constraint

## Quick Quiz
1. What does `px-6 py-3` apply?
   - a) 6px padding all around, 3px margin
   - b) Left/right padding of 24px, top/bottom padding of 12px
   - c) 6rem padding horizontal, 3rem vertical
   - d) 6 and 3 units of padding evenly distributed

   **Answer:** b) px = horizontal padding × 4px/unit: 6×4=24px; py = vertical: 3×4=12px.

2. How do you center a `div` horizontally with a max width?
   - a) `center max-w-lg`
   - b) `max-w-4xl mx-auto`
   - c) `align-center width-limited`
   - d) `container`

   **Answer:** b) `max-w-4xl mx-auto` — max-width limits it, auto margins center it.

3. What does `min-h-screen` do?
   - a) Sets minimum font size to screen-readable
   - b) Sets minimum height to 100vh (full viewport height)
   - c) Makes the element take up the full screen width
   - d) Sets minimum screen resolution

   **Answer:** b) `min-h-screen` = `min-height: 100vh` — useful for full-page sections.

## Next Up
**Flexbox and Grid with Tailwind** — layout utilities.
