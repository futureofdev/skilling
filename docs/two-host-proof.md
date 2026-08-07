# Two-host proof

The live verification that the [skill pack](../spec/skill-pack.md) actually works against a
real, unmodified Agent Skills host — not a test double, not a mocked model, not this
repository's own test runner pretending to be one. Everything the automated suite can check
(byte-equivalence between two delivery paths, every adversarial input a misbehaving host could
send, frontmatter shape, install/uninstall mechanics) is already covered by
`packages/skilling/tests/`. What it cannot check is whether a stock `codex` or Claude Code
session, reading only the bundled `SKILL.md`/`references/*.md` files and driving nothing but
the `skilling` command line, actually delivers a lesson the way the choreography says it will.
This document is the script for that run, and the place its result gets recorded.

**Status: NOT YET RUN — pending maintainer execution.** Every section below the falsifiability
criteria is instructions for a human to carry out with a real terminal, a real `codex`
installation, a real Claude Code installation, and a real private repository — none of which
this task had access to. Nothing in this file is a transcript, a completed record, or a
pass/fail claim. Sections that will eventually hold those are marked as placeholders, not
filled in with invented content, because a fabricated proof is a worse outcome than an honest
gap: it is exactly the failure mode this specification's provenance rules
([`objectives_met.provenance`](../spec/runtime.md#objectives-and-the-record)) exist to prevent
everywhere else, and this document would be a poor advertisement for that principle if it broke
the same rule about itself.

## Falsifiability criteria

Decided here, before any run, so a favourable-looking transcript cannot retroactively redefine
what counts as passing:

- **A gate that opens without learner input fails the gate.** If the transcript shows
  `gate-concept` or `gate-exercise` resolved by anything other than the learner's own next
  message — the host answering for them, a default, a timeout — that gate has failed,
  regardless of what the rest of the session looks like.
- **An answer visible before the learner answers fails it.** If a quiz option's correctness,
  a later question, or an explanation appears in the host's output before the learner has
  submitted their own answer for the current question, the quiz has failed, regardless of
  whether the learner later answers correctly.
- **A record mutation not paired with a CLI invocation visible in the transcript fails it.**
  Every write to `record.yaml`, `completed.yaml`, or the homework mailbox must correspond to a
  `skilling` subcommand actually invoked in the session — `advance`, `complete`, `ceremony`,
  `objective settle`, `homework submit`. A record that changed between two checks with no
  matching command in the transcript means something wrote state outside the CLI, which is a
  failure independent of whether the resulting record looks correct.
- **A private-repo fetch that succeeds with no usable credentials present fails it.** The
  negative half of the credential-boundary check (below) must actually fail closed. If it
  succeeds anyway, something other than the runner's own git/gh authentication did the work,
  and that is a failure of the claim that Skilling never handles a credential itself.
- **An offline rerun that requires network access fails it.** If any step in the offline gate
  needs connectivity once course content and dependencies are already on disk, the "no account
  anywhere, works offline" claim is false.

A run that satisfies all five is what lets [`docs/implementations.md`](implementations.md)
move the bundled triad's row from "pending the two-host proof" to "shipped."

## Prerequisites

- `skilling` installed and on `PATH` (`uv run skilling` from a checkout of this repository, or
  an installed release once one is published).
- A real, unmodified `codex` CLI session and a real, unmodified Claude Code session — no system
  prompt edits, no pre-answered gates, no scripted input.
- A private GitHub repository the runner can access through their own `git`/`gh`
  authentication, containing a directory that validates as a Skilling course (a private mirror
  of `examples/hello-skilling` is enough).
- A way to disable outbound networking after content is on disk (turning off Wi-Fi is
  sufficient; a firewall rule works too).

## Step 1 — install the triad

```bash
cd /path/to/skilling            # a checkout of this repository
uv run skilling install
```

Confirm the printed output lists all three skills under both conventions
(`~/.claude/skills/{learn,progress,homework}/`, invoked `/learn` etc., and
`~/.agents/skills/{learn,progress,homework}/`, invoked `$learn` etc.) before starting either
host session.

## Step 2 — `hello-skilling` in Codex

```bash
codex
```

In the session, name the course directly by path so the first-ever session has no earlier
`fetch` to reuse (see [skill-pack.md](../spec/skill-pack.md#course-enumeration) — the
enumeration alone cannot resolve a location for a course never fetched before):

```
$learn deliver /path/to/skilling/examples/hello-skilling to me, starting from lesson 1.
```

Watch for, across the whole lesson:

- The persona/tone `hello-skilling`'s manifest declares (or a plain neutral voice, if it
  declares none) — adopted from `skilling next`'s envelope, never stated as if remembered.
- Both gates (`gate-concept`, `gate-exercise`) waiting for an actual reply — try answering a
  concept-gate follow-up ("go deeper") at least once before proceeding, to confirm position
  does not move.
- The quiz delivered one question at a time, with at least one deliberately wrong answer, to
  confirm remediation is offered and the reason given is real.
- A completion, and — since `hello-skilling` is three lessons in one phase — a ceremony at the
  end of it.

After the session, inspect the resulting record directly:

```bash
cat ~/.skilling/state/hello-skilling/record.yaml
```

and confirm `completed` matches what the transcript actually delivered, no more and no less.

## Step 3 — `coding-bootcamp`'s first practice objective, in Codex

The earliest structured objective in `examples/coding-bootcamp` that carries a `verify`
sentence is `create-and-remove-files` in phase 0, lesson 3
(`phases/phase-0-getting-started/lesson-03-navigating-the-filesystem.md`): *"A file the learner
created from the terminal exists, and one they removed is gone."*

Deliver `coding-bootcamp` far enough to reach that lesson (naming it the same way as Step 2),
then actually do what the objective asks — create a file from the terminal and remove it again
— before telling the host you have. A good prompt once you have:

```
I created a file from the terminal and then deleted it. Can you confirm that objective is met?
```

The host should look for itself (there is no other honest way to settle a `practice`
objective — see [objectives.md](../packages/skilling/src/skilling/skills/learn/references/objectives.md))
and, only after looking, call:

```bash
skilling objective settle create-and-remove-files --course /path/to/skilling/examples/coding-bootcamp \
  --evidence observed --attested-by codex \
  --checked "ran touch scratch.txt then rm scratch.txt; ls shows it is gone" \
  --capability observe
```

Confirm the resulting `objectives_met` entry in `record.yaml` carries a `provenance` block with
`checked`, `verify`, and `attested_by` — not just `evidence: observed` on its own.

Then the negative half, run directly (this half does not need the host's judgement — it is
checking that the CLI's own enforcement holds, live, against the same course and objective):

```bash
skilling objective settle create-and-remove-files --course /path/to/skilling/examples/coding-bootcamp \
  --evidence observed --attested-by codex --checked "looked" --capability converse
```

Confirm this exits `4` (`ILLEGAL`, `capability-missing`) and leaves the objective unsettled — a
runtime that only declared `converse` must not be able to settle a `practice` objective no
matter what it claims to have checked.

## Step 4 — `hello-skilling` in Claude Code

Repeat Step 2 in Claude Code, using the `/learn` slash-command convention instead of `$learn`:

```
/learn deliver /path/to/skilling/examples/hello-skilling to me, starting from lesson 1.
```

Same checklist as Step 2. The point of running it twice, in two independently-implemented
hosts, is that nothing in the choreography can be an accident of one host's particular
tool-calling quirks — if both hosts hold every gate open and never touch state outside the CLI,
that is evidence the choreography itself is doing the work, not one host's leniency.

## Step 5 — private-repo fetch, on the learner's own credentials

Positive: prove your own git/gh authentication is what makes this work.

```bash
skilling fetch gh:<owner>/<private-repo> --json
```

This should succeed and print the resolved `path`, using whatever `git`/`gh` credential setup
already exists on your machine — Skilling holds no credential of its own to have used instead.

Negative: prove it actually needed those credentials, by stripping them away and confirming the
identical command now fails.

```bash
GIT_CONFIG_NOSYSTEM=1 HOME=/tmp/empty skilling fetch gh:<owner>/<private-repo> --json
```

This should fail closed — no clone, no cache entry, a `GitFailed`-shaped refusal — because the
credential helpers, SSH keys, and `gh` auth state that made the positive case work all live
under the real `$HOME`, which this invocation does not have.

## Step 6 — offline rerun

With `coding-bootcamp` and `hello-skilling` already resolved once (so nothing below needs a
fresh fetch), disable networking, then:

```bash
uv run pytest packages/skilling/tests/test_equivalence.py packages/skilling/tests/test_adversarial_host.py
```

and deliver one more lesson by hand, in either host, through the installed triad exactly as in
Step 2 or 4 — fully offline, no account, no network call anywhere in the transcript.

## Recording the outcome

Once run, commit the resulting artifacts under `docs/two-host-proof/` (not under any state
root — these are records of a specific proof run, not a learner's live progress):

- `docs/two-host-proof/hello-skilling.codex.record.yaml`
- `docs/two-host-proof/hello-skilling.claude-code.record.yaml`
- `docs/two-host-proof/coding-bootcamp.objective.record.yaml`
- A transcript summary (not a full raw transcript, unless the maintainer wants to commit one)
  covering what each host actually said and did at every gate, quiz answer, and completion.

## Outcome

**NOT YET RUN — pending maintainer execution.**

| Falsifiability criterion | Result |
|---|---|
| Every gate opened only on real learner input | *pending* |
| No answer visible before the learner answered | *pending* |
| Every record mutation paired with a visible CLI call | *pending* |
| Private-repo fetch failed closed with no credentials present | *pending* |
| Offline rerun needed no network access | *pending* |

Once this run has actually happened, replace this table and the placeholders above with what
was actually observed, and update [`docs/implementations.md`](implementations.md)'s triad row
from "pending the two-host proof" to "shipped" — or, if something in the choreography did not
survive contact with a real host, record that honestly here and in
[`spec/CHANGELOG.md`](../spec/CHANGELOG.md) as an errata entry, exactly as every other gap this
specification has found in itself was recorded rather than quietly patched over.
