---
title: "Your First Webpage (Project)"
phase: 1
lesson: 9
duration_minutes: 60
prerequisites: ["1.8"]
skills_unlocked: [web-fundamentals]
objectives:
  - id: build-a-responsive-page
    text: "Build a complete, styled, responsive webpage from scratch"
    tested_by: [1, 3]
  - id: apply-what-you-learned
    text: "Apply HTML, CSS, Flexbox, Grid, responsiveness and forms together"
    tested_by: [2]
  - id: have-a-real-project
    text: "Have a real project to show off"
sections:
  key_terms:
    status: none
    intent: "Project lesson: it applies the vocabulary introduced earlier in the phase rather than adding any."
  exercise: present
  next_up: present
---

## The Concept
This is a project lesson. You're going to build a complete personal webpage using raw HTML and CSS (no frameworks). This teaches you the foundations before we add tools like Astro and Tailwind.

The page will have:
1. A navigation bar (Flexbox)
2. A hero section (full-screen, centered)
3. An about section (two-column grid on desktop)
4. A projects section (card grid with auto-fill)
5. A contact form
6. A footer
7. Responsive for mobile + desktop

## Hands-On Exercise
Build the full page! Here's the structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your Name — Developer</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <nav>...</nav>
  <section id="hero">...</section>
  <section id="about">...</section>
  <section id="projects">...</section>
  <section id="contact">...</section>
  <footer>...</footer>
</body>
</html>
```

Use what you've learned in every section! Ask Claude for help if you get stuck.

## Quick Quiz
1. Which CSS property creates a two-column layout?
   - a) `display: two-column`
   - b) `grid-template-columns: 1fr 1fr` or `display: flex`
   - c) `columns: 2`
   - d) `layout: grid`

   **Answer:** b) Either Grid (`grid-template-columns: 1fr 1fr`) or Flexbox with two children.

2. How do you center content vertically AND horizontally using Flexbox?
   - a) `text-align: center; vertical-align: middle`
   - b) `justify-content: center; align-items: center`
   - c) `margin: auto`
   - d) `position: center`

   **Answer:** b) `justify-content: center` (horizontal) + `align-items: center` (vertical) on the container.

3. What viewport meta tag is required for responsive design?
   - a) `<meta name="responsive" content="true">`
   - b) `<meta name="mobile" content="enabled">`
   - c) `<meta name="viewport" content="width=device-width, initial-scale=1.0">`
   - d) No meta tag needed

   **Answer:** c) The viewport meta tag — without it, mobile browsers zoom out to fit the "desktop" layout.

## Homework Assignment
### Phase 1 Homework: Personal Webpage

**Objective:** Build a complete, styled, responsive personal webpage using only HTML and CSS.

**Requirements:**
- [ ] Navigation bar using Flexbox (logo on left, links on right)
- [ ] Hero section with your name, role/title, and a call-to-action button
- [ ] About section with a paragraph about yourself
- [ ] Projects section with at least 3 project cards in a grid
- [ ] Contact form with name, email, and message fields (with labels)
- [ ] Footer with copyright text
- [ ] Responsive: works on mobile (single column) and desktop (multi-column)
- [ ] At least 3 different colors used (not default blue/black/white)
- [ ] `box-sizing: border-box` reset applied

**Stretch Goals:**
- [ ] Add hover effects on navigation links and buttons
- [ ] Add a CSS transition/animation somewhere
- [ ] Make the navigation sticky (stays at top while scrolling)

**Submission:** Share a screenshot of your page on desktop and mobile, or open the file in VS Code and show Claude.

## Next Up
Phase 2: **JavaScript** — making your webpage interactive with real programming!
