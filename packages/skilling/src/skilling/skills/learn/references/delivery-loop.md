# Delivery loop — learn

Every learner turn is one `skilling` verb, one JSON envelope back, and — when the envelope
puts you at a gate — one open wait for the learner before you call anything else. Every
example below assumes you already resolved `--course <path>` (see
`course-resolution.md`) and are passing the same `--state`/`--learner` throughout.

## The beats, in order

`welcome → objectives → concept → gate-concept → exercise → gate-exercise → quiz →
[remediate →] complete → [ceremony →] done`

`exercise`/`gate-exercise` are skipped for a lesson that declares no exercise; `remediate`
only appears after a wrong quiz answer; `ceremony` only appears when the completed lesson was
the last in its phase. Never assume this shape yourself — the envelope's `beat.name` and
`legal_inputs` are the only authority on where the learner actually is and what they can do
next.

## `skilling next --course <path>`

Call it when unsure where things stand. It does not advance the lesson. First use may
initialize a record, and reading after an interrupted completion may finish its already
prepared writes. Reads of consistent existing state leave learner progress unchanged. Its
envelope:

```json
{
  "ok": true, "verb": "next",
  "course": {"id": "...", "title": "...", "version": "..."},
  "tutor": {"persona": "...", "tone": ["..."]},
  "position": {"phase": 0, "lesson": 1, "beat": null, "question_index": null},
  "beat": {"name": "welcome", "content": {"coordinate": "0.1", "title": "..."}},
  "legal_inputs": ["next"],
  "revision": "...", "completed_count": 0, "lesson_count": 3
}
```

`tutor` is absent from the envelope entirely when the manifest declares no persona — not
present with a null value, simply not a key — use a plain, neutral voice then, never an
invented one. `beat.content` is exactly what that beat needs to present (objectives text,
concept body, the open quiz question, and so on) — nothing speculative beyond it, so there is
nothing to look ahead at even if you wanted to.

## `skilling advance --course <path> --input <input>`

Applies exactly one transition and persists the result. `--input` must be one of the
envelope's own `legal_inputs` — never guess one, and never call `advance` to "help the
learner along" before they have actually done what the current beat asked for:

| Beat | Legal inputs | What they mean |
|---|---|---|
| `welcome`, `objectives`, `concept`, `exercise` | `next` | Acknowledge and move on — not a gate |
| `gate-concept` | `go-deeper`, `proceed` | Ask a follow-up (stays put, position unchanged) / move on |
| `gate-exercise` | `hint`, `attempted` | Ask for a hint (stays put) / the learner reports they tried |
| `quiz` | `answer-correct`, `answer-wrong` | Never call this directly — see the quiz verbs below |
| `remediate` | `continue`, `revisit-concept` | Move to the next question / go back to the concept |

`advance` refuses (exit 4, `illegal-transition`) once the beat reaches `complete` or
`ceremony` — those are finished by `skilling complete`/`skilling ceremony`, never by
`advance`, even though the machine models a `next` transition out of them too.

An optional `--key <token>` replays a successfully saved call's envelope without reapplying
it. It is not a general crash-recovery guarantee: interruption after the record write but
before scratch is saved can leave the key missing, so blindly retrying may advance again.
After an uncertain `advance`, call `next` and inspect the current beat before deciding what
the learner's input still authorizes. Do not manufacture a second input to compensate. This
remaining interruption gap is tracked in [#64](https://github.com/futureofdev/skilling/issues/64).

## Gates are open waits

When `next`/`advance` reports `gate-concept` or `gate-exercise`, stop. Ask the learner the
question the gate implies and wait for their actual reply — do not answer for them, do not
assume agreement from silence or enthusiasm, and do not call `advance` until they have
genuinely responded. A gate exists so a human decision happens exactly where the format put
one; skipping it is a violation even when you are confident what they would say, and there is
no timeout — a learner who returns in a fortnight finds the same gate waiting.

## The quiz verbs, specifically

Never read a lesson's quiz section yourself, at any point — the questions, their options,
and the correct label are withheld from every other verb precisely so the learner cannot
see them ahead of time and so you cannot accidentally reveal them. The loop:

1. `skilling quiz next --course <path>` — the open question only:
   ```json
   {"ok": true, "question": {"number": 1, "text": "...", "options": {"a": "...", "b": "..."}}}
   ```
   Nothing here reveals which option is correct, why, or even that the word "correct"
   applies to any of them.
2. Render it to the learner and collect their chosen label.
3. `skilling answer <label> --course <path>` — submits it and returns the verdict:
   ```json
   {"ok": true, "correct": false, "reason": "...",
    "remediation": {"offered": true, "objectives": ["..."]}}
   ```
   Relay `correct` and `reason` verbatim — do not soften a wrong answer or embellish a right
   one. If `remediation.objectives` names one, that is the objective the wrong answer
   implicates; center your re-explanation on it rather than re-presenting the whole concept
   from the top. `remediation.offered` mirrors `should_offer_revisit` — once the learner has
   missed two questions in this quiz, offer to revisit the concept before continuing, but the
   choice is theirs.
4. Repeat from step 1. `answer` itself advances the underlying beat (to the next question, to
   `remediate`, or — once feedback for the final question has been delivered — to
   `complete`); you do not call `advance` for any of this. Once `quiz next` refuses with
   `quiz-finished`, the quiz is done.

## Finishing a lesson

Once the envelope reports the `complete` beat, call `skilling complete --course <path>`. It
prepares the whole completion write set — log, streak, badges, homework placement or queue,
and completion scratch reset — before applying it. Reopening recovers a pending prepared
completion. A retry preserves the original completion time and uses its durable identity,
not the record's next-lesson position or completed-list order. This guarantee applies to new
journaled completions, not arbitrary earlier submissions or mid-lesson transitions.

Its envelope adds `already_completed`, `badges_awarded`, `phase_completed`, `homework_placed`,
and `homework_queued` to the current resume fields. Report newly awarded badges and placed or
queued homework, but do not announce fresh progress for an `already_completed` replay. Once
the next lesson has begun, an old receipt does not authorize completing it early.

If a call reports `recovery-required`, preserve the state and ask for inspection; never edit
or delete the journal, replay guessed transitions, or invent missing historical homework.
Old completed records can remain readable without evidence to reconstruct every old effect.
Completion recovery does not make confirmed homework submission interruption-safe: uncertain
submissions need inspection of the active slot and archive before another submission
([#63](https://github.com/futureofdev/skilling/issues/63)).

When `phase_completed` is true, call `skilling ceremony --course <path>` next for the
phase-boundary copy — `phase_name`, `phase_highlight`, and (if the course declares a brand)
`share_text`. State only what the envelope actually gives you; never invent a product name,
a URL, or a handle the ceremony content did not supply.

After completion (and ceremony, when there was one), call `skilling next` again for the
following lesson's `welcome` beat and keep going, or — when `completed_count` has reached
`lesson_count` — tell the learner the course itself is complete.
