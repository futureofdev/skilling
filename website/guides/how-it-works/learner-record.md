---
title: The learner record
description: What Skilling saves about your learning, and why it doesn't need the chat.
---

# The learner record

Your progress is a small file in your workspace: the lessons you've finished, dates, a streak
and any badges. It never depends on the conversation that produced it.

## No transcript needed

If progress lived in a chat log, switching tutor would mean losing it. Change model, change
assistant, change job, and your history would be gone. So the record never needs message
history. Any tutor can pick it up and carry on.

## Nothing that can drift

The record doesn't store anything it can work out. Counts, percentages and "lesson 3 of 9" are
all calculated from the course manifest and the lessons you've completed. Numbers that are
written down in several places eventually disagree. Numbers that are calculated can't.

## An append-only log

Next to the record sits a completion log, with one entry per finished lesson. It's never
rewritten or reordered. If the record and the log ever disagree, the log wins, and the record
can be rebuilt from it. That also means you can always answer "when did I finish that lesson,
and on which version of the course?"

## What the record doesn't know

The record is deliberately thin. It can say you finished a lesson. It can't say how well you
understood it, and a quiz score never counts as proof that you've learned something. Objectives
are only marked as met when a tutor that can gather real evidence settles them.

Read the [design rationale](https://github.com/futureofdev/skilling/blob/main/docs/concepts/the-learner-record.md)
or the [runtime specification](/spec/runtime#the-progress-record).
