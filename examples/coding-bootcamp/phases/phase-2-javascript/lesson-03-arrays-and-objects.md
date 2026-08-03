---
title: "Arrays and Objects"
phase: 2
lesson: 3
duration_minutes: 40
prerequisites: ["2.2"]
skills_unlocked: []
objectives:
  - id: create-arrays
    text: "Create and manipulate arrays"
  - id: array-methods
    text: "Use .map(), .filter(), and .find() on arrays"
    tested_by: [1]
  - id: objects
    text: "Create and access objects"
    tested_by: [2]
  - id: destructuring
    text: "Use destructuring for cleaner code"
    tested_by: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
**Arrays** are ordered lists of values:
```javascript
const fruits = ["apple", "banana", "cherry"];
console.log(fruits[0]);        // "apple" (0-indexed!)
console.log(fruits.length);    // 3

// Essential array methods:
fruits.push("date");           // add to end
fruits.pop();                  // remove from end

// .map() — transform every item, returns new array
const upper = fruits.map(f => f.toUpperCase());
// ["APPLE", "BANANA", "CHERRY"]

// .filter() — keep items that pass a test
const long = fruits.filter(f => f.length > 5);
// ["banana", "cherry"]

// .find() — first item that matches
const found = fruits.find(f => f.startsWith("b"));
// "banana"
```

**Objects** are collections of key-value pairs:
```javascript
const person = {
  name: "Alice",
  age: 25,
  skills: ["HTML", "CSS", "JavaScript"],
};

// Access values:
console.log(person.name);        // "Alice" (dot notation)
console.log(person["age"]);      // 25 (bracket notation)

// Destructuring — extract values into variables
const { name, age } = person;
console.log(name, age);          // "Alice" 25

// Spread — copy/merge objects
const updated = { ...person, age: 26 };
```

## Key Terms
- **Array**: Ordered list of values, accessed by index (0-based)
- **`.map()`**: Transforms every item, returns new array (same length)
- **`.filter()`**: Returns new array with only items that pass test
- **`.find()`**: Returns first item matching condition
- **Object**: Collection of key-value pairs
- **Destructuring**: Extracting values from objects/arrays into variables
- **Spread operator (`...`)**: Copies properties from one object/array to another

## Hands-On Exercise
```javascript
const projects = [
  { id: 1, title: "Portfolio", tags: ["Astro", "React"], featured: true },
  { id: 2, title: "Blog", tags: ["Astro"], featured: false },
  { id: 3, title: "Todo App", tags: ["React"], featured: true },
];

// Get only featured projects
const featured = projects.filter(p => p.featured);
console.log(featured.length); // 2

// Get just the titles
const titles = projects.map(p => p.title);
console.log(titles); // ["Portfolio", "Blog", "Todo App"]

// Find a specific project
const portfolio = projects.find(p => p.title === "Portfolio");
const { title, tags } = portfolio;
console.log(title, tags); // "Portfolio" ["Astro", "React"]
```

## Quick Quiz
1. What does `.map()` return?
   - a) A single value
   - b) A new array with each item transformed by the callback
   - c) The same array, modified in place
   - d) The first matching item

   **Answer:** b) A new array of the same length with each item transformed.

2. How do you access a property called `title` on an object called `project`?
   - a) `project[title]`
   - b) `project->title`
   - c) `project.title`
   - d) `get(project, title)`

   **Answer:** c) `project.title` — dot notation is the most common way.

3. What does destructuring do?
   - a) Deletes properties from an object
   - b) Extracts values from objects or arrays into named variables
   - c) Converts an array to an object
   - d) Copies an object

   **Answer:** b) Extracts values into variables — `const { name } = person` is cleaner than `const name = person.name`.

## Next Up
**Control Flow** — making decisions and repeating code with if/else and loops.
