# Branding the public GitHub repository

The public front door is learner-first: benefit, persistent installation, the pinned Welcome
course, then course sources and author material. The version-2 banner reflects that order.

## Assets

- README: `assets/github/readme-banner-light.png` and `readme-banner-dark.png` in a `<picture>`.
- Social preview: `assets/github/social-preview-1280x640.png`.
- Avatar: `assets/github/avatar-460.png` (or the Cloud tile variant).
- Badges: only the current files generated from `BADGES` in `build.py`.

The Cut is always Ink on a light field. The light banner uses the page as its field; the dark
banner carries a Build-lime tile. There is no white or reversed mark.

## Copy contract

The command-bearing source of truth is the repository README. It installs package `0.6.0`
persistently and starts `gh:futureofdev/skilling@v0.6.0#examples/welcome-skilling`. Brand copy
may say `skilling start · 0.5.0`, but must not advertise transient execution, the legacy text
walker as the learner route, an unpinned course, an old specification version or retired
licence/implementation badges.

Package publication and the immutable repository tag are required before the public route is
executable. Candidate screenshots or previews must be labelled as candidate evidence.

## Regeneration and review

Run the commands in [README.md](README.md), compare generated hashes, and inspect both GitHub
themes. Inspect the package long description separately: its banner URLs are absolute and
pinned, with the light `<img>` as the fallback. Do not commit `dist/` or `.DS_Store` files.
