# Homework workflows

Every call below assumes you already resolved `--course <path>` (see
`course-resolution.md`) and pass the same `--state`/`--learner` throughout.

## `skilling homework check --course <path>`

Read-only — never a write, not even scratch, so call it as often as you like. Returns the
active slot as-is:

```json
{"ok": true, "verb": "homework-check",
 "course": {"id": "...", "version": "..."},
 "active": {
   "coordinate": "1.2", "title": "Write Your Own Course",
   "objective": "Author a conforming two-lesson course and validate it.",
   "requirements": [{"text": "...", "verdict": null, "reason": ""}],
   "stretch_goals": [{"text": "...", "verdict": null, "reason": ""}],
   "submission": "Share the directory with your tutor.",
   "unlocked_at": "2026-08-05T14:31:07Z",
   "queued": []
 },
 "revision": "..."}
```

`active` is `null` when the slot is empty — nothing has unlocked a homework assignment yet.
`verdict` starts (and, through this verb alone, stays) `null`; `skilling` never fills it in.
`queued` lists any further assignments already waiting behind this one (a learner who
finished two phases back-to-back before submitting either).

## Display

Call `homework check`. If `active` is `null`, tell the learner plainly that nothing is active
right now and that finishing a phase is what unlocks one — do not invent an assignment.
Otherwise show `objective`, each `requirements`/`stretch_goals` entry's `text`, and
`submission` — the instructions for how to hand it in. Mention `queued` only if it is
non-empty, so the learner knows something is waiting behind the current assignment.

## Check (feedback, not completion)

Call `homework check` for the current requirements. Ask the learner to show or describe their
work, then **judge each requirement yourself** — met, partial, or not-yet, with a reason —
exactly the way a `practice` objective's evidence is gathered: look, don't take their word for
it, and say plainly if you cannot look this turn. Report stretch goals the same way, but never
let them gate anything.

This is entirely conversational. There is no verb that records a verdict — `skilling` never
computes or writes one, so your feedback here changes nothing about the slot's state, and you
can give it as many times as the learner asks. Make that explicit if it is not already clear:
telling the learner "this looks ready" is not the same as it being submitted, and only
`homework submit` changes anything durable.

## Submit

Submission requires the learner's confirmation as its **own, distinct** reply — never
inferred from a passing check, from enthusiasm, or from silence. Ask directly ("ready to
submit this?") and wait for an actual yes before calling anything.

On confirmation:

```
skilling homework submit --course <path>
# {"ok": true, "verb": "homework-submit", "course": {"id": "...", "version": "..."},
#  "archived": {"coordinate": "...", "title": "...", "requirements": [...],
#               "stretch_goals": [...], "submitted_at": "..."}}
```

This archives the assignment exactly as it stood (whatever, if anything, is in `verdict`/
`reason` — usually still `null`, since nothing upstream of this call writes them) and, if
anything was queued, loads it into the active slot. Idempotent: submitting an assignment
already archived is a no-op that returns the same archived result rather than duplicating it,
so a retry after an uncertain call is safe.

`no-homework` (exit 4) means there is nothing active or archived at all to submit — tell the
learner plainly rather than trying again with different arguments.
