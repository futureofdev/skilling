# GitHub README snippet

The repository README uses the version-2 light/dark banners directly from this tree:

```html
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/assets/github/readme-banner-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="brand/assets/github/readme-banner-light.png">
    <img alt="Skilling — learn one-to-one with Claude Code or Codex"
         src="brand/assets/github/readme-banner-light.png" width="100%">
  </picture>
</p>
```

The package README uses the same paths as absolute raw-GitHub URLs pinned to `v0.5.0`, because
PyPI renders it outside the repository. The `<img>` light banner is the fallback when a
renderer ignores `<picture>` or `<source>`.

Current badges live under `assets/github/badges/`. They state specification 1.4.0-draft,
Apache-2.0 code licence, CC BY 4.0 specification text, zero independent implementations,
self-certified conformance and the model-free reference runtime. Do not restore retired badge
filenames or claims.

Use `avatar-460.png` or `avatar-460-cloud.png` for an avatar and
`social-preview-1280x640.png` for GitHub's social preview. The avatar must use a tile: a bare
transparent mark is not valid on dark chrome.
