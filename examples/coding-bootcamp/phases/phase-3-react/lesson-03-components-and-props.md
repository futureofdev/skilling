---
title: "Components and Props"
phase: 3
lesson: 3
duration_minutes: 35
prerequisites: ["3.2"]
skills_unlocked: []
objectives:
  - id: create-components
    text: "Create functional React components"
  - id: pass-props
    text: "Pass data to components via props"
    tested_by: [1, 2]
  - id: destructure-props
    text: "Destructure props for cleaner code"
  - id: compose-components
    text: "Compose components together"
    tested_by: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
Components are functions that return JSX. Props are the arguments you pass to them.

```jsx
// Define a component
function Button({ label, onClick, variant = "primary" }) {
  return (
    <button
      onClick={onClick}
      className={`btn btn-${variant}`}
    >
      {label}
    </button>
  );
}

// Use it (pass props like HTML attributes)
<Button label="Save" onClick={handleSave} />
<Button label="Cancel" onClick={handleCancel} variant="secondary" />
```

**Props rules:**
- Props flow DOWN (parent → child), never up
- Props are read-only — don't mutate them
- Default values: `function Button({ variant = "primary" })`

**Composition** — build complex UIs from simple components:
```jsx
function Card({ title, description, children }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <p>{description}</p>
      {children}  {/* anything between <Card> tags */}
    </div>
  );
}

// Using children
<Card title="My Project" description="A cool app">
  <a href="/demo">View Demo</a>
</Card>
```

## Key Terms
- **Component**: A function that accepts props and returns JSX
- **Props**: Data passed to a component (read-only)
- **`children`**: Special prop representing content between opening/closing tags
- **Default prop**: A fallback value when prop isn't provided
- **Composition**: Building complex UIs by combining simple components

## Hands-On Exercise
Build a `ProjectCard` component:
```jsx
function ProjectCard({ title, description, tags, liveUrl, githubUrl }) {
  return (
    <article className="project-card">
      <h3>{title}</h3>
      <p>{description}</p>
      <div className="tags">
        {tags.map(tag => <span key={tag} className="tag">{tag}</span>)}
      </div>
      <div className="links">
        {githubUrl && <a href={githubUrl}>GitHub</a>}
        {liveUrl && <a href={liveUrl}>Live Site</a>}
      </div>
    </article>
  );
}
```

## Quick Quiz
1. How do you pass a prop to a component?
   - a) `Component.propName = value`
   - b) Like an HTML attribute: `<Component propName={value} />`
   - c) Using `setState()`
   - d) Through global variables

   **Answer:** b) Like HTML attributes — `<Button label="Click me" onClick={fn} />`.

2. Can a child component modify its props?
   - a) Yes, always
   - b) No — props are read-only
   - c) Yes, but only with `setState()`
   - d) Only if the parent allows it

   **Answer:** b) Props are read-only — to change UI, the parent must update its state and pass new props.

3. What is the `children` prop?
   - a) A list of child component types
   - b) Content placed between a component's opening and closing tags
   - c) Props inherited from parent components
   - d) The number of child elements

   **Answer:** b) The JSX between tags — `<Card><p>Hello</p></Card>` passes `<p>Hello</p>` as `children`.

## Next Up
**useState** — making components interactive by managing changing data.
