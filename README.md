<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/assets/github/readme-banner-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="brand/assets/github/readme-banner-light.png">
    <img alt="Skilling — learn one-to-one with Claude Code or Codex" src="brand/assets/github/readme-banner-light.png" width="100%">
  </picture>
</p>

# Skilling

Learn through a portable course in **Claude Code or Codex**. Skilling keeps the course,
progress and work in one folder, so you can stop, resume and move your learning workspace
without tying it to one tutor.

## Start learning

Already have [Git](https://git-scm.com/downloads),
[uv](https://docs.astral.sh/uv/getting-started/installation/) and Claude Code or Codex?
Paste this prompt into your coding host:

> Check that Git and uv are available. If either is missing, stop and show me the matching
> official installation instructions linked from the Skilling README. Install Skilling
> persistently with `uv tool install skilling`, then run `skilling --version` in the
> same environment. Run
> `skilling start 'gh:futureofdev/skilling@v0.6.0#examples/welcome-skilling' my-learning --json`.
> Use the returned workspace path, read its generated host instructions and installed learn
> skill and references, run learner commands from that workspace, and start teaching me. Wait
> for my real replies at every gate. If this host must be reopened to discover the installed
> skills, tell me the exact workspace to open and to invoke `/learn` in Claude Code or `$learn`
> in Codex.

Skilling itself has no language-model dependency. Your chosen host supplies the model and has
its own account and network requirements.

### Terminal route

Run the same setup yourself:

```bash
uv tool install skilling
skilling --version
skilling start 'gh:futureofdev/skilling@v0.6.0#examples/welcome-skilling' my-learning --json
```

Then open the returned `workspace` in Claude Code or Codex. Use `/learn` in Claude Code or
`$learn` in Codex. If the host was already open, reopen that exact folder so it discovers the
new folder-scoped skills.

> [!NOTE]
> The pinned example command works once the `v0.6.0` tag is published. Before then, maintainers
> test the same flow with the retained candidate wheel and an exact commit ref; that
> substitution is not the public learner route.

Next: [learn how the workspace behaves](docs/learning-a-course.md),
[choose another course source](docs/course-sources.md), or
[solve setup problems](docs/troubleshooting.md).

## What stays yours

- **The course:** a validated snapshot is copied into the workspace.
- **The record:** progress, homework and evidence live under the workspace's `.skilling/`
  machinery rather than in a chat transcript.
- **Your work:** visible learner output belongs under `showcase/` and moves with the workspace.
- **Your choice of tutor:** the same workspace installs instructions for Claude Code and Codex.

After setup, the CLI, cached course content and learner state work locally. A cloud-hosted model
may still need its normal network access; Skilling does not make the model offline.

## Find a course

The [Welcome to Skilling](examples/welcome-skilling/) course is the shortest orientation.
The [examples index](examples/README.md) also explains `hello-skilling`, which teaches the
format, and `workbench`, which gives you practical shell and Git exercises.

Course sources may be a GitHub repository or subdirectory pinned by tag or full commit, a
generic Git HTTPS/SSH repository root, or a local course directory. Private repositories use
your existing Git or `gh` credentials. See [Course sources](docs/course-sources.md) for exact
syntax, caching and update behaviour.

## Write a course

Authors can scaffold a course and validate it with the same persistent CLI:

```bash
skilling init my-course
skilling validate ./my-course --strict
```

Use the [authoring walkthrough](docs/authoring-a-course.md), then preview the result in a fresh
learner workspace before publishing a stable Git tag and a tested `skilling start` command.

## Reference implementation and specification

The `skilling` package is an **LLM-free** reference implementation: typed models, a loader,
validator, pure delivery state machine, progress store and learner CLI. It does not include an
agent framework, model or API key.

Specification **1.4.0-draft** is normative. Start with the
[specification index](spec/README.md), [course format](spec/course-format.md),
[runtime](spec/runtime.md), [workspace](spec/workspace.md), or
[implementation guide](docs/implementing-a-runtime.md). Known implementations and the limits
of their claims are listed in [docs/implementations.md](docs/implementations.md).

## Contributing and licence

See [CONTRIBUTING.md](CONTRIBUTING.md). Specification text under `spec/` is
[CC BY 4.0](spec/LICENSE); the reference implementation and other repository content are
[Apache-2.0](LICENSE).
