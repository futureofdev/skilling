---
title: "Lists and Keys"
phase: 3
lesson: 5
duration_minutes: 25
prerequisites: ["3.4"]
skills_unlocked: []
objectives:
  - id: render-arrays
    kind: practice
    text: "Render arrays of data with .map()"
  - id: use-keys
    kind: practice
    text: "Use keys correctly to help React identify items"
    about: [1, 3]
  - id: conditional-rendering
    kind: practice
    text: "Conditionally render content"
    about: [2]
  - id: combine-state-and-lists
    kind: practice
    text: "Combine state and list rendering"
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
Rendering lists is one of React's core tasks. Use `.map()` to convert an array of data into an array of JSX elements.

```jsx
const projects = [
  { id: 1, title: "Portfolio", tag: "Astro" },
  { id: 2, title: "Blog", tag: "React" },
];

function ProjectList() {
  return (
    <ul>
      {projects.map((project) => (
        <li key={project.id}>
          <strong>{project.title}</strong> — {project.tag}
        </li>
      ))}
    </ul>
  );
}
```

**Keys must be:**
- Unique among siblings
- Stable (don't use array index if list reorders)
- Use IDs from your data when possible

**Conditional rendering:**
```jsx
// && operator — render only if condition is true
{isLoggedIn && <UserMenu />}

// Ternary — either/or
{isLoading ? <Spinner /> : <Content />}

// null — renders nothing
{error ? <ErrorMessage /> : null}
```

## Key Terms
- **Key**: Unique prop React uses to track list items across renders
- **Conditional rendering**: Showing/hiding content based on state or props
- **`&&` operator**: Renders right side only if left side is truthy
- **Ternary in JSX**: `{condition ? <A /> : <B />}` — either/or rendering

## Hands-On Exercise
Build a filterable list:
```jsx
function FilterableList({ items }) {
  const [filter, setFilter] = useState("");

  const visible = items.filter(item =>
    item.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div>
      <input
        value={filter}
        onChange={e => setFilter(e.target.value)}
        placeholder="Filter items..."
      />
      {visible.length === 0 ? (
        <p>No items match.</p>
      ) : (
        <ul>
          {visible.map(item => <li key={item}>{item}</li>)}
        </ul>
      )}
    </div>
  );
}
```

## Quick Quiz
1. What happens if you use array index as a key?
   - a) Nothing — it works fine
   - b) React may confuse items when the list reorders, causing rendering bugs
   - c) React throws an error
   - d) Performance improves

   **Answer:** b) Using index as key causes bugs when lists reorder — React can't tell items apart.

2. What does `{isLoggedIn && <Dashboard />}` render when `isLoggedIn` is false?
   - a) An empty `<Dashboard />`
   - b) The string "false"
   - c) Nothing — `false` renders nothing in React
   - d) An error

   **Answer:** c) Nothing — when the left side of `&&` is falsy, React renders nothing.

3. What must be true about a `key` in a list?
   - a) It must be a number
   - b) It must match the item's array index
   - c) It must be unique among siblings in the same list
   - d) It must be a UUID

   **Answer:** c) Unique among siblings — the key uniquely identifies each item in the list.

## Next Up
**useEffect** — running code in response to changes (fetching data, subscriptions).
