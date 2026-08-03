---
title: "CSS: Styling the Web"
phase: 1
lesson: 3
duration_minutes: 40
prerequisites: ["1.2"]
skills_unlocked: []
objectives:
  - id: write-css-rules
    text: "Write CSS rules with selectors, properties, and values"
    tested_by: [1]
  - id: link-a-stylesheet
    text: "Connect a CSS file to an HTML file"
  - id: common-properties
    text: "Use the most common CSS properties"
    tested_by: [2]
  - id: specificity-and-the-cascade
    text: "Understand specificity and the cascade"
    tested_by: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
CSS (Cascading Style Sheets) controls how HTML looks. A CSS rule has three parts:

```css
selector {
  property: value;
  property: value;
}
```

**Selectors** target HTML elements:
- `p` — all paragraphs
- `.class-name` — elements with class="class-name"
- `#id-name` — element with id="id-name"
- `h1, h2` — multiple selectors
- `nav a` — `<a>` elements inside a `<nav>`

**Common properties:**
```css
color: #333;              /* text color */
background-color: white;  /* background */
font-size: 16px;          /* text size */
font-weight: bold;        /* text weight */
font-family: sans-serif;  /* font */
margin: 16px;             /* space outside */
padding: 16px;            /* space inside */
border: 1px solid black;  /* border */
border-radius: 8px;       /* rounded corners */
text-decoration: none;    /* remove underline from links */
```

**The Cascade**: When multiple rules target the same element, the more specific rule wins. If specificity is equal, the last rule wins.

## Key Terms
- **Selector**: CSS code that targets HTML elements
- **Property**: What you're styling (color, margin, font-size)
- **Value**: What you're setting the property to
- **Class**: Reusable label added with `class="name"` in HTML
- **Specificity**: How "specific" a selector is (determines which rule wins)
- **Cascade**: CSS rules flowing from multiple sources, with specificity determining winners

## Hands-On Exercise
Add CSS to your HTML from last lesson:

1. Create `styles.css` in the same folder as `index.html`
2. Link it in `<head>`: `<link rel="stylesheet" href="styles.css">`
3. Add these styles:

```css
/* Reset some defaults */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: sans-serif;
  color: #333;
  background: #f9f9f9;
}

header {
  background: #0D0F14;
  color: white;
  padding: 40px;
  text-align: center;
}

nav a {
  color: #00D4AA;
  text-decoration: none;
  margin: 0 16px;
}

h1 { font-size: 2.5rem; margin-top: 16px; }
h2 { font-size: 1.5rem; margin-bottom: 16px; }

main { max-width: 800px; margin: 40px auto; padding: 0 24px; }
section { margin-bottom: 40px; }
footer { text-align: center; padding: 24px; color: #666; }
```

Refresh your browser — your page now has styles!

## Quick Quiz
1. How do you target all elements with `class="card"` in CSS?
   - a) `card { }`
   - b) `#card { }`
   - c) `.card { }`
   - d) `*card { }`

   **Answer:** c) `.card { }` — dot prefix targets class names.

2. What is the difference between `margin` and `padding`?
   - a) Margin is inside the element; padding is outside
   - b) Margin is space outside the element; padding is space inside
   - c) They are the same
   - d) Margin affects text; padding affects borders

   **Answer:** b) Margin is space outside; padding is space inside.

3. If two CSS rules target the same element with equal specificity, which wins?
   - a) The first rule wins
   - b) The last rule wins (cascade)
   - c) Neither — they cancel out
   - d) The shorter rule wins

   **Answer:** b) The last rule wins — CSS cascades top to bottom, later rules override earlier ones.

## Next Up
Understanding **the CSS Box Model** — the foundation of all layout.
