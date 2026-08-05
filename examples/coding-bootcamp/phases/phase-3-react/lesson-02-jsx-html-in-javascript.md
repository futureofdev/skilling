---
title: "JSX: HTML in JavaScript"
phase: 3
lesson: 2
duration_minutes: 30
prerequisites: ["3.1"]
skills_unlocked: []
objectives:
  - id: write-jsx
    kind: practice
    text: "Write JSX correctly"
  - id: jsx-vs-html
    kind: knowledge
    text: "Know the differences between JSX and HTML"
    about: [1]
  - id: embed-expressions
    kind: practice
    text: "Embed JavaScript expressions in JSX"
    about: [2]
  - id: render-lists
    kind: practice
    text: "Render lists with .map()"
    about: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
JSX is HTML-like syntax that compiles to JavaScript. It's not HTML — it's syntactic sugar.

```jsx
// JSX (what you write)
const element = <h1 className="title">Hello, {name}!</h1>;

// What it compiles to (what the browser gets)
const element = React.createElement("h1", { className: "title" }, `Hello, ${name}!`);
```

**JSX vs HTML differences:**
- `class` → `className` (class is a JS keyword)
- `for` → `htmlFor` (for is a JS keyword)
- Self-closing tags must close: `<img />`, `<input />`
- Inline styles are objects: `style={{ color: "red", fontSize: "16px" }}`
- Comments: `{/* comment */}`

**Expressions in JSX (anything in `{}`):**
```jsx
const items = ["React", "Astro", "TypeScript"];

function SkillList() {
  return (
    <ul>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}
```

**Rules:**
- Return a single root element (or use `<>` Fragment)
- Every component must start with a capital letter

## Key Terms
- **JSX**: JavaScript XML — HTML-like syntax in JavaScript
- **Expression**: JavaScript value inside `{}` in JSX
- **`className`**: JSX equivalent of HTML `class`
- **Fragment** (`<>`): Invisible wrapper when you need to return multiple elements
- **Key**: Unique identifier required on list items

## Hands-On Exercise
Translate this HTML to JSX:
```html
<div class="card">
  <img src="photo.jpg" alt="Profile photo">
  <h2>Alice Johnson</h2>
  <p style="color: gray; font-size: 14px">Developer</p>
</div>
```

Answer:
```jsx
<div className="card">
  <img src="photo.jpg" alt="Profile photo" />
  <h2>Alice Johnson</h2>
  <p style={{ color: "gray", fontSize: "14px" }}>Developer</p>
</div>
```

## Quick Quiz
1. Why do we use `className` instead of `class` in JSX?
   - a) React prefers it
   - b) `class` is a reserved keyword in JavaScript
   - c) `className` is more descriptive
   - d) HTML requires it

   **Answer:** b) `class` is a JS keyword (for ES6 classes), so JSX uses `className` to avoid conflicts.

2. How do you embed a JavaScript expression in JSX?
   - a) With `${}` like template literals
   - b) With `<% %>` like template engines
   - c) With `{}` curly braces
   - d) You can't — JSX is static

   **Answer:** c) Curly braces `{}` — anything valid JavaScript expression goes between them.

3. What is required on list items rendered with `.map()` in React?
   - a) An `id` attribute
   - b) A `key` prop with a unique value
   - c) A `class` attribute
   - d) A `data-index` attribute

   **Answer:** b) A `key` prop — React uses it to efficiently update the list when it changes.

## Next Up
**Components and Props** — building reusable, composable UI pieces.
