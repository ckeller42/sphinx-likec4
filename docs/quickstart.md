# Quickstart

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

In a PDF or epub build the same directive embeds a static PNG instead; `:render: png` does that on
an HTML page too — see [Directives](directives.md#static-images).
