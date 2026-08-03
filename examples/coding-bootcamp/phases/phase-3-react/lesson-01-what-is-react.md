---
title: "What Is React and Why It Exists"
phase: 3
lesson: 1
duration_minutes: 25
prerequisites: ["2.8"]
skills_unlocked: []
objectives:
  - id: what-react-solves
    text: "Understand what React is and the problem it solves"
    tested_by: [1]
  - id: vanilla-vs-react
    text: "Know the difference between vanilla JavaScript DOM manipulation and React's approach"
    tested_by: [3]
  - id: the-component-model
    text: "Understand the component mental model"
    tested_by: [2]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
React is a JavaScript library for building user interfaces. Facebook created it in 2013 to solve a hard problem: **keeping the UI in sync with data**.

With vanilla JS, when your data changes, you manually update the DOM:
```javascript
// Vanilla JS — update 10 places when data changes 😫
document.getElementById("name").textContent = user.name;
document.getElementById("avatar").src = user.avatar;
// ...8 more places
```

With React, you describe what the UI should look like for given data. React handles updating the DOM:
```jsx
// React — describe it once, React keeps it in sync 😍
function Profile({ user }) {
  return (
    <div>
      <img src={user.avatar} />
      <h2>{user.name}</h2>
    </div>
  );
}
```

**Key ideas:**
- **Components**: Reusable pieces of UI (like functions that return HTML)
- **State**: Data that changes over time, causing re-renders
- **Props**: Data passed into components (like function arguments)
- **Declarative**: You describe the desired state; React makes it happen

## Key Terms
- **React**: JavaScript library for building component-based UIs
- **Component**: A reusable, self-contained piece of UI
- **JSX**: HTML-like syntax used in React
- **State**: Data that when changed, causes a component to re-render
- **Props**: Read-only data passed from parent to child component
- **Declarative**: Describing *what* you want, not *how* to do it

## Hands-On Exercise
Look at this mental model shift:

**Vanilla JS thinking:** "When the button is clicked, find the counter element, read its current value, add 1, update the element."

**React thinking:** "I have a `count` variable. Show a button. When clicked, increase `count`. The display always shows the current `count`."

React automatically re-renders when `count` changes — you don't manually update the DOM.

Write out in plain English: what 3 pieces of state would a Twitter-like app need?

## Quick Quiz
1. What problem does React solve?
   - a) Making websites load faster
   - b) Keeping the UI automatically synchronized with changing data
   - c) Writing CSS more easily
   - d) Connecting to databases

   **Answer:** b) Keeping UI in sync with data — manually syncing them in vanilla JS is error-prone and tedious.

2. What is a React component?
   - a) A JavaScript file
   - b) A reusable piece of UI that can receive data (props) and manage state
   - c) A CSS class
   - d) An HTML tag

   **Answer:** b) A reusable UI piece — think of it like a custom HTML element with logic built in.

3. What does "declarative" mean in the context of React?
   - a) You declare variables before using them
   - b) You describe what the UI should look like for given data; React handles the updates
   - c) You write more code than with vanilla JS
   - d) Components are declared at the top of files

   **Answer:** b) Describe the desired output, React figures out the DOM operations needed.

## Next Up
**JSX** — the HTML-in-JavaScript syntax that makes React components readable.
