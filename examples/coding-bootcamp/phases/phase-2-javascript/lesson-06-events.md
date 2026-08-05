---
title: "Events: Responding to User Actions"
phase: 2
lesson: 6
duration_minutes: 35
prerequisites: ["2.5"]
skills_unlocked: []
objectives:
  - id: add-event-listeners
    kind: practice
    text: "Add event listeners to DOM elements"
    about: [3]
  - id: handle-common-events
    kind: practice
    text: "Handle click, input, and submit events"
    about: [1]
  - id: the-event-object
    kind: practice
    text: "Use the event object to get details about the event"
    about: [2]
  - id: build-a-counter
    kind: practice
    text: "Build an interactive counter"
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
Events are things that happen in the browser: clicks, keypresses, form submissions, page loads, mouse movements.

```javascript
const button = document.querySelector("button");

// Add an event listener
button.addEventListener("click", (event) => {
  console.log("Button clicked!");
  console.log(event.target); // the element that was clicked
});

// Input event — fires as user types
const input = document.querySelector("input");
input.addEventListener("input", (e) => {
  console.log("Current value:", e.target.value);
});

// Form submission — always preventDefault!
const form = document.querySelector("form");
form.addEventListener("submit", (e) => {
  e.preventDefault(); // stop page reload
  const name = form.querySelector("#name").value;
  console.log("Submitted:", name);
});
```

**Common events:** `click`, `input`, `change`, `submit`, `keydown`, `mouseover`, `load`

## Key Terms
- **Event**: Something that happens (click, keypress, etc.)
- **Event listener**: A function that runs when an event occurs
- **`addEventListener(event, callback)`**: Attach an event listener
- **Event object (`e`)**: Contains details about the event
- **`e.target`**: The element that triggered the event
- **`e.preventDefault()`**: Stop the browser's default behavior

## Hands-On Exercise
Build a click counter:

```html
<button id="counter-btn">Clicked: 0 times</button>
<button id="reset-btn">Reset</button>
```

```javascript
let count = 0;
const btn = document.getElementById("counter-btn");
const reset = document.getElementById("reset-btn");

btn.addEventListener("click", () => {
  count++;
  btn.textContent = `Clicked: ${count} times`;
  if (count >= 10) {
    btn.style.background = "#FF6B35";
  }
});

reset.addEventListener("click", () => {
  count = 0;
  btn.textContent = "Clicked: 0 times";
  btn.style.background = "";
});
```

## Quick Quiz
1. What does `event.preventDefault()` do on a form submission?
   - a) Validates the form data
   - b) Stops the page from reloading (the browser's default form behavior)
   - c) Clears the form fields
   - d) Sends the form to the server

   **Answer:** b) Stops the browser's default behavior — which for forms is reloading the page.

2. What is `event.target`?
   - a) Where the event will be sent
   - b) The element that triggered the event
   - c) The type of event
   - d) The event listener function

   **Answer:** b) The element that triggered the event — useful when one handler covers multiple elements.

3. What event fires as a user types in an input field?
   - a) `click`
   - b) `keydown` only
   - c) `input`
   - d) `change` only

   **Answer:** c) `input` fires on every character change; `change` only fires when the input loses focus.

## Next Up
**Async JavaScript and Fetch** — getting data from the internet!
