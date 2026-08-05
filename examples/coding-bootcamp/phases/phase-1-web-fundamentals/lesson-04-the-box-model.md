---
title: "The Box Model"
phase: 1
lesson: 4
duration_minutes: 30
prerequisites: ["1.3"]
skills_unlocked: []
objectives:
  - id: the-box-model
    kind: knowledge
    text: "Understand the CSS box model: content, padding, border, margin"
    about: [1]
  - id: border-box
    kind: practice
    text: "Use box-sizing: border-box correctly"
    about: [2]
  - id: debug-with-devtools
    kind: practice
    text: "Debug layout issues using browser DevTools"
  - id: control-spacing
    kind: practice
    text: "Control spacing between and around elements"
    about: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
Every HTML element is a rectangular box. The **box model** defines the layers of that box:

```
┌─────────────────────────────┐
│           margin            │
│  ┌───────────────────────┐  │
│  │        border         │  │
│  │  ┌─────────────────┐  │  │
│  │  │     padding     │  │  │
│  │  │  ┌───────────┐  │  │  │
│  │  │  │  content  │  │  │  │
│  │  │  └───────────┘  │  │  │
│  │  └─────────────────┘  │  │
│  └───────────────────────┘  │
└─────────────────────────────┘
```

- **Content**: The actual text/image
- **Padding**: Space between content and border
- **Border**: A line around the padding
- **Margin**: Space outside the border (between elements)

**`box-sizing: border-box`** (always use this!)
By default, `width: 200px` means the content is 200px wide — padding and border ADD to that. With `border-box`, `width: 200px` means the TOTAL box is 200px.

```css
/* Always add this — prevents math headaches */
* { box-sizing: border-box; }
```

## Key Terms
- **Box model**: The layered model of content, padding, border, and margin
- **Content box**: Default sizing — width = content only
- **Border box**: Better sizing — width = content + padding + border
- **Margin collapse**: When adjacent vertical margins merge into one

## Hands-On Exercise
Open your browser DevTools (F12) and:

1. Go to any website
2. Click the Elements tab
3. Hover over elements — you'll see the box model highlighted
4. Click an element, look at "Computed" in the right panel
5. You'll see the actual box model dimensions!

Now in your project CSS, experiment:
```css
.card {
  width: 300px;
  padding: 24px;
  border: 2px solid #ccc;
  margin: 16px;
  background: white;
  border-radius: 8px;
  /* box-sizing: border-box is already set in your * reset */
}
```

## Quick Quiz
1. What does `padding` do?
   - a) Creates space outside the element
   - b) Creates space between the content and the border
   - c) Creates a visible line around the element
   - d) Adjusts the content size

   **Answer:** b) Creates space between content and border — it's inside the element.

2. Why is `box-sizing: border-box` recommended?
   - a) It makes borders look better
   - b) It makes width include padding and border, preventing unexpected sizing
   - c) It removes all margins
   - d) It's required by browsers

   **Answer:** b) It makes width predictable — the element stays the width you specify.

3. What is margin collapse?
   - a) When a margin becomes zero
   - b) When vertical margins between adjacent elements merge into the larger of the two
   - c) When too many margins cause a layout error
   - d) When margins and padding are equal

   **Answer:** b) When vertical margins between adjacent elements merge — two 16px margins touching become 16px (not 32px).

## Next Up
**Flexbox** — the modern way to create rows and columns in CSS.
