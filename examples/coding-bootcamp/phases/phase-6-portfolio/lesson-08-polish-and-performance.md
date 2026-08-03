---
title: "Polish and Performance"
phase: 6
lesson: 8
duration_minutes: 35
prerequisites: ["6.7"]
skills_unlocked: [portfolio-complete]
objectives:
  - id: run-lighthouse
    text: "Run Lighthouse to measure performance"
    tested_by: [2]
  - id: optimise-images-and-fonts
    text: "Optimise images and fonts"
    tested_by: [1]
  - id: meta-tags-for-sharing
    text: "Add meta tags for search and social sharing"
    tested_by: [3]
  - id: verify-accessibility
    text: "Verify the site is accessible"
sections:
  key_terms:
    status: none
    intent: "Build lesson: the vocabulary was established in the phases this section draws on."
  exercise:
    status: none
    intent: "Project phase: the exercise is the learner's own portfolio, built section by section as the lesson goes."
  next_up: present
---

## The Concept
A great portfolio needs great performance. Astro gives you a head start (zero JS by default), but there are still optimizations to make.

**Check your Lighthouse score:**
1. `npm run build && npm run preview`
2. Open Chrome DevTools → Lighthouse → Analyze
3. Aim for 90+ on Performance, Accessibility, SEO

**SEO meta tags** (in BaseLayout.astro):
```html
<meta name="description" content="Your description" />
<meta property="og:title" content={title} />
<meta property="og:description" content={description} />
<meta property="og:image" content="/og-image.png" />
```

**Font optimization:** We import from Google Fonts — use `display=swap` to prevent invisible text while fonts load (it's in our Google Fonts URL already).

**Accessibility checklist:**
- All images have `alt` text
- Color contrast meets WCAG AA (4.5:1 for text)
- All interactive elements are keyboard-navigable
- Form inputs have labels

## Quick Quiz
1. What does `font-display: swap` (in Google Fonts URL) do?
   - a) Swaps fonts dynamically
   - b) Shows fallback system font immediately while custom font loads, preventing invisible text
   - c) Swaps between light and bold
   - d) Enables font animations

   **Answer:** b) Prevents FOIT (Flash of Invisible Text) — users see content immediately.

2. What Lighthouse score should you aim for on a static portfolio?
   - a) 50+ is fine
   - b) 70+ for Performance
   - c) 90+ for Performance, Accessibility, and SEO
   - d) 100 is impossible

   **Answer:** c) 90+ — Astro sites regularly hit 100/100 with proper setup.

3. What does `og:image` meta tag do?
   - a) Optimizes images on the page
   - b) Specifies the image shown when your page is shared on social media
   - c) Sets the favicon
   - d) Enables image lazy loading

   **Answer:** b) Social sharing image — this is what appears in Twitter/LinkedIn preview cards.

## Homework Assignment
### Phase 6 Homework: Complete Portfolio

**Objective:** Have your complete portfolio site running, polished, and ready for deployment.

**Requirements:**
- [ ] All sections built: Nav, Hero, About, Skills, Projects, Contact, Footer
- [ ] Projects filter works (click tags, list updates)
- [ ] Contact form validates and shows success state
- [ ] Responsive — works on mobile and desktop
- [ ] Lighthouse Performance score ≥ 85
- [ ] Lighthouse Accessibility score ≥ 90
- [ ] All images have alt text
- [ ] OG meta tags set in BaseLayout

**Stretch Goals:**
- [ ] Lighthouse score 95+ on all metrics
- [ ] Add a `/uses` page (tools and tech setup)
- [ ] Add a simple blog with 1 post using Astro Content Collections

**Submission:** Run `npm run build` successfully. Show Claude your Lighthouse scores and the running site.

## Next Up
Phase 7: **Git & GitHub** — versioning your code and pushing it online!
