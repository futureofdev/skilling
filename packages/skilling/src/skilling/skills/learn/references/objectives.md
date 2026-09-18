# Objectives — learn

An objective is met when you — the host — have actual evidence for it, never because the
learner sounds confident or says they are done. `skilling objective settle` enforces this
mechanically (it refuses without the right capability and, for observed evidence, without
provenance); what makes the record trustworthy beyond that enforcement is you being honest
about what you actually checked.

## See what is open

```
skilling objective show --course <path> [--capability converse] [--capability observe] ...
# {"ok": true, "verb": "show", "course": {"id": "...", "version": "..."},
#  "objectives": [
#    {"id": "...", "kind": "knowledge", "verify": null, "check": null, "settleable_now": true},
#    {"id": "...", "kind": "practice", "verify": "...", "check": "...", "settleable_now": false}
#  ]}
```

Read-only. Pass `--capability` for every capability you genuinely hold this session so
`settleable_now` reflects reality; passing one you do not actually have makes the field lie
to you, not to `skilling`. Use the same course path, state root, and learner id as the active
delivery session. Read objective and verification facts only from this envelope; do not open
the lesson Markdown to discover them.

## `kind` decides how it can be settled at all

| `kind` | How you settle it | `--evidence` |
|---|---|---|
| `knowledge` | Judge the conversation yourself | `explained` |
| `practice` | Look, if you have `verify` and the capability to check it | `observed` |
| — | Follows from a homework verdict | `homework` |

**Knowledge.** Settle it only if the learner actually explained the idea back in their own
words in this conversation — not because they said "got it" or agreed when asked if they
understood. Judging that is the whole of the evidence; there is nothing else to inspect.

**Practice.** A `practice` objective with no `verify` sentence cannot be settled by
observation from outside at all — leave it alone unless a homework verdict gives you grounds
(`--evidence homework`). One with a `verify` sentence tells you what success looks like in
prose, not as a literal command; work out *how* to look yourself; you have the capability
to.

**Never** settle a `practice` objective on the learner's report that they did it. Look —
read the file, run the check, inspect the output, whatever `verify` implies — and only then
call `settle`, citing what you actually saw. If you cannot look this session, say so and
leave it open.

## `check` is a proposal, never silent

Some objectives carry a `check` — a literal command the course author suggests. It is a
suggestion, not an instruction: run it, if at all, through your host's own permission model,
and only after the learner knows it is about to happen. Declining it is fine; fall back to
looking some other way. `skilling` itself never executes `check` — it only prints it for you
to weigh.

## Settling it

```
skilling objective settle <objective-id> --course <path> \
  --evidence explained|observed|homework \
  [--attested-by <your-host-name>] [--checked "<what you actually inspected>"] \
  [--capability converse] [--capability observe] [--capability assess]
```

`--evidence observed` additionally requires `--attested-by` (who is making the claim —
`"claude-code"`, `"codex"`, and so on) and `--checked` (what you actually looked at, in your
own words — `"ran node --version, got v22.20.0"`, not a repeat of the objective's own
wording). `settle_objective` records `--checked` alongside the objective's own `verify`
sentence, verbatim, never a sentence you compose — the claim cannot be independently
verified, so what gets written down is exactly who attested to what, for a later reader to
weigh.

A successful call returns:

```json
{"ok": true, "verb": "settle", "course": {"id": "...", "version": "..."},
 "objective": {"id": "...", "evidence": "observed", "at": "2026-08-06",
                "provenance": {"checked": "...", "verify": "...", "attested_by": "..."}},
 "newly_met": true, "revision": "..."}
```

`newly_met` is `false` on a repeat settle of one already met — safe to call again without
double-recording anything.

## Refusals worth recognising

- `capability-missing` — you did not pass a `--capability` that settles this objective's
  kind. Do not add one you do not actually hold to make the call succeed; that is exactly the
  dishonesty this enforcement exists to prevent.
- `no-verify` — a `practice` objective with nothing to check against. There is nothing to
  observe here, ever, from any capability.
- `missing-provenance` — `--evidence observed` without both `--attested-by` and `--checked`.
- `objective-unknown` — the id does not belong to the current lesson; call `objective show`
  again rather than guessing one.

None of these are worth retrying with the same arguments — read `troubleshooting.md` before
trying anything else.
