"""The likec4-view / likec4-model directives."""
from __future__ import annotations

import html
import re
from typing import ClassVar

from docutils import nodes
from docutils.parsers.rst import Directive, directives
from sphinx.errors import ExtensionError

_HEIGHT_RE = re.compile(r"^[0-9]+(px|em|rem|vh|%)$")


def _rel(docname: str) -> str:
    return "../" * docname.count("/")


def _placeholder(text: str) -> nodes.raw:
    return nodes.raw("", f'<p class="likec4-placeholder"><em>{html.escape(text, quote=True)}</em></p>',
                      format="html")


def _mode(argument):
    return directives.choice(argument, ("diagram", "sequence"))


def _height(argument):
    if not argument or not _HEIGHT_RE.match(argument):
        raise ValueError(f"height must match {_HEIGHT_RE.pattern!r}, got {argument!r}")
    return argument


class LikeC4View(Directive):
    required_arguments = 1
    option_spec: ClassVar[dict] = {"height": _height, "title": directives.unchanged, "mode": _mode}

    def run(self):
        env = self.state.document.settings.env
        view = self.arguments[0]
        mode = getattr(env, "likec4_mode", "html")
        if mode == "non-html":
            para = nodes.paragraph()
            para += nodes.Text(f"LikeC4 view {view!r} (interactive — see the HTML docs)")
            return [para]
        if mode == "warn":                                  # build unavailable
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
        height = self.options.get("height", "460px")
        title = html.escape(self.options.get("title", f"LikeC4 view {view}"), quote=True)
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


class LikeC4Model(Directive):
    option_spec: ClassVar[dict] = {"link-only": directives.flag, "height": _height}

    def run(self):
        env = self.state.document.settings.env
        mode = getattr(env, "likec4_mode", "html")
        if mode == "non-html":
            para = nodes.paragraph()
            para += nodes.Text("LikeC4 model (interactive — see the HTML docs)")
            return [para]
        if mode == "warn":
            return [_placeholder("LikeC4 model (viewer not built — node/npx unavailable)")]
        for f in getattr(env, "likec4_sources", ()):
            env.note_dependency(f)
        src = _rel(env.docname) + "_likec4/"
        if "link-only" in self.options:
            content = f'<p><a class="likec4-model-link" href="{src}">Open the interactive model</a></p>'
        else:
            height = self.options.get("height", "600px")
            content = (
                f'<iframe class="likec4-model" src="{src}" loading="lazy" '
                f'title="LikeC4 model" style="width:100%;height:{height};'
                f'border:1px solid rgba(120,120,120,.3);border-radius:8px;"></iframe>'
            )
        return [nodes.raw("", content, format="html")]
