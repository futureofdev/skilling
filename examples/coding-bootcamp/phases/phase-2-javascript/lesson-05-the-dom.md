---
title: "The DOM: Connecting JS to HTML"
phase: 2
lesson: 5
duration_minutes: 35
prerequisites: ["2.4"]
skills_unlocked: []
objectives:
  - id: select-elements
    text: "Select HTML elements using JavaScript"
    tested_by: [1]
  - id: change-content-and-styles
    text: "Read and change element content and styles"
    tested_by: [3]
  - id: create-and-append
    text: "Create and append new elements"
  - id: the-dom-tree
    text: "Understand the DOM tree"
    tested_by: [2]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
The **DOM** (Document Object Model) is how JavaScript sees and interacts with your HTML. When a browser loads HTML, it creates a tree of objects representing each element. JavaScript can read and modify this tree.

```javascript
// Select elements
const heading = document.querySelector("h1");
const buttons = document.querySelectorAll("button");
const byId = document.getElementById("my-id");

// Read content
console.log(heading.textContent);    // text inside
console.log(heading.innerHTML);      // HTML inside

// Change content
heading.textContent = "New Heading!";

// Change styles
heading.style.color = "#00D4AA";

// Toggle a CSS class
heading.classList.add("active");
heading.classList.remove("active");
heading.classList.toggle("active");

// Create and add elements
const newPara = document.createElement("p");
newPara.textContent = "I was added by JavaScript!";
document.body.appendChild(newPara);
```

## Key Terms
- **DOM**: Document Object Model — tree representation of HTML
- **`querySelector`**: Select first element matching CSS selector
- **`querySelectorAll`**: Select all elements matching CSS selector (returns NodeList)
- **`textContent`**: The text content of an element
- **`innerHTML`**: The HTML content inside an element
- **`classList`**: Methods to add/remove/toggle CSS classes
- **`createElement`**: Create a new HTML element in JavaScript

## Hands-On Exercise
In your browser console on any page:

```javascript
// Find the first heading
const h1 = document.querySelector("h1");
console.log(h1.textContent);

// Change it (go ahead, it's just temporary!)
h1.textContent = "JavaScript was here!";
h1.style.color = "hotpink";

// Add a banner
const banner = document.createElement("div");
banner.textContent = "🚀 Hello from JavaScript!";
banner.style.cssText = "background: #00D4AA; color: #0D0F14; padding: 16px; text-align: center; font-weight: bold;";
document.body.prepend(banner);
```

Refresh the page — it's all gone. The DOM changes were temporary!

## Quick Quiz
1. What does `document.querySelector(".card")` return?
   - a) All elements with class "card"
   - b) The first element with class "card"
   - c) An error if no cards exist
   - d) The text inside the first card

   **Answer:** b) The first matching element — use `querySelectorAll` for all matches.

2. What is the DOM?
   - a) A database of web content
   - b) A tree structure representing the HTML document that JavaScript can modify
   - c) A JavaScript framework
   - d) A CSS layout system

   **Answer:** b) A tree of objects JavaScript uses to read and modify the HTML page.

3. What does `element.classList.toggle("active")` do?
   - a) Always adds the "active" class
   - b) Removes all classes
   - c) Adds "active" if not present; removes it if it is
   - d) Checks if the class exists

   **Answer:** c) Toggles — adds if absent, removes if present.

## Next Up
**Events** — responding to user actions like clicks, typing, and form submissions.
