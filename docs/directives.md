# Directives

## likec4-view

Embeds one view as an interactive iframe. **Dynamic views (sequences) share the same id
space** and embed identically.

```rst
.. likec4-view:: cloud-to-amazon
   :height: 420px
   :title: Upload flow
```

MyST form:

````markdown
```{likec4-view} cloud-to-amazon
:height: 420px
```
````

Options: `height` (default `460px`), `title` (iframe title, for accessibility), `render`
(see [Static images](#static-images)), and `mode` — `diagram` (viewer default) or `sequence`,
which opens a **dynamic view directly in its sequence rendering** (appends the viewer's
`?dynamic=` parameter):

```rst
.. likec4-view:: cloud-to-amazon
   :mode: sequence
```

An unknown view id **fails the build** (works with `-W`).

### Static images

`render` picks how the view is embedded: `iframe` (HTML default), `png`, `jpg`, or `text`.
It is a **preference, not a demand** — the same source builds for every output format:

```rst
.. likec4-view:: cloud
   :render: png
   :width: 80%
   :alt: Cloud, structural view
```

- On non-HTML builders (`latex`/PDF, `epub`, …) views are images by default; `:render: iframe`
  there falls back to the builder's default.
- On builders that can't embed images at all (`text`, `man`, `linkcheck`) everything is plain text
  and no image export runs.
- `:render: jpg` needs `"jpg"` somewhere in `likec4_render` (only PNG is exported unless asked).
- In image mode `width`, `height`, `alt`, `align`, `scale` pass through to the image with the
  standard docutils validators; `alt` defaults to `title`. `mode` is ignored — dynamic views
  export in their diagram layout.

## likec4-model

Embeds the whole viewer gallery, or just links it:

```rst
.. likec4-model::
   :height: 600px

.. likec4-model::
   :link-only:
```
