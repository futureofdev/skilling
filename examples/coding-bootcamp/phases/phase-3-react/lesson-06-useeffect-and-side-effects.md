---
title: "useEffect and Side Effects"
phase: 3
lesson: 6
duration_minutes: 35
prerequisites: ["3.5"]
skills_unlocked: []
objectives:
  - id: use-useeffect
    kind: practice
    text: "Use useEffect for side effects"
    about: [1]
  - id: fetch-on-mount
    kind: practice
    text: "Fetch data when a component mounts"
  - id: clean-up-effects
    kind: practice
    text: "Clean up effects with the return function"
    about: [2]
  - id: the-dependency-array
    kind: knowledge
    text: "Understand the dependency array"
    about: [1, 3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
`useEffect` lets you run code after React renders. It's for "side effects" — things that reach outside the component (API calls, timers, subscriptions).

```jsx
import { useState, useEffect } from "react";

function UserProfile({ userId }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // This runs after render
    async function fetchUser() {
      setLoading(true);
      const res = await fetch(`/api/users/${userId}`);
      const data = await res.json();
      setUser(data);
      setLoading(false);
    }
    fetchUser();
  }, [userId]); // Dependency array: re-run when userId changes

  if (loading) return <p>Loading...</p>;
  return <h2>{user?.name}</h2>;
}
```

**Dependency array:**
- `[]` — runs once on mount only
- `[value]` — runs on mount AND when `value` changes
- No array — runs after EVERY render (usually wrong)

**Cleanup function** (prevent memory leaks):
```jsx
useEffect(() => {
  const timer = setInterval(() => console.log("tick"), 1000);
  return () => clearInterval(timer); // cleanup on unmount
}, []);
```

## Key Terms
- **Side effect**: Anything that reaches outside the component (fetch, timers, DOM)
- **`useEffect(fn, deps)`**: Run `fn` after render, based on `deps`
- **Dependency array**: Values that, when changed, re-trigger the effect
- **Mount**: When a component first appears in the DOM
- **Unmount**: When a component is removed from the DOM
- **Cleanup function**: Returned from useEffect to clean up before re-running

## Hands-On Exercise
Fetch and display data:
```jsx
function RandomFact() {
  const [fact, setFact] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadFact() {
    setLoading(true);
    const res = await fetch("https://catfact.ninja/fact");
    const data = await res.json();
    setFact(data.fact);
    setLoading(false);
  }

  useEffect(() => { loadFact(); }, []); // fetch on mount

  return (
    <div>
      {loading ? <p>Loading...</p> : <p>{fact}</p>}
      <button onClick={loadFact}>New Fact</button>
    </div>
  );
}
```

## Quick Quiz
1. When does `useEffect(() => { ... }, [])` run?
   - a) Before every render
   - b) After every render
   - c) Once, after the first render (mount)
   - d) Never

   **Answer:** c) Once on mount — the empty array means "no dependencies to watch".

2. What is a cleanup function in useEffect?
   - a) A function that resets state
   - b) A function returned from useEffect that runs before the next effect or on unmount
   - c) A function that clears the console
   - d) A function that removes event listeners globally

   **Answer:** b) The returned function runs before the effect re-runs or when the component unmounts.

3. What's wrong with `useEffect(() => fetchData(), )`? (no dependency array)
   - a) Nothing — this is correct
   - b) It runs after every render, potentially causing infinite loops
   - c) It never runs
   - d) Syntax error

   **Answer:** b) Runs after every render — if fetching sets state, which triggers a render, which triggers a fetch... infinite loop!

## Next Up
**Forms in React** — controlled components for handling user input.
