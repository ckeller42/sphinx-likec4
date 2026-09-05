---
name: sphinx-likec4
description: Use when embedding LikeC4 architecture views or dynamic-view sequence diagrams in Sphinx documentation, when configuring the sphinx-likec4 extension, or when its build fails with unknown view id, npx/node missing, or likec4 CLI errors.
---

# sphinx-likec4 — embedding LikeC4 views in Sphinx

The extension builds the LikeC4 viewer from your `.c4`/`.likec4` sources during `sphinx-build`
(pinned CLI via npx, node ≥ 20 required, content-hash cached) and embeds views as iframes.
Do not guess directive names — the exact surface is below and nothing else exists.

## Setup

```python
# conf.py
extensions = ["sphinx_likec4"]
likec4_source_dir = "model"          # dir of .c4/.likec4 files, relative to conf.py — REQUIRED
likec4_render = {"latex": "jpg"}     # optional: default render mode per output format (keyed by builder format; epub uses "epub")
```

Install: `pip install sphinx-likec4` (PyPI) or `pip install "sphinx-likec4 @ git+https://github.com/ckeller42/sphinx-likec4"`.

## Directives

```rst
.. likec4-view:: <view-id>
   :height: 420px            # optional, default 460px
   :title: Upload flow       # optional iframe title (a11y)
   :mode: sequence           # optional: diagram (default) | sequence — dynamic views only
   :render: png              # optional: iframe (HTML default) | png | jpg | text — a preference; non-HTML builders default to png
   :width: 80%               # image-mode passthroughs: width, height, alt, align, scale

.. likec4-model::            # embed the whole viewer gallery
   :height: 600px
.. likec4-model::
   :link-only:               # a styled link instead of an iframe
```

MyST markdown form:

````markdown
```{likec4-view} cloud-to-amazon
:mode: sequence
```
````

- `<view-id>` = the view name from your `views { view <id> ... }` / `dynamic view <id>` blocks.
  Dynamic views share the same id space; `:mode: sequence` opens them in sequence rendering.
- An **unknown view id fails the build** (lists the known ids) — fix the id, don't retry blindly.
- Non-HTML builders (text/latex/epub) render plain text automatically.

## Configuration

| conf.py | default | meaning |
|---|---|---|
| `likec4_source_dir` | — required | model sources dir |
| `likec4_version` | pinned (e.g. `1.59.2`) | exact CLI version; never unpin |
| `likec4_missing` | `error` | node/npx absent: `error` fails build, `warn` renders placeholders |
| `likec4_build_args` | `[]` | extra `likec4 build` args |

## Troubleshooting

- `unknown view id 'X' (known: …)` → use an id from the list; check `views {}` blocks.
- `npx not found` → install node ≥ 20, or set `likec4_missing = "warn"` for a degraded build.
- `likec4 failed: …` → the CLI's stderr follows; usually a `.c4` syntax error — run
  `npx -y likec4@<version> validate <source_dir>` to see it directly.
- Stale output after model edits → the cache keys on file content + version + args; if in doubt
  delete the `likec4/` dir under the Sphinx doctrees and rebuild.
- The viewer lands at `<output>/_likec4/` with hash routes (`_likec4/#/view/<id>/`) — safe under
  any subpath; don't hand-write viewer URLs, use the directives.

Full docs: https://ckeller42.github.io/sphinx-likec4/ (LLM summary: /llms.txt)
