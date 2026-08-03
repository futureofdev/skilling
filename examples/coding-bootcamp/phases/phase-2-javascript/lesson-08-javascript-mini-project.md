---
title: "JavaScript Mini-Project"
phase: 2
lesson: 8
duration_minutes: 60
prerequisites: ["2.7"]
skills_unlocked: [javascript-fundamentals]
objectives:
  - id: build-an-interactive-app
    text: "Build a complete interactive application using vanilla JavaScript"
  - id: combine-dom-events-and-fetch
    text: "Combine DOM manipulation, events, and async fetch"
    tested_by: [1, 3]
  - id: handle-loading-gracefully
    text: "Handle loading states and errors gracefully"
    tested_by: [2]
  - id: have-a-javascript-project
    text: "Have a real JavaScript project to show"
sections:
  key_terms:
    status: none
    intent: "Project lesson: it applies the vocabulary introduced earlier in the phase rather than adding any."
  exercise: present
  next_up: present
---

## The Concept
You're going to build a **GitHub Profile Viewer** — enter a GitHub username, fetch their profile from the GitHub API, display their info and repositories.

This combines everything:
- **Variables and types** — storing the username and data
- **Functions** — `fetchUser()`, `renderProfile()`
- **Arrays** — `.map()` over repositories
- **Events** — listening for form submission
- **Async fetch** — calling the GitHub API
- **DOM manipulation** — displaying the results

## Hands-On Exercise
Build the GitHub Profile Viewer:

**HTML:**
```html
<div class="app">
  <form id="search-form">
    <input type="text" id="username" placeholder="Enter GitHub username" required>
    <button type="submit">Search</button>
  </form>
  <div id="loading" style="display: none">Loading...</div>
  <div id="error" style="display: none"></div>
  <div id="profile" style="display: none"></div>
</div>
```

**JavaScript:**
```javascript
const form = document.getElementById("search-form");
const loading = document.getElementById("loading");
const errorDiv = document.getElementById("error");
const profileDiv = document.getElementById("profile");

function showLoading() {
  loading.style.display = "block";
  errorDiv.style.display = "none";
  profileDiv.style.display = "none";
}

function showError(message) {
  loading.style.display = "none";
  errorDiv.style.display = "block";
  errorDiv.textContent = message;
}

async function fetchUser(username) {
  showLoading();
  try {
    const res = await fetch(`https://api.github.com/users/${username}`);
    if (!res.ok) throw new Error("User not found");
    const user = await res.json();

    loading.style.display = "none";
    profileDiv.style.display = "block";
    profileDiv.innerHTML = `
      <img src="${user.avatar_url}" width="100" style="border-radius: 50%">
      <h2>${user.name || user.login}</h2>
      <p>${user.bio || "No bio"}</p>
      <p>⭐ ${user.public_repos} repos · 👥 ${user.followers} followers</p>
      <a href="${user.html_url}" target="_blank">View on GitHub</a>
    `;
  } catch (error) {
    showError(`Error: ${error.message}`);
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const username = document.getElementById("username").value.trim();
  if (username) fetchUser(username);
});
```

## Quick Quiz
1. Why do we call `e.preventDefault()` on form submission?
   - a) To validate the form
   - b) To stop the page from reloading when the form is submitted
   - c) To clear the input field
   - d) To make the fetch faster

   **Answer:** b) Stop the page reload — without this, the form submits normally and the page refreshes.

2. What's the purpose of the loading state?
   - a) It slows down the app
   - b) It gives users visual feedback that something is happening while data loads
   - c) It's required by the fetch API
   - d) It prevents multiple requests

   **Answer:** b) User feedback — showing a loading state prevents confusion while waiting for data.

3. How do you safely insert user data into `innerHTML`?
   - a) Always use innerHTML — it's fine
   - b) Never use innerHTML
   - c) Be careful — only insert trusted API data, not raw user text (XSS risk)
   - d) Use `innerText` instead always

   **Answer:** c) Be careful with innerHTML — data from APIs is usually safe, but never insert raw user text (that's XSS).

## Homework Assignment
### Phase 2 Homework: Interactive App

**Objective:** Build an interactive JavaScript app that fetches data from a public API and displays it dynamically.

**Requirements:**
- [ ] A form or button that triggers a data fetch
- [ ] Uses `async/await` and `fetch()` to call a public API
- [ ] Shows a loading state while fetching
- [ ] Handles errors (network failure, not found)
- [ ] Displays the fetched data by manipulating the DOM
- [ ] Uses `.map()` to render a list of items
- [ ] Looks styled (use your CSS skills!)

**API suggestions (free, no auth needed):**
- `https://pokeapi.co/api/v2/pokemon/{name}` — Pokémon data
- `https://dog.ceo/api/breeds/list/all` — Dog breeds
- `https://api.github.com/users/{username}` — GitHub profiles
- `https://jsonplaceholder.typicode.com/posts` — Fake blog posts

**Stretch Goals:**
- [ ] Local search/filter of fetched data
- [ ] Pagination or "load more" button
- [ ] Save favorites to localStorage

**Submission:** Show Claude your app working with at least 3 different searches/inputs.

## Next Up
Phase 3: **React** — the component-based UI library that makes building interactive UIs much more organized!
