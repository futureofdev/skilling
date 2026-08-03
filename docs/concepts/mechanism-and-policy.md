# Mechanism and policy

*The line between what Skilling specifies and what you decide.*

## The line

**Mechanism** is what must be identical across every implementation for courses and records to be portable: the course format, the loop's transitions, what a completion writes, what a store guarantees.

**Policy** is everything an organisation reasonably wants to be different: who may enrol, when a cohort starts, what a badge is worth, whether there are deadlines, how progress is reported, what the interface looks like, which model does the teaching.

Skilling specifies the first and refuses the second. Not because policy is unimportant — it is usually the part an adopter cares about most — but because a standard that specifies policy is a product, and nobody's policy fits anybody else.

## What the refusal looks like in practice

| Question | Answer |
|---|---|
| How do learners find courses? | Not specified. A catalogue is yours |
| Who is allowed to start one? | Not specified. `learner_id` is opaque and is not authentication |
| Is there a deadline? | Not specified. Build it on the record, never inside the loop |
| What does completing a phase entitle someone to? | Not specified. Badges are strings; meaning is yours |
| Which model teaches? | Not specified, and never named normatively |
| What does the interface look like? | Not specified. Terminal, chat, web, voice |
| Where is progress stored? | Any conforming store: files, Postgres, whatever you run |
| What does a celebration say? | Not specified. The course supplies [facts a tutor may not invent](../../spec/course-format.md#ceremony); the words are the tutor's |
| Where do learning events go? | Not specified. [Register a sink](the-telemetry-sink.md); the core ships no destination |

The list of what *is* specified is much shorter, and that asymmetry is the design.

## The two boundaries that make this real

A refusal only means something if it is enforceable. Two rules do the work:

**No orchestration inside a runtime.** A runtime delivers one course to one learner. The moment it grows course discovery, enrolment, or cohort management, every adopter inherits one organisation's assumptions about how learning is administered — and the format stops being portable, because now you need *their* orchestration too.

**No writing learner state around the runtime.** Read records for reporting freely. Do not write them, and do not synthesise learner input to unlock a gate. A producer that writes progress directly has, at that moment, become a second runtime with none of the guarantees — and the record's meaning quietly stops being trustworthy.

An implementation that breaks either isn't a Skilling runtime with extras. It is an LMS using a borrowed file format.

## Where policy attaches

Policy hangs off the artifacts, not the machinery:

- **The record and completion log** — reporting, dashboards, reminders, certificates, nudges
- **The homework archive** — grading workflows, moderation, resubmission rules
- **The course directory** — your own build steps, review process, translation pipeline
- **Around the runtime** — enrolment, catalogues, cohorts, interfaces, billing

**Since 1.1, policy attaches by name.** A runtime emits [eight events](../../spec/runtime.md#the-registry) — lesson started, gate opened, quiz answered, lesson completed, badge awarded, phase completed, course completed, homework submitted — and an adopter subscribes a sink to them. Dashboards, HR exports, reminder jobs, share campaigns: all of them read events and none of them live inside the runtime.

Hooks were deliberately absent at 1.0. Specifying extension points before anyone has extended anything is how a specification acquires surfaces nobody uses, so the rule was: wait for an adopter with real policy. That adopter turned up with nine branded share prompts and a completion beacon that 1.0 had nowhere to put, and hooks bound in the next minor. Every remaining deferred surface is waiting on the same bar.

## What this costs

An adopter arriving expecting a platform will find a format and a library, and will have to build the interface, the catalogue, and the reporting themselves. That is a real cost and the honest description of it.

What they get in exchange is that their courses and their learners' records are not hostage to any of those choices — including the ones they will make badly the first time.

## See also

[Open gates](open-gates.md) · [The learner record](the-learner-record.md) · [Implementing a runtime](../implementing-a-runtime.md)
