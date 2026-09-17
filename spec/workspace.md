# Workspace

> One folder a learner opens in any Agent-Skills host — Claude Code, Codex, Claude Cowork,
> ChatGPT Work — holding everything a tutored course needs: the machinery hidden under
> `.skilling/`, a visible root that grows with what the learner builds. Read
> [runtime](runtime.md) first: a workspace changes where state lives, never what gets written
> to it. In development alongside this wave; nothing on this page binds until an
> implementation has exercised it.

The [progress record](runtime.md#the-progress-record) already outlives any one runtime. A
workspace makes the same promise about a *folder*: a learner's state, the course content it
refers to, and the work they produced travel together — zipped, synced, or mounted into a
sandbox — and any conforming implementation finds all three in the same places.

## The layout

```
<workspace>/
├── CLAUDE.md                    # entry file, for hosts that read CLAUDE.md
├── AGENTS.md                    # entry file, for hosts that read AGENTS.md
├── .claude/skills/<name>/       # folder-scoped skill pack (Claude Code convention)
├── .agents/skills/<name>/       # folder-scoped skill pack (generic convention)
├── showcase/<course-id>/        # the only visible per-course output directory
└── .skilling/
    ├── workspace.yaml           # the manifest; what makes this folder a workspace
    ├── state/                   # a <state-root>, exactly per the file layout
    │   └── <course-id>/         #   record.yaml, completed.yaml, homework/…
    └── courses/                 # fetched course content
        └── <id>@<version>/      #   one directory per resolved course
```

Everything the machinery needs hides under `.skilling/`. The visible root holds only the
entry files, the skill directories the two host conventions require, and what the learner
builds — a workspace should look like the learner's folder, not like a tool's.

State and content are disjoint subtrees by construction: `state/<course-id>/` and
`courses/<id>@<version>/` can never name the same directory, so a course's progress and its
content never collide however the two are enumerated.

### The state root

`.skilling/state/` is a `<state-root>` exactly as [the file layout](runtime.md#the-file-layout)
specifies. Nothing about the record, the completion log, or the homework mailbox changes
because it sits inside a workspace: any conforming runtime or store reads and writes it
unchanged. A workspace re-points the layout; it does not fork it.

### Fetched content

`.skilling/courses/` holds course content, one directory per resolved course, named
`<id>@<version>`. That naming is what this page binds — it is what keeps content directories
disjoint from state. An implementation may keep a resolver index beside them; the index is its
own business and carries no meaning here.

An id/version alone is not proof that two fetched sources contain the same course. A resolver
that reuses a fetched directory must verify the source binding and content identity before
returning it. Different payloads claiming the same id/version must refuse without replacing
the existing directory or silently binding the new source to it. Equivalent payloads may share
the directory. A verified cached ref remains a snapshot; resolving it again does not implicitly
update a moving remote branch. An interrupted acquisition must not create a trusted source
binding to missing or unverified content. Private recovery/index representation remains an
implementation detail; the directory layout and installed-workspace loading stay unchanged.
When an existing unversioned or deliberately invalidated tree's prior executable intent
cannot be established independently, remote adoption must refuse rather than infer that
intent from the newly fetched source. On Windows this includes plain trees without retained
trusted Git mode metadata, even if their visible bytes match. Direct loading of already
installed workspace content remains available offline.

The reference implementation's comparison, legacy adoption and recovery behavior are described
in [course sources](../docs/course-sources.md).

## The manifest

`.skilling/workspace.yaml` is what makes a folder a workspace. It records, per course the
learner has added:

| Field | Meaning |
|---|---|
| `id` | The course id, as its own manifest declares it |
| `version` | The course version this workspace holds |
| `ref` | Source provenance — a local path, a `gh:` shorthand, or a URL with credentials and query secrets omitted |
| `path` | Where the content lives, relative to `.skilling/` |
| `showcase` | The course's visible output directory, relative to the workspace root |
| `added_at` | When the course was added to this workspace |

```yaml
# .skilling/workspace.yaml
courses:
  - id: hello-skilling
    version: "1.0.0"
    ref: gh:claudeacademy/hello-skilling
    path: courses/hello-skilling@1.0.0
    showcase: showcase/hello-skilling
    added_at: 2026-08-03T14:31:07Z
```

**Every path in the manifest is relative** — `path` to `.skilling/`, `showcase` to the
workspace root — and uses POSIX separators. A workspace gets zipped and synced into sandboxed
hosts; one absolute path in the manifest and the folder stops surviving the trip. `ref` is provenance rather than a location: it records the source, not where the content
is now. Newly persisted remote provenance omits URL credentials and query/fragment secrets;
ordinary SSH usernames may remain. Local paths and ordinary GitHub refs retain their spelling.
Existing manifests are not a credential-migration surface: exact recovery before-images can
contain historical secrets and must not be rewritten silently.

The manifest records exactly the fact that state alone never holds: a progress record names a
course id but never where that course's content lives. Within a workspace that question has a
durable answer, and it moves with the folder.

## Recoverable local imports

A local import publishes validated content and its manifest binding as one recoverable
operation. Cooperating starts and learner commands serialize on a persistent workspace lock;
discovery and content reads recover pending imports before exposing their content. The
reference implementation holds the lock through each learner command, including an interactive
delivery session. A competing start may time out while that session remains open.

Before replacing content, persist an intent containing the staged and prior content identities,
relative owned paths, and exact before/after manifest bytes. Preserve the prior valid copy until
the new content and manifest are committed. Recovery validates the complete intent and current
files before effects, then finishes publication when the validated replacement survives, or
restores a validated prior copy and its exact manifest. If neither result is provable, refuse
explicitly and preserve the copies for investigation. The existence of a lock file does not
mean a process owns its kernel lock.

Local replacement invalidates remote-cache bindings under the workspace-then-cache lock order.
Later remote resolution must independently verify source identity; workspace import metadata
is not trusted Git executable provenance. The Windows legacy-adoption refusal above still
applies. Entry files, skills, and showcase finishing steps follow durable publication and can
be rerun after a failure without deleting committed content or learner work.

These guarantees cover caught I/O failures and process death on a cooperating local filesystem.
They do not imply physical power-loss durability, hostile concurrent path protection, or
network-filesystem coordination. Stop all writers before moving a workspace. Pending recovery
metadata uses relative paths; legacy before-images retain their exact bytes. Unowned staging
leftovers are preserved, never guessed to be disposable.

## Discovery

Finding the enclosing workspace is git's model: walk up from the current directory until a
directory containing `.skilling/workspace.yaml` appears. The nearest one wins; reaching the
filesystem root without finding one means there is no workspace, which is a normal state and
not an error. The `SKILLING_WORKSPACE` environment variable, when set, overrides the *start
point* of the walk, not its answer — pointing it anywhere inside a workspace finds that
workspace's root.

Discovery keys on the manifest existing, or a pending import intent that first recovers its
manifest, never on a bare `.skilling/` directory. A stray
state directory from before workspaces existed — or any other tool's dot-directory that
happens to share the name — is not a workspace and must not be mistaken for one.

## Showcase

`showcase/<course-id>/` is the only visible per-course directory a workspace defines: where
the work a learner produces for a course accumulates, in the folder they can see, not under
the machinery. This page binds the location and nothing about what goes inside it.

## Artifacts

Since 1.4 the [progress record](runtime.md#the-progress-record) may carry an `artifacts`
list: pointers to work the learner built. Each entry names a `path` (workspace-relative,
POSIX separators), a `title`, the `coordinate` it was recorded at, and `added_at`.

Artifacts are recorded **only through the CLI**, at exactly two moments the loop already
owns: [phase ceremony](runtime.md#phase-boundary-ceremony) and confirmed
[homework submission](runtime.md#submit). A tutor never writes one on its own say-so, for the
same reason it never writes anything else around the runtime.

**Artifacts never gate the flow.** No beat waits on one, no completion requires one, and a
record with none is not a lesser record. They are pointers for a later reader — the learner,
a next tutor, whoever the learner shows the folder to — not a fourth kind of evidence.

Artifact recording defaults to the latest completed lesson in completion-log append order,
subject to [history validation and legacy fallback](runtime.md#the-completion-log).
`artifact add --coordinate` selects a known completed lesson explicitly; it cannot bypass
invalid history. A record's completed-array ordering and artifact write times never determine
completion chronology.

## Entry files

`CLAUDE.md` and `AGENTS.md` at the workspace root are how a host that reads such files learns
what this folder is. An implementation maintains its contribution inside marked blocks:

```markdown
<!-- skilling:workspace -->
…maintained by the implementation…
<!-- /skilling:workspace -->
```

Writing is create-or-grow: the file is created when absent, and only the content between the
implementation's own markers is rewritten when present. **Foreign content outside the markers
is never touched** — the [receipt philosophy](skill-pack.md#installing-and-removing) applied
to documents: touch exactly what you wrote, and nothing you did not.

## Folder-scoped skill installs

Within a workspace, the [skill pack](skill-pack.md) installs into the workspace's own
`.claude/skills/` and `.agents/skills/` by default, receipted exactly as
[installing and removing](skill-pack.md#installing-and-removing) binds — the learner's home
profile is the opt-in, not the default. A pack in the folder travels with the folder, which
is the point: a sandboxed host that mounts the workspace gets the skills with it, where a
home-profile install can never follow.

## What this page does not bind

**Host behaviour.** Whether a given host reads `CLAUDE.md` or `AGENTS.md`, loads a
folder-scoped skill, or honours any of this at all is an empirical question — see
[implementations](../docs/implementations.md) for what has actually been run against a live
host, exactly as [skill pack](skill-pack.md#what-this-page-does-not-bind) already treats it.

**Artifact content.** What an artifact *is* — a file, a directory, a deployed thing's local
copy — and whether it is any good. The record holds a pointer and a title, never a judgement;
judgements about work belong to [homework verdicts](runtime.md#check), which have rules.

**Showcase substructure.** How work is arranged inside `showcase/<course-id>/` is between the
course and the learner.
