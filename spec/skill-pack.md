# Skill pack

> How a Skilling course reaches a learner through a host's own Agent Skills mechanism —
> Claude Code, Codex, or any of the other hosts that read the generic convention — instead of
> through a bespoke chat integration. Read [runtime](runtime.md) first: a skill pack is one way
> to realise a [Conforming Runtime](README.md#conforming-runtime) and a
> [Conforming Producer](README.md#conforming-producer), not a second way to write learner state.

A skill pack is the set of Agent Skills an implementation ships so that a host's own
skill-invocation mechanism — `/name` in Claude Code, `$name` in the generic convention — can
drive a Skilling course. The host supplies the language model and the conversation; the skill
pack supplies the choreography; the `skilling` command line remains the only thing that ever
writes the learner's record. This page binds what makes that arrangement honest.

## Installed once per learner, not once per course

A skill pack is installed once, independent of how many courses a learner takes. Nothing about
a course — its id, its title, its phase names, its lesson count — is baked into a skill at
install time. A learner who starts a second course does not reinstall anything, and an upgrade
to the skill pack reaches every course a learner has, not just the one a pack happened to be
generated for.

This rules out generating a skill from a specific course's content. A skill pack's content is
fixed at the implementation's own release cadence, exactly like the CLI it drives — not at
course-authoring time.

## No course-structure fact is ever baked in

Every fact a skill pack states about a specific course — its title, a lesson count, a phase
name, a learner's position — must be read from the CLI at the moment it is needed, never
authored into the skill's own files and never carried over from an earlier turn. This is the
same [no-authored-counts rule](course-format.md#derived-counts) applied to the delivery
interface itself: a skill pack that states a count from memory can drift from the manifest in
exactly the way this format exists to prevent.

Course identity and persona are resolved the same way, at invocation time:

- **Which course.** A skill pack does not maintain a registry mapping a course name to its
  content. When the learner names a course, the skill pack resolves it fresh through the CLI's
  own course resolution (fetching it if it is not local). When they do not, it asks the CLI
  which courses this learner has touched before and defaults to the most recently active one,
  asking the learner to choose only when two or more genuinely tie.
- **Persona and tone.** A course may declare a `tutor` persona in its manifest. A skill pack
  adopts it by reading it back from the CLI at the start of each session — never by writing a
  persona into the skill's own content, and never by inventing one for a course that declared
  none.

## Course enumeration

A skill pack needs a way to answer "which courses has this learner touched, and which one most
recently" without being handed a course explicitly — the mechanism a per-course pack never
needed, because it was always handed exactly one course. This is a read-only enumeration over
the learner's local state: every course with a progress record, most-recently-active first,
each reporting an id, a display title, and the calendar date it was last touched.

The title is resolved on a best-effort basis — from wherever the course's content can still be
found, falling back to the id itself when it cannot — and is not authoritative; a skill pack
must not treat a fallen-back title as license to invent a nicer one. The enumeration reports no
path and no version: it answers *which* course to resume, never *where* its content lives.
Resolving a location for a chosen id remains the same course resolution described above.

Two or more courses tied on the same calendar date is a genuine tie, not a rounding artifact —
a skill pack must list the candidates and ask rather than picking one for the learner. An empty
enumeration is a normal empty state, meaning nothing has ever been delivered to this learner —
not a failure to report as one.

## The Agent Skills floor

A skill's frontmatter carries exactly two keys, within the constraints every Agent Skills host
enforces: `name`, lowercase kebab-case, 1–64 characters, and `description`, non-empty, at most
1024 characters. A third key, an undersized or oversized name or description, or a name outside
kebab-case is not a richer skill — it is one a stricter host refuses to load at all. This is the
portable minimum; everything else about a skill's content is free.

A skill's files are its `SKILL.md` plus zero or more `references/*.md` files beside it, each one
linked from `SKILL.md` — an unlinked reference is dead content a host has no path to.

## Two host conventions

No single directory is read by both major Agent Skills conventions, so a skill pack targets
both by default:

| Convention | Skills live at | A learner invokes one as |
|---|---|---|
| Claude Code | `.claude/skills/<name>/` | `/<name>` |
| Generic Agent Skills (Codex and others) | `.agents/skills/<name>/` | `$<name>` |

Installing writes into a learner's home profile by default, or into a project directory instead
— to be committed alongside a course repository — when asked for a repo-local install. Both are
legitimate; a repo-local install is how a course maintainer ships the pack alongside the course
itself rather than asking every learner to install it separately.

## Installing and removing

Installing writes every file the skill pack ships, verbatim, and records a receipt of exactly
what was written — the relative paths and a content hash of each. Reinstalling upgrades an
already-installed copy in place: the same relative paths are written again, nothing stale from
an older release is left behind, and a hand-edited file is silently overwritten, exactly as a
reinstall of any other software overwrites what it manages.

Removal is the receipt read backwards, and it is atomic across the whole pack: if any receipted
file anywhere in the pack has changed since it was installed, nothing is removed anywhere — not
even from a skill that was itself untouched. A learner never ends up with some skills removed
and one left dangling because of an edit to a different skill. A file that is not on the receipt
— something a learner or another tool put there — is never touched by either installing or
removing.

## What this page does not bind

**The exact wording of a skill's choreography.** Exactly as [runtime](runtime.md) binds
transitions and never prose, this page binds the properties above and never the sentences a
skill's `SKILL.md` or `references/*.md` use to state them. Two skill packs can satisfy every
rule on this page while reading nothing alike.

**How many skills a pack contains, or what they are named.** Nothing here requires a
`learn`/`progress`/`homework` split specifically — an implementation is free to ship one skill,
or a different division of labour, as long as every skill it ships satisfies the rules above.

**Whether a given host actually honours any of this.** The rules bind what a skill pack must
say and how it must behave when a host follows its instructions faithfully. Whether a real,
unmodified host does that is an empirical question this page cannot answer by itself — see
[implementations](../docs/implementations.md) for what has actually been run against a live
host, and what has not.
