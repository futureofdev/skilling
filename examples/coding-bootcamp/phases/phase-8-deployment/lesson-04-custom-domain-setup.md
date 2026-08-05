---
title: "Custom Domain Setup"
phase: 8
lesson: 4
duration_minutes: 25
prerequisites: ["8.3"]
skills_unlocked: []
objectives:
  - id: buy-a-domain
    kind: practice
    text: "Purchase a domain name, if you want one"
  - id: connect-a-custom-domain
    kind: practice
    text: "Connect a custom domain to Cloudflare Pages"
    verify: "The custom domain resolves to the deployed site"
    about: [3]
  - id: dns-basics
    kind: knowledge
    text: "Understand DNS basics"
    about: [1]
  - id: https-automatically
    kind: practice
    text: "Enable HTTPS automatically"
    verify: "The site is served over HTTPS with a certificate the browser accepts"
    about: [2]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
Your site is live at `yoursite.pages.dev`. A custom domain (`yourname.dev`, `yourname.com`) looks more professional.

**Getting a domain:**
- `namecheap.com`, `porkbun.com`, or `cloudflare.com/registrar` (competitive pricing)
- `.dev` domains (~$10-15/year) — perfect for developers, HTTPS required
- `.com` domains (~$10-15/year) — most recognizable

**Connecting to Cloudflare Pages:**
1. Cloudflare Pages → your project → Custom Domains → Add Domain
2. Enter your domain (e.g., `yourname.dev`)
3. If domain is on Cloudflare's registrar: done automatically
4. If elsewhere: add the CNAME record they provide to your domain registrar

**DNS** (Domain Name System):
- `CNAME record`: Points your domain to another domain
- Cloudflare provides: `yourname.dev → yoursite.pages.dev`
- HTTPS is automatic — Cloudflare provisions a free SSL certificate

## Key Terms
- **Domain registrar**: Where you buy domain names
- **DNS (Domain Name System)**: Translates domain names to IP addresses
- **CNAME record**: DNS record pointing domain to another domain
- **SSL certificate**: Enables HTTPS encryption (free with Cloudflare)
- **Propagation**: Time for DNS changes to spread globally (up to 48h)

## Hands-On Exercise
If you have or purchase a domain:
1. In Cloudflare Pages: Settings → Custom Domains → Add
2. Enter your domain
3. Follow the DNS instructions
4. Wait for propagation (often minutes, sometimes hours)
5. Your site is live at `https://yourname.dev`!

If you don't have a domain yet: the `.pages.dev` URL works great for now!

## Quick Quiz
1. What is a CNAME DNS record?
   - a) A record that maps a domain to an IP address
   - b) A record that points a domain to another domain name
   - c) A record that holds email settings
   - d) A record for security certificates

   **Answer:** b) Domain-to-domain pointer — your domain points to your Cloudflare Pages domain.

2. Is HTTPS (SSL) free with Cloudflare Pages?
   - a) No — you need to buy a certificate
   - b) Yes — Cloudflare automatically provisions and renews SSL certificates
   - c) Only for paid plans
   - d) HTTPS isn't supported on Pages

   **Answer:** b) Free and automatic — one of Cloudflare Pages' best features.

3. Why might a custom domain take up to 48 hours to work?
   - a) Cloudflare is slow
   - b) DNS propagation — DNS changes must spread to servers worldwide, which takes time
   - c) SSL certificate generation takes 48 hours
   - d) It always takes exactly 48 hours

   **Answer:** b) DNS propagation — changes spread gradually to DNS servers globally.

## Next Up
**Going Live: Launch Checklist** — the final checks before sharing your portfolio with the world!
