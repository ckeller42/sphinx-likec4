# Configuration

| `conf.py` value | default | meaning |
|---|---|---|
| `likec4_source_dir` | — (required) | directory of `.c4`/`.likec4` sources, relative to `conf.py` |
| `likec4_version` | `"1.59.2"` | exact CLI version run via `npx -y likec4@<version>` |
| `likec4_missing` | `"error"` | when node/npx is absent: `error` fails the build, `warn` renders placeholders |
| `likec4_build_args` | `[]` | extra arguments appended to `likec4 build` |
| `likec4_render` | `{}` | default render mode per output format, keyed by builder format (`"html"`, `"latex"`, …; epub uses `"epub"`), e.g. `{"latex": "jpg", "epub": "png"}`; values `iframe`, `png`, `jpg`, `text` |
| `likec4_export_images` | `True` | set `False` to never run the image export: HTML renders iframes only, non-HTML builders fall back to plain text, no Chromium needed |

Node ≥ 20 must be on `PATH` at doc-build time. The build is **cached** on a content hash of
the sources + version + args, so incremental Sphinx builds don't re-run the CLI. The viewer is
copied into the output at `_likec4/` and uses hash routing, so it works from any subpath.

The `likec4_missing="warn"` warning is tagged `type="likec4"`, so it can be silenced even under
`-W` with `suppress_warnings = ["likec4"]` in `conf.py`.

## Static images and PDF

Only the views a build actually embeds are exported: a page's directive renders its view on
first use (`likec4 export png --flat -f <id>`), and rebuilds re-export the remembered set in
one run per format when the sources changed. Plain HTML never starts a browser unless a page
uses `:render: png`; unreferenced views are never rendered. The renders live under the doctree
dir (`likec4/images-<fmt>/`), cached on the same content hash as the viewer. If the batched
re-export fails on a builder whose default is the iframe, the build continues with a `likec4`
warning and `:render: png` falls back to the iframe; an export failure for an explicitly
requested image is an error. Set `likec4_export_images = False` to disable images entirely.
The export renders in headless Chromium through Playwright. If no
browser is present the extension installs one **once**, using likec4's own Playwright so the
revision matches:

```bash
npx -y --package likec4@1.59.2 -c 'playwright install chromium'   # what it runs for you
```

(≈150 MB, into Playwright's cache under your home directory.) On a minimal Linux CI image add
`--with-deps` to that command yourself if Chromium complains about missing shared libraries.

For a PDF: `sphinx-build -M latexpdf docs docs/_build` — nothing LikeC4-specific to configure.
The extension's own docs use `latex_engine = "xelatex"` for the Unicode arrows in the text.
