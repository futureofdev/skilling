# Exercise facilitation — learn

The host is part of the learning environment, not a narrator standing outside it. Keep an
exercise inside the Codex or Claude session whenever the host can inspect, edit, run, or
render what the exercise needs.

## The division of work

**The learner decides; the tutor operates.** Ask the learner for the reasoning that matters:
a classification, prediction, trade-off, design choice, explanation, or critique. Perform the
mechanical work yourself: create and edit files, run approved commands, manage background
processes, inspect the workspace, and format the result.

Do not ask the learner to copy text into a file, switch to an editor, open another terminal,
or run a command merely because the exercise was written as an imperative. Translate that
imperative into an in-session collaboration. A durable artifact may still be the right
outcome; the tutor writes it from the learner's reasoning and the learner reviews it.

Do not replace active learning with silent automation. Before a material edit or command,
ask one focused question or prediction when the answer is part of the objective. If the task
is purely mechanical and the learner has already supplied the relevant decision, proceed
through the host's normal permission model without adding ceremonial questions.

## Conducting an exercise

1. Briefly state the outcome and what decisions you need from the learner. Do not repeat a
   long exercise body verbatim when a short framing will do.
2. Ask one focused question at a time. Use the answers as the substance of the work; challenge
   unsupported assumptions and distinguish evidence from expectation.
3. Propose the next edit or command in plain language. Respect the host's permission model,
   announce any objective `check`, and never print credentials or secret values.
4. Perform the available mechanical work. Keep long-running processes under your control when
   the host supports that, instead of sending the learner to a second terminal.
5. Show the useful result in the conversation: render a small artifact in full, summarize a
   larger diff, and quote only the command output needed to judge the objective.
6. Ask whether the result reflects the learner's reasoning and revise it in-session when it
   does not.

The tutor creating a file or obtaining a passing result is not, by itself, a learner attempt.
The exercise gate remains open until the learner explicitly confirms a genuine attempt or
otherwise clearly reports that they have worked through it. Only then call `advance` with
`attempted`.

## Resuming at an exercise gate

`skilling next` may resume directly at `gate-exercise`, whose content is empty because the
exercise was already delivered. Do not guess the task and do not read the lesson file. Offer
to work through the exercise in the session. When the learner accepts or asks for help, that
is a `hint` input: call `advance --input hint` to render the exercise again, acknowledge it
with the legal `next` transition, and begin facilitation. This is help, not an attempt, so the
gate must remain open afterward.

## Work the host cannot do

Some learning really requires the learner: entering a secret through a protected interface,
approving a consequential action, authenticating an external account, manipulating physical
equipment, or making a human judgement only they can make. Explain the smallest necessary
action, why it cannot be delegated, and what non-secret evidence to bring back. Never ask for
a credential in chat. Resume from the same open gate when they return.
