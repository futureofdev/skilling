# Homework workflows

Every call below assumes you already resolved `--course <path>` (see
`course-resolution.md`) and pass the same `--state`/`--learner` throughout.

## `skilling homework check --course <path>`

Inspect the active slot without creating state or changing the assignment. A previously
accepted interrupted operation may finish recovery before the read. Repeated checks issue
no token files and return the same token while the slot is unchanged:

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
 "revision": "...", "submission_token": "..."}
```

`active` and `submission_token` are `null` when the slot is empty. Explain that there is
no active assignment; do not invent one or submit a previous archive.
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

Call `homework check`, display the assignment, and retain its exact `submission_token`.
The token identifies that assignment and checked revision; it is not proof of consent.

Submission requires the learner's confirmation as its **own, distinct** reply — never
inferred from a passing check, from enthusiasm, or from silence. Ask directly ("ready to
submit this?") and wait for an actual yes before calling anything.

On confirmation:

```
skilling homework submit --course <path> --token <the-retained-submission_token>
# {"ok": true, "verb": "homework-submit", "course": {"id": "...", "version": "..."},
#  "archived": {"coordinate": "...", "title": "...", "requirements": [...],
#               "stretch_goals": [...], "submitted_at": "..."}}
```

This archives the assignment exactly as it stood (whatever, if anything, is in `verdict`/
`reason` — usually still `null`, since nothing upstream of this call writes them) and, if
anything was queued, loads it into the active slot. Retry an uncertain call with the **same
retained token**: it returns the original archive, including its original timestamp and
verdicts, even the next day or after another assignment becomes active. It cannot submit
that next assignment. Never check again just to replace a retry token.

The submit response deliberately has no `showcase`. After a successful confirmed submit,
you may offer to register work the learner already created, but this is optional and never
gates submission. Combine only the `archived.coordinate` returned by this submit with the
workspace and `showcase` fact retained earlier from `start --json` or ceremony. If an
existing file is under that exact showcase directory, call:

```
skilling artifact add <existing-path> --title <learner-facing-title> \
  --course <path> --coordinate <archived.coordinate>
```

Pass the same `--state`/`--learner`. Do not expect `showcase` in the submit response, create
placeholder work, infer a location, or make artifact registration a condition of success.
When no retained workspace/showcase fact or existing file is available, skip it.

`conflict` (exit 3) means the checked slot changed before acceptance, including a verdict
or queue change. Check and display the new state, then ask for a new, distinct confirmation
before using its new token. Do not silently refresh the token and submit.

A missing, malformed, or wrong-stream token produces `invalid-submission-token` (exit 2)
before opening learner state. Preserve an uncertain call's token for retry; without it,
inspect current state and explain the uncertainty rather than guessing which archive or
assignment the learner intended. Corrupt recovery metadata requires inspection, not edits.
If the store is `store-busy`, wait for the other operation to finish and inspect again;
never delete lock/state files or replace the accepted token merely to force progress.
