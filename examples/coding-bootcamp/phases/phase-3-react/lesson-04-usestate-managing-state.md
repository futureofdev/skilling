---
title: "useState: Managing State"
phase: 3
lesson: 4
duration_minutes: 40
prerequisites: ["3.3"]
skills_unlocked: []
objectives:
  - id: use-usestate
    kind: practice
    text: "Use useState to add state to components"
    about: [1]
  - id: update-state-correctly
    kind: practice
    text: "Update state correctly, never mutating it directly"
    about: [2, 3]
  - id: state-triggers-rerenders
    kind: knowledge
    text: "Understand that state changes trigger re-renders"
  - id: build-interactive-components
    kind: practice
    text: "Build interactive components"
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
State is data that changes over time. When state changes, React re-renders the component.

```jsx
import { useState } from "react";

function Counter() {
  // [currentValue, setterFunction] = useState(initialValue)
  const [count, setCount] = useState(0);

  return (
    <div>
      <p>Count: {count}</p>
      <button onClick={() => setCount(count + 1)}>+</button>
      <button onClick={() => setCount(count - 1)}>-</button>
      <button onClick={() => setCount(0)}>Reset</button>
    </div>
  );
}
```

**Rules:**
- Never mutate state directly: ❌ `count = count + 1` 
- Always use the setter: ✅ `setCount(count + 1)`
- For objects/arrays, spread to create a new one:
  ```jsx
  const [user, setUser] = useState({ name: "Alice", age: 25 });
  setUser({ ...user, age: 26 }); // create new object
  ```

**Functional updates** (when new state depends on old state):
```jsx
setCount(prev => prev + 1); // safer than setCount(count + 1)
```

## Key Terms
- **State**: Component data that when changed, causes re-render
- **`useState(initial)`**: Hook that returns `[value, setter]`
- **Setter function**: The `set*` function — the only correct way to update state
- **Re-render**: React calling your component function again with new state
- **Immutability**: Never mutate state directly — always create new values

## Hands-On Exercise
Build a filter component:
```jsx
function TagFilter({ tags }) {
  const [activeTag, setActiveTag] = useState("All");
  const allTags = ["All", ...tags];

  return (
    <div>
      <div className="filters">
        {allTags.map(tag => (
          <button
            key={tag}
            onClick={() => setActiveTag(tag)}
            className={activeTag === tag ? "active" : ""}
          >
            {tag}
          </button>
        ))}
      </div>
      <p>Showing: {activeTag}</p>
    </div>
  );
}
```

## Quick Quiz
1. What does `useState(0)` return?
   - a) The number 0
   - b) An array of `[currentValue, setterFunction]`
   - c) A React component
   - d) A Promise

   **Answer:** b) An array — destructured as `const [count, setCount] = useState(0)`.

2. Why must you use the setter function instead of directly mutating state?
   - a) The setter validates the value
   - b) Direct mutation doesn't trigger a re-render — React won't know to update the UI
   - c) Direct mutation is slower
   - d) The setter saves to a database

   **Answer:** b) React only re-renders when state changes through the setter — direct mutation is invisible to React.

3. What is the correct way to update an object in state?
   - a) `setState({ newProp: value })`
   - b) `state.newProp = value`
   - c) `setState(prev => ({ ...prev, newProp: value }))`
   - d) `Object.assign(state, { newProp: value })`

   **Answer:** c) Spread the previous state and add/override properties — always create a new object.

## Next Up
**Lists and Keys** — rendering arrays of data efficiently.
