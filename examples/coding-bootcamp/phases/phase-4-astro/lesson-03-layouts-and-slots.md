---
title: "Layouts and Slots"
phase: 4
lesson: 3
duration_minutes: 30
prerequisites: ["4.2"]
skills_unlocked: []
objectives:
  - id: create-a-layout
    text: "Create a reusable layout component"
  - id: use-slot
    text: "Use <slot /> to inject page content"
    tested_by: [1]
  - id: pass-props-to-layouts
    text: "Pass props to layouts"
    tested_by: [2, 3]
  - id: astro-and-react-children
    text: "Understand Astro's equivalent of React children"
    tested_by: [1]
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Conceptual phase: Astro's ideas are practised on the portfolio build rather than in isolation."
  next_up: present
---

## The Concept
Layouts are Astro components that wrap page content. They provide consistent HTML shell, navigation, and footer.

```astro
---
// src/layouts/BaseLayout.astro
const { title = "My Site" } = Astro.props;
---

<!doctype html>
<html>
  <head>
    <title>{title}</title>
  </head>
  <body>
    <nav>Navigation here</nav>
    <main>
      <slot />  <!-- page content goes here -->
    </main>
    <footer>Footer here</footer>
  </body>
</html>
```

Using a layout in a page:
```astro
---
// src/pages/about.astro
import BaseLayout from '../layouts/BaseLayout.astro';
---

<BaseLayout title="About Me">
  <!-- This content fills the <slot /> -->
  <h1>About Me</h1>
  <p>I'm a developer...</p>
</BaseLayout>
```

**Named slots** — multiple slots:
```astro
<slot name="header" />  <!-- <div slot="header">...</div> -->
<slot />                <!-- default slot -->
```

## Key Terms
- **Layout**: A reusable Astro component wrapping page content
- **`<slot />`**: Where child content is inserted (like React's `children`)
- **Named slot**: A specific slot for named content
- **`Astro.props`**: Object containing props passed to the component

## Quick Quiz
1. What does `<slot />` do in a layout?
   - a) Creates an empty slot visually
   - b) Marks where child content from the page gets inserted
   - c) Adds a navigation slot
   - d) Creates a database slot

   **Answer:** b) Where child content goes — equivalent to React's `{children}` prop.

2. How do you pass a prop to an Astro component?
   - a) Same as React: `<Layout title="Home" />`
   - b) Only through global variables
   - c) Through YAML frontmatter
   - d) Props aren't supported in Astro

   **Answer:** a) Same as React — `<BaseLayout title="About" />` passes `title` as a prop.

3. How do you access props inside an Astro component?
   - a) `this.props`
   - b) `Astro.props` or destructuring in frontmatter: `const { title } = Astro.props`
   - c) `props.title`
   - d) `getProps()`

   **Answer:** b) `Astro.props` — destructure in frontmatter: `const { title = "Default" } = Astro.props`.

## Next Up
**Astro vs React Components** — choosing the right tool for each piece of UI.
