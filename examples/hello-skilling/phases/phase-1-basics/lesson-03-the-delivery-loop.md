---
title: "The Delivery Loop"
phase: 1
lesson: 3
duration_minutes: 20
prerequisites: ["1.2"]
skills_unlocked: [first-course]
sections:
  key_terms: present
  exercise:
    status: none
    intent: "The homework is the exercise: you'll author and validate a real course of your own."
  next_up:
    status: none
    intent: "Last lesson of the course — there is nothing after this to tease."
---

## Learning Objectives
By the end of this lesson, you will:
- Be able to describe the beats a tutor delivers, in order
- Understand what a gate is and why it never times out
- Know what gets written to a learner's record when a lesson completes

## The Concept
You've seen what an author writes. Now: what does a tutor do with it?

It walks the lesson's sections in order, turning each into a **beat**. Welcome, objectives, concept, exercise, quiz, completion. Between some of the beats it stops and waits.

### Gates

A **gate** is a stop where the tutor will not move on until the learner says something.

There are two: one after the concept, one after the exercise.

At the concept gate the tutor offers both directions — go deeper, or move on. Asking to go deeper keeps you in the concept beat, and crucially does not advance your position. You can ask four follow-up questions and still be exactly where you started, because curiosity isn't progress and shouldn't be recorded as any.

At the exercise gate the tutor waits for you to report an attempt. Asking for a hint keeps you in the exercise beat.

Now the important part: **a gate has no timeout.** None. A learner who shuts the laptop mid-exercise and comes back a fortnight later finds the same gate, still open, waiting. Silence is never taken as consent. Neither is enthusiasm — "this is great!" does not mean "I've finished the exercise".

This is the difference between tutoring and playback. Every one of those gates is a place a video would simply have kept going. Remove a gate — advance on a timer, treat a good mood as agreement — and you have a lecture with extra steps.

### The quiz

Three questions, delivered strictly one at a time. Before you have answered the current question, a conforming tutor will not show you the next one, will not tell you which option is right, and will not explain anything.

After each answer it tells you whether you were right **and why**. That "and why" is not decoration: a learner who guessed correctly still needs the reason, or they've learned nothing but luck.

Get one wrong and the tutor offers to explain the concept again. Get two or more wrong and it should offer to go back to the concept beat properly before finishing. It's still your choice — in informal delivery a wrong answer never blocks completion. But there is always a way back.

The course this format came from had no way back at all. You could answer all three questions wrongly and be congratulated.

### Completion

The lesson is complete only once you've had feedback on the *final* quiz question. At that moment the tutor writes, through a store:

- Your coordinate added to the completed set
- Your position advanced to the next lesson
- Any badges this lesson unlocks, added to your record
- Your streak updated, and today stamped as your last activity
- An entry appended to your completion log

That log is append-only and never rewritten. Your record's completed set has to be reconstructible from the log alone, and where the two disagree the log wins.

And none of it requires a conversation transcript. Your record is deliberately independent of the chat that produced it — which is what lets you change tutor, model, or product entirely and keep your history.

Completion is also idempotent. Re-reading a lesson you've already finished changes nothing: not your completed set, not your log, not your streak. You can revisit anything. Revisiting isn't completing.

### Ceremony

When the lesson you just finished is the last in its phase, the tutor marks the phase complete, awards any outstanding badges, drops the phase's homework into your mailbox, and celebrates.

You're about to experience that one directly.

## Key Terms
- **Beat**: One step of delivery, derived from a lesson section
- **Gate**: An open wait — the tutor will not advance without explicit learner input, and never times out
- **Remediation**: The re-explanation a tutor offers after a wrong answer
- **Progress record**: What is durably true about one learner in one course, independent of any transcript
- **Completion log**: The append-only history from which the record can be rebuilt
- **Ceremony**: What happens at a phase boundary — badges, homework, celebration
- **Idempotent**: Doing it twice has the same effect as doing it once

## Quick Quiz
1. A learner goes quiet at the exercise gate for eleven days, then returns. What should a conforming tutor do?
   - a) Have already advanced them to the quiz, since they clearly finished
   - b) Have marked the lesson abandoned and restart the phase
   - c) Still be at the same open gate, waiting
   - d) Ask whether they'd like to skip the exercise this time

   **Answer:** c) Still be at the same open gate. Gates have no timeouts at all, and
   silence is never read as consent — that's precisely what separates tutoring from
   a video that keeps playing while you make tea.

2. A learner asks the tutor to explain the concept a third time. What happens to their recorded position?
   - a) Nothing — going deeper stays in the concept beat and doesn't advance position
   - b) It advances, because each explanation counts as progress
   - c) It rolls back to the start of the lesson
   - d) It advances only on the third request

   **Answer:** a) Nothing. Going deeper deliberately does not advance position;
   curiosity isn't progress, and recording it as progress would push a confused
   learner forward for asking good questions.

3. Why must a learner's record be reconstructible without the conversation transcript?
   - a) Transcripts are too large to store
   - b) So the learner's history survives a change of tutor, model, or product
   - c) Because transcripts may contain personal information
   - d) So the tutor can run without any memory at all

   **Answer:** b) So the history survives. If your progress lived inside a chat log,
   changing tutor would mean losing everything — the record is the portable part, and
   the transcript is just one runtime's convenience.

## Homework Assignment
### Write Your Own Course
**Objective:** Prove you can author a conforming course from the specification, not from this example.

Create a small course of your own on any subject you like — two lessons in one phase is plenty. Then validate it.

- [ ] A `course.yaml` with `spec_version`, `id`, `title`, `version`, and one phase containing two lessons
- [ ] Both lesson files at their correct derived paths, with frontmatter agreeing with the manifest
- [ ] Every required section present, in registry order, in both lessons
- [ ] Every optional section declared — present, or absent with an intent someone else would find convincing
- [ ] A Quick Quiz in each lesson: three questions, four options, one correct, each with an answer line giving the reason
- [ ] No structural count written anywhere in the course
- [ ] `skilling validate ./your-course` reports zero errors

**Stretch Goals:**
- [ ] Register a badge in the manifest and unlock it from your second lesson
- [ ] Add an `assets/` image and reference it with a relative path from a lesson
- [ ] Deliberately break one rule, run the validator, and read the error code it gives you

**Submission:** Tell your tutor when it's ready and share the directory. Expect feedback on each requirement separately.
