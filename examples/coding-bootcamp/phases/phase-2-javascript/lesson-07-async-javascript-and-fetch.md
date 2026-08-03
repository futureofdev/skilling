---
title: "Async JavaScript and Fetch"
phase: 2
lesson: 7
duration_minutes: 40
prerequisites: ["2.6"]
skills_unlocked: []
objectives:
  - id: why-async-exists
    text: "Understand why asynchronous code exists"
    tested_by: [1]
  - id: async-await
    text: "Use async/await to handle Promises"
    tested_by: [2]
  - id: fetch-from-an-api
    text: "Fetch data from a public API"
    tested_by: [3]
  - id: loading-and-errors
    text: "Handle loading states and errors"
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
JavaScript is **single-threaded** — it can only do one thing at a time. But some operations (fetching data, reading files) take time. If JS waited for them, your UI would freeze.

**Async** code says "do this, and come back when it's done — don't block anything else."

```javascript
// Fetching data from an API
async function getUser() {
  try {
    const response = await fetch("https://api.github.com/users/octocat");
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const user = await response.json();
    console.log(user.name);      // "The Octocat"
    console.log(user.followers); // number
    return user;
  } catch (error) {
    console.error("Failed to fetch user:", error);
  }
}

getUser();
```

**The pattern:**
1. `async function` — marks a function as asynchronous
2. `await` — pauses execution until the Promise resolves
3. `try/catch` — handles errors (network failure, bad response)
4. `response.json()` — parses the response body as JSON

## Key Terms
- **Asynchronous**: Code that doesn't block — runs in the background
- **Promise**: An object representing a future value
- **`async/await`**: Syntax for working with Promises more readably
- **`fetch()`**: Web API for making HTTP requests
- **JSON**: JavaScript Object Notation — common API data format
- **`try/catch`**: Error handling for async code

## Hands-On Exercise
```javascript
// Fetch a random dog image from a public API
async function getRandomDog() {
  const response = await fetch("https://dog.ceo/api/breeds/image/random");
  const data = await response.json();
  
  const img = document.createElement("img");
  img.src = data.message;
  img.style.width = "300px";
  img.style.borderRadius = "8px";
  document.body.appendChild(img);
  
  console.log("Dog image URL:", data.message);
}

getRandomDog();
// Call it multiple times for multiple dogs!
```

## Quick Quiz
1. Why do we need asynchronous JavaScript?
   - a) JavaScript can't run synchronously
   - b) To prevent the UI from freezing while waiting for slow operations (like network requests)
   - c) Asynchronous code is faster
   - d) Browsers require it

   **Answer:** b) To prevent freezing — async lets other code run while waiting for data.

2. What does `await` do?
   - a) Waits a fixed number of milliseconds
   - b) Pauses the async function until the Promise resolves, then returns the result
   - c) Makes the function run faster
   - d) Converts a callback to a Promise

   **Answer:** b) Pauses and waits for the Promise — but only inside an `async` function.

3. What does `response.json()` return?
   - a) A string of JSON text
   - b) A Promise that resolves to the parsed JavaScript object
   - c) The raw HTTP response
   - d) A JSON file

   **Answer:** b) A Promise — that's why we `await` it too!

## Next Up
The Phase 2 capstone: a **JavaScript Mini-Project** putting everything together!
