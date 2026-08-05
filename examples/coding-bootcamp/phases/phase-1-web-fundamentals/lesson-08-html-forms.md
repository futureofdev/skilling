---
title: "HTML Forms"
phase: 1
lesson: 8
duration_minutes: 30
prerequisites: ["1.7"]
skills_unlocked: []
objectives:
  - id: create-forms
    kind: practice
    text: "Create HTML forms with various input types"
    about: [2]
  - id: labels-for-accessibility
    kind: practice
    text: "Use labels correctly for accessibility"
    about: [1]
  - id: style-forms
    kind: practice
    text: "Style forms with CSS"
  - id: form-validation-basics
    kind: knowledge
    text: "Understand form validation basics"
    about: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
Forms are how users send data to your app — contact forms, login forms, search boxes, etc.

```html
<form action="/submit" method="POST">
  <label for="name">Name</label>
  <input type="text" id="name" name="name" required placeholder="Your name">

  <label for="email">Email</label>
  <input type="email" id="email" name="email" required>

  <label for="message">Message</label>
  <textarea id="message" name="message" rows="4"></textarea>

  <button type="submit">Send</button>
</form>
```

**Important input types:**
- `type="text"` — single line text
- `type="email"` — email with built-in validation
- `type="password"` — hidden text
- `type="number"` — numeric input
- `type="checkbox"` — true/false toggle
- `type="radio"` — one of many options
- `type="submit"` — submit button

**Accessibility:**
- Always connect `<label>` to `<input>` using matching `for` and `id`
- This lets screen readers announce the label when the input is focused
- Use `required` for required fields
- Use `placeholder` for hints (not as a replacement for labels!)

## Key Terms
- **Form**: HTML element for collecting user input
- **Input**: Form field for user to type in
- **Label**: Text description for a form field (critical for accessibility)
- **Placeholder**: Hint text shown inside an empty input
- **Required**: HTML attribute that prevents form submission if empty
- **Textarea**: Multi-line text input

## Hands-On Exercise
Style a contact form:

```css
form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 480px;
}

label {
  font-size: 14px;
  color: #666;
  margin-bottom: 4px;
  display: block;
}

input, textarea {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 16px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.2s;
}

input:focus, textarea:focus {
  border-color: #00D4AA;
}

button[type="submit"] {
  padding: 12px 24px;
  background: #FF6B35;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  cursor: pointer;
}
```

## Quick Quiz
1. Why must `<label>` be connected to its `<input>`?
   - a) It's required for the form to submit
   - b) For accessibility — screen readers announce the label when the input is focused
   - c) To make the label appear above the input
   - d) Labels only work when connected

   **Answer:** b) For accessibility — this lets screen readers and assistive technology work correctly.

2. What does `type="email"` do differently than `type="text"`?
   - a) It shows a keyboard with @ on mobile and validates email format
   - b) It encrypts the email address
   - c) It sends the email automatically
   - d) Nothing — they're the same

   **Answer:** a) Shows a mobile-friendly keyboard and validates the email format before submission.

3. What is the `required` attribute on an input?
   - a) Makes the field read-only
   - b) Prevents form submission if the field is empty
   - c) Marks the field as important visually
   - d) Requires the field to have a label

   **Answer:** b) Prevents form submission if the field is empty — built-in validation.

## Next Up
The Phase 1 capstone: **Your First Webpage** — putting everything together!
