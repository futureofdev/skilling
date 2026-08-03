---
title: "JavaScript Basics: Variables and Types"
phase: 2
lesson: 1
duration_minutes: 35
prerequisites: ["1.9"]
skills_unlocked: []
objectives:
  - id: let-and-const
    text: "Declare variables with let and const"
    tested_by: [1]
  - id: primitive-types
    text: "Know JavaScript's primitive data types"
    tested_by: [3]
  - id: template-literals
    text: "Use template literals for string interpolation"
    tested_by: [2]
  - id: typeof
    text: "Understand typeof"
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
JavaScript is the programming language of the web. It runs in the browser and lets you make things happen.

**Variables** store data. Use `const` for values that won't change, `let` for values that will.

```javascript
const name = "Alice";        // string — text
let age = 25;                // number — integer or decimal
const isHired = true;        // boolean — true or false
const score = null;          // null — intentional absence of value
let future;                  // undefined — not yet assigned

// Template literals: embed variables in strings
const greeting = `Hello, ${name}! You are ${age} years old.`;
console.log(greeting);
// "Hello, Alice! You are 25 years old."
```

**Avoid `var`** — it's the old way and has confusing scoping rules. Always use `const` or `let`.

**Rule of thumb**: Use `const` by default. Only switch to `let` if you need to reassign.

## Key Terms
- **Variable**: A named container for a value
- **`const`**: A variable that cannot be reassigned
- **`let`**: A variable that can be reassigned
- **String**: Text data, in quotes
- **Number**: Numeric data (integers and decimals)
- **Boolean**: `true` or `false`
- **`null`**: Intentional empty value
- **`undefined`**: Unintentionally missing value
- **Template literal**: Backtick string with `${expression}` interpolation

## Hands-On Exercise
Open your browser's Console (F12 → Console tab) and type:

```javascript
const myName = "Your Name Here";
const myAge = 20;
const isLearningCode = true;

console.log(`Hi! I'm ${myName}, I'm ${myAge} years old.`);
console.log(`Am I learning code? ${isLearningCode}`);
console.log(typeof myName);    // "string"
console.log(typeof myAge);     // "number"
console.log(typeof isLearningCode); // "boolean"
```

## Quick Quiz
1. When should you use `let` instead of `const`?
   - a) Always
   - b) When the value will be reassigned after declaration
   - c) When the value is a string
   - d) Never — `const` is always better

   **Answer:** b) When the value needs to be reassigned — use `const` by default, `let` when mutation is needed.

2. What does a template literal use instead of regular quotes?
   - a) Single quotes ('')
   - b) Double quotes ("")
   - c) Backticks (``)
   - d) Brackets ([])

   **Answer:** c) Backticks — template literals use backticks and `${expression}` for interpolation.

3. What is the difference between `null` and `undefined`?
   - a) They're identical
   - b) `null` is an intentional empty value; `undefined` means a variable has been declared but not yet given a value
   - c) `null` is a string; `undefined` is a number
   - d) `undefined` is intentional; `null` is accidental

   **Answer:** b) `null` = intentional nothing; `undefined` = not yet assigned.

## Next Up
**Functions and Scope** — reusable blocks of code.
