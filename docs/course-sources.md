# Course sources and cached snapshots

`skilling start REF WORKSPACE` accepts an existing local course directory, a Git URL, or
`gh:owner/repository[@branch-or-tag-or-full-commit][#course/subdirectory]`. Git uses your
configured authentication. A local directory is loaded directly by the resolver; remote
courses are fetched, validated, and copied into the cache before they are returned.

A remote ref is a **cached snapshot**. The first successful resolution records the requested
pin/subdirectory and full resolved Git commit. Repeating that exact ref verifies the local
payload and uses it without contacting the remote. Moving a branch upstream does not update
an existing snapshot. Use a separate workspace/cache to try a different revision of the same
course version; authors should change the course version when changing its content.

The standalone resolver uses `~/.skilling/courses`, or `SKILLING_CACHE_DIR` when set. Workspace
acquisition uses `.skilling/courses`. Both retain the portable `<id>@<version>` directory
layout. Returned course, phase, lesson and resource paths all point into durable content.

## Content identity and conflicts

An id/version identifies a directory, not proof that two repositories contain the same
course. The resolver compares sorted relative paths, directory/file kinds, executable intent
from Git, and file bytes. Empty files and directories contribute to identity; Git administrative
files do not. Equivalent payloads may share a directory with distinct verified source records.
Different payloads claiming the same id/version raise `CacheConflict` without replacing the
existing content or remembering the conflicting ref.

Every cache hit verifies its payload digest and loaded course id/version. Missing or modified
content, corrupt metadata, and symlink/reparse/special-file payloads refuse with `CacheInvalid`.
Preserve the old cache and use a separate one when investigating. Executable intent is stored
independently of Windows checkout mode bits. POSIX caches also check actual executable bits;
a transfer that loses them refuses instead of silently accepting changed intent.

The private `.index.json` is versioned metadata, not a public interchange format. It stores
SHA-256 digests of exact input refs as lookup keys and sanitized display provenance: URL
credentials and query values are omitted, while ordinary SSH usernames remain. The cached
payload excludes `.git`, including clone configuration. Resolver diagnostics omit transport
credentials. `ResolvedSource.ref` still returns the exact input to its caller. These cache
guarantees do not rewrite existing workspace manifests or other caller-owned copies of refs.

## Interrupted and concurrent acquisition

Network fetches happen outside one persistent `.cache.lock`. Cooperating publishers serialize
the final comparison, content publication and atomic index replacement. A busy cache produces
`CacheBusy` after a bounded wait; the lock file's existence is not evidence of ownership.

The resolver stages a validated copy beside the cache on the same filesystem. Under the lock
it first reserves content identity in the index, then renames the directory, then binds the
requested ref in a second atomic index write. Reserving identity before rename preserves Git
executable intent if the process dies on Windows. An unbound reservation without a directory
is never a hit and may be replaced by the next successful publisher. A directory without a
final ref binding is an orphan: a fresh fetch must match its reserved identity before adoption.
Interrupted index writes preserve prior source mappings. Retries do not implicitly replace an
existing verified directory.

These guarantees cover cooperating processes on a local filesystem and caught I/O failures
or process death. They do not promise safety against hostile concurrent path replacement,
moving a live cache, network filesystems, or power loss. Stop all writers before relocating
a cache; preserve file bytes and executable intent when moving between platforms.

## Legacy caches and deliberate replacement

Older indexes mapped raw refs directly to id/version directories. Those mappings have no
verified provenance. The first request for a legacy ref fetches that exact source and compares
its payload before adopting it. If the remote is unavailable, retry online or use the already
installed workspace course ID offline. A failed verification leaves old content intact.
Successful migration removes Git metadata from the adopted tree and hashes remaining legacy
lookup keys; each remaining ref still requires its own verification.
The verified content identity is reserved durably before old Git metadata is removed, so an
interruption during cleanup does not erase the only recoverable executable-intent evidence.

On Windows, an unversioned tree needs retained plain Git metadata to establish its previous
executable intent independently. Its index must contain stage-zero entries covering every
regular payload file. Without that evidence, remote adoption refuses with a
separate-cache remedy even when the visible bytes appear equivalent. POSIX can compare the
existing executable bits. A legacy checkout whose line endings differ from a fresh Git fetch
also conflicts: migration does not rewrite its files to make the comparison pass.

The Python `invalidate_cached_course(cache, course_id, version)` context manager is the narrow
integration seam for deliberate replacement. It forgets every verified binding, pending legacy
binding and content reservation for that key while holding the cache lock. A caller that also
needs a workspace lock must acquire the workspace lock first and replace content inside the
context. The helper never changes course files, manifests, or learner state; subsequent remote
resolution must verify any remaining content again.
On Windows, a plain tree left after invalidation or local replacement has no trusted prior
mode metadata and therefore cannot be adopted remotely in place. Use a separate cache for the
remote source. Already-installed workspace course-ID loading remains available offline.
