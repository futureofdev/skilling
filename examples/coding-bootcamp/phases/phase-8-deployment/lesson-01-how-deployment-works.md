---
title: "How Deployment Works"
phase: 8
lesson: 1
duration_minutes: 20
prerequisites: ["7.5"]
skills_unlocked: []
objectives:
  - id: what-deployment-means
    kind: knowledge
    text: "Understand what deployment means"
    about: [1]
  - id: static-vs-server-hosting
    kind: knowledge
    text: "Know the difference between static hosting and server hosting"
  - id: why-cloudflare-suits-astro
    kind: knowledge
    text: "Understand why Cloudflare Pages suits an Astro site"
    about: [2, 3]
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Orientation lesson — there is nothing deployed to work on yet, and the practical work starts with the production build next."
  next_up: present
---

## The Concept
**Deployment** = making your site accessible on the internet.

When you run `npm run dev`, Astro serves your site on `localhost:4321` — only you can see it. Deployment puts it on a server anyone can access.

**Types of hosting:**
- **Static hosting** (Cloudflare Pages, Netlify, Vercel): Serves pre-built HTML/CSS/JS files. Perfect for Astro.
- **Server hosting** (VPS, EC2): Runs server-side code. Needed for Node.js APIs, databases.

**Why Cloudflare Pages for Astro:**
- Free tier is generous
- Global CDN — serves from 300+ locations worldwide
- Automatic deployments on git push
- Built-in SSL (HTTPS)
- Zero config for Astro

**The deployment flow:**
1. Push code to GitHub
2. Cloudflare detects the push
3. Cloudflare runs `npm run build`
4. Cloudflare serves the `dist/` folder globally

## Key Terms
- **Deployment**: Making your site accessible on the internet
- **Static hosting**: Serving pre-built files (no server-side rendering)
- **CDN (Content Delivery Network)**: Servers worldwide that serve your files from the closest location
- **SSL/HTTPS**: Encrypted connection (required for all modern sites)
- **`dist/`**: The build output folder containing your built site

## Quick Quiz
1. What's the difference between `localhost:4321` and a deployed site?
   - a) localhost is faster
   - b) localhost is only accessible on your computer; deployed sites are accessible worldwide
   - c) localhost uses HTTP; deployed sites use HTTPS
   - d) There's no difference

   **Answer:** b) localhost = only your machine; deployed = the whole internet.

2. Why is Cloudflare Pages good for Astro?
   - a) It's the only option for Astro
   - b) It specializes in static site hosting — perfectly matched to Astro's build output
   - c) It costs less than alternatives
   - d) Cloudflare owns Astro

   **Answer:** b) Static hosting match — Astro builds to static files; Cloudflare Pages hosts static files.

3. What happens when you push to GitHub if connected to Cloudflare Pages?
   - a) Nothing — you must manually trigger deployment
   - b) Cloudflare automatically detects the push, builds, and deploys your site
   - c) GitHub deploys it
   - d) You get an email notification

   **Answer:** b) Automatic deployment — this is the CD part of CI/CD.

## Next Up
**Building for Production** — the `npm run build` process.
