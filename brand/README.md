# Skilling brand assets

**Version 2.0 · child of Future of Dev v1.0 · mark: The Cut**

Editable vectors, tokens, markup and `build.py` are the **source of truth** and are committed.
Rasters, the `.ico`, badge SVGs, contrast report and distributable zip are **derived**.
`build.py` regenerates them. Derived assets referenced by repository and package READMEs are
committed; only `dist/` is ignored.
`generated-sha256.json` records the regenerated public-asset hashes used by documentation
checks.

Everything below is the short version of the rules. The full specification document
(`skilling-brand-kit.html`) is listed under **Outstanding** at the bottom — it has not been
regenerated yet.

## Regenerating

```bash
# contrast report only — stdlib, no dependencies
uv run brand/build.py --only-report

# + geometry rasters: tiles, favicons, .ico, mark PNGs, avatar
uv run --with pillow brand/build.py

# + text-bearing assets: banners, social preview, masthead, badges
# (first run: uv run --with playwright playwright install chromium)
uv run --with pillow --with playwright brand/build.py --with-browser --zip

# regenerate in scratch space, compare public hashes, and scan the release ZIP
uv run --with pillow --with playwright brand/check.py
```

Pillow and Playwright are build-time tooling. They belong in a dependency group — never in
`packages/skilling` runtime deps.

The browser stage exists because those assets need real Archivo, and because badge padding is
*measured* rather than estimated. An SVG referenced through `<img>` cannot load a webfont, so
badges fall back to Verdana at 11px like shields.io, with widths measured in a real browser.

---

## The one rule you cannot break

**The Cut is always Ink on a light field.**

The mark covers 80.1% of its square. That mass is what gives it authority at 16px, and it is
also the constraint: in a mark this heavy, the channels *are* the counters. Reverse the colours
and the counters become the strokes — the letter does not degrade, it reads as a **mirrored S**.

This was tested at 16, 20, 24, 32, 48 and 180px, on Ink, Void and Signal fields, both bare and
inside a bounded tile. White-on-dark fails in every one of those cases, **including inside a
tile**. So there is no reversed lockup and no white mark in this pack — `FIELDS` in `build.py`
is that rule expressed in code. On light pages the page is the field; on dark pages the mark
brings its own as a tile.

| Surface | Use |
|---|---|
| White or Cloud page | `assets/mark/skilling-mark.svg` — bare Ink mark |
| Dark page, dark email, dark GitHub chrome | `assets/tiles/skilling-tile-build.svg` or `-cloud.svg` |
| One-ink print, embroidery, stamp | `assets/mark/skilling-mark-mono.svg` (inherits `currentColor`) |
| Anything below 16px | Don't. Use the wordmark alone. |

The tile is a 36 × 36 field with the 28 × 28 mark centred — 4 units of padding, the same width
as the channel, so the padding and the counters agree.

Note this is a real divergence from the parent, and it costs something: Future of Dev's mark
works bare on any surface and Skilling's does not. It also buys something. The Shift's Signal
quarter measures 3.36:1 on Ink and fails, which is why the parent has to swap it for lime in
dark mode. The Cut has no second colour and therefore no such defect.

---

## What's here

```
assets/
  mark/      The symbol. Font-independent vector. + construction reference.
  tiles/     The mark on its field, for dark surfaces.
  icons/     20 glyphs as one sprite, 24x24, 2px stroke, currentColor.
  favicon/   favicon.svg + webmanifest (PNGs and .ico are derived).
  github/    README snippet (avatar, banners, social preview, badges are derived).
  email/     Masthead markup (PNGs are derived).
  tokens/    CSS, SCSS, JSON + the contrast report.
build.py     Regenerates everything derived.
```

### A note on the wordmark

The **symbol** is pure geometry with no font dependency. Text-bearing generated assets use
Archivo 800 at width 112, rendered into the README banners, social preview and email masthead.
Standalone symbol-plus-wordmark lockups are not yet part of this pack; do not infer them from
those composite images.

Archivo, Inter and JetBrains Mono are open-licensed build inputs. A browser is used during
generation so their measured rendering is baked into the committed images.

---

## GitHub

See `assets/github/README-snippet.md` for copy-paste markdown.

| Asset | Where it goes |
|---|---|
| `avatar-460.png` | Organisation / repository avatar |
| `social-preview-1280x640.png` | Settings → Social preview (GitHub requires 1280×640) |
| `readme-banner-light.png` / `-dark.png` | Top of README, via a `<picture>` element |
| `badges/*.svg` | Under the banner |

**Use the tile for the avatar, never the bare mark** — GitHub renders avatars against both
light and dark chrome, and a transparent Cut inverts.

`badges/built-with-skilling.svg` is for third parties; encourage course authors and runtime
implementers to put it in their own READMEs.

---

## Email

The masthead ships as a **flat PNG of the Build-lime tile lockup**. Never inline SVG, never a
transparent PNG. Gmail and Outlook invert colours without asking; they do not invert images, so
a PNG on a lime field is the only version that survives a subscriber's dark mode intact. Always
set `alt="Skilling"` so a stripped image still says the name.

---

## Tokens

`assets/tokens/skilling-tokens.css` is the source of truth. Prefixed `--sk-` so Skilling and
Future of Dev tokens can coexist in one stylesheet — a real requirement, since the newsletter
renders course cards inside its own pages.

Two things to know before using the palette:

1. **Not one hex value is forked from the parent.** The core six and the inherited extensions
   are byte-identical to Future of Dev v1.0. What differs is what each colour is *for*.
2. **`--sk-graphite-deep` exists because the inherited Graphite fails.** Graphite on Cloud
   measures 4.43:1 — below AA for small text. That barely shows in the parent brand and shows
   constantly in Skilling, where captions sit on Cloud panels all day. When in doubt use
   Graphite Deep: it passes on white *and* Cloud.

### Colour meanings

| Colour | Means |
|---|---|
| **Ink** `#111827` | Type, the mark, authority, specification surfaces |
| **Signal** `#4355FF` | Links, navigation, system actions, runtime compatibility |
| **Build** `#C8FF3D` | Learner action and completed evidence — nothing else. Plus the tile field. |
| **Cloud** `#F3F5F8` | Learning cards, technical panels, the mark's field on dark |
| **Accent** `#42D7FF` | Diagrams only. Never a CTA, never a state. |
| **Base** `#FFFFFF` | Reading space, and the mark's default field |

Build lime is the one to be careful with. It marks *the learner did something* — a practice
step, a build brief, a demonstrated outcome, progress. It does not mark premium, featured or
new, and it never marks conformance. If lime appears on a course card before the learner has
done anything, the card is lying.

---

## Non-negotiables

- Border radius is zero everywhere.
- Both channels are 4 units deep and 20 long. Always.
- The mark is Ink on a light field. No reversed version exists.
- The mark never substitutes for a letter — it reads as "killing" in the wordmark.
- The mark never shows progress. That lives in the four-stage bar.
- The extension is `.skilling` — lowercase, dotted, in mono, forever.
- Conformance and quality never share a shape, a colour or a container.
- Compatibility claims always carry a tested date.
- The Future of Dev mark never appears larger than Skilling's, and never on a specification page.

---

## Outstanding

This pack was rebuilt after the previous copy was lost. Sources, rasters and badges are
regenerable: every PNG opens, every SVG parses, the mark path is shared by the files that carry
it, and no white-mark asset exists. The release ZIP is generated rather than committed. Two
things are still outstanding:

| Missing | How to get it |
|---|---|
| `skilling-brand-kit.html` — the full spec document | Needs rewriting; ask and it is regenerated |
| `assets/lockups/` — symbol + wordmark SVGs and PNGs | Needs adding to `build.py`. Geometry must be read back from the DOM rather than computed by hand: `getBBox` on SVG text returns line-box bounds, not ink bounds, which is how the first attempt got the stacked lockup's spacing wrong. |

`assets/icons/` ships as one sprite rather than 20 separate files. Splitting it is a small
addition to `build.py` if you want them individually.

## Provenance

Skilling, created by Future of Dev. The Cut is the parent's 28 × 28 square, in the same
position on the same 32 × 32 canvas, with the parent's own 4-unit channel driven through it
twice. Same square, same grid, same device, opposite verb: in The Shift a quarter leaves; in
The Cut nothing leaves — which is the ownership promise the format is built on.
