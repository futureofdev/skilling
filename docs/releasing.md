# Releasing Skilling

This runbook prepares and publishes the `skilling` Python package and its companion brand
archive. A release owner and a different environment reviewer carry out the steps. The
workflow builds once, retains the result as `skilling-0.6.0-candidate`, and publishes those
same bytes after approval.

## Current release blockers

As observed on 18 September 2026, release execution remains blocked until an authorised
repository or package owner configures and reads back every item below:

- protect `main` and release tags matching `v*`, and enable immutable GitHub releases;
- create a protected `pypi` environment with a required reviewer other than the dispatcher;
- confirm the PyPI `skilling` project and owner roles;
- configure PyPI trusted publishing for owner `futureofdev`, repository `skilling`, workflow
  `release.yml`, environment `pypi`;
- merge the reviewed learner front door, including the final `brand/` sources, and complete
  the retained two-host candidate proof.

Repository settings are outside this workflow. Do not weaken the checks when a prerequisite
is absent. Obtain separate authorisation for a settings change and read the setting back
before recording it as ready.

## Preconditions and owners

The release owner selects an exact commit already at `main`. The candidate must contain
package version `0.6.0`, specification version `1.4.0-draft`, the reviewed
`examples/welcome-skilling` fixture, and the final brand source. Required CI must be green at
that commit and the tree must match the independently reviewed implementation head.

The environment reviewer checks the retained candidate identity and evidence before allowing
the `publish` job to obtain an OpenID Connect token. The workflow grants `id-token: write`
only to that job. The PyPI publisher identity must match the repository, workflow and `pypi`
environment listed above; no API token is used.

## Build and inspect the candidate

From the Actions page, select **Release candidate**, choose the `main` branch and enter the
full 40-character commit as `candidate_sha`. The workflow rejects any other selected ref,
any input that differs from the dispatch commit, and any commit that is not the current
`origin/main` tip. It verifies a clean tree, the frozen lock, all source gates, package
identity and both built distributions before assembling the handoff.

Download `skilling-0.6.0-candidate` from the completed build job. It has this fixed layout:

```text
dist/skilling-0.6.0-py3-none-any.whl
dist/skilling-0.6.0.tar.gz
github-release/skilling-brand-assets-v2.0.zip
SHA256SUMS
candidate.json
verification/package_smoke.py
verification/source_package_smoke.py
verification/import_package_probe.py
verification/resources.json
verification/welcome-skilling/
```

`SHA256SUMS` contains exactly the wheel, sdist and brand ZIP, sorted by candidate-relative
path, with lowercase SHA-256 and two spaces before each path. `candidate.json` binds the
package and specification versions to the full commit and tree. `resources.json` additionally
binds package metadata, console entry point, README and licence hashes, every installed
resource, skill/reference resources, distribution names, sizes and hashes, the three retained
controllers, and every Welcome fixture file. Verification rejects symlinks, path traversal or
any file or directory outside this fixed layout.

Before continuing, extract into an empty directory and run:

```sh
python tools/release_candidate.py verify --candidate CANDIDATE
cd CANDIDATE
sha256sum --check SHA256SUMS
```

On macOS, use `shasum -a 256 -c SHA256SUMS`. Record the workflow run/job, commit, tree,
filenames and hashes in the dated private strategy launch record. Inspection does not itself
authorise publication.

## Tag and approve publication

While the publish job waits at the protected `pypi` environment, create annotated tag
`v0.6.0` at the exact candidate commit using the repository's protected release process.
Read it back from the remote and compare the peeled commit with `candidate.json`. A missing,
wrong-version or differently pointed tag makes the publish job fail before it requests a PyPI
token.

The reviewer compares the pending job, downloaded artifact and recorded hashes. Approval lets
the workflow verify the complete handoff again from reviewed checkout code. It passes only
`candidate/dist/` to PyPI; `verification/` and `github-release/` are never package inputs.
The job does not execute a script downloaded in the candidate and never rebuilds an artifact.

## Create the GitHub release

After PyPI succeeds, create the immutable GitHub release for existing tag `v0.6.0` using
[the 0.6.0 notes](releases/0.6.0.md). Attach the exact retained file
`github-release/skilling-brand-assets-v2.0.zip`; do not run the brand generator again. Verify
the file against its `SHA256SUMS` row immediately before upload. Download the published
attachment into a new directory, hash it again, and compare it byte-for-byte with the retained
candidate. Record the GitHub release URL and readback hash.

## Read back the public release

Use a clean environment and read the package metadata from PyPI. Install exactly
`skilling==0.6.0`, verify `skilling --version`, and run the retained installed-package probe.
Confirm the PyPI wheel and sdist hashes match the retained candidate. Then verify the GitHub
tag, release attachment and a tag-pinned learner start command from two supported hosts.

## Failure and rerun rules

The candidate artifact is immutable. A failed source gate, missing brand source, checksum
error, identity mismatch or wrong tag stops the release. Fixing source creates a new reviewed
commit and requires a new workflow run, candidate, evidence set and two-host proof. Never
replace bytes under an existing artifact, tag or release.

A transient failure before publication may rerun the failed build only if it produces a new
candidate that is re-inspected and re-recorded. A transient publish failure may retry only
with the same retained artifact and after confirming PyPI does not already contain either
filename. PyPI filenames and versions are immutable; if partial publication occurred, stop
and follow PyPI recovery guidance rather than rebuilding `0.6.0`.
