# Configuration

| `conf.py` value | default | meaning |
|---|---|---|
| `likec4_source_dir` | — (required) | directory of `.c4`/`.likec4` sources, relative to `conf.py` |
| `likec4_version` | `"1.59.2"` | exact CLI version run via `npx -y likec4@<version>` |
| `likec4_missing` | `"error"` | when node/npx is absent: `error` fails the build, `warn` renders placeholders |
| `likec4_build_args` | `[]` | extra arguments appended to `likec4 build` |

Node ≥ 20 must be on `PATH` at doc-build time. The build is **cached** on a content hash of
the sources + version + args, so incremental Sphinx builds don't re-run the CLI. The viewer is
copied into the output at `_likec4/` and uses hash routing, so it works from any subpath.

The `likec4_missing="warn"` warning is tagged `type="likec4"`, so it can be silenced even under
`-W` with `suppress_warnings = ["likec4"]` in `conf.py`.
