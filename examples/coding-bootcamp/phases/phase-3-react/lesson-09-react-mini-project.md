---
title: "React Mini-Project"
phase: 3
lesson: 9
duration_minutes: 60
prerequisites: ["3.8"]
skills_unlocked: [react-fundamentals]
objectives:
  - id: build-a-multi-component-app
    kind: practice
    text: "Build a complete multi-component React app"
    verify: "A React app exists whose interface is assembled from more than one component"
    about: [1, 2]
  - id: apply-the-react-concepts
    kind: practice
    text: "Apply the React concepts from this phase together"
    about: [3]
  - id: have-a-react-project
    kind: practice
    text: "Have a real React project in your portfolio"
sections:
  key_terms:
    status: none
    intent: "Project lesson: it applies the vocabulary introduced earlier in the phase rather than adding any."
  exercise: present
  next_up: present
---

## The Concept
Build a **React Task Manager** with:
- Add tasks with a form
- Mark tasks complete (toggle)
- Filter by status (All / Active / Completed)
- Delete tasks
- Show count of remaining tasks

## Hands-On Exercise
```jsx
import { useState } from "react";

function App() {
  const [tasks, setTasks] = useState([]);
  const [input, setInput] = useState("");
  const [filter, setFilter] = useState("all");

  const addTask = (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    setTasks(prev => [...prev, { id: Date.now(), text: input, done: false }]);
    setInput("");
  };

  const toggle = (id) =>
    setTasks(prev => prev.map(t => t.id === id ? { ...t, done: !t.done } : t));

  const remove = (id) =>
    setTasks(prev => prev.filter(t => t.id !== id));

  const visible = tasks.filter(t =>
    filter === "all" ? true : filter === "active" ? !t.done : t.done
  );

  const remaining = tasks.filter(t => !t.done).length;

  return (
    <div className="app">
      <h1>Tasks <span className="count">{remaining} left</span></h1>
      <form onSubmit={addTask}>
        <input value={input} onChange={e => setInput(e.target.value)} placeholder="Add a task..." />
        <button type="submit">Add</button>
      </form>
      <div className="filters">
        {["all", "active", "completed"].map(f => (
          <button key={f} onClick={() => setFilter(f)} className={filter === f ? "active" : ""}>{f}</button>
        ))}
      </div>
      <ul>
        {visible.map(task => (
          <li key={task.id} className={task.done ? "done" : ""}>
            <input type="checkbox" checked={task.done} onChange={() => toggle(task.id)} />
            {task.text}
            <button onClick={() => remove(task.id)}>×</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

## Quick Quiz
1. How do we add a task to the tasks array without mutating it?
   - a) `tasks.push(newTask)`
   - b) `setTasks([...tasks, newTask])` or `setTasks(prev => [...prev, newTask])`
   - c) `tasks[tasks.length] = newTask`
   - d) `setTasks(tasks.concat)` 

   **Answer:** b) Spread into a new array — never mutate state directly.

2. How does the filter feature work without an API call?
   - a) It sends a request to a backend
   - b) It derives the visible list from state using `.filter()` each render
   - c) It hides elements with CSS
   - d) It stores separate lists in state

   **Answer:** b) Derived state — filter is stored, the visible list is computed from tasks + filter on each render.

3. What's the advantage of using `Date.now()` as a task ID?
   - a) It's always sequential
   - b) It's a timestamp — unique enough for our use case
   - c) React requires it
   - d) It's the same as UUID

   **Answer:** b) `Date.now()` gives milliseconds since epoch — unique enough for a local app, though not cryptographically unique.

## Homework Assignment
### Phase 3 Homework: React Application

**Objective:** Build a React application that demonstrates all Phase 3 skills.

**Requirements:**
- [ ] At least 3 separate components
- [ ] State managed with `useState`
- [ ] At least one list rendered with `.map()` and correct keys
- [ ] Filter or search functionality using derived state
- [ ] A controlled form with at least 2 fields
- [ ] Form validation with error messages
- [ ] At least one `useEffect` (e.g., fetch data from an API, or save to localStorage)
- [ ] Responsive layout using CSS

**Stretch Goals:**
- [ ] `localStorage` persistence (data survives page refresh)
- [ ] Animations using CSS transitions triggered by state changes
- [ ] `useMemo` optimization on the filtered list

**Submission:** Show Claude your app running with multiple components visible and state changing.

## Next Up
Phase 4: **Astro** — the framework that combines all of this into a blazing-fast website with Islands Architecture!
