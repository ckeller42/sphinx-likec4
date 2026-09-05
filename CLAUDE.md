# sphinx-likec4

## Workflow
- **PR-only.** `main` is protected (admins too, conversation resolution required). Branch → commit → `gh pr create`. Direct push fails.
- Commit prefixes per history: `feat:` `fix:` `docs:` `test:` `ci:` `chore:`.
- CodeRabbit reviews every PR. Unresolved threads block merge: fix, then resolve via GraphQL `resolveReviewThread` (or PR UI).

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
