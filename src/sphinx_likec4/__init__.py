"""sphinx-likec4 — embed interactive LikeC4 views in Sphinx HTML documentation."""
from __future__ import annotations

import shutil
from pathlib import Path

from sphinx.errors import ConfigError
from sphinx.util import logging

__version__ = "0.1.0"
DEFAULT_LIKEC4_VERSION = "1.59.2"
logger = logging.getLogger(__name__)


def _builder_inited(app):
    from . import _runner
    if app.builder.format != "html":
        app.env.likec4_views = set()      # directives degrade to links elsewhere; keep simple
        app.env.likec4_dist = None
        return
    src = app.config.likec4_source_dir
    if not src:
        raise ConfigError("sphinx-likec4: set likec4_source_dir in conf.py")
    source_dir = Path(app.confdir) / src
    if not source_dir.is_dir():
        raise ConfigError(f"sphinx-likec4: likec4_source_dir {source_dir} does not exist")
    cache_dir = Path(app.doctreedir) / "likec4"
    try:
        dist, views = _runner.ensure_build(
            source_dir, cache_dir, app.config.likec4_version,
            list(app.config.likec4_build_args))
    except _runner.LikeC4Missing as e:
        if app.config.likec4_missing == "warn":
            logger.warning("sphinx-likec4: %s — views render as placeholders", e,
                           type="likec4", subtype="missing")
            app.env.likec4_views = None
            app.env.likec4_dist = None
            return
        raise ConfigError(f"sphinx-likec4: {e} (set likec4_missing='warn' to build without it)")
    app.env.likec4_views = views
    app.env.likec4_dist = str(dist)


def _build_finished(app, exc):
    if exc or app.builder.format != "html":
        return
    dist = getattr(app.env, "likec4_dist", None)
    if dist:
        shutil.copytree(dist, Path(app.outdir) / "_likec4", dirs_exist_ok=True)


def setup(app):
    from ._directives import LikeC4Model, LikeC4View
    app.add_config_value("likec4_source_dir", None, "env")
    app.add_config_value("likec4_version", DEFAULT_LIKEC4_VERSION, "env")
    app.add_config_value("likec4_missing", "error", "env")
    app.add_config_value("likec4_build_args", [], "env")
    app.add_directive("likec4-view", LikeC4View)
    app.add_directive("likec4-model", LikeC4Model)
    app.connect("builder-inited", _builder_inited)
    app.connect("build-finished", _build_finished)
    return {"version": __version__, "parallel_read_safe": True, "parallel_write_safe": True}
