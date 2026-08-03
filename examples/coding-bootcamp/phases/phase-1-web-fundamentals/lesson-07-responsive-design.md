---
title: "Responsive Design"
phase: 1
lesson: 7
duration_minutes: 35
prerequisites: ["1.6"]
skills_unlocked: []
objectives:
  - id: media-queries
    text: "Use media queries to adapt styles for different screen sizes"
    tested_by: [2]
  - id: mobile-first
    text: "Understand mobile-first design"
    tested_by: [1]
  - id: the-viewport-meta-tag
    text: "Use the viewport meta tag correctly"
    tested_by: [3]
  - id: layouts-across-devices
    text: "Build layouts that work on mobile, tablet, and desktop"
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
**Responsive design** means your website adapts to any screen size — phone, tablet, desktop, TV.

**The viewport meta tag** (in your `<head>`) — always include this:
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0">
```
Without this, mobile browsers zoom out to show the "full" desktop site.

**Media queries** apply styles only when conditions are met:
```css
/* Mobile styles first (no query needed) */
.container { padding: 16px; }

/* Tablet and up */
@media (min-width: 768px) {
  .container { padding: 32px; }
}

/* Desktop and up */
@media (min-width: 1024px) {
  .container { padding: 64px; }
}
```

**Mobile-first** approach: Start with mobile styles, add complexity for larger screens. This is best practice — mobile is harder, so solve it first.

**Common breakpoints:**
- Mobile: < 640px (no query)
- Tablet: 640px - 1024px
- Desktop: > 1024px

## Key Terms
- **Responsive design**: Layouts that adapt to different screen sizes
- **Viewport**: The visible area of the browser window
- **Media query**: CSS rule that applies only when conditions are met
- **Breakpoint**: The screen width at which the layout changes
- **Mobile-first**: Writing mobile styles first, adding desktop styles after

## Hands-On Exercise
Make your layout responsive:

```css
/* Mobile first */
.hero {
  padding: 60px 24px;
  text-align: center;
}

.hero h1 { font-size: 2rem; }

.projects-grid {
  grid-template-columns: 1fr; /* Single column on mobile */
  padding: 24px;
}

/* Tablet */
@media (min-width: 640px) {
  .hero h1 { font-size: 3rem; }
  .projects-grid {
    grid-template-columns: 1fr 1fr;
    padding: 32px;
  }
}

/* Desktop */
@media (min-width: 1024px) {
  .hero { padding: 120px 64px; }
  .hero h1 { font-size: 4rem; }
  .projects-grid {
    grid-template-columns: repeat(3, 1fr);
    padding: 64px;
  }
}
```

Open DevTools → click the phone icon → test different screen sizes!

## Quick Quiz
1. Why is mobile-first design a best practice?
   - a) Mobile is more popular
   - b) Starting with constraints forces better design decisions; then you enhance for larger screens
   - c) It's required by Google
   - d) Desktop layouts are no longer supported

   **Answer:** b) Starting with constraints forces better design — it's easier to add complexity than remove it.

2. What does this media query do: `@media (min-width: 768px)`?
   - a) Applies styles only on screens SMALLER than 768px
   - b) Applies styles on screens 768px wide and wider
   - c) Sets the minimum page width to 768px
   - d) Applies styles only on 768px screens exactly

   **Answer:** b) Applies on screens 768px wide and wider — `min-width` means "at least this wide".

3. What is the viewport meta tag used for?
   - a) Setting the page title for mobile
   - b) Telling mobile browsers not to zoom out to show the full desktop site
   - c) Enabling touch events
   - d) Setting the background color on mobile

   **Answer:** b) Telling mobile browsers to use the actual device width — critical for responsive design.

## Next Up
**HTML Forms** — collecting input from users.
