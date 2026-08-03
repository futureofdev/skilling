---
title: "Forms in React (Controlled Components)"
phase: 3
lesson: 7
duration_minutes: 35
prerequisites: ["3.6"]
skills_unlocked: []
objectives:
  - id: controlled-components
    text: "Build controlled form components with React state"
    tested_by: [1]
  - id: one-handlechange
    text: "Use a single handleChange for all inputs"
    tested_by: [2]
  - id: validate-before-submit
    text: "Validate form data before submission"
    tested_by: [3]
  - id: show-error-messages
    text: "Show error messages"
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
In React, form inputs should be "controlled" — their value is stored in React state.

```jsx
function ContactForm() {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    message: "",
  });

  // Single handler using computed property names [e.target.name]
  function handleChange(e) {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  }

  function handleSubmit(e) {
    e.preventDefault();
    // formData now has all values
    console.log(formData);
  }

  return (
    <form onSubmit={handleSubmit}>
      <input
        name="name"
        value={formData.name}
        onChange={handleChange}
        placeholder="Your name"
      />
      <input
        name="email"
        type="email"
        value={formData.email}
        onChange={handleChange}
        placeholder="Email"
      />
      <textarea
        name="message"
        value={formData.message}
        onChange={handleChange}
      />
      <button type="submit">Send</button>
    </form>
  );
}
```

**The `[e.target.name]` trick**: Computed property names let one handler update any field — `{ ...prev, [name]: value }` where `name` comes from the input's `name` attribute.

## Key Terms
- **Controlled component**: Input whose value is controlled by React state
- **`value` + `onChange`**: The two props that make a controlled input
- **Computed property name**: `{ [variable]: value }` — uses variable as the key
- **`e.target.name`**: The `name` attribute of the input that triggered the event
- **`e.preventDefault()`**: Stop form from reloading the page

## Hands-On Exercise
Add validation:
```jsx
const [errors, setErrors] = useState({});

function validate() {
  const newErrors = {};
  if (!formData.name.trim()) newErrors.name = "Name is required";
  if (!formData.email.includes("@")) newErrors.email = "Invalid email";
  if (!formData.message.trim()) newErrors.message = "Message is required";
  setErrors(newErrors);
  return Object.keys(newErrors).length === 0;
}

function handleSubmit(e) {
  e.preventDefault();
  if (!validate()) return; // stop if invalid
  // submit!
}

// In JSX:
{errors.name && <p className="error">{errors.name}</p>}
```

## Quick Quiz
1. What makes a form input "controlled" in React?
   - a) Adding `required` attribute
   - b) Having its value controlled by React state via `value` and `onChange` props
   - c) Disabling the input
   - d) Using a `ref`

   **Answer:** b) `value={state}` + `onChange={handler}` — React state is the single source of truth.

2. How does `[e.target.name]: value` work in the state update?
   - a) It's a syntax error
   - b) It uses computed property names — the variable `e.target.name` becomes the object key
   - c) It sets all form fields at once
   - d) It creates an array

   **Answer:** b) Computed property names — `[name]` where name is a variable, creates a key with that variable's value.

3. Why call `e.preventDefault()` in a form's `onSubmit` handler?
   - a) To validate the form
   - b) To prevent the browser from navigating/reloading on form submission
   - c) To clear the form
   - d) To enable async submission

   **Answer:** b) Without it, the browser reloads the page — which would clear all React state.

## Next Up
**Component Composition** — building complex UIs by combining simple components.
