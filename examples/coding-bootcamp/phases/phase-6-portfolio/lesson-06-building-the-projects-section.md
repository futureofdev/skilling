---
title: "Building the Projects Section (React)"
phase: 6
lesson: 6
duration_minutes: 40
prerequisites: ["6.5"]
skills_unlocked: []
objectives:
  - id: projects-with-filtering
    kind: practice
    text: "Build the React Projects component with tag filtering"
    about: [2, 3]
  - id: usestate-for-the-filter
    kind: practice
    text: "Use useState for the active filter state"
  - id: usememo-to-optimise
    kind: practice
    text: "Use useMemo to optimise the filtered list"
    about: [1]
  - id: hover-effects-on-cards
    kind: practice
    text: "Implement hover effects on project cards"
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
This is the key React island — the filter buttons change which projects show, requiring state.

```tsx
import { useState, useMemo } from "react";
import { projects } from "../data/projects";

const allTags = ["All", ...new Set(projects.flatMap(p => p.tags))];

export default function Projects() {
  const [activeTag, setActiveTag] = useState("All");

  // useMemo: only recalculate when activeTag changes
  const filtered = useMemo(
    () => activeTag === "All" ? projects : projects.filter(p => p.tags.includes(activeTag)),
    [activeTag]
  );

  return (
    <section id="projects">
      {/* Filter buttons */}
      <div>
        {allTags.map(tag => (
          <button key={tag} onClick={() => setActiveTag(tag)}
            className={activeTag === tag ? "active-style" : "default-style"}>
            {tag}
          </button>
        ))}
      </div>
      {/* Project grid */}
      <div className="grid">
        {filtered.map(project => <ProjectCard key={project.id} project={project} />)}
      </div>
    </section>
  );
}
```

**`useMemo` teaching moment:** Without it, filtering recalculates on every render. With it, only recalculates when `activeTag` changes — a micro-optimization worth knowing.

## Quick Quiz
1. Why is `useMemo` used for the filtered projects list?
   - a) It's required when using `useState`
   - b) It caches the filtered result — only recalculates when `activeTag` changes, not on every render
   - c) It prevents the list from rendering
   - d) It memoizes the project data

   **Answer:** b) Caching — avoids re-filtering the array on every render when other state changes.

2. Why use `new Set()` when building `allTags`?
   - a) Sets are faster than arrays
   - b) `Set` automatically removes duplicates — ensures each tag appears once even if used by many projects
   - c) `Set` sorts the tags alphabetically
   - d) Arrays don't work with `.flatMap()`

   **Answer:** b) Deduplication — `Set` only stores unique values.

3. What does `projects.flatMap(p => p.tags)` produce?
   - a) An array of project objects
   - b) A flat array of all tags from all projects (some may be duplicates)
   - c) An object mapping projects to tags
   - d) A nested array of tags

   **Answer:** b) Flat array of all tags — `.flatMap()` maps then flattens one level.
