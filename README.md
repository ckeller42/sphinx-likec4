# sphinx-likec4

[![CI](https://github.com/ckeller42/sphinx-likec4/actions/workflows/ci.yml/badge.svg)](https://github.com/ckeller42/sphinx-likec4/actions/workflows/ci.yml)
[![docs](https://img.shields.io/badge/docs-github%20pages-blue)](https://ckeller42.github.io/sphinx-likec4/)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Embed interactive [LikeC4](https://likec4.dev) architecture views — including
`dynamic view` **sequence diagrams** — in Sphinx documentation.

The extension runs the **pinned** LikeC4 CLI for you (node ≥ 20 required at doc-build
time), caches the build on a content hash, validates every embedded view id at build time
(`-W` friendly), and serves the viewer with hash routing so it works from any subpath.

## Agent skill

An [Agent Skill](https://agentskills.io) documenting the directive surface ships in `skills/`:

```bash
npx skills add ckeller42/sphinx-likec4      # installs into your agent's skills dir
```

An LLM-oriented summary of the whole project lives at
[`/llms.txt`](https://ckeller42.github.io/sphinx-likec4/llms.txt).

## Quickstart

```bash
pip install sphinx-likec4
```

```python
# conf.py
extensions = ["sphinx_likec4"]
likec4_source_dir = "model"
```

```rst
.. likec4-view:: cloud-to-amazon
```

Docs: https://ckeller42.github.io/sphinx-likec4/ · License: MIT
