# Browser producer walkthrough

The [local browser example](../examples/python-producer/README.md) implements the public
[session facade](python-session.md) and [conversational tutor](python-tutor.md) together.
Follow its README to create an explicit disposable workspace, add Welcome, configure a provider
and run the loopback server. The unchanged Welcome course is the teaching input.

Learn through conversation: choose a topic, ask for an explanation, explain it in your own words,
ask about a gap, request a changed example or pace, then revisit what changed. Conversation
alone does not advance a gate. Use each explicit control only when you intend its displayed
operation. Answer quiz questions yourself; canonical correctness, authored explanation and
remediation are shown before the next step becomes available.

In lesson 1.2, write the complete Markdown note with your own Goal, Takeaway and Next action.
Save, inspect and request review, then separately attest authorship and confirm the displayed
positive review. Saving or receiving advice does not settle an objective. For a knowledge
objective, provide your own explanation. Note edits and stale runtime state invalidate reviews.

Complete the lesson, then add a review of what changed to the note. Supply actual evidence for
all homework requirements, including your topic choice, own-words explanation and requested
change. Inspect the updated note and display feedback for every requirement before separately
confirming submission. Feedback is informal and the durable homework archive retains null
verdicts. Artifact registration is optional and cannot gate completion.

Restart the server with the same workspace to verify durable progress and pending quiz feedback.
Conversation is not persisted; fresh evidence is required for new advice. Read the same state
with installed CLI commands from a nested workspace directory. Stop every writer before moving
this disposable workspace, then restart with the new explicit path and verify the relative note
and artifact pointer. Do not move unrelated user files.

Automated source, DOM and clean wheel/sdist journey tests cover the reference controller and
installation. Their model responses are synthetic. An authentic learner/model run, captured
costs and limitations, and independent milestone closure remain separate evidence obligations.

Conversation can request current course controls through the app-owned native Agent output
contract. The model receives only current safe material and read-only control labels/ids.
The producer stages the recommendation against the exact snapshot, then applies it only
after the browser paints that teaching turn. It supplies fresh material before the next
reply. Continuations can present normal beats automatically, but cannot invent another
learner gate choice or quiz answer. Each learner message has at most four tutor turns;
canonical quiz feedback stops progression until its separate rendering acknowledgement.
Generic `SkillingRunner.chat` remains read-only; the app's recommendations are producer
policy, never new core authority, privileged model tools or automatic work confirmation.

Explicit “continue” from a rendered beat applies the current legal SDK transition before the tutor receives the resulting material. Tutoring progression uses chat; no advance buttons are shown. Gates still require the learner’s choice, and exercise attempts and quiz answers are never inferred from a generic continue.
