# sphinx-likec4

## Workflow
- **PR-only.** `main` is protected (admins too, conversation resolution required). Branch → commit → `gh pr create`. Direct push fails.
- Commit prefixes per history: `feat:` `fix:` `docs:` `test:` `ci:` `chore:`.
- CodeRabbit reviews every PR. Unresolved threads block merge: fix, then resolve via GraphQL `resolveReviewThread` (or PR UI).
- Claude reviews every same-repo PR too (`.github/workflows/claude-code-review.yml`, inline comments) and answers `@claude` in issues/PR comments (`claude.yml`); both run on the maintainer's subscription via the `CLAUDE_CODE_OAUTH_TOKEN` secret.

## Test / lint
- `./test.sh` = ruff + pytest + strict sphinx build (mirrors CI). Bare `pytest` also works (`testpaths` set).
- Doctests live in `src/` docstrings, collected via `--doctest-modules`; `tests/roots/*` is excluded (Sphinx test roots, loaded from disk, not imported).
- `tests/test_integration.py` needs node/`npx` (skips otherwise); first run downloads pinned likec4, slow.

## Gotchas
- `gh pr view --json author` reports bots as `app/dependabot`; REST `.user.login` gives `dependabot[bot]`. Use the latter for checks.
- `dependabot-auto-merge.yml` is intentionally independent of the repo "Allow auto-merge" toggle (`allow_auto_merge: false`). Don't "fix" by enabling it.
- Version is duplicated: `pyproject.toml:version` and `src/sphinx_likec4/__init__.py:__version__` must match.
- `DEFAULT_LIKEC4_VERSION` (`__init__.py`) is a pinned string — Dependabot does NOT track it. Bump manually + run integration test.
- Directive surface is documented in 4 places: `README.md`, `docs/directives.md`, `skills/sphinx-likec4/SKILL.md`, `llms.txt`. Changing `option_spec` → update all four.
- Sphinx's epub builder reports `format == "html"`; use `env.likec4_format` (`_format_key`), never `builder.format`, to decide HTML-ness.
- Doctrees are cached per document, not per builder: builder-specific nodes need the `env-get-outdated` re-read (`_env_get_outdated`) or `-M html` then `-M latexpdf` shares stale nodes. Images are exported lazily: directives export their own view on demand and record it in `env.likec4_needed` (purged/merged via `env-purge-doc`/`env-merge-info`); `builder-inited` re-exports that set batched. Test fakes of `ensure_images` take `(source_dir, cache_dir, version, fmt, views, seq=False)`.
- Test-matrix quirks: two `Sphinx()` apps in one test need `docutils_namespace()` each (Sphinx 7 re-registration warning); `warningiserror=True` raises on Sphinx 7 but only sets `statuscode` on ≥8.1; handler exceptions arrive wrapped in `ExtensionError` (check `.orig_exc`); LaTeX escapes `'` to `\textquotesingle{}` and writes `\sphinxincludegraphics{{name}.png}`; docutils 0.22 renders a unitless image height as `height="N"`, 0.21 as `style`.
- The docs model is NOT in the repo: `docs/conf.py` fetches LikeC4's `examples/cloud-system` at a pinned SHA into `docs/_build/cloud-system/` on first build (network needed, like npx). Bump `_EXAMPLE_SHA` to follow upstream; embedded view ids must survive.
- Windows CI cell: always pass `encoding="utf-8"` to `read_text`/`write_text` (cp1252 default chokes on the curly quotes in placeholders and on non-ASCII model titles); the checkout is on `D:` and `tmp_path` on `C:`, so tests must build from a `tmp_path` copy of the test root (`_root_copy`) — `os.path.relpath` cannot cross drives. Image URIs are normalized to forward slashes.
- Verify Sphinx-7-only failures locally with a scratch venv: `.venv/bin/python -m venv /tmp/s7 && /tmp/s7/bin/pip install -e '.[test]' 'sphinx>=7,<8'`.
