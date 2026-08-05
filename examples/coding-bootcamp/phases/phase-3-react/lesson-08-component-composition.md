---
title: "Component Composition"
phase: 3
lesson: 8
duration_minutes: 30
prerequisites: ["3.7"]
skills_unlocked: []
objectives:
  - id: compose-reusable-components
    kind: practice
    text: "Compose complex interfaces from simple, reusable components"
  - id: lift-state-up
    kind: practice
    text: "Lift state up to share it between components"
    about: [1]
  - id: callbacks-as-props
    kind: practice
    text: "Pass callbacks as props for child-to-parent communication"
    about: [2]
  - id: when-to-split
    kind: knowledge
    text: "Understand when to split components and when to keep them together"
    about: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
**Composition** is building complex UIs by combining simple components. This is React's superpower.

**Lifting state up** — when two components need the same data, move state to their common parent:
```jsx
function App() {
  const [activeTag, setActiveTag] = useState("All"); // lifted up

  return (
    <div>
      <FilterBar activeTag={activeTag} onTagChange={setActiveTag} />
      <ProjectList activeTag={activeTag} />
    </div>
  );
}

function FilterBar({ activeTag, onTagChange }) {
  return (
    <div>
      {["All", "React", "Astro"].map(tag => (
        <button
          key={tag}
          onClick={() => onTagChange(tag)}
          className={activeTag === tag ? "active" : ""}
        >
          {tag}
        </button>
      ))}
    </div>
  );
}

function ProjectList({ activeTag }) {
  const filtered = projects.filter(
    p => activeTag === "All" || p.tags.includes(activeTag)
  );
  return <ul>{filtered.map(p => <ProjectCard key={p.id} {...p} />)}</ul>;
}
```

**When to split a component:**
- It's used in more than one place → split it
- It's getting too complex → split it
- It has its own state that doesn't affect siblings → keep it

## Key Terms
- **Composition**: Combining small components to build complex UIs
- **Lifting state up**: Moving state to a common ancestor component
- **Callback prop**: Passing a function as a prop so children can communicate up
- **Single responsibility**: Each component does one thing well
- **Prop drilling**: Passing props through many levels (a sign to refactor)

## Hands-On Exercise
Split this monolithic component into 3:
```jsx
// Before: one giant component
function Portfolio() { /* 200 lines... */ }

// After: composed
function Portfolio() {
  const [tag, setTag] = useState("All");
  return (
    <section>
      <TagFilter activeTag={tag} onChange={setTag} />
      <ProjectGrid activeTag={tag} />
    </section>
  );
}
// TagFilter and ProjectGrid are separate, focused components
```

## Quick Quiz
1. When should you "lift state up"?
   - a) Always — state should always be at the top
   - b) When two or more sibling components need access to the same state
   - c) When state is too complex
   - d) Only in class components

   **Answer:** b) When siblings need shared data — move state to their closest common parent.

2. How does a child component communicate back to its parent?
   - a) By modifying the parent's state directly
   - b) By calling a callback function passed as a prop
   - c) By using global variables
   - d) Children can't communicate up

   **Answer:** b) Callback props — the parent passes a function, the child calls it with data.

3. What is a sign that a component should be split into smaller ones?
   - a) It has more than 10 lines
   - b) It uses hooks
   - c) It's doing too many things, is hard to understand, or is reused in multiple places
   - d) It has more than 3 props

   **Answer:** c) Multiple responsibilities, complexity, or reuse — these are signals to split.

## Next Up
The Phase 3 capstone: a **React Mini-Project** putting everything together!
