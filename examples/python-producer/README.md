# Local browser producer

This installable reference app delivers **Welcome to Skilling** through the public
`FileSession` and conversational `SkillingRunner` APIs. It runs one learner and one explicit
workspace on loopback. It is an experimental local example; these sources do not publish a
package or provide multi-user hosting.

From a checkout, install the locked workspace and create a disposable learner workspace:

```sh
uv sync --frozen
uv run skilling start ./examples/welcome-skilling /absolute/path/to/learner-workspace --json
```

Select and install the provider SDK required by your model in the server environment; supply
credentials through that provider's server-side environment configuration. For example, install
`pydantic-ai-slim[openai]>=2.52.0,<2.53.0` for an OpenAI model. The model argument is explicit;
there is no default provider, key capture, or tracing setup.

```sh
uv pip install --python .venv/bin/python 'pydantic-ai-slim[openai]>=2.52.0,<2.53.0'
.venv/bin/skilling --version
.venv/bin/python -c 'import skilling, skilling_tutor, skilling_producer_example; print(skilling.__version__, skilling_tutor.__version__)'
```

Use the installed entry point directly after adding a producer-selected SDK: a later `uv sync`
may remove dependencies not declared in your own environment. On Windows, these environment
executables live under `.venv/Scripts/` instead of `.venv/bin/`. Provider credentials remain in
the server environment; never paste them into chat or the note.

```sh
/absolute/path/to/skilling/.venv/bin/skilling-producer-example serve \
  --workspace /absolute/path/to/learner-workspace --course welcome-skilling \
  --model openai:YOUR_MODEL --host 127.0.0.1 --port 8765
```

Open <http://127.0.0.1:8765>. Startup validates configuration without requesting a model response.
Use the conversation for explanations, hints, informal feedback and course progression.
Say “continue” to apply the current legal transition first, then hear the tutor explain the
new material. Other choices can use the tutor’s current legal-control recommendation, applied
after its reply renders. Normal teaching presentation
continues automatically, with at most four tutor turns per learner message. Further gate
choices and quiz answers require a new learner response. Canonical quiz feedback comes from Skilling and must be
rendered before acknowledgement permits continuation. A failed model response does not undo a
committed action; refresh the state and retry conversation separately.

The note textarea saves the learner's exact UTF-8 Markdown to
`showcase/welcome-skilling/goal.md`. Include your own Goal, Takeaway and Next action, then inspect
and request review. Objective confirmation is a separate authorship/review action. After the
lesson, update the note with what changed, provide actual evidence for every homework requirement,
request feedback and separately confirm submission. Optional artifact registration records a
relative pointer to that note. Informal displayed advice is not a score or certification; the
archived assignment's null verdicts do not preserve the displayed advice.

Conversation, unrendered progression recommendations and outstanding review state are memory-only. Restarting discards them while the
file runtime retains committed progress and pending canonical feedback. Supply fresh evidence
for reviews after restart. The ordinary installed `skilling next`, `progress`, `homework check`
and `artifact list` commands read the same workspace, including from nested directories. Stop
all writers before relocating the workspace; restart with its new explicit absolute path.

The browser never receives provider credentials or homework tokens. Cookie/session, CSRF,
Host/Origin validation and plain text rendering protect this loopback example. Do not expose
it as a network service.

Workspace filesystem permissions remain the host boundary. The note rejects symlinks and
checks containment and file identity before saving. POSIX uses held directory descriptors;
Windows uses path prechecks and identity checks, which provide weaker protection against
concurrent filesystem changes. This example does not guarantee confinement against a local
actor who can rename workspace directories during an operation. Stop other writers before
moving the workspace.

Run source and DOM tests with `task test` (Node 20+ runs the dependency-free DOM tests).
`task package:tutor:smoke` builds the core/tutor wheel and sdist pairs, builds the app from a
copy outside the checkout and exercises its synthetic Welcome journey in fresh installed
environments. Synthetic tests disable real model calls; genuine learner/provider proof is
separate. See [the producer walkthrough](../../docs/python-producer.md) and
[the conversational adapter](../../docs/python-tutor.md).

Dependencies follow the current [FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/),
[testing guidance](https://fastapi.tiangolo.com/tutorial/testing/) and
[Uvicorn minimal installation](https://uvicorn.dev/installation/). FastAPI/Uvicorn belong to this
example, while HTTPX belongs to its test setup; neither is a core dependency.

Explicit “continue” from a rendered beat applies the current legal SDK transition before the tutor receives the resulting material. Tutoring progression uses chat; no advance buttons are shown. Gates still require the learner’s choice, and exercise attempts and quiz answers are never inferred from a generic continue.
