---
title: "Flexbox Layout"
phase: 1
lesson: 5
duration_minutes: 40
prerequisites: ["1.4"]
skills_unlocked: []
objectives:
  - id: display-flex
    text: "Use display: flex to create flexible layouts"
    tested_by: [3]
  - id: direction-and-alignment
    text: "Control direction, alignment, and distribution of items"
    tested_by: [1, 2]
  - id: build-a-nav-and-card-row
    text: "Build a navigation bar and a card row with flexbox"
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
Flexbox is a CSS layout system for arranging items in a row or column, with powerful alignment controls.

```css
.container {
  display: flex;
  /* now children are flex items */
}
```

**Key properties on the container:**
- `flex-direction: row | column` — direction of items
- `justify-content: flex-start | center | flex-end | space-between | space-around` — alignment along main axis
- `align-items: stretch | center | flex-start | flex-end` — alignment along cross axis
- `gap: 16px` — space between items
- `flex-wrap: wrap` — allow items to wrap to next line

**Key properties on items:**
- `flex: 1` — item grows to fill available space
- `flex-shrink: 0` — item won't shrink
- `align-self` — override container's align-items for this item

## Key Terms
- **Flex container**: The parent element with `display: flex`
- **Flex items**: Direct children of the flex container
- **Main axis**: The primary direction (row = horizontal, column = vertical)
- **Cross axis**: Perpendicular to the main axis
- **justify-content**: Alignment along the main axis
- **align-items**: Alignment along the cross axis

## Hands-On Exercise
Build a navigation bar:

```css
.nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 40px;
  background: #0D0F14;
}

.nav-logo { color: #00D4AA; font-weight: bold; }

.nav-links {
  display: flex;
  gap: 24px;
  list-style: none;
}

.nav-links a {
  color: white;
  text-decoration: none;
}
```

```html
<nav class="nav">
  <span class="nav-logo">~/dev</span>
  <ul class="nav-links">
    <li><a href="#">About</a></li>
    <li><a href="#">Projects</a></li>
    <li><a href="#">Contact</a></li>
  </ul>
</nav>
```

## Quick Quiz
1. What does `justify-content: space-between` do?
   - a) Centers all items
   - b) Places items with equal space between them, first and last flush with edges
   - c) Adds space around each item including the edges
   - d) Stacks items vertically

   **Answer:** b) Places items with equal space between them, first and last at the edges — perfect for nav bars.

2. What does `align-items: center` do?
   - a) Centers items horizontally
   - b) Centers text inside items
   - c) Centers items along the cross axis (vertically in a row layout)
   - d) Makes all items the same width

   **Answer:** c) Centers items along the cross axis — in a row layout, this vertically centers items.

3. What does `flex: 1` do on a flex item?
   - a) Makes the item 1px wide
   - b) Makes the item grow to fill available space
   - c) Sets the item's flex order to 1
   - d) Removes the item from the flex layout

   **Answer:** b) Makes the item grow to fill available space — useful for making elements fill remaining room.

## Next Up
**CSS Grid** — the two-dimensional layout system for complex page layouts.
