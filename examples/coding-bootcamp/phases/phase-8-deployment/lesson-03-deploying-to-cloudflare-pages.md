---
title: "Deploying to Cloudflare Pages"
phase: 8
lesson: 3
duration_minutes: 35
prerequisites: ["8.2"]
skills_unlocked: []
objectives:
  - id: connect-github-to-cloudflare
    text: "Connect GitHub to Cloudflare Pages"
  - id: configure-build-settings
    text: "Configure build settings for Astro"
    tested_by: [1]
  - id: deploy-successfully
    text: "Deploy successfully"
    tested_by: [3]
  - id: automatic-deployments
    text: "Understand automatic deployments"
    tested_by: [2]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
Deploying to Cloudflare Pages takes about 5 minutes.

**Step-by-step:**

1. **Create Cloudflare account** at cloudflare.com (free)

2. **Go to Workers & Pages → Create application → Pages → Connect to Git**

3. **Connect GitHub** — authorize Cloudflare to access your repos

4. **Select your repository** — `zero-to-portfolio`

5. **Configure build settings:**
   - Framework preset: Astro
   - Build command: `npm run build`
   - Build output directory: `dist`
   - Node.js version: 20 (set in Environment variables: `NODE_VERSION = 20`)

6. **Click "Save and Deploy"**

Cloudflare will:
- Clone your repo
- Install dependencies
- Run `npm run build`
- Deploy `dist/` to their global CDN

Your site gets a URL like `zero-to-portfolio-abc.pages.dev`!

**Automatic deploys:** Every push to `main` triggers a new deployment.

## Key Terms
- **Cloudflare Pages**: Static site hosting platform
- **Build command**: `npm run build`
- **Build output directory**: `dist`
- **Deploy preview**: Automatic preview URL for each PR/branch
- **Production deployment**: The live site on your main URL

## Hands-On Exercise
Deploy right now! Follow the steps above.

Then verify:
1. Open your `*.pages.dev` URL
2. Check all sections load
3. Test Projects filter buttons
4. Test Contact form validation
5. Check on mobile (resize browser or use DevTools)

## Quick Quiz
1. What build output directory should you set in Cloudflare for Astro?
   - a) `build/`
   - b) `public/`
   - c) `dist/`
   - d) `out/`

   **Answer:** c) `dist/` — Astro's default build output directory.

2. After connecting GitHub to Cloudflare Pages, when does it auto-deploy?
   - a) Only when you manually trigger it
   - b) Every push to the connected branch (usually main)
   - c) Every 24 hours
   - d) Only on tagged releases

   **Answer:** b) Every push — continuous deployment means every merge to main goes live automatically.

3. What is a deploy preview?
   - a) A screenshot of the deployed site
   - b) A temporary URL Cloudflare creates for each PR — lets you preview changes before merging
   - c) The staging environment
   - d) A Cloudflare dashboard preview

   **Answer:** b) PR preview URL — you can share `pr-123.zero-to-portfolio.pages.dev` to show reviewers.

## Next Up
**Custom Domain Setup** — `yourname.com` instead of `yourname.pages.dev`.
