# sphinx-likec4

Embed interactive [LikeC4](https://likec4.dev) architecture views — including
`dynamic view` sequence diagrams — in Sphinx documentation.

```python
# conf.py
extensions = ["sphinx_likec4"]
likec4_source_dir = "model"
```

```rst
.. likec4-view:: cloud-to-amazon
```
