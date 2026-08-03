---
title: "Functions and Scope"
phase: 2
lesson: 2
duration_minutes: 40
prerequisites: ["2.1"]
skills_unlocked: []
objectives:
  - id: write-functions
    text: "Write functions using both declaration and arrow syntax"
  - id: parameters-and-returns
    text: "Understand parameters and return values"
    tested_by: [1, 2]
  - id: scope
    text: "Understand scope: which variables are accessible where"
    tested_by: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
Functions are reusable blocks of code. Instead of writing the same logic repeatedly, write it once as a function and call it.

```javascript
// Function declaration
function greet(name) {
  return `Hello, ${name}!`;
}

// Arrow function (modern syntax — preferred in React/Astro)
const greet = (name) => {
  return `Hello, ${name}!`;
};

// Short arrow function (implicit return when one expression)
const greet = (name) => `Hello, ${name}!`;

console.log(greet("Alice")); // "Hello, Alice!"
```

**Scope** determines where variables are accessible:
```javascript
const global = "I'm everywhere";

function myFunction() {
  const local = "I'm only inside this function";
  console.log(global); // ✅ accessible
  console.log(local);  // ✅ accessible
}

console.log(global); // ✅ accessible
console.log(local);  // ❌ ReferenceError — local is out of scope
```

## Key Terms
- **Function**: A named, reusable block of code
- **Parameter**: Variable in function definition (`name` in `greet(name)`)
- **Argument**: Actual value passed when calling (`greet("Alice")`)
- **Return value**: The output of a function (after `return`)
- **Arrow function**: Modern function syntax using `=>`
- **Scope**: The context in which a variable is accessible

## Hands-On Exercise
```javascript
// Write a function that calculates a tip
const calculateTip = (billAmount, tipPercent) => {
  const tip = billAmount * (tipPercent / 100);
  const total = billAmount + tip;
  return { tip, total };
};

const result = calculateTip(50, 18);
console.log(`Tip: $${result.tip}`);
console.log(`Total: $${result.total}`);

// Write a function that checks if someone can vote
const canVote = (age) => age >= 18;
console.log(canVote(20)); // true
console.log(canVote(16)); // false
```

## Quick Quiz
1. What is the difference between a parameter and an argument?
   - a) They're the same thing
   - b) Parameter is the variable in the function definition; argument is the value passed when calling
   - c) Arguments are required; parameters are optional
   - d) Parameters go inside the function; arguments go outside

   **Answer:** b) Parameter = placeholder in definition; argument = actual value passed in.

2. What does `return` do in a function?
   - a) Prints the value to the console
   - b) Sends the value back to wherever the function was called
   - c) Stops the program
   - d) Defines a new variable

   **Answer:** b) Sends the value back — without `return`, the function returns `undefined`.

3. Can a function access variables defined outside itself?
   - a) No — functions are completely isolated
   - b) Yes — functions can access variables in their outer scope
   - c) Only if you pass them as parameters
   - d) Only global variables

   **Answer:** b) Yes — inner scopes can access outer scopes (but not vice versa).

## Next Up
**Arrays and Objects** — the data structures you'll use constantly.
