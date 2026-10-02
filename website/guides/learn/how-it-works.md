---
title: Behind the scenes
description: Who does what when you learn with Skilling, and why your progress doesn't live in the chat.
---

# Behind the scenes

You don't need to know any of this to learn. But if you're curious how it fits together, or
want to trust it, here's the picture.

## Three parts, three jobs

```mermaid
flowchart LR
    You["You"]:::learner <--> AI["<b>Your assistant</b><br/>Claude Code or Codex<br/>talks and explains"]
    AI <--> S["<b>Skilling</b><br/>knows the lesson order,<br/>saves your progress"]
    S <--> F["<b>Your folder</b><br/>the course<br/>and your record"]:::saved
    classDef learner stroke-width:1px
    classDef saved stroke-width:1px
```

| Part | Its job | What it doesn't do |
|---|---|---|
| **Your assistant** | Talks to you. Explains, asks, listens, adapts. | Decide the lesson order, or keep the record. |
| **Skilling** | Says what comes next. Saves what's finished. | Think or talk. It has no AI inside. |
| **Your folder** | Holds the course and your record as plain files. | Depend on any one company. |

## What happens when you type /learn

```mermaid
sequenceDiagram
    actor You
    participant AI as Assistant
    participant S as Skilling
    participant F as Your folder
    You->>AI: /learn
    AI->>S: Where is this learner?
    S->>F: Read the record
    F-->>S: Lesson 2, the idea step
    S-->>AI: Here's the lesson 2 idea
    AI->>You: Explains, then asks a question
    You->>AI: Your answer
    AI->>S: The learner replied, move on
    S->>F: Save the new position
```

The assistant asks Skilling at every step. That's how the tutor knows where you are, even in a
brand new chat on a different day.

## Why your progress isn't in the chat

If your progress lived in a chat, you'd lose it whenever the chat ended, or if you switched to
a different assistant. So Skilling keeps a small record file instead. It holds:

- which lessons you've finished, and when,
- where you are now,
- your streak and badges,
- your homework.

It **doesn't** store the conversation. Any tutor that follows the Skilling format can read the
record and carry on, so you can switch between Claude Code and Codex in the same folder.

Next to the record is a **completion log** with one line per finished lesson. It's only ever
added to, never rewritten. If the two ever disagree, the log wins, and the record can be
rebuilt from it.

## What the tutor decides, and what it doesn't

```mermaid
flowchart TB
    subgraph Fixed ["Fixed by the course and Skilling"]
      direction LR
      F1["Lesson order"] ~~~ F2["Waiting for you"] ~~~ F3["Quiz answers<br/>not shown early"] ~~~ F4["Saving progress"]
    end
    subgraph Free ["Up to the tutor"]
      direction LR
      T1["Its words"] ~~~ T2["Its examples"] ~~~ T3["Its pace"] ~~~ T4["How it re-explains"]
    end
    Fixed ~~~ Free
```

This split is on purpose. No one can force an AI to teach well. But Skilling can make sure the
parts around it are right, and those parts are tested.

## Limits worth knowing

- **The record says what you finished, not how well you understood it.** A quiz score is never
  treated as proof that you've mastered something.
- **The AI can make mistakes.** If something seems wrong, ask it to check or explain again.
- **Practical tasks need an assistant that can look at your files.** That's one more reason
  Skilling uses a coding assistant rather than a chat website.

Next: [your workspace](your-workspace).
