# sphinx-likec4

Embed interactive [LikeC4](https://likec4.dev) architecture views — including
`dynamic view` **sequence diagrams** — in Sphinx documentation.

The extension runs the **pinned** LikeC4 CLI for you (node ≥ 20 required at doc-build
time), caches the build on a content hash, validates every embedded view id at build time
(`-W` friendly), and serves the viewer with hash routing so it works from any subpath.

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
