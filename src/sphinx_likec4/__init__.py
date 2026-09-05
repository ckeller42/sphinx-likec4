"""sphinx-likec4 — embed interactive LikeC4 views in Sphinx HTML documentation."""
from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

from sphinx.errors import ConfigError
from sphinx.util import logging

__version__ = "0.1.0"
DEFAULT_LIKEC4_VERSION = "1.59.2"
logger = logging.getLogger(__name__)


def _default_render(builder, overrides: dict) -> str:
    """Render mode a builder gets when a directive doesn't say: ``likec4_render`` first, else
    ``iframe`` for HTML, ``png`` for any other builder that can embed images, ``text`` otherwise.

    >>> from types import SimpleNamespace as B
    >>> _default_render(B(format="html", supported_image_types=["image/png"]), {})
    'iframe'
    >>> _default_render(B(format="latex", supported_image_types=["application/pdf", "image/png"]), {})
    'png'
    >>> _default_render(B(format="latex", supported_image_types=["image/png"]), {"latex": "jpg"})
    'jpg'
    >>> _default_render(B(format="text", supported_image_types=[]), {"text": "png"})   # can't embed
    'text'
    """
    if not builder.supported_image_types:
        return "text"
    return overrides.get(builder.format) or ("iframe" if builder.format == "html" else "png")


def _builder_inited(app):
    """``builder-inited`` handler: validate config, build the viewer and/or export images.

    Sets ``app.env.likec4_mode`` to one of:

    - ``"non-html"`` — builder can't embed images (text, man, linkcheck…); directives emit
      plain text and nothing is exported.
    - ``"warn"`` — node/npx unavailable and ``likec4_missing == "warn"``; directives render
      placeholders.
    - ``"ready"`` — viewer built (HTML) and/or images exported; ``likec4_views``,
      ``likec4_images``, ``likec4_dist``, ``likec4_render_default`` are populated.
    """
    from . import _runner
    from ._directives import _RENDER_MODES
    cfg = app.config
    if cfg.likec4_missing not in ("error", "warn"):
        raise ConfigError(
            f"sphinx-likec4: likec4_missing must be 'error' or 'warn', got {cfg.likec4_missing!r}"
        )
    bad = {k: v for k, v in cfg.likec4_render.items() if v not in _RENDER_MODES}
    if bad:
        raise ConfigError(f"sphinx-likec4: likec4_render values must be one of {_RENDER_MODES}, got {bad!r}")
    env = app.env
    # epub subclasses the HTML builder and reports format == "html" like real HTML does, but it
    # can't embed our iframe viewer and gets no viewer build — treat it as its own format here.
    is_epub = app.builder.name.startswith("epub")
    builder_for_default = (
        SimpleNamespace(format="epub", supported_image_types=app.builder.supported_image_types)
        if is_epub else app.builder
    )
    env.likec4_render_default = _default_render(builder_for_default, cfg.likec4_render)
    env.likec4_images = {}
    env.likec4_dist = None
    if env.likec4_render_default == "text":
        env.likec4_mode = "non-html"
        env.likec4_views = set()
        return
    src = cfg.likec4_source_dir
    if not src:
        raise ConfigError("sphinx-likec4: set likec4_source_dir in conf.py")
    source_dir = Path(app.confdir) / src
    if not source_dir.is_dir():
        raise ConfigError(f"sphinx-likec4: likec4_source_dir {source_dir} does not exist")
    # directives note_dependency() on these so a rename/edit invalidates cached
    # doctrees on incremental builds (otherwise a stale doctree hides an id change)
    env.likec4_sources = [
        str(p) for p in sorted(source_dir.rglob("*")) if p.suffix in (".c4", ".likec4")
    ]
    cache_dir = Path(app.doctreedir) / "likec4"
    # png is always exported for an image-capable builder (a lone ":render: png" must find its
    # file); jpg only when this or any other format's config asks for it.
    formats = {"png"} | {v for v in (env.likec4_render_default, *cfg.likec4_render.values()) if v == "jpg"}
    try:
        if app.builder.format == "html" and not is_epub:
            dist, views = _runner.ensure_build(
                source_dir, cache_dir, cfg.likec4_version, list(cfg.likec4_build_args))
            env.likec4_dist = str(dist)
        else:
            views = _runner.ensure_views(source_dir, cache_dir, cfg.likec4_version)
        # ponytail: exports png even if no directive asks; gate behind a flag if the Playwright time hurts
        env.likec4_images = {
            f: str(_runner.ensure_images(source_dir, cache_dir, cfg.likec4_version, f))
            for f in sorted(formats)
        }
    except _runner.LikeC4Missing as e:
        if cfg.likec4_missing == "warn":
            logger.warning("sphinx-likec4: %s — views render as placeholders", e,
                           type="likec4", subtype="missing")
            env.likec4_mode = "warn"
            env.likec4_views = None
            env.likec4_dist = None
            env.likec4_images = {}
            return
        raise ConfigError(f"sphinx-likec4: {e} (set likec4_missing='warn' to build without it)")
    env.likec4_mode = "ready"
    env.likec4_views = views


def _build_finished(app, exc):
    """``build-finished`` handler: copy the built viewer into ``<outdir>/_likec4``.

    No-op if the build errored or the builder isn't HTML.
    """
    if exc or app.builder.format != "html":
        return
    dist = getattr(app.env, "likec4_dist", None)
    if dist:
        target = Path(app.outdir) / "_likec4"
        shutil.rmtree(target, ignore_errors=True)  # drop orphaned assets from a prior build
        shutil.copytree(dist, target, dirs_exist_ok=True)


def setup(app):
    """Sphinx extension entry point: register config values, directives, and hooks."""
    from ._directives import LikeC4Model, LikeC4View
    app.add_config_value("likec4_source_dir", None, "env")
    app.add_config_value("likec4_version", DEFAULT_LIKEC4_VERSION, "env")
    app.add_config_value("likec4_missing", "error", "env")
    app.add_config_value("likec4_build_args", [], "env")
    app.add_config_value("likec4_render", {}, "env")
    app.add_directive("likec4-view", LikeC4View)
    app.add_directive("likec4-model", LikeC4Model)
    app.connect("builder-inited", _builder_inited)
    app.connect("build-finished", _build_finished)
    return {"version": __version__, "parallel_read_safe": True, "parallel_write_safe": True}
