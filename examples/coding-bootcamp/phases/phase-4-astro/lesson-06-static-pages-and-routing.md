---
title: "Static Pages and Routing"
phase: 4
lesson: 6
duration_minutes: 25
prerequisites: ["4.5"]
skills_unlocked: []
objectives:
  - id: file-based-routing
    kind: knowledge
    text: "Understand Astro's file-based routing"
    about: [1]
  - id: create-pages
    kind: practice
    text: "Create new pages"
  - id: dynamic-routes
    kind: practice
    text: "Create dynamic routes with [slug].astro"
    about: [2, 3]
  - id: astro-url-and-site
    kind: practice
    text: "Use Astro.url and Astro.site"
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Conceptual phase: Astro's ideas are practised on the portfolio build rather than in isolation."
  next_up: present
---

## The Concept
Astro uses **file-based routing** — the file structure in `src/pages/` maps to URLs.

```
src/pages/
├── index.astro        →  /
├── about.astro        →  /about
├── blog/
│   ├── index.astro    →  /blog
│   └── [slug].astro   →  /blog/any-slug
└── 404.astro          →  404 page
```

**Dynamic routes** with `[slug].astro`:
```astro
---
// src/pages/blog/[slug].astro
export function getStaticPaths() {
  const posts = [
    { slug: "hello-world", title: "Hello World" },
    { slug: "learning-astro", title: "Learning Astro" },
  ];
  return posts.map(post => ({
    params: { slug: post.slug },
    props: { post },
  }));
}

const { post } = Astro.props;
---
<h1>{post.title}</h1>
```

## Key Terms
- **File-based routing**: URL structure mirrors `src/pages/` file structure
- **Dynamic route**: `[param].astro` — one file handles multiple URLs
- **`getStaticPaths()`**: Function that tells Astro which paths to generate
- **`Astro.props`**: Props for the current page
- **`Astro.params`**: URL parameters for dynamic routes

## Quick Quiz
1. If you create `src/pages/contact.astro`, what URL does it create?
   - a) `/pages/contact`
   - b) `/contact`
   - c) `/astro/contact`
   - d) `/src/contact`

   **Answer:** b) `/contact` — Astro's file-based routing maps files to URLs directly.

2. What does `[slug].astro` do?
   - a) Creates a page named "slug"
   - b) Creates a dynamic route that handles any URL matching the pattern
   - c) Causes an error — brackets aren't valid in filenames
   - d) Creates a slug for SEO

   **Answer:** b) Dynamic route — `[slug]` matches any segment, available as `Astro.params.slug`.

3. What must `getStaticPaths()` return?
   - a) An array of URLs as strings
   - b) An array of objects with `params` (and optionally `props`)
   - c) A Promise
   - d) An object with all page data

   **Answer:** b) Array of `{ params, props }` objects — one for each page Astro should generate.

## Next Up
**Data Fetching in Astro** — loading data at build time.
