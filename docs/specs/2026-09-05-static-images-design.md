# sphinx-likec4 — static image rendering (2026-09-05)

Render LikeC4 views as static **PNG/JPG** images instead of iframes, selectable per directive, per
output format (Sphinx builder), or by built-in default. Makes non-HTML builds — LaTeX/PDF, epub —
carry the model content that today degrades to a plain-text stub. Extends the 2026-08-30 design;
everything there stays as is.

## Constraints that shape the design

- `likec4@1.59.2` exports `png` and `jpg` only (plus `json`/`drawio`). **No SVG/PDF export exists.**
  SVG is out of scope; it would require scraping the rendered viewer DOM.
- Export drives headless Chromium via Playwright (`likec4` pins `playwright@1.60.0`). No browser →
  no image. There is no server-side renderer: layout is Graphviz-in-WASM, pixels are browser-drawn.
- Sphinx's image collector runs while each document is *read* and requires the image file to exist
  then. Directives are read in the same phase, so images must exist **before reading starts** —
  i.e. be produced at `builder-inited`, like the viewer build. Consequence: export *all* views
  (which ids are referenced isn't known yet). Cost is bounded by content-hash caching.
- Verified: a `nodes.image` whose URI is a path relative to the document that escapes `srcdir`
  (`../../.doctrees/likec4/images-png/x.png`) passes the collector and is copied/embedded correctly
  by both the html (`_images/`) and latex builders, under `-W`.

## Interface

### Config

```python
likec4_render = {"latex": "jpg"}   # optional; key = builder.format, value = "iframe"|"png"|"jpg"|"text"
```

Resolution, most specific wins: directive `:render:` → `likec4_render[app.builder.format]` →
built-in default:

| builder                                                        | default  |
|----------------------------------------------------------------|----------|
| `format == "html"` (html, dirhtml, singlehtml…)                | `iframe` |
| `supported_image_types` non-empty (latex, epub, texinfo…)      | `png`    |
| otherwise (text, man, gettext, linkcheck, xml, dummy…)         | `text`   |

`text` is today's plain-text stub, and a `text`-mode build **never runs the image export**.
Existing users see no change: HTML stays iframe.

### Directive

```rst
.. likec4-view:: cloud-to-amazon
   :render: png          # preference, not a demand (see below)
   :width: 80%           # image-mode passthroughs: width, height, alt, align, scale
   :title: Cloud → Amazon
```

- `:render:` is a **preference**: the same `.rst` builds for HTML and PDF, so an option that errors
  under one builder and not the other is hostile. `iframe` requested on a builder that can't
  embed one → builder default. `png`/`jpg` under HTML → a static `<img>` (print-friendly pages).
- Image passthroughs are the docutils `image` directive's own options (`width`, `height`, `alt`,
  `align`, `scale`) — same validators, same names. `alt` defaults to `:title:`, which defaults to
  `LikeC4 view <id>` (unchanged). `:height:` keeps its iframe meaning and is passed to the image
  node when set in image mode.
- `:mode: sequence` (existing, dynamic views) is **ignored in image mode**: the CLI's `--seq` is
  global to an export run, not per view. Dynamic views export in diagram layout.
  `# ponytail: add a filtered --seq pass into images-<fmt>/seq when someone needs sequence PNGs.`
- `likec4-model` has no single-image equivalent (it is the whole gallery). Non-iframe modes keep
  the existing plain-text line. Unchanged.

## Architecture

### `_runner.py` — `ensure_images(source_dir, cache_dir, version, fmt) -> Path`

Sibling of `ensure_build`, same shape:

1. `digest = source_hash(source_dir, version, [fmt])` — reuses the existing hasher; `fmt` rides in
   the `build_args` slot so png and jpg caches are distinct.
2. Cache hit (`cache_dir/images-<fmt>.stamp == digest` and dir exists) → return
   `cache_dir/images-<fmt>`.
3. Else `rm -rf` the dir, run
   `npx -y likec4@<version> export <fmt> --flat -o <cache_dir>/images-<fmt> <source_dir>`.
   `--flat` puts `<view-id>.<fmt>` directly in the outdir (**verify in task 1** — the one
   assumption that needs the browser to check).
4. If the run fails and stderr mentions `playwright`/`browser`/`executable`, run once
   `npx -y --package likec4@<version> -c 'playwright install chromium'` and retry the export.
   Using likec4's own Playwright keeps the Chromium revision in sync with what it launches.
   A second failure raises the existing `RuntimeError` with stdout/stderr, like `_run` does today.
5. Write stamp, return dir. No `-i`: a view that fails to export fails the build — same policy
   as an unknown view id.

### `__init__.py` — `_builder_inited`

Today: non-html → `likec4_mode = "non-html"`, return early. New:

- Compute `app.env.likec4_default_render` from the table above (one expression on
  `app.builder.format` / `app.builder.supported_image_types`, then `likec4_render` override).
- Run the viewer build as today **only** when `format == "html"` (unchanged).
- Run `ensure_images` when the builder has `supported_image_types` (this includes HTML — a lone
  `:render: png` on an HTML page must find its file; the cache makes the cost a one-off).
  Formats exported: **`png` always**, plus `jpg` if it is the resolved default or appears anywhere
  in `likec4_render` values. Store `app.env.likec4_images = {fmt: str(dir)}`. A directive asking
  `:render: jpg` when jpg was not exported raises `ExtensionError` naming the fix (add `"jpg"` to
  `likec4_render`) — png needs no such opt-in.
  `# ponytail: HTML exports png even if no directive ever asks; gate behind a flag if the Playwright time hurts.`
- `text` default (no `supported_image_types`) → today's early return, no export.
- `LikeC4Missing` (no npx) handling is unchanged and now also covers image export, since both go
  through npx.

`_build_finished` unchanged: Sphinx copies images itself.

### `_directives.py` — `LikeC4View.run`

Resolve `mode = options.get("render") or env.likec4_default_render`, then fall back per the
preference rule. Three branches:

- `iframe` → existing code, untouched.
- `png`/`jpg` → `nodes.image(uri=os.path.relpath(images_dir / f"{view}.{fmt}", dirname(doc source)),
  alt=…, **passthrough options)`. Sphinx does the rest per builder.
- `text` → existing plain paragraph.

View-id validation against `env.likec4_views` applies to all modes — that set comes from
`export json`, which runs alongside the image export when there is no viewer build (non-html).
`note_dependency` on the sources stays as is.

## Docs & CI

- `docs/example.md` gains a `likec4-view` with `:render: png` — a visible static image on the
  HTML site proving the path, and the whole docs render in the PDF.
- `docs/index.md` links the PDF.
- `ci.yml` `docs-build`: install `latexmk texlive-latex-recommended texlive-latex-extra
  texlive-fonts-recommended`, run `sphinx -M latexpdf docs docs/_build -W`, copy the PDF into
  the html output before the Pages upload → `https://ckeller42.github.io/sphinx-likec4/sphinx-likec4.pdf`.
  One job, no cross-job artifact plumbing; adds ~3 min to that job on PRs.
- `test.sh` (local gate) unchanged — a local TeX install is not required to contribute.

## Testing

- `tests/test_runner.py`: `ensure_images` with the existing fake `subprocess.run` — first call
  exports, second is a cache hit; a first failure mentioning `playwright` triggers exactly one
  `playwright install chromium` then a retry; a second failure raises.
- `tests/test_extension.py` (fake npx, as today): html build with `:render: png` emits `<img` and
  copies to `_images/`; latex build of the test root emits `\sphinxincludegraphics`; `text` builder
  performs no export call; `likec4_render = {"html": "png"}` turns every view into an image;
  `:render: iframe` under latex falls back to png; unknown view id still fails in image mode.
- `tests/test_integration.py` (real npx, skipped without node): add a `png` export of the real
  model and assert the file exists and the html embeds it. Downloads Chromium on first run.
- Doctest on the default-mode resolver if it is a pure function.

## Out of scope

SVG/PDF export, per-view sequence layout in image mode, dark theme, exporting only referenced
views (lazy export bypasses Sphinx's image collector and reimplements per-builder copying — the
riskiest part of the extension, for a gain only large models would notice).
