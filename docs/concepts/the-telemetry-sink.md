# The telemetry sink

*An opt-in, content-free destination for learning events — and an honest account of what opting in exposes.*

Normative home: [runtime § hooks](../../spec/runtime.md#hooks) and [§ telemetry](../../spec/runtime.md#telemetry).

## Why it exists

Course authors deserve to know their work is being used. That instinct is right, and the course this format came from acted on it the wrong way: it POSTed to one author's hardcoded analytics endpoint from inside the framework's own prompts, and its consent flow fought the host's permission model.

Skilling keeps the instinct and moves the layer. Telemetry is a **sink you register**, not a destination baked in. The core ships no endpoint at all — the framework phones nobody's home by default, and the only sinks in the box write to a local file or to nowhere.

## Three non-negotiables

**Opt-in, per learner, ternary.** `opt_in` is `null`, `true`, or `false`. `null` means the learner has never been asked, so ask once. `false` means silence forever. There is no "ask again next week".

**Identity is a fresh pseudonym.** A learner who says yes gets a `anonymous_id` assigned once and never derived from the producer's `learner_id`. A learner who later says no keeps it rather than having it recycled, because recycling an id is how two people become one row in someone's dashboard.

**Payloads carry no content.** Event names, coordinates, question numbers, booleans, timestamps. Never conversation text, never a written answer, never homework.

Consent is enforced in the dispatcher, before a sink is ever handed an event. That is a deliberate structural choice: a sink that *forgot* to check `opt_in` must not be able to leak. There is a test that a sink registered as telemetry receives literally nothing until the learner has agreed.

## Fire-and-forget, and why it has to be

Emitting must never block or delay the lesson, and a broken sink must never reach the learner. Both are obvious. The one people miss is that this has to hold for **slow** sinks too: a sink taking five seconds to answer has stopped the lesson just as effectively as one that raises.

So the dispatcher swallows every exception, and `ThreadedSink` puts a bounded queue in front of anything that might be slow. When that queue fills, it **drops**. That is the right trade: telemetry is directional signal, and the completion log is the audit trail. Losing an event costs an author a data point; blocking on one costs a learner their lesson.

## Content-free is not behaviour-free

This is the part worth being blunt about, because it is easy to describe telemetry in a way that is technically accurate and quietly misleading.

An opted-in learner emits `gate_opened` when they reach a gate and `quiz_answered` with a boolean for each question. From those, with their timestamps, a sink operator can reconstruct **which questions this learner got wrong and roughly how long they sat at each gate**. No prose left the machine. A behavioural trace did.

That is the honest description of what "share anonymous progress data" means here, and it is why the reference runtime's consent prompt says which lessons you finish and which answers you get right, in those words, with the decline as the default. A producer that presents the choice as harmless is misrepresenting it.

## When it works

An author of an open course gets adoption signal without running accounts or analytics of their own. An enterprise points the same channel at its own collector and never sends anything outside. Because the sink is registered rather than compiled in, neither has to trust the framework's judgement about where data should go — there is no default destination to override.

## Limits

**Anonymous ids are pseudonymous, not anonymous.** In a cohort of six, "the learner who failed question 2 on Tuesday" may be one person. Adopters in regulated environments owe themselves a real privacy assessment; this page is not one.

**Honest opt-in costs volume.** Most learners will decline, and the design accepts that. A prompt engineered to raise the yes rate is a dark pattern, and [the Producer rules](../../spec/README.md#conforming-producer) forbid it.

**Telemetry is lossy by construction.** Dropped on overflow, silent on failure. Never use it as an audit log — that is what the [append-only completion log](the-learner-record.md#the-log-is-the-truth) is for.

**The funnel is chatty.** Eight events per lesson rather than two. If you only need adoption signal, register a sink that ignores what it does not need rather than asking for less.

## See also

[Mechanism and policy](mechanism-and-policy.md) · [The learner record](the-learner-record.md) · [Implementing a runtime](../implementing-a-runtime.md)
