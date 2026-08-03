# What the record knows

*Why a badge and an objective are different claims, and what the record still does not know about a learner.*

Normative home: [runtime § objectives and the record](../../spec/runtime.md#objectives-and-the-record) and [course format § structured objectives](../../spec/course-format.md#structured-objectives).

## Two claims that look like one

The record can say two different things about a learner, and the difference matters:

| | Means | Written when |
|---|---|---|
| `skills_unlocked` | This lesson completed | The lesson's final quiz feedback is delivered |
| `objectives_met` | This capability was demonstrated | A runtime judged it, or a quiz proved it |

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

## Evidence, and the refusal to guess

Every entry in `objectives_met` carries `evidence`: `quiz`, `exercise`, `homework`, or `tutor`. That is deliberately a closed set, and it is deliberately mandatory.

Writing objectives is **optional** — the same position as homework checking. A runtime that cannot judge whether an objective was met writes nothing and conforms. What it must never do is guess, because an objective recorded as met without evidence is worse than one left absent: a later tutor will believe it, and will skip teaching something the learner never learned.

`tested_by` is the bridge that lets a model-free runtime participate honestly. When every question testing an objective is answered correctly, the quiz demonstrated it. When any of them was wrong, it did not. No judgement required, and no guessing either.

One detail that matters more than it looks: a question re-answered *after* remediation keeps its first verdict. Being told the answer and agreeing is not a demonstration.

## Limits

**The record still knows very little.** How long a learner spent, which explanations they needed, where they hesitated, what they said — none of it is stored, and most of it never will be. That thinness is what makes the record portable, and it is a real cost: you cannot build a diagnostic profile out of it.

**Objectives are only as good as the author's mapping.** `tested_by` says a question tests an objective; nobody checks that it really does. A badly aimed question produces a confidently wrong capability claim, and the format cannot see the difference.

**An objective with no `tested_by` is unverifiable by machinery.** Plenty of worthwhile objectives are like that — "appreciate why this matters" is not a quiz question. Those need a tutor with judgement, or they stay absent.

**Badges are unchanged, and still mean attendance.** 1.1 does not fix them; it stops the specification implying otherwise. If a badge in your course should mean a demonstrated capability, the objectives behind it are where the evidence has to come from.

## See also

[The learner record](the-learner-record.md) · [The homework mailbox](the-homework-mailbox.md) · [The delivery loop](the-delivery-loop.md)
