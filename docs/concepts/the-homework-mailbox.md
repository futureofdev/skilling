# The homework mailbox

*Why there is exactly one slot, and why checking can never finish anything.*

Normative home: [runtime § the homework mailbox](../../spec/runtime.md#the-homework-mailbox).

## The shape

One slot per learner per course. It fills at a phase boundary, can be checked any number of times, and empties only on an explicitly confirmed submission. A second assignment queues behind the first rather than replacing it.

That is the entire mechanism. It is small on purpose.

## The load-bearing separation

**A check is feedback. A submit is completion. Nothing collapses the two.**

A check evaluates the work against the assignment's `- [ ]` requirements and reports on each one — `met`, `partial`, `not-yet`, with a reason. It does not change the slot, does not touch the completion log, and does not finish the assignment no matter how finished the work looks.

Why so absolute? Because a learner needs to be able to ask "how am I doing?" without risk. If a good check might submit their work, then asking becomes a gamble, and the learner who most needs feedback — the one who is unsure — is the one who stops asking for it.

The same reasoning makes submission require its own confirmation, distinct from the input that requested it. Not inferred from a passing check, not from enthusiasm, not from silence. This is [an open gate](open-gates.md) wearing different clothes.

## Per-requirement verdicts, not a grade

A check must report on each requirement separately. A single overall verdict — 70%, "nearly there", three stars — tells a learner nothing they can act on. "The semantic HTML is there, the alt text isn't yet" tells them what to do next, which is the only thing feedback is for.

This is also why the assignment grammar uses checkboxes. The `- [ ]` items are not formatting; they are the unit of feedback, and an author writing them is deciding what a tutor will report on.

## Why only one slot

Because two assignments in flight is a queue, a queue needs priorities, priorities need deadlines, and deadlines need policy — and the moment the runtime holds policy it has started becoming an LMS.

So the slot holds one thing. Multiple concurrent assignments, deadlines, reminders, grading workflows, resubmission rules: all of that is an adopter's business, built on the archive and the record. Built *on* the mailbox, never *into* it.

The queue that does exist is minimal and mechanical: if a phase ends while an assignment is still active, the new one waits rather than overwriting. Overwriting would silently destroy work a learner was in the middle of.

## Archives are immutable

A confirmed submission writes an archive entry — the assignment, its final verdicts, a timestamp — and archives are never rewritten. Retrying with the same checked-assignment token returns that original archive, even after
another assignment becomes active. A new assignment needs a new check and confirmation.
If the checked slot changes before submission is accepted, the old token conflicts.

That idempotence is not defensive coding. A learner on a flaky connection will retry, and a system that archives twice has invented work that never happened.

## Limits

The core can do all of the above and cannot check anything, because checking needs judgement about a learner's actual work. That is a runtime's job, and it is explicitly optional: a tutor that cannot judge displays the assignment and accepts a submission, and conforms. Pretending to check would be worse than declining to.

Nothing here verifies authorship either. Whether the learner did their own homework is outside what any format can promise, and [conformance says so plainly](../../spec/runtime.md#what-conformance-cannot-promise).

## See also

[Open gates](open-gates.md) · [Mechanism and policy](mechanism-and-policy.md)
