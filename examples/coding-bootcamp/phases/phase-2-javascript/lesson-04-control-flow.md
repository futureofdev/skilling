---
title: "Control Flow: if/else and Loops"
phase: 2
lesson: 4
duration_minutes: 30
prerequisites: ["2.3"]
skills_unlocked: []
objectives:
  - id: if-else
    kind: practice
    text: "Write if/else statements"
  - id: ternary-expressions
    kind: practice
    text: "Use ternary expressions for concise conditions"
    about: [1]
  - id: loop-over-arrays
    kind: practice
    text: "Loop over arrays with .forEach() and for...of"
    about: [3]
  - id: logical-operators
    kind: practice
    text: "Use && and || for logical conditions"
    about: [2]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
**if/else** — make decisions:
```javascript
const age = 20;

if (age >= 18) {
  console.log("You can vote!");
} else if (age >= 16) {
  console.log("Almost there!");
} else {
  console.log("Too young to vote.");
}

// Ternary — one-line if/else (great for JSX!)
const status = age >= 18 ? "adult" : "minor";
```

**Logical operators:**
```javascript
const isLoggedIn = true;
const isPremium = false;

if (isLoggedIn && isPremium) console.log("Premium member");
if (isLoggedIn || isPremium) console.log("Either one works");
if (!isLoggedIn) console.log("Please log in");
```

**Loops:**
```javascript
const skills = ["HTML", "CSS", "JavaScript"];

// .forEach() — run a function for each item
skills.forEach(skill => {
  console.log(`I know ${skill}`);
});

// for...of — modern loop syntax
for (const skill of skills) {
  console.log(skill);
}
```

## Key Terms
- **if/else**: Conditional execution — run code only when condition is true
- **Ternary operator**: `condition ? valueIfTrue : valueIfFalse`
- **`&&` (AND)**: Both conditions must be true
- **`||` (OR)**: At least one condition must be true
- **`!` (NOT)**: Inverts a boolean
- **`.forEach()`**: Runs a function for each array item (doesn't return)
- **`for...of`**: Loops over iterable values

## Hands-On Exercise
```javascript
const grades = [85, 92, 78, 95, 60, 88];

// Find passing grades (>= 70)
const passing = grades.filter(g => g >= 70);

// Assign letter grades
const letterGrades = grades.map(g => {
  if (g >= 90) return "A";
  else if (g >= 80) return "B";
  else if (g >= 70) return "C";
  else return "F";
});

console.log(letterGrades); // ["B", "A", "C", "A", "F", "B"]

// Count As
const aCount = letterGrades.filter(g => g === "A").length;
console.log(`${aCount} students got an A!`);
```

## Quick Quiz
1. What does the ternary operator `age >= 18 ? "adult" : "minor"` return when age is 15?
   - a) "adult"
   - b) "minor"
   - c) undefined
   - d) true

   **Answer:** b) "minor" — the condition is false (15 < 18), so the value after `:` is returned.

2. What's the difference between `&&` and `||`?
   - a) `&&` requires one condition true; `||` requires both
   - b) `&&` requires both conditions true; `||` requires at least one
   - c) They're the same
   - d) `&&` is for numbers; `||` is for strings

   **Answer:** b) `&&` = AND (both must be true); `||` = OR (either must be true).

3. What does `.forEach()` return?
   - a) A new array
   - b) The first matching item
   - c) `undefined` — it's used for side effects, not creating new arrays
   - d) The original array

   **Answer:** c) `undefined` — use `.map()` when you need a new array; `.forEach()` just runs code for each item.

## Next Up
**The DOM** — connecting JavaScript to your HTML to make things change on the page!
