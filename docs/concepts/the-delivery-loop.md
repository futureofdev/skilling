# The delivery loop

*Why a lesson has a fixed anatomy, and why it isn't configurable.*

Normative home: [runtime § the delivery loop](../../spec/runtime.md#the-delivery-loop) and [course format § the section registry](../../spec/course-format.md#the-section-registry).

## The problem

A tutor delivering your course has never read it before and cannot ask you what you meant. It has a lesson file and nothing else — no author on hand, no style guide, no follow-up questions.

So the lesson's shape has to be knowable without asking. Not conventionally, not usually — always, in every course, including the one written last night by someone who has never read this page.

That is the whole reason the section list is fixed and the headings are exact. Not tidiness. A tutor knows there is a concept to teach and a quiz to ask because *every* lesson has one.

## What configurability would actually cost

A pluggable anatomy sounds generous, and it moves the guessing rather than removing it. Each course would teach the tutor a new shape, and a tutor that must infer shape will infer wrongly some of the time — usually on the lesson where it matters, silently, at delivery.

The originating course showed the cheap version of this failure. Twenty-four of its sixty-four lessons had no exercise, and nobody had decided that; it just accumulated. The tutor, finding no exercise, helpfully improvised one. Every learner got a different course, and no two of them could compare notes on the same material.

The format's answer is not "always have an exercise". It is [declare the absence](../../spec/course-format.md#declared-absence): absence is fine, and undeclared absence is the defect, because a reader — human or tutor — must be able to tell a decision from an oversight.

## Sections become beats

Each section becomes one delivered step:

| Section | Beat |
|---|---|
| — | welcome |
| `## Learning Objectives` | objectives |
| `## The Concept`, `## Key Terms` | concept |
| `## Hands-On Exercise` | exercise |
| `## Quick Quiz` | quiz |
| `## Next Up` | completion |

Ordering is the section registry's ordering. This is why `## The Concept` carries so much weight: a tutor re-presents it when a learner asks to go deeper, and again on a wrong answer. A thin concept section is a lesson that cannot be taught twice, and being taught twice is most of what tutoring is.

## What the loop deliberately does not decide

The loop fixes *when* things happen, and says nothing about what they say. Persona, warmth, analogies, how a re-explanation differs from the first explanation — all yours. You cannot require a language model to teach well; you can require the machinery around it to be correct, and that is [exactly the line conformance draws](../../spec/runtime.md#scope-of-conformance).

## Limits

A fixed anatomy is a real constraint, and it will fit some material badly. A course that wants five reading sections and no quiz cannot be a Skilling course. That is a deliberate trade: the format buys tutor portability with authoring flexibility, and if your material genuinely needs a different shape, this is the wrong format rather than a format to fight.

Three quiz questions and four options are likewise fixed, and the number is not defensible on pedagogical grounds — it is defensible on interoperability grounds. It was validated in one real course, and it is the same in every course so that a runtime, a validator, and a learner all expect the same thing.

## See also

[Open gates](open-gates.md) · [Mechanism and policy](mechanism-and-policy.md)
