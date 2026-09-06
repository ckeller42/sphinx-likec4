# Review guide

This is a small Sphinx extension (`src/sphinx_likec4/`, three modules) that shells out to the
pinned `likec4` CLI. Read `CLAUDE.md` first — it lists the repository's workflow rules and the
non-obvious gotchas (Sphinx version differences, doctree caching, the lazy image export).

Focus on:

- Correctness across the CI matrix: Sphinx 7 and 8/9, docutils 0.21 and 0.22 behave differently
  (see `CLAUDE.md`). A test that only passes on one is a bug.
- Silent failures: a directive that emits nothing on LaTeX/epub, a cached doctree that is not
  re-read after a state change, an export failure that gets swallowed.
- The directive surface is documented in four places (`README.md`, `docs/directives.md`,
  `skills/sphinx-likec4/SKILL.md`, `llms.txt`); flag any change to `option_spec` that does not
  update all four.
- Anything interpolated into a CLI argv or raw HTML without validation/escaping.

Do not comment on: formatting (ruff runs in CI), docstring style, or the deliberate 3-line
duplication noted in `_runner.py`.
