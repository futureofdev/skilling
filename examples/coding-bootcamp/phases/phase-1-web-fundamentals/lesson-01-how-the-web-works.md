---
title: "How the Web Works"
phase: 1
lesson: 1
duration_minutes: 20
prerequisites: ["0.6"]
skills_unlocked: []
objectives:
  - id: client-server-model
    kind: knowledge
    text: "Understand the client-server model"
    about: [3]
  - id: what-happens-on-a-url
    kind: knowledge
    text: "Know what happens when you type a URL in a browser"
    about: [1]
  - id: http-requests-and-responses
    kind: knowledge
    text: "Understand HTTP requests and responses at a basic level"
  - id: html-css-js-roles
    kind: knowledge
    text: "Know what HTML, CSS, and JavaScript each do"
    about: [2]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
When you type `google.com` in your browser:

1. **DNS lookup**: Your computer asks "what's the IP address for google.com?" — like looking up a phone number in a directory
2. **TCP connection**: Your computer connects to Google's server
3. **HTTP request**: Your browser asks the server "please send me the homepage"
4. **HTTP response**: The server sends back an HTML file
5. **Rendering**: Your browser reads the HTML and draws the page

**The three languages of the web:**
- **HTML**: Structure — the skeleton (headings, paragraphs, images, links)
- **CSS**: Style — the appearance (colors, fonts, layout)
- **JavaScript**: Behavior — the interactivity (clicks, animations, data fetching)

Every website you've ever visited is built with these three things.

## Key Terms
- **Client**: The browser requesting content (your computer)
- **Server**: The computer serving content (Google, GitHub, etc.)
- **HTTP**: Protocol for web communication (HyperText Transfer Protocol)
- **URL**: Web address (Uniform Resource Locator)
- **DNS**: Domain Name System — converts domain names to IP addresses
- **HTML**: HyperText Markup Language — web page structure
- **CSS**: Cascading Style Sheets — web page appearance
- **JavaScript**: Programming language for web interactivity

## Hands-On Exercise
Open your browser's Developer Tools (`F12` on Windows/Linux, or `Cmd+Option+I` on Mac):

1. Go to any website (try github.com)
2. Click the "Network" tab
3. Refresh the page
4. Watch the requests load — each row is an HTTP request!
5. Click on the first request (the HTML document)
6. Look at "Headers" — you can see the HTTP request and response

You just watched the web work in real time!

## Quick Quiz
1. What does DNS do?
   - a) Makes websites load faster
   - b) Converts domain names (like google.com) to IP addresses
   - c) Encrypts your connection
   - d) Stores web pages

   **Answer:** b) Converts domain names to IP addresses — like a phone book for the internet.

2. What is the role of CSS in a webpage?
   - a) Structure — organizing content into headings and paragraphs
   - b) Behavior — handling clicks and animations
   - c) Style — controlling appearance (colors, fonts, layout)
   - d) Communication — sending data to servers

   **Answer:** c) Style — CSS controls how things look.

3. In the client-server model, what is the "client"?
   - a) The website's database
   - b) The server's operating system
   - c) The browser on your computer requesting content
   - d) The internet service provider

   **Answer:** c) The browser on your computer requesting content — the client asks and the server answers, which is the direction that makes the whole model work.

## Next Up
Now let's write HTML — the language that structures every webpage.
