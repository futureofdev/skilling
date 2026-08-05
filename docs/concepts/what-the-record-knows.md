# What the record knows

*Why a badge and an objective are different claims, and what the record still does not know about a learner.*

Normative home: [runtime § objectives and the record](../../spec/runtime.md#objectives-and-the-record) and [course format § structured objectives](../../spec/course-format.md#structured-objectives).

## Two claims that look like one

The record can say two different things about a learner, and the difference matters:

| | Means | Written when |
|---|---|---|
| `skills_unlocked` | This lesson completed | The lesson's final quiz feedback is delivered |
| `objectives_met` | This capability was demonstrated | A runtime with the right capability gathered evidence for it |

> **1.1 got this wrong and 1.2 fixes it.** 1.1 let a quiz settle an objective, which put 168
> capability claims into the golden example's record on the strength of multiple-choice answers
> — 142 of them resting on a single four-option question. Worse, 31 described actions a quiz
> cannot observe: `Have Node.js installed` was being settled by *"Why use nvm instead of
> installing Node.js directly?"*, which a learner with no Node at all answers correctly. This
> page said such claims are worse than absence, and then the implementation made 168 of them.

A badge is a **completion marker**. An objective is a **capability claim**. A runtime must not infer either from the other.

## The mistake the field name invites

1.0 had only badges, and named the field `skills_unlocked`. That reads like a claim about what the learner can now do. It isn't. It is written the moment a lesson finishes, so a badge called `git-basics` means, precisely, *was present for the git lesson*.

The original course this format generalises had exactly this shape, and worse: it declared badges on eleven lessons and never wrote any of them. 1.0 fixed the writing. It did not fix the meaning, and for a while the specification let the field name do the arguing.

The sharpest version of the problem came from someone reading the format cold: a course whose second lesson unlocks a `tarp-rigging` badge awards it when the lesson completes, which is *before* the learner has rigged anything — the rigging is in the homework. The badge was true about attendance and false about capability, and nothing in the format could tell the difference.

Objectives are where that difference now lives.

## Why objectives had to be addressable

Objectives were always the real contract of a lesson. "By the end of this lesson, you will be able to open a terminal" is a claim you could check. But as a markdown bullet list, nothing could reference one — so a tutor could not target remediation at the objective a wrong answer implicated, could not check them off, could not tell you which one you were missing.

Giving them ids costs an author almost nothing and buys three things:

- **Remediation that names the problem.** "That one was about opening a terminal" rather than re-printing the concept at someone.
- **A record that means something.** `objectives_met` is a list of things this learner demonstrated, with evidence of how.
- **A tutor that can pick up where another left off.** A fresh runtime reading the record learns what the learner can do, not only which files they were shown.

## Kinds, capabilities, and the refusal to guess

**Since 1.2**, an objective declares what *kind* of claim it is, and a runtime declares what it
can *see*. The two have to match before anything is written.

| Kind | The claim | Needs a runtime that can |
|---|---|---|
| `knowledge` | The learner can explain something | hold a conversation and judge the answer (`converse`) |
| `practice` | The learner did something, or their machine is in some state | go and look (`observe`) |

`Understand what npm is` and `Have npm installed` read alike and need completely different
evidence: one is a conversation, the other is a fact about a computer. A chat tutor settles the
first and must leave the second alone however confident the learner sounds.

The rule is enforced in the shared machinery rather than trusted to each runtime — the same
reason telemetry consent lives in the dispatcher. A runtime that claims more than it can observe
is not merely discouraged; it is unable to write it.

Every entry in `objectives_met` carries `evidence` — `explained`, `observed`, or `homework` —
and there is deliberately no value for a quiz.

Writing objectives is **optional** — the same position as homework checking. A runtime that cannot judge whether an objective was met writes nothing and conforms. What it must never do is guess, because an objective recorded as met without evidence is worse than one left absent: a later tutor will believe it, and will skip teaching something the learner never learned.

### What the quiz is actually for

A quiz is a **checkpoint**, not an assessment. It surfaces confusion so remediation can happen,
and `about` names which objective a wrong answer implicates so the tutor can say "that one was
about opening a terminal" rather than replaying the whole concept.

Note the asymmetry, because it is the whole point. `about` steers what a tutor *says*, where
being slightly wrong costs a slightly-off sentence. Evidence goes into a record that outlives
the conversation, where being slightly wrong is a lie. One field cannot serve both needs, and
1.1's mistake was trying.

### Verifying practice

A `practice` objective may carry a `verify` clause — a sentence saying what success looks like,
for a runtime that can go and look:

```yaml
verify: Both node and npm report a version number when asked for one
```

Prose rather than a command, deliberately. An agent with shell access is good at working out
*how* to check something; a literal `node --version` is wrong behind a version manager and
differs between Windows and macOS for the identical objective. A literal `check` is available
where determinism matters, and is explicitly a proposal a runtime may decline.

## Limits

**The record still knows very little.** How long a learner spent, which explanations they needed, where they hesitated, what they said — none of it is stored, and most of it never will be. That thinness is what makes the record portable, and it is a real cost: you cannot build a diagnostic profile out of it.

**Most practice cannot be observed at all.** In the golden example only 22 of 171 practice
objectives carry a `verify` clause. "Apply the design system consistently" is a judgement, not
a check, and inventing one would be exactly the false confidence 1.2 exists to remove. Those
stay unsettled.

**`verify` is only as good as the author's sentence.** Nothing checks that "the repository has
an origin remote" is really what the objective meant. A vague clause produces a vague check.

**No runtime today has `observe`.** The surface that would provide it — delivery into a coding
harness over MCP — is specified for and not yet built. So the golden example's practice
objectives are currently unsettled, honestly, and will stay that way until something can look.

**Badges are unchanged, and still mean attendance.** 1.1 does not fix them; it stops the specification implying otherwise. If a badge in your course should mean a demonstrated capability, the objectives behind it are where the evidence has to come from.

## See also

[The learner record](the-learner-record.md) · [The homework mailbox](the-homework-mailbox.md) · [The delivery loop](the-delivery-loop.md)
