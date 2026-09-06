"""sphinx-likec4 — embed interactive LikeC4 views in Sphinx HTML documentation."""
from __future__ import annotations

import shutil
from pathlib import Path

from sphinx.errors import ConfigError
from sphinx.util import logging

__version__ = "0.2.0"
DEFAULT_LIKEC4_VERSION = "1.59.2"
logger = logging.getLogger(__name__)


def _format_key(builder) -> str:
    """Output-format key for ``likec4_render`` and the built-in defaults.

    Sphinx's epub builder subclasses the HTML builder and reports ``format == "html"``,
    but it can't host the iframe viewer — key it as ``"epub"``.

    >>> from types import SimpleNamespace as B
    >>> _format_key(B(name="html", format="html"))
    'html'
    >>> _format_key(B(name="epub", format="html"))
    'epub'
    >>> _format_key(B(name="latex", format="latex"))
    'latex'
    """
    return "epub" if builder.name.startswith("epub") else builder.format


def _default_render(fmt: str, image_capable: bool, overrides: dict) -> str:
    """Render mode a builder gets when a directive doesn't say: ``likec4_render[fmt]`` first,
    else ``iframe`` for HTML (needs no image export, so it's available even when
    ``image_capable`` is False — e.g. ``likec4_export_images = False``), ``png`` for any other
    builder that can embed images, ``text`` when it can't (text, man, linkcheck…) or when
    image export was turned off for a builder that would otherwise need it. An image mode
    (``png``/``jpg``), whether from an override or the built-in default, always requires image
    capability — HTML included, so a ``likec4_render = {"html": "png"}`` override can't demand an
    export that ``likec4_export_images = False`` disabled.

    >>> _default_render("html", True, {})
    'iframe'
    >>> _default_render("html", False, {})   # likec4_export_images=False: iframe needs no export
    'iframe'
    >>> _default_render("latex", True, {})
    'png'
    >>> _default_render("epub", True, {})
    'png'
    >>> _default_render("latex", True, {"latex": "jpg"})
    'jpg'
    >>> _default_render("latex", False, {})  # not image-capable: falls back to text
    'text'
    >>> _default_render("text", False, {"text": "png"})   # can't embed images: override ignored
    'text'
    >>> _default_render("html", False, {"html": "png"})   # export disabled: image override ignored
    'iframe'
    >>> _default_render("latex", True, {"latex": "iframe"})   # no iframes off HTML: image instead
    'png'
    >>> _default_render("latex", False, {"latex": "iframe"})
    'text'
    """
    mode = overrides.get(fmt) or ("iframe" if fmt == "html" else "png")
    if mode == "iframe" and fmt != "html":      # only HTML can host the viewer
        mode = "png"
    if mode in ("png", "jpg") and not image_capable:
        return "iframe" if fmt == "html" else "text"
    return mode


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
    env.likec4_format = _format_key(app.builder)
    image_capable = bool(app.builder.supported_image_types) and cfg.likec4_export_images
    env.likec4_render_default = _default_render(env.likec4_format, image_capable, cfg.likec4_render)
    env.likec4_images = {}
    env.likec4_images_seq = {}
    env.likec4_dynamic_views = set()
    env.likec4_dist = None
    if not hasattr(env, "likec4_needed"):
        env.likec4_needed = {}                       # docname -> {(view, fmt, seq)}; survives via the env pickle
    if env.likec4_render_default == "text":
        env.likec4_mode = "non-html"
        env.likec4_views = set()
        _set_render_key(env)
        return
    src = cfg.likec4_source_dir
    if not src:
        raise ConfigError("sphinx-likec4: set likec4_source_dir in conf.py")
    source_dir = Path(app.confdir) / src
    if not source_dir.is_dir():
        raise ConfigError(f"sphinx-likec4: likec4_source_dir {source_dir} does not exist")
    env.likec4_source_dir = str(source_dir)
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
        views, dynamic = _runner.ensure_views(source_dir, cache_dir, cfg.likec4_version)
        if env.likec4_format == "html":
            env.likec4_dist = str(_runner.ensure_build(
                source_dir, cache_dir, cfg.likec4_version, list(cfg.likec4_build_args)))
        if image_capable:
            env.likec4_images = {f: str(cache_dir / f"images-{f}") for f in sorted(formats)}
            env.likec4_images_seq = ({f: str(cache_dir / f"images-{f}-seq") for f in sorted(formats)}
                                     if dynamic else {})
            # Validate (and wipe/restamp when the sources changed) every image dir here, in
            # the main process before any read worker forks: two workers seeing a stale stamp
            # at once could wipe files one of them had just exported. No views → no CLI run.
            for f in sorted(formats):
                _runner.ensure_images(source_dir, cache_dir, cfg.likec4_version, f, [])
                if dynamic:
                    _runner.ensure_images(source_dir, cache_dir, cfg.likec4_version, f, [], seq=True)
            # Lazy export: the directives export what they embed (LikeC4View._image) and
            # remember it in env.likec4_needed; here, re-export the previous build's set in
            # one run per (format, layout) so doctrees that won't be re-read still find
            # their files after a source change wiped the dirs.
            # If the render target changed since the pickled env (builder switch, images
            # toggled), every document is re-read and exports on demand — a batched pass
            # now would render files the re-read immediately abandons (-M latexpdf followed
            # by -M html would start Chromium for nothing).
            expected_key = (env.likec4_format, env.likec4_render_default, image_capable)
            rerender_expected = getattr(env, "likec4_render_key", expected_key) != expected_key
            needed: dict[tuple[str, bool], set[str]] = {}
            if not rerender_expected:
                for entries in getattr(env, "likec4_needed", {}).values():
                    for view, f, seq in entries:
                        if f in formats and (not seq or view in dynamic):
                            needed.setdefault((f, seq), set()).add(view)
            try:
                for (f, seq), ids in sorted(needed.items()):
                    _runner.ensure_images(source_dir, cache_dir, cfg.likec4_version, f, ids, seq=seq)
            except RuntimeError as e:
                if env.likec4_render_default in ("png", "jpg"):
                    raise
                # this builder renders iframes by default — a browser problem must not kill it
                logger.warning("sphinx-likec4: image export failed; :render: png/jpg fall back "
                               "to %s — %s", env.likec4_render_default, e,
                               type="likec4", subtype="images")
                env.likec4_images = {}
                env.likec4_images_seq = {}
    except _runner.LikeC4Missing as e:
        if cfg.likec4_missing == "warn":
            logger.warning("sphinx-likec4: %s — views render as placeholders", e,
                           type="likec4", subtype="missing")
            env.likec4_mode = "warn"
            env.likec4_views = None
            env.likec4_dist = None
            env.likec4_images = {}
            env.likec4_images_seq = {}
            _set_render_key(env)
            return
        raise ConfigError(f"sphinx-likec4: {e} (set likec4_missing='warn' to build without it)")
    env.likec4_mode = "ready"
    env.likec4_views = views
    env.likec4_dynamic_views = dynamic
    _set_render_key(env)


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


def _set_render_key(env) -> None:
    """Remember what this build renders; a change since the pickled env re-reads every document.

    Availability of images is part of it: a build that fell back to iframes/placeholders
    (export failed, npx missing) must not leave those cached once images are back.
    """
    key = (env.likec4_format, env.likec4_render_default, bool(env.likec4_images))
    env.likec4_rerender = getattr(env, "likec4_render_key", key) != key
    env.likec4_render_key = key


def _env_get_outdated(app, env, added, changed, removed):
    """``env-get-outdated`` handler: re-read every document when the render target changed.

    ``-M html`` followed by ``-M latexpdf`` shares one doctree dir; without this, LaTeX
    would be handed the cached HTML iframe nodes and drop them silently.
    """
    return set(env.found_docs) if getattr(env, "likec4_rerender", False) else set()


def _env_purge_doc(app, env, docname):
    """``env-purge-doc``: forget what a removed/re-read document embedded."""
    getattr(env, "likec4_needed", {}).pop(docname, None)


def _env_merge_info(app, env, docnames, other):
    """``env-merge-info``: fold a parallel read worker's embeds into the main env."""
    theirs = getattr(other, "likec4_needed", {})
    env.likec4_needed.update({d: theirs[d] for d in docnames if d in theirs})


def setup(app):
    """Sphinx extension entry point: register config values, directives, and hooks."""
    from ._directives import LikeC4Model, LikeC4View
    app.add_config_value("likec4_source_dir", None, "env")
    app.add_config_value("likec4_version", DEFAULT_LIKEC4_VERSION, "env")
    app.add_config_value("likec4_missing", "error", "env")
    app.add_config_value("likec4_build_args", [], "env")
    app.add_config_value("likec4_render", {}, "env")
    app.add_config_value("likec4_export_images", True, "env")
    app.add_directive("likec4-view", LikeC4View)
    app.add_directive("likec4-model", LikeC4Model)
    app.connect("builder-inited", _builder_inited)
    app.connect("env-get-outdated", _env_get_outdated)
    app.connect("env-purge-doc", _env_purge_doc)
    app.connect("env-merge-info", _env_merge_info)
    app.connect("build-finished", _build_finished)
    return {"version": __version__, "parallel_read_safe": True, "parallel_write_safe": True}
