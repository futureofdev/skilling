# Course sources

`skilling start REF WORKSPACE` accepts a local course directory or a Git repository. It
validates the course, copies a portable snapshot into the learner workspace and records where
the snapshot came from.

## GitHub shorthand

Use GitHub shorthand for a repository root, optional tag/full commit, and optional course
subdirectory:

```text
gh:owner/repository
gh:owner/repository@v1.0.0
gh:owner/repository@0123456789abcdef0123456789abcdef01234567
gh:owner/repository@v1.0.0#courses/my-course
```

A release tag is readable and repeatable; a full commit is the strongest immutable pin.
An unpinned branch/default ref is allowed, but an existing cached snapshot does not update
automatically when that branch moves.

## Generic Git URLs

Generic URLs name a course at the repository root:

```text
https://example.com/team/course.git
ssh://git@example.com/team/course.git
git+ssh://git@example.com/team/course.git
```

Git also understands `file://` and `git://` transports. Generic URLs do **not** support the
GitHub shorthand's `@pin` or `#subdirectory` grammar. SCP-style `git@example.com:repo.git`
does not contain `://` and is not a supported Skilling ref.

## Local directories and downloaded archives

A local directory containing `course.yaml` is supported:

```bash
skilling start ../my-course my-learning --json
```

Skilling does not download ZIP archives directly. Download and safely extract an archive
yourself, then pass the extracted course directory as a local source.

## Private repositories

Remote acquisition uses Git and therefore the credentials already configured for the same
URL: for example the Git credential manager, an SSH agent, or authenticated `gh` setup.
Skilling does not define a second login flow. Do not put passwords or access tokens in course
refs; sanitized provenance deliberately removes URL credentials and query values.

## Snapshots, identity and updates

The first successful remote resolution records the requested ref, resolved Git commit and
course payload. Repeating the exact ref verifies and reuses that cached snapshot without
contacting the remote. Course content lives under a portable `<id>@<version>` directory.

Course id and version identify a directory, but are not proof that two repositories contain
the same bytes. If different payloads claim the same id/version, Skilling refuses the conflict
without overwriting the existing content. Missing or modified cached files are also refused.

There is no automatic update service. To use changed content, authors publish an appropriate
course version and learners start that new ref. Use a separate workspace/cache when comparing
different revisions that claim the same course version.

## Copies and offline use

`start` copies validated content into the workspace; later teaching does not read the author's
checkout. An installed workspace course remains available to local CLI commands when the
remote is unavailable. This means local tooling and state can work offline after setup. It
does not promise that a cloud-hosted tutor model works without network access.

Move the whole workspace to retain course content, state, installed skills and learner work.
For the learner workflow, see [Learn with Skilling](learning-a-course.md).
