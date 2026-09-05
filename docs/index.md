# sphinx-likec4

Embed interactive [LikeC4](https://likec4.dev) architecture views — including
`dynamic view` **sequence diagrams** — in Sphinx documentation. The extension runs the
pinned LikeC4 CLI for you, caches the build, and validates every embedded view id.

Also available as a [PDF](https://ckeller42.github.io/sphinx-likec4/sphinx-likec4.pdf) — built by
the same extension, with every view rendered as a static image.

## Quickstart

```bash
pip install sphinx-likec4        # node >= 20 required at doc-build time
```

```python
# conf.py
extensions = ["sphinx_likec4"]
likec4_source_dir = "model"      # your *.c4 / *.likec4 files
```

```rst
.. likec4-view:: index
```

That renders this (LikeC4's official *cloud-system* example):

```{likec4-view} index
```

```{toctree}
:maxdepth: 1

directives
configuration
example
```
