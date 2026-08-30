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

Options: `height` (default `460px`), `title` (iframe title, for accessibility).
An unknown view id **fails the build** (works with `-W`).

## likec4-model

Embeds the whole viewer gallery, or just links it:

```rst
.. likec4-model::
   :height: 600px

.. likec4-model::
   :link-only:
```
