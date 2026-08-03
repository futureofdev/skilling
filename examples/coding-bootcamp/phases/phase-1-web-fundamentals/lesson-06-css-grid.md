---
title: "CSS Grid"
phase: 1
lesson: 6
duration_minutes: 35
prerequisites: ["1.5"]
skills_unlocked: []
objectives:
  - id: display-grid
    text: "Create grid layouts with display: grid"
  - id: define-columns-and-rows
    text: "Define columns and rows"
    tested_by: [1]
  - id: responsive-grids
    text: "Use auto-fill and minmax() for responsive grids"
    tested_by: [3]
  - id: grid-vs-flexbox
    text: "Know when to use Grid rather than Flexbox"
    tested_by: [2]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
CSS Grid is a two-dimensional layout system — you control both rows AND columns simultaneously.

```css
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr; /* 3 equal columns */
  gap: 24px;
}
```

**Key properties:**
- `grid-template-columns` — defines column sizes
- `grid-template-rows` — defines row sizes
- `gap` — space between cells
- `fr` unit — "fraction" of available space
- `auto-fill` + `minmax()` — responsive grid that adapts to screen size

**Responsive magic:**
```css
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 24px;
}
```
This creates as many columns as fit, each at least 280px wide — responsive with no media queries!

**Grid vs Flexbox:**
- Use **Flexbox** for 1D layouts (a single row or column)
- Use **Grid** for 2D layouts (rows AND columns)

## Key Terms
- **Grid container**: Element with `display: grid`
- **Grid item**: Direct child of a grid container
- **Grid line**: The dividing lines making up the grid
- **fr unit**: Fraction of the available grid space
- **auto-fill**: Fills the row with as many columns as will fit
- **minmax(min, max)**: Column size between min and max

## Hands-On Exercise
Create a project card grid:

```css
.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 24px;
  padding: 40px;
}

.card {
  background: white;
  border-radius: 12px;
  padding: 24px;
  border: 1px solid #eee;
}
```

```html
<section class="projects-grid">
  <div class="card"><h3>Project 1</h3><p>Description here.</p></div>
  <div class="card"><h3>Project 2</h3><p>Description here.</p></div>
  <div class="card"><h3>Project 3</h3><p>Description here.</p></div>
  <div class="card"><h3>Project 4</h3><p>Description here.</p></div>
</section>
```

Resize your browser — the grid adapts automatically!

## Quick Quiz
1. What does `grid-template-columns: 1fr 2fr 1fr` create?
   - a) Three equal columns
   - b) Three columns where the middle is twice as wide as the others
   - c) Columns of 1px, 2px, and 1px
   - d) A single column

   **Answer:** b) Three columns where the middle is twice as wide — `fr` units distribute proportionally.

2. When should you choose CSS Grid over Flexbox?
   - a) Always — Grid is better in every situation
   - b) When you need 2D control (rows AND columns simultaneously)
   - c) Only for navigation bars
   - d) Never — Flexbox replaced Grid

   **Answer:** b) When you need 2D control — Grid excels at complex layouts with both rows and columns.

3. What does `repeat(auto-fill, minmax(200px, 1fr))` do?
   - a) Creates exactly 200 columns
   - b) Creates columns that are always 200px wide
   - c) Creates as many columns as will fit, each between 200px and 1fr
   - d) Repeats the grid automatically

   **Answer:** c) Creates as many columns as will fit, each at least 200px — this is the responsive grid pattern.

## Next Up
**Responsive Design** — making your site look great on mobile, tablet, and desktop.
