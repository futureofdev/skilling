---
title: "Building for Production"
phase: 8
lesson: 2
duration_minutes: 25
prerequisites: ["8.1"]
skills_unlocked: []
objectives:
  - id: run-the-build
    kind: practice
    text: "Run the production build successfully"
    verify: "The production build completes without error"
  - id: what-dist-contains
    kind: knowledge
    text: "Understand what the dist folder contains"
    about: [2]
  - id: preview-the-build
    kind: practice
    text: "Preview the production build locally"
    verify: "The built site serves locally from the preview server"
    about: [1]
  - id: fix-build-errors
    kind: practice
    text: "Fix common build errors"
    about: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
`npm run build` runs Astro's build process:
1. Renders all `.astro` pages to HTML
2. Bundles and minifies JavaScript (React islands)
3. Processes CSS (Tailwind generates only used classes)
4. Optimizes images
5. Outputs everything to `dist/`

```bash
npm run build
# ✓ Completed in 1.23s

npm run preview
# Preview server running at http://localhost:4321
```

`dist/` contains your complete, optimized website — static files ready to serve.

**Common build errors:**
- TypeScript errors — fix type issues
- Missing imports — check file paths
- `Cannot use import outside a module` — add `type="module"` or fix exports
- Image not found — verify `public/` paths

**Build vs dev differences:**
- Dev: live reloading, not optimized, source maps
- Build: minified, tree-shaken, no source maps, no dev server

## Key Terms
- **Build**: The process of compiling source code into production-ready files
- **`dist/`**: Build output directory
- **Minification**: Removing whitespace/comments to reduce file size
- **Tree-shaking**: Removing unused code from bundles
- **`npm run preview`**: Serve the built `dist/` locally to test

## Hands-On Exercise
```bash
cd ~/projects/zero-to-portfolio

# Build the site
npm run build

# See what was built
ls dist/

# Preview the production build
npm run preview

# Check the bundle sizes
du -sh dist/
```

Your site should be lightning fast in preview mode!

## Quick Quiz
1. What does `npm run preview` do?
   - a) Shows a live preview of source files
   - b) Serves the built `dist/` folder locally — simulates production
   - c) Previews your GitHub repository
   - d) Opens the Cloudflare preview

   **Answer:** b) Serves the production build — lets you test the built site before deploying.

2. Why is the production CSS bundle much smaller than development?
   - a) Tailwind removes itself in production
   - b) Tailwind tree-shakes and only includes CSS classes actually used in your HTML
   - c) CSS is disabled in production
   - d) Images are compressed

   **Answer:** b) Tree-shaking — Tailwind v4 automatically eliminates unused utility classes.

3. If `npm run build` succeeds but `npm run dev` worked, what's likely wrong?
   - a) Nothing — builds always work if dev works
   - b) TypeScript errors that dev mode ignores, or environment-specific code issues
   - c) The computer is out of memory
   - d) npm needs to be updated

   **Answer:** b) TypeScript strictness — Astro's build is stricter than dev mode about types.

## Next Up
**Deploying to Cloudflare Pages** — going live!
