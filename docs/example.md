# Example — cloud-system

LikeC4's official [`cloud-system` example](https://github.com/likec4/likec4/tree/main/examples/cloud-system)
(MIT), vendored under `docs/model/`.

## Structural view

```{likec4-view} cloud
:height: 520px
```

## Sequence (dynamic view)

```{likec4-view} cloud-to-amazon
:height: 420px
:mode: sequence
```

The same dynamic view as a static **sequence** PNG (`:mode: sequence` + `:render: png`) — this is
what a PDF build gets for it:

```{likec4-view} cloud-to-amazon
:render: png
:mode: sequence
:width: 100%
:alt: cloud-to-amazon dynamic view, sequence layout as a static PNG
```

## Static image

The same structural view rendered as a **PNG** — this is what every non-HTML builder
(LaTeX/PDF, epub) gets by default, and what `:render: png` gives you on an HTML page:

```{likec4-view} cloud
:render: png
:width: 100%
:alt: cloud-system structural view, static PNG
```

Source: [`model.c4`](https://github.com/likec4/likec4/blob/main/examples/cloud-system/model.c4)
