---
title: "HTML: Structure of the Web"
phase: 1
lesson: 2
duration_minutes: 40
prerequisites: ["1.1"]
skills_unlocked: []
objectives:
  - id: write-valid-html
    text: "Write valid HTML documents"
  - id: semantic-elements
    text: "Use semantic HTML elements correctly"
    tested_by: [1]
  - id: block-vs-inline
    text: "Understand the difference between block and inline elements"
    tested_by: [3]
  - id: links-images-and-lists
    text: "Create links, images, lists, and basic page structure"
    tested_by: [2]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
HTML (HyperText Markup Language) uses **tags** to give meaning and structure to content.

Tags look like: `<tagname>content</tagname>`

The browser reads these tags and knows how to display the content.

**The basic HTML document structure:**
```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <title>Page Title</title>
  </head>
  <body>
    <!-- Visible content goes here -->
    <h1>Hello, World!</h1>
    <p>This is a paragraph.</p>
  </body>
</html>
```

**Semantic HTML** means using the right tag for the right content:
- `<header>` — page header
- `<nav>` — navigation
- `<main>` — main content
- `<article>` — self-contained content
- `<section>` — thematic grouping
- `<footer>` — page footer
- `<h1>`-`<h6>` — headings (hierarchy matters!)
- `<p>` — paragraph
- `<a href="url">` — link
- `<img src="url" alt="description">` — image
- `<ul>`, `<ol>`, `<li>` — lists

## Key Terms
- **Tag**: HTML marker like `<p>` or `</p>`
- **Element**: Opening tag + content + closing tag
- **Attribute**: Extra information on a tag (like `href` in `<a href="...">`)
- **Semantic HTML**: Using the right tag for the meaning of content
- **Block element**: Takes full width, starts on new line (`<div>`, `<p>`, `<h1>`)
- **Inline element**: Flows within text (`<span>`, `<a>`, `<strong>`)

## Hands-On Exercise
Create your first HTML file:

1. Open VS Code
2. Create a file called `index.html`
3. Type `!` and press Tab — Emmet generates the HTML boilerplate!
4. Add this inside `<body>`:

```html
<header>
  <nav>
    <a href="#about">About</a>
    <a href="#projects">Projects</a>
  </nav>
  <h1>My Name</h1>
  <p>Aspiring Developer</p>
</header>

<main>
  <section id="about">
    <h2>About Me</h2>
    <p>I'm learning web development and loving it!</p>
  </section>

  <section id="projects">
    <h2>My Projects</h2>
    <ul>
      <li>Project 1</li>
      <li>Project 2</li>
    </ul>
  </section>
</main>

<footer>
  <p>Built by My Name</p>
</footer>
```

5. Open the file in your browser (right-click → Open with browser, or drag into browser)

## Quick Quiz
1. What is semantic HTML?
   - a) HTML that loads faster
   - b) Using the right tag for the meaning of content
   - c) HTML without CSS
   - d) Compressed HTML

   **Answer:** b) Using the right tag for the meaning of content — `<nav>` for navigation, `<article>` for articles, etc.

2. What does the `alt` attribute on an `<img>` tag do?
   - a) Sets the image size
   - b) Links to another image
   - c) Provides descriptive text for accessibility and when image fails to load
   - d) Sets the image color

   **Answer:** c) Provides descriptive text for accessibility — screen readers read alt text aloud.

3. What's the difference between `<div>` and `<span>`?
   - a) `<div>` is for text; `<span>` is for images
   - b) `<div>` is a block element (full width); `<span>` is inline (flows in text)
   - c) `<div>` is semantic; `<span>` is not
   - d) They're identical

   **Answer:** b) `<div>` is block; `<span>` is inline — div creates a new line, span doesn't.

## Next Up
Time to make our HTML look good with **CSS**!
