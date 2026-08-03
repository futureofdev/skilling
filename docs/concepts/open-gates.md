# Open gates

*Why a gate has no timeout, and what breaks the moment one is added.*

Normative home: [runtime § gates](../../spec/runtime.md#gates).

## The idea

There are two points in a lesson where the tutor stops and will not continue: after the concept, and after the exercise. A gate is an **open wait** — no advance without an explicit input from the learner, and no timeout of any length.

A learner who closes the laptop mid-exercise and comes back a fortnight later finds the same gate, still open.

## Why this is the load-bearing constraint

Every gate is a place a video would simply have kept playing.

That is the whole distinction. A course with no gates is a recording with a progress bar; the learner's presence makes no difference to what happens next. A course with gates cannot proceed without the learner, which means the learner's attention is structurally required rather than merely hoped for.

Remove one gate and you have a lecture with extra steps. Not a worse tutor — a different medium.

## The three ways gates get quietly removed

None of these look like removing a gate:

- **A timeout.** "If they haven't responded in five minutes, move on." Now silence means consent, and the learner who went to make tea has been taught a lesson they did not attend.
- **Inferring an answer.** A learner says "this is really interesting!" at the exercise gate. That is enthusiasm, not a completed exercise. Treating it as one records work that was never done.
- **A passing check counting as agreement.** Common in homework, and the reason [checking can never complete anything](the-homework-mailbox.md).

The specification's phrasing is deliberately blunt about the first two: silence is not completion, and neither is enthusiasm.

## Going deeper is not progress

At the concept gate the learner may go deeper instead of proceeding — and going deeper returns to the concept beat **without advancing position**.

This looks like a detail and is not. If curiosity advanced position, then a learner who asks four follow-up questions because they are confused would be pushed four steps forward for admitting confusion. The system would reward silence over questions, which is the opposite of what a tutor is for.

So the record cannot move. A learner can ask as much as they like and remain exactly where they were.

## Gates and resume

Because gates never expire, resume is simple: a gate that was open when the session ended is recorded as that gate, and resuming lands on it. Not near it — on it, with the same choices.

The reference runtime does this literally. Walk away at the concept gate and the record reads `beat: gate-concept`; come back and it asks the same question again.

## Limits

Open gates make a course impossible to finish on a schedule, and some adopters genuinely want deadlines. Those belong outside the runtime: build them on the record and the completion log, where an adopter can nudge, remind, or escalate however their organisation works. What must not happen is a deadline reaching *inside* the loop and advancing a learner who never answered.

Gates also make abandonment invisible from within a lesson — a learner at a gate and a learner who quit look identical to the runtime. That is a reporting question, answered from the record's `last_activity`, not a reason to add a timeout.

## See also

[The delivery loop](the-delivery-loop.md) · [The homework mailbox](the-homework-mailbox.md) · [Mechanism and policy](mechanism-and-policy.md)
