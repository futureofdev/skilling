---
title: "Data Fetching in Astro"
phase: 4
lesson: 7
duration_minutes: 30
prerequisites: ["4.6"]
skills_unlocked: [astro-fundamentals]
objectives:
  - id: fetch-in-frontmatter
    text: "Fetch data in Astro frontmatter"
    tested_by: [1]
  - id: content-collections
    text: "Use Astro Content Collections for Markdown"
    tested_by: [2]
  - id: build-time-vs-runtime
    text: "Understand build-time versus runtime data fetching"
    tested_by: [3]
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Conceptual phase: Astro's ideas are practised on the portfolio build rather than in isolation."
  next_up: present
---

## The Concept
Astro fetches data at **build time** — in the frontmatter. This means your page is pre-rendered with the data baked in.

```astro
---
// This runs at BUILD TIME — not in the browser
const res = await fetch("https://api.github.com/users/octocat");
const user = await res.json();

// Markdown Content Collections
import { getCollection } from 'astro:content';
const posts = await getCollection('blog');
---

<main>
  <h1>{user.name}</h1>
  <ul>
    {posts.map(post => <li>{post.data.title}</li>)}
  </ul>
</main>
```

**Content Collections** — Astro's built-in CMS for Markdown:
```
src/content/
└── blog/
    ├── hello-world.md
    └── second-post.md
```

Each Markdown file has YAML frontmatter for metadata. Astro validates and types it automatically.

## Key Terms
- **Build-time fetching**: Data fetched once when building — baked into HTML
- **Content Collections**: Astro's system for type-safe Markdown/MDX content
- **`getCollection(name)`**: Get all content in a collection
- **Frontmatter (content)**: YAML metadata at top of Markdown files

## Quick Quiz
1. When does Astro's frontmatter fetch run?
   - a) Every time a user visits the page
   - b) Once at build time — the result is baked into the HTML
   - c) Every 5 minutes
   - d) On the client in the browser

   **Answer:** b) Build time — faster and more secure than fetching at request time.

2. What are Astro Content Collections used for?
   - a) Storing user data
   - b) Managing and querying Markdown/MDX content files in a type-safe way
   - c) CSS class collections
   - d) API endpoint collections

   **Answer:** b) Type-safe Markdown management — perfect for blog posts, case studies, etc.

3. What's the advantage of build-time data fetching over client-side fetching?
   - a) Build-time is always faster
   - b) Data is baked into HTML — no loading states, works without JavaScript, better SEO
   - c) Build-time is more secure because it uses HTTPS
   - d) There's no advantage

   **Answer:** b) HTML with data baked in — immediate content, better SEO, no client-side JavaScript needed.

## Homework Assignment
### Phase 4 Homework: Astro Page

**Objective:** Add a new page to the portfolio site using Astro.

**Requirements:**
- [ ] Create `src/pages/uses.astro` — a "Uses" page listing your tools/setup
- [ ] Use `BaseLayout.astro` for consistent header/footer
- [ ] Fetch data in the frontmatter (either from an API or a local data file)
- [ ] Render a list of items with Astro template syntax
- [ ] Add the page to the navigation in `Nav.astro`
- [ ] Style the page consistently with the rest of the site

**Stretch Goals:**
- [ ] Create a `src/content/blog/` collection with 2 Markdown posts
- [ ] Create `src/pages/blog/index.astro` listing all posts
- [ ] Create `src/pages/blog/[slug].astro` for individual posts

**Submission:** Show Claude the new page working at `http://localhost:4321/uses`.

## Next Up
Phase 5: **Tailwind CSS** — the utility-first CSS framework powering your portfolio's design!
