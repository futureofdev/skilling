---
title: "Building the Contact Form (React)"
phase: 6
lesson: 7
duration_minutes: 40
prerequisites: ["6.6"]
skills_unlocked: []
objectives:
  - id: a-controlled-contact-form
    text: "Build the controlled React contact form"
    tested_by: [2]
  - id: validation-with-messages
    text: "Implement validation with error messages"
  - id: async-submission-states
    text: "Handle async submission states"
    tested_by: [1, 3]
  - id: success-and-error-feedback
    text: "Show success and error feedback"
    tested_by: [3]
sections:
  key_terms:
    status: none
    intent: "Build lesson: the vocabulary was established in the phases this section draws on."
  exercise:
    status: none
    intent: "Project phase: the exercise is the learner's own portfolio, built section by section as the lesson goes."
  next_up:
    status: none
    intent: "Build lessons run straight into the next section of the portfolio, so the teaser is generated rather than written."
---

## The Concept
The contact form needs React because it has complex state: form values, validation errors, and submission status.

```tsx
type FormStatus = "idle" | "loading" | "success" | "error";

export default function ContactForm() {
  const [formData, setFormData] = useState({ name: "", email: "", message: "" });
  const [errors, setErrors] = useState({});
  const [status, setStatus] = useState<FormStatus>("idle");

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const validate = () => {
    const errs = {};
    if (!formData.name.trim()) errs.name = "Required";
    if (!/^[^@]+@[^@]+\.[^@]+$/.test(formData.email)) errs.email = "Invalid email";
    if (!formData.message.trim()) errs.message = "Required";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;
    setStatus("loading");
    await new Promise(r => setTimeout(r, 1500)); // simulate API
    setStatus("success");
  };

  if (status === "success") return <SuccessMessage />;
  return <Form ... />;
}
```

**Multiple state pieces:** Each piece of state represents something different — form data, validation state, submission state. This is perfectly normal React.

## Quick Quiz
1. Why is `FormStatus` defined as a TypeScript union type?
   - a) TypeScript requires it for forms
   - b) It restricts `status` to only valid values — IDE warns if you use an invalid status
   - c) Union types are faster
   - d) It enables async operations

   **Answer:** b) Type safety — prevents typos like `"sucess"` from being valid.

2. What's the advantage of using `{ ...prev, [name]: value }` vs updating each field manually?
   - a) It's more readable
   - b) One `handleChange` works for ALL form fields — no need for separate handlers per input
   - c) It creates a new object reference
   - d) It prevents re-renders

   **Answer:** b) Single handler — the computed property `[name]` uses the input's `name` attribute as the key.

3. What does the `status === "loading"` state provide UX-wise?
   - a) Nothing — it's only for debugging
   - b) Visual feedback that submission is in progress, preventing duplicate submits
   - c) It speeds up the API call
   - d) It validates the form again

   **Answer:** b) UX feedback — disable button, show loading text so users know something is happening.
