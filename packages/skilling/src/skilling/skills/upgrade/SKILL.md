---
name: upgrade
description: This skill should be used when a learner wants to update Skilling or a Skilling course — for example "upgrade", "is there a newer version", "update my course", "check for updates", "update skilling", or after the learn skill offers an upgrade because a course envelope carried an `upgrade` hint or a `version-mismatch` refusal. Asks before every network call or change, one multiple-choice question at a time, and applies a course upgrade only through `skilling upgrade --yes` after an explicit yes.
---

# upgrade — update Skilling and courses, with the learner's say-so

You help the learner pick up newer versions of two separate things: the Skilling tool itself,
and the course content in their workspace. Nothing here happens without asking first. Every
check touches the network and every upgrade changes something, so each one waits for the
learner's actual answer.

## What is in this skill

- `references/course-resolution.md` explains which course to check, before you call anything
  else.
- `references/reading-the-check.md` explains the fields `skilling upgrade --check --json`
  prints, and how to put them into plain words.

## How to ask

Ask **one question at a time**, as a multiple-choice question. When the host has a structured
question tool (a picker the learner clicks), use it. Otherwise write a short lettered list
(`a)`, `b)`) and wait for the reply. Keep the voice plain and friendly, with no jargon the
learner didn't use first. Never treat silence, "ok, what's next?", or a reply to a different
question as a yes.

## The rules that matter most

- Never upgrade anything without an explicit yes to that specific upgrade.
- Never edit, move or delete anything under `.skilling/`: no records, journals, manifests or
  cached courses. `skilling` is the only thing that writes there.
- Never delete progress, and never suggest deleting state by hand. When progress can't carry
  over, the learner stays on their current version until they choose otherwise, and you
  point them to the troubleshooting guidance rather than acting yourself.
- Report what the CLI printed. Don't guess versions, lesson counts or what changed.

## The flow

### 1. Skilling itself

Ask: "Shall I check for a newer version of Skilling?" a) Yes, check  b) Not now.

On yes:

1. Run `skilling --version` and tell the learner the version they have.
2. Run `uv tool upgrade skilling`. If uv says Skilling isn't installed as a uv tool, or `uv`
   isn't available, don't improvise an installer. Tell the learner how Skilling is meant to
   be installed (`uv tool install skilling`, from the Skilling README) and let them choose.
3. Run `skilling --version` again and say whether it changed.
4. Run `skilling install` from the workspace root. It refreshes the skills in this folder for
   both Claude Code and Codex.
5. Tell the learner to **start a new session** (reopen the workspace) so the updated skills
   load. Skills already loaded in this conversation stay the old ones until then.

### 2. Course updates

Ask: "Shall I check whether your course has an update?" a) Yes, check  b) Not now.

On yes, resolve the course (`references/course-resolution.md`), then run:

```
skilling upgrade --course <course-id> --check --json
```

Put the result into plain words using `references/reading-the-check.md`: the version they
have, the version on offer, what kind of change it is (a small fix, new lessons added, or a
restructure), and whether their progress carries over.

### 3. Offer the choice

When `status` is `available` or `pending` and `progress.status` is `carries-over` (or
`none`, when there is no progress yet), ask: a) Upgrade now  b) Not now.

When `progress.status` is `not-resumable`, an automatic upgrade is off the table. Ask:
a) Stay on my current version  b) Explain what starting fresh would mean. For b), explain
that the new version can't pick up where they left off, and that their current progress is
kept exactly as it is. Starting the new version fresh is a deliberate step covered by the
Skilling troubleshooting guidance. You don't take that step yourself, and you never delete
anything.

When `status` is `up-to-date`, `pinned` or `no-same-major`, say so plainly. If
`source.newer_major` is set, mention that a new major release exists and that progress
wouldn't carry over to it automatically. Then stop.

### 4. Apply, only on yes

On an explicit "Upgrade now":

```
skilling upgrade --course <course-id> --yes --json
```

Report the outcome: the new version, and that progress was rolled forward. Mention any
`dropped_objectives`, or a `lesson_restarted: true`, in plain words. If it refuses, relay the
message (see `references/reading-the-check.md`) and don't retry with different flags. Then
offer: a) Continue learning (hand over to the learn skill)  b) Stop here.

In ordinary workspace use, omit `--state` and use the default learner. If the session chose
an explicit `--state` or `--learner`, pass the same value on every call.
