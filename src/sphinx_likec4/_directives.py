"""The likec4-view / likec4-model directives."""
from __future__ import annotations

import html
import os
import re
from pathlib import Path
from typing import ClassVar

from docutils import nodes
from docutils.parsers.rst import Directive, directives
from docutils.parsers.rst.directives.images import Image
from sphinx.errors import ExtensionError

_HEIGHT_RE = re.compile(r"^[0-9]+(px|em|rem|vh|%)$")


def _rel(docname: str) -> str:
    """Relative prefix from ``docname``'s output page back to the site root.

    >>> _rel("index")
    ''
    >>> _rel("guide/install")
    '../'
    >>> _rel("a/b/c")
    '../../'
    """
    return "../" * docname.count("/")


def _placeholder(text: str) -> nodes.raw:
    """Build a raw HTML ``<p>`` node carrying ``text``, escaped, as a placeholder.

    >>> _placeholder('a "view" & <me>').astext()
    '<p class="likec4-placeholder"><em>a &quot;view&quot; &amp; &lt;me&gt;</em></p>'
    """
    return nodes.raw("", f'<p class="likec4-placeholder"><em>{html.escape(text, quote=True)}</em></p>',
                      format="html")


def _text(text: str) -> nodes.paragraph:
    """Plain-text stand-in for builders that can't embed the viewer or an image."""
    para = nodes.paragraph()
    para += nodes.Text(text)
    return para


def _view_text(view: str) -> nodes.paragraph:
    return _text(f"LikeC4 view {view!r} (interactive — see the HTML docs)")


_MODEL_TEXT = "LikeC4 model (interactive — see the HTML docs)"


def _mode(argument):
    """Docutils option validator: accept only ``"diagram"`` or ``"sequence"``.

    >>> _mode("sequence")
    'sequence'
    >>> _mode("bogus")  # doctest: +ELLIPSIS
    Traceback (most recent call last):
        ...
    ValueError: "bogus" unknown; choose from ...
    """
    return directives.choice(argument, ("diagram", "sequence"))


def _height(argument):
    """Docutils option validator: a CSS length (``"460px"``, ``"60vh"``, ``"50%"``) or any
    docutils image length (``"12pt"``, unitless ``"100"`` = pixels).

    >>> _height("460px")
    '460px'
    >>> _height("60%")
    '60%'
    >>> _height("100")
    '100'
    >>> _height("12pt")
    '12pt'
    >>> _height("tall")  # doctest: +ELLIPSIS
    Traceback (most recent call last):
        ...
    ValueError: ...
    """
    if argument and _HEIGHT_RE.match(argument):
        return argument
    return directives.length_or_unitless(argument)


def _css_height(height: str) -> str:
    """Docutils allows a unitless height (pixels); CSS does not — add the unit for iframes.

    >>> _css_height("300")
    '300px'
    >>> _css_height("12pt")
    '12pt'
    """
    return f"{height}px" if height.isdigit() else height


_RENDER_MODES = ("iframe", "png", "jpg", "text")


def _render(argument):
    """Docutils option validator for ``:render:``.

    >>> _render("png")
    'png'
    >>> _render("svg")  # doctest: +ELLIPSIS
    Traceback (most recent call last):
        ...
    ValueError: "svg" unknown; choose from ...
    """
    return directives.choice(argument, _RENDER_MODES)


def _resolve_render(requested: str | None, default: str, is_html: bool, images: dict) -> str:
    """Pick one directive's render mode. ``:render:`` is a preference, not a demand.

    ``default`` is the builder's resolved default (see ``sphinx_likec4._default_render``);
    ``images`` maps exported formats to their directories.

    >>> _resolve_render(None, "iframe", True, {"png": "/c"})
    'iframe'
    >>> _resolve_render("png", "iframe", True, {"png": "/c"})      # static image on an HTML page
    'png'
    >>> _resolve_render("iframe", "png", False, {"png": "/c"})     # LaTeX can't embed an iframe
    'png'
    >>> _resolve_render("png", "text", False, {})                  # text builder has no images
    'text'
    >>> _resolve_render("text", "iframe", True, {"png": "/c"})
    'text'
    >>> _resolve_render("jpg", "png", False, {"png": "/c"})
    Traceback (most recent call last):
        ...
    sphinx.errors.ExtensionError: likec4-view: ':render: jpg' needs "jpg" in likec4_render (only png was exported)
    """
    if not requested:
        return default
    if requested == "text":
        return "text"
    if requested == "iframe":
        return "iframe" if is_html else default
    if not images:
        return default
    if requested not in images:
        raise ExtensionError(
            f"likec4-view: ':render: {requested}' needs \"{requested}\" in likec4_render "
            f"(only {', '.join(sorted(images))} was exported)"
        )
    return requested


class LikeC4View(Directive):
    """``.. likec4-view:: <view-id>`` — embed one LikeC4 view.

    Renders per :func:`sphinx_likec4._builder_inited`'s ``likec4_mode`` and the resolved
    render mode (see :func:`_resolve_render`): an iframe, a static PNG/JPG image, or plain
    text. ``"warn"`` mode (node/npx unavailable) renders a placeholder.
    """

    required_arguments = 1
    option_spec: ClassVar[dict] = {
        "height": _height, "title": directives.unchanged, "mode": _mode, "render": _render,
        # image-mode passthroughs: same names and validators as the docutils image directive
        **{k: Image.option_spec[k] for k in ("width", "alt", "align", "scale")},
    }

    def run(self):
        env = self.state.document.settings.env
        view = self.arguments[0]
        mode = getattr(env, "likec4_mode", "ready")
        if mode == "non-html":
            return [_view_text(view)]
        if mode == "warn":                                  # build unavailable
            if env.likec4_format != "html":
                return [_view_text(view)]
            return [_placeholder(f"LikeC4 view “{view}” (viewer not built — node/npx unavailable)")]
        for f in getattr(env, "likec4_sources", ()):
            env.note_dependency(f)
        views = env.likec4_views
        if view not in views:
            # A docutils DirectiveError (self.error()) is swallowed into an in-page
            # error node and does not fail the build even under warningiserror; an
            # unknown view id is a hard authoring error, so raise for real.
            raise ExtensionError(
                f"likec4-view: unknown view id {view!r} (known: {', '.join(sorted(views))})"
            )
        render = _resolve_render(self.options.get("render"), env.likec4_render_default,
                                 env.likec4_format == "html", env.likec4_images)
        title = self.options.get("title", f"LikeC4 view {view}")
        if render == "text":
            return [_view_text(view)]
        if render in ("png", "jpg"):
            return [self._image(env, view, render, title)]
        height = _css_height(self.options.get("height", "460px"))
        title = html.escape(title, quote=True)
        src = _rel(env.docname) + f"_likec4/#/view/{html.escape(view, quote=True)}/"
        dyn_mode = self.options.get("mode")
        if dyn_mode:                   # the viewer's ?dynamic= search param lives inside the hash
            src += f"?dynamic={dyn_mode}"
        iframe = (
            f'<iframe class="likec4-view" src="{src}" loading="lazy" title="{title}" '
            f'style="width:100%;height:{height};border:1px solid rgba(120,120,120,.3);'
            f'border-radius:8px;"></iframe>'
        )
        return [nodes.raw("", iframe, format="html")]

    def _image(self, env, view: str, fmt: str, title: str) -> nodes.image:
        """A standard image node pointing into the export cache; Sphinx copies/embeds it per builder.

        The URI is relative to this document so Sphinx's image collector resolves it —
        relative paths may escape ``srcdir``.
        """
        # ponytail: :mode: sequence is ignored here — --seq is global to an export run; add a
        # filtered --seq pass into images-<fmt>/seq when someone needs sequence PNGs
        file = Path(env.likec4_images[fmt]) / f"{view}.{fmt}"
        if not file.exists():
            raise ExtensionError(
                f"likec4-view: no exported {fmt} for view {view!r} in {file.parent} "
                f"(likec4 export names files by view id; check the export dir)")
        uri = os.path.relpath(file, os.path.dirname(env.doc2path(env.docname)))
        opts = {k: v for k, v in self.options.items() if k in ("width", "height", "alt", "align", "scale")}
        opts.setdefault("alt", title)
        return nodes.image(uri=uri, **opts)


class LikeC4Model(Directive):
    """``.. likec4-model::`` — embed the whole model, or link to it, as an iframe.

    Same mode-driven rendering as :class:`LikeC4View`. With ``:link-only:`` set,
    renders a plain link to the built viewer instead of embedding an iframe.
    """

    option_spec: ClassVar[dict] = {"link-only": directives.flag, "height": _height}

    def run(self):
        env = self.state.document.settings.env
        mode = getattr(env, "likec4_mode", "ready")
        if mode == "non-html":
            return [_text(_MODEL_TEXT)]
        if mode == "warn":
            if env.likec4_format != "html":
                return [_text(_MODEL_TEXT)]
            return [_placeholder("LikeC4 model (viewer not built — node/npx unavailable)")]
        if env.likec4_format != "html":                     # the gallery has no single-image form
            return [_text(_MODEL_TEXT)]
        for f in getattr(env, "likec4_sources", ()):
            env.note_dependency(f)
        src = _rel(env.docname) + "_likec4/"
        if "link-only" in self.options:
            content = f'<p><a class="likec4-model-link" href="{src}">Open the interactive model</a></p>'
        else:
            height = _css_height(self.options.get("height", "600px"))
            content = (
                f'<iframe class="likec4-model" src="{src}" loading="lazy" '
                f'title="LikeC4 model" style="width:100%;height:{height};'
                f'border:1px solid rgba(120,120,120,.3);border-radius:8px;"></iframe>'
            )
        return [nodes.raw("", content, format="html")]
