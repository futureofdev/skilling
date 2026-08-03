---
title: "Building the Navigation"
phase: 6
lesson: 2
duration_minutes: 35
prerequisites: ["6.1"]
skills_unlocked: []
objectives:
  - id: a-fixed-nav-in-astro
    text: "Build a fixed navigation bar in Astro"
    tested_by: [2]
  - id: scroll-aware-styling
    text: "Implement scroll-aware styling with vanilla JavaScript"
    tested_by: [1, 3]
  - id: smooth-scroll-links
    text: "Create smooth-scroll anchor links"
sections:
  key_terms:
    status: none
    intent: "Build lesson: the vocabulary was established in the phases this section draws on."
  exercise:
    status: none
    intent: "Project phase: the exercise is the learner's own portfolio, built section by section as the lesson goes."
  next_up:
    status: none
    intent: "Build lessons run straight into the next section of the portfolio, so the teaser is generated rather than written."
---

## The Concept
The nav is Astro + vanilla JS. No React because it's mostly static — the scroll effect is simple enough for vanilla JS.

```astro
---
// Nav.astro — runs at build time
const links = [
  { label: "About", href: "#about" },
  { label: "Skills", href: "#skills" },
  { label: "Projects", href: "#projects" },
  { label: "Contact", href: "#contact" },
];
---

<header id="nav" class="fixed top-0 left-0 right-0 z-50">
  <nav class="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
    <a href="/" class="font-mono text-lg font-bold" style="color: var(--color-accent)">
      ~/your-name
    </a>
    <ul class="flex gap-8 list-none">
      {links.map(link => (
        <li>
          <a href={link.href} class="text-sm font-medium" style="color: var(--color-text-muted)">
            {link.label}
          </a>
        </li>
      ))}
    </ul>
  </nav>
</header>

<script>
  // Vanilla JS — no React needed for this!
  const nav = document.getElementById("nav");
  window.addEventListener("scroll", () => {
    if (window.scrollY > 50) {
      nav.style.background = "rgba(13,15,20,0.95)";
      nav.style.backdropFilter = "blur(12px)";
    } else {
      nav.style.background = "transparent";
      nav.style.backdropFilter = "none";
    }
  }, { passive: true });
</script>
```

**Teaching moment:** Not everything needs React. Vanilla JS is perfectly valid for simple effects.

## Quick Quiz
1. Why use `{ passive: true }` on the scroll event listener?
   - a) It makes the listener passive/inactive
   - b) It tells the browser the handler won't call `preventDefault()`, allowing scroll optimization
   - c) It's required for all event listeners
   - d) It reduces memory usage

   **Answer:** b) Performance optimization — passive scroll listeners don't block scrolling.

2. What CSS does `fixed top-0 left-0 right-0 z-50` achieve?
   - a) Makes the element fixed at the bottom
   - b) Fixed position at top, spanning full width, above other content (z-index 50)
   - c) Sticky positioning
   - d) Absolute positioning at top-left

   **Answer:** b) Fixed to top, full width — the sticky navbar pattern.

3. Why does the nav use an inline `<script>` instead of a `.tsx` React component?
   - a) React can't handle scroll events
   - b) The scroll effect doesn't need state or React features — vanilla JS is simpler and adds zero overhead
   - c) Inline scripts are faster
   - d) Astro requires inline scripts for events

   **Answer:** b) Right tool for the job — vanilla JS for simple effects, React only where state is needed.
