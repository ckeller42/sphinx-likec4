# sphinx-likec4 — design spec (2026-08-30)

A standalone Sphinx extension that embeds interactive [LikeC4](https://likec4.dev) architecture
views in Sphinx documentation. Turnkey: `pip install sphinx-likec4`, one `extensions` entry, one
config value. First consumer: [open-california](https://github.com/ckeller42/open-california)
(replaces its local `docs/_ext/likec4_embed.py` + hand-wired `build_site.sh` step).

## Identity

- **Name:** `sphinx-likec4` (PyPI), module `sphinx_likec4`, repo `ckeller42/sphinx-likec4`,
  checkout `~/src/sphinx-likec4`. MIT. All names verified free (PyPI 404, GitHub empty).
- Python ≥3.10, Sphinx ≥7. Node ≥20 required at doc-build time (documented; behavior on absence
  is configurable, see below).

## Architecture (build-orchestrating, cache-aware)

1. **`builder-inited`** (html builders only): hash the `.c4`/`.likec4` files under
   `likec4_source_dir` (+ the pinned CLI version). On change, run
   `npx -y likec4@<likec4_version> build --use-hash-history --base ./ -o <cachedir>`;
   else reuse the cache (`outdir`-adjacent, survives incremental builds).
   Also run `likec4 export json` once to collect the **valid view ids**.
2. **Directives** resolve at parse time; unknown view id → Sphinx **error** (fails `-W` builds).
3. **`build-finished`**: copy the built viewer into the output at `_likec4/`.
4. **Node/npx missing:** `likec4_missing = "error"` (default) fails the build;
   `"warn"` emits a warning and directives render a plain placeholder link.

Encodes the lessons from the open-california integration: `--use-hash-history` (routes are
subpath-independent — without it the SPA router 404s under a subpath), **pinned CLI version**
(unpinned npx = supply chain), depth-aware relative iframe `src`.

## Directives (v1 — lean core)

- `.. likec4-view:: <view-id>` — embeds `_likec4/#/view/<id>/` as an iframe.
  Options: `:height:` (default `460px`), `:title:` (iframe title/a11y).
  Non-HTML builders emit plain text.
  **Sequence diagrams are first-class:** LikeC4 `dynamic view` ids live in the same view-id
  space, so `likec4-view` embeds them identically — validated against the same
  `export json` view list. A dedicated test + a docs embed prove it.
- `.. likec4-model::` — embeds the full viewer gallery; `:link-only:` renders a styled link
  instead. Same non-HTML fallback.
- Both work from MyST markdown via the standard ```` ```{likec4-view} ```` fence.

Deferred (explicitly out of v1): static PNG export directive (chromium dependency), inline-DSL
directive.

## Configuration

| conf.py value | default | meaning |
|---|---|---|
| `likec4_source_dir` | — (required) | directory of `.c4`/`.likec4` sources, relative to conf dir |
| `likec4_version` | pinned known-good (e.g. `1.59.2`) | exact CLI version npx runs |
| `likec4_missing` | `"error"` | `error` or `warn` when node/npx is unavailable |
| `likec4_build_args` | `[]` | extra args appended to `likec4 build` |

## Documentation (dogfooding, concise)

`docs/` built with Sphinx + furo **using sphinx-likec4 itself**, embedding LikeC4's official
**`cloud-system`** example (copied from `likec4/likec4` `examples/cloud-system`, MIT, attributed).
Four pages, no more:

1. **index** — what it is, 3-line quickstart, one live `likec4-view` embed.
2. **directives** — `likec4-view` / `likec4-model`, every option, MyST forms.
3. **configuration** — the table above + node requirement + `likec4_missing` behavior.
4. **example** — the cloud-system model embedded: one structural view **and one of its
   `dynamic view` sequences** (`cloud-to-amazon`), with the `.c4` source linked.

Deployed to GitHub Pages by CI (build with `-W`; the docs build doubles as an end-to-end test).

## Testing / CI

- pytest with Sphinx test-roots (`app.build()` on fixture projects): happy path (iframe emitted,
  viewer copied), **dynamic-view embed**, unknown view id fails, `likec4_missing="warn"` placeholder, page-depth relative
  paths, cache reuse (second build skips the CLI).
- GitHub Actions: py {3.10, 3.13} × sphinx {7, 8}, node 22; ruff; docs build+deploy job.
- Release: `pyproject.toml` (hatchling), PyPI trusted publishing on tag.

## Consumer migration (separate follow-up PR in open-california)

Remove `docs/_ext/likec4_embed.py` + the `likec4 build` line in `build_site.sh`; add
`sphinx-likec4` to `docs/requirements.txt`; set `likec4_source_dir = "likec4"`. The existing
`docs/likec4/*.c4` stay as-is; `/model/` gallery link is replaced by `.. likec4-model::`.
