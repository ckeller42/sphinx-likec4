# Static PNG/JPG Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `likec4-view` render as a static PNG/JPG — per directive, per Sphinx output format, or by built-in default — so LaTeX/PDF and epub builds carry the diagrams instead of a text stub, and produce the docs PDF in CI.

**Architecture:** `_runner.py` gains `ensure_views` (cached `export json`) and `ensure_images` (cached `export png|jpg --flat`, with a one-shot Playwright Chromium install on first failure). `__init__._builder_inited` computes a per-builder default render mode, exports images for every image-capable builder (HTML included, png always), and records `env.likec4_render_default` / `env.likec4_images`. `_directives.LikeC4View` resolves `:render:` as a preference and emits a standard `nodes.image` whose URI is a path relative to the document into the cache — Sphinx's own image collector then copies/embeds per builder, so there is zero per-builder code.

**Tech Stack:** Python ≥3.10, Sphinx ≥7, docutils, pytest (+doctests), `likec4@1.59.2` via npx (Playwright `1.60.0` inside it), TeX Live + latexmk in CI only.

**Spec:** `docs/specs/2026-09-05-static-images-design.md` — read it first; this plan argues from it.

## Global Constraints

- Repo root `/Users/ckeller/src/sphinx-likec4`; work on branch `feat/static-images` (already exists, spec committed). **Never commit to `main`** — it is branch-protected; the work lands via one PR at the end.
- Local gate: `./test.sh` (ruff + `pytest src/ tests/` + strict sphinx html build). Run it before every commit. Bare `pytest` also works.
- Doctests live in `src/` docstrings and are collected (`--doctest-modules`); any new pure function gets one.
- Version pin is `likec4@1.59.2` (`DEFAULT_LIKEC4_VERSION` in `src/sphinx_likec4/__init__.py`). Never run unpinned `npx likec4`.
- Package version lives in **two** places that must match: `pyproject.toml:version` and `src/sphinx_likec4/__init__.py:__version__`.
- The directive surface is documented in **four** places: `README.md`, `docs/directives.md`, `skills/sphinx-likec4/SKILL.md`, `llms.txt`. Task 5 updates all four.
- Render modes are exactly `("iframe", "png", "jpg", "text")`. Only `png`/`jpg` are image modes.
- Cache layout under `<doctreedir>/likec4/`: `images-<fmt>/` + `images-<fmt>.stamp`; `views.stamp` + `views-only.json` for `ensure_views`. Existing `dist/`, `stamp`, `views.json`, `model.json` are `ensure_build`'s and stay untouched.
- Commit messages: conventional prefix (`feat:`/`test:`/`docs:`/`ci:`), imperative, body explains why. The harness appends attribution trailers.
- Tests never invoke a real `npx` except `tests/test_integration.py` (skipped without node). Everything else fakes `subprocess.run` or monkeypatches `_runner.*`.

---

## File Structure

| File | Responsibility after this plan |
|---|---|
| `src/sphinx_likec4/_runner.py` | CLI orchestration: `_require_npx`, `source_hash`, `_run`, `_view_ids`, `ensure_build` (unchanged), **`ensure_views`**, **`ensure_images`** |
| `src/sphinx_likec4/__init__.py` | Sphinx wiring; **`_default_render(builder, overrides)`**, `_builder_inited` decides what to export and stores `env.likec4_render_default`, `env.likec4_images`, `env.likec4_mode ∈ {"ready","warn","non-html"}` |
| `src/sphinx_likec4/_directives.py` | Directives; **`_render` validator, `_resolve_render`**, image branch in `LikeC4View.run`, plain text for `LikeC4Model` on non-HTML |
| `tests/test_runner.py` | fake-`subprocess.run` tests for `ensure_views` / `ensure_images` |
| `tests/test_extension.py` | in-process Sphinx builds (html/latex/text) with `_runner` monkeypatched |
| `tests/test_integration.py` | real npx: html + latex builds with a real PNG export |
| `tests/test_setup.py` | config registration |
| `docs/*.md`, `docs/conf.py`, `README.md`, `skills/sphinx-likec4/SKILL.md`, `llms.txt` | user docs, example image, PDF link, `latex_engine` |
| `.github/workflows/ci.yml` | TeX install + `latexpdf` + PDF into the Pages site |

---

### Task 1: Runner — `ensure_views` and `ensure_images` (with Playwright install-and-retry)

**Files:**
- Modify: `src/sphinx_likec4/_runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: existing `source_hash(source_dir, version, build_args) -> str`, `_run(npx, args, cwd)` (raises `RuntimeError` whose message contains stdout+stderr), `_view_ids(data) -> set[str]`, `LikeC4Missing`.
- Produces:
  - `_require_npx() -> str` — path to npx or raises `LikeC4Missing`.
  - `ensure_views(source_dir: Path, cache_dir: Path, version: str) -> set[str]`
  - `ensure_images(source_dir: Path, cache_dir: Path, version: str, fmt: str) -> Path` — returns `cache_dir / f"images-{fmt}"` containing `<view-id>.<fmt>` files.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_runner.py`:

```python
def _fake_cli(calls, fail_first_export_with: bytes | None = None):
    """subprocess.run stand-in: fakes `likec4 export json|png|jpg` and `playwright install`."""
    state = {"failed": False}

    def fake_run(cmd, **kw):
        calls.append(cmd)
        ok = type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()
        if "export" not in cmd:                       # playwright install
            return ok
        fmt = cmd[cmd.index("export") + 1]
        if fmt == "json":
            Path(cmd[cmd.index("-o") + 1]).write_text(json.dumps({"views": {"index": {}}}))
            return ok
        if fail_first_export_with and not state["failed"]:
            state["failed"] = True
            return type("R", (), {"returncode": 1, "stdout": b"", "stderr": fail_first_export_with})()
        out = Path(cmd[cmd.index("-o") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / f"index.{fmt}").write_bytes(b"img")
        return ok

    return fake_run


def test_ensure_views_runs_export_json_once_then_caches(tmp_path, monkeypatch):
    src = _model(tmp_path)
    calls = []
    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", _fake_cli(calls))

    assert _runner.ensure_views(src, tmp_path / "c", "1.59.2") == {"index"}
    assert len(calls) == 1 and "json" in calls[0]
    assert _runner.ensure_views(src, tmp_path / "c", "1.59.2") == {"index"}
    assert len(calls) == 1                                  # cache hit


def test_ensure_images_exports_flat_then_caches(tmp_path, monkeypatch):
    src = _model(tmp_path)
    calls = []
    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", _fake_cli(calls))

    out = _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png")
    assert out == tmp_path / "c" / "images-png"
    assert (out / "index.png").exists()
    cmd = calls[0]
    assert cmd[:2] == ["npx", "-y"] and "likec4@1.59.2" in cmd
    assert cmd[cmd.index("export") + 1] == "png" and "--flat" in cmd
    assert cmd[cmd.index("-o") + 1] == str(out) and cmd[-1] == str(src)

    assert _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png") == out
    assert len(calls) == 1                                  # cache hit

    jpg = _runner.ensure_images(src, tmp_path / "c", "1.59.2", "jpg")
    assert jpg == tmp_path / "c" / "images-jpg" and len(calls) == 2   # separate cache per format


def test_ensure_images_installs_chromium_once_when_playwright_is_missing(tmp_path, monkeypatch):
    src = _model(tmp_path)
    calls = []
    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", _fake_cli(
        calls, fail_first_export_with=b"browserType.launch: Executable doesn't exist. "
                                      b"Please run: npx playwright install"))

    out = _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png")
    assert (out / "index.png").exists()
    assert [("export" in c, "install" in " ".join(c)) for c in calls] == [
        (True, False), (False, True), (True, False)]
    install = calls[1]
    assert install[:2] == ["npx", "-y"]
    assert install[install.index("--package") + 1] == "likec4@1.59.2"
    assert install[install.index("-c") + 1] == "playwright install chromium"


def test_ensure_images_reraises_non_playwright_failures(tmp_path, monkeypatch):
    src = _model(tmp_path)
    calls = []
    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", _fake_cli(
        calls, fail_first_export_with=b"Error: invalid view predicate"))
    with pytest.raises(RuntimeError, match="invalid view predicate"):
        _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png")
    assert len(calls) == 1                                  # no install attempt, no retry


def test_ensure_images_and_views_raise_when_npx_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(_runner, "_npx", lambda: None)
    with pytest.raises(_runner.LikeC4Missing):
        _runner.ensure_images(_model(tmp_path), tmp_path / "c", "1.59.2", "png")
    with pytest.raises(_runner.LikeC4Missing):
        _runner.ensure_views(_model(tmp_path), tmp_path / "c", "1.59.2")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_runner.py -q`
Expected: the 5 new tests FAIL with `AttributeError: module 'sphinx_likec4._runner' has no attribute 'ensure_views'` / `'ensure_images'`; the 3 existing tests still pass.

- [ ] **Step 3: Implement**

In `src/sphinx_likec4/_runner.py`, add after `_npx()`:

```python
def _require_npx() -> str:
    """Return the ``npx`` path, or raise :class:`LikeC4Missing` when node isn't installed."""
    npx = _npx()
    if npx is None:
        raise LikeC4Missing("npx not found on PATH — node >= 20 is required to build LikeC4 views")
    return npx
```

In `ensure_build`, replace the three lines

```python
    npx = _npx()
    if npx is None:
        raise LikeC4Missing("npx not found on PATH — node >= 20 is required to build LikeC4 views")
```

with

```python
    npx = _require_npx()
```

Append at the end of the module:

```python
def ensure_views(source_dir: Path, cache_dir: Path, version: str) -> set[str]:
    """Return the model's view ids via ``likec4 export json`` (cached on the source hash).

    For builders that need images but no viewer build (LaTeX, epub…); ``ensure_build``
    keeps its own copy of this step because its stamp already covers it.
    """
    npx = _require_npx()
    cache_dir.mkdir(parents=True, exist_ok=True)
    stamp, views_file = cache_dir / "views.stamp", cache_dir / "views-only.json"
    digest = source_hash(source_dir, version, ["json"])
    if stamp.exists() and stamp.read_text() == digest and views_file.exists():
        return set(json.loads(views_file.read_text()))
    export = cache_dir / "model.json"
    _run(npx, [f"likec4@{version}", "export", "json", "-o", str(export), str(source_dir)],
         cwd=source_dir)
    views = _view_ids(json.loads(export.read_text()))
    views_file.write_text(json.dumps(sorted(views)))
    stamp.write_text(digest)
    return views


def ensure_images(source_dir: Path, cache_dir: Path, version: str, fmt: str) -> Path:
    """Export every view as ``<view-id>.<fmt>`` into ``cache_dir/images-<fmt>`` (cached).

    ``fmt`` is ``"png"`` or ``"jpg"``. The export drives headless Chromium through
    Playwright; if the first attempt fails for lack of a browser, install Chromium once
    through likec4's *own* Playwright (so the browser revision matches) and retry. Any
    other failure, or a second one, propagates as ``RuntimeError``.
    """
    npx = _require_npx()
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"images-{fmt}"
    stamp = cache_dir / f"images-{fmt}.stamp"
    digest = source_hash(source_dir, version, [fmt])
    if stamp.exists() and stamp.read_text() == digest and out.is_dir():
        return out
    shutil.rmtree(out, ignore_errors=True)
    cli = f"likec4@{version}"
    export = [cli, "export", fmt, "--flat", "-o", str(out), str(source_dir)]
    try:
        _run(npx, export, cwd=source_dir)
    except RuntimeError as e:
        if "playwright" not in str(e).lower():
            raise
        _run(npx, ["--package", cli, "-c", "playwright install chromium"], cwd=source_dir)
        _run(npx, export, cwd=source_dir)
    stamp.write_text(digest)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_runner.py -q`
Expected: 8 passed.

- [ ] **Step 5: Verify the one assumption that needs a real browser — `--flat` names files `<view-id>.<fmt>`**

Run (downloads Chromium ≈150 MB the first time; that is the auto-install path working for real):

```bash
rm -rf /tmp/likec4-flat && cd /Users/ckeller/src/sphinx-likec4 && .venv/bin/python -c "
from pathlib import Path; from sphinx_likec4 import _runner
out = _runner.ensure_images(Path('tests/roots/test-basic/model').resolve(), Path('/tmp/likec4-flat'), '1.59.2', 'png')
print(sorted(p.name for p in out.iterdir()))"
```

Expected: `['index.png']`. If the listing shows a subdirectory or a different name, the flat naming assumption is wrong — stop, report the actual layout, and adjust `LikeC4View`'s file lookup in Task 4 accordingly (`out / f"{view}.{fmt}"` is what it assumes).

- [ ] **Step 6: Gate and commit**

Run: `./test.sh` → expect `local gate: OK`.

```bash
git add src/sphinx_likec4/_runner.py tests/test_runner.py
git commit -m "feat(runner): cached export of view ids and PNG/JPG images

ensure_views mirrors ensure_build's json step for builders that need no viewer;
ensure_images exports all views flat into a per-format cache dir. A first
export failure mentioning Playwright triggers a one-shot Chromium install via
likec4's own Playwright (matching browser revision) and one retry."
```

---

### Task 2: Directive-side render resolution (pure function + validator)

**Files:**
- Modify: `src/sphinx_likec4/_directives.py` (module level, above `class LikeC4View`)

**Interfaces:**
- Produces:
  - `_RENDER_MODES = ("iframe", "png", "jpg", "text")`
  - `_render(argument) -> str` — docutils option validator.
  - `_resolve_render(requested: str | None, default: str, is_html: bool, images: dict) -> str` — raises `sphinx.errors.ExtensionError` for an image format that was not exported.

- [ ] **Step 1: Write the doctests (they are the tests)**

Insert after `_height` in `src/sphinx_likec4/_directives.py`:

```python
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
    >>> _resolve_render("jpg", "png", False, {"png": "/c"})  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    ExtensionError: likec4-view: ':render: jpg' needs "jpg" in likec4_render
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
```

- [ ] **Step 2: Run the doctests to verify they pass**

Run: `.venv/bin/python -m pytest src/sphinx_likec4/_directives.py -q`
Expected: 6 passed (4 existing doctests + `_render` + `_resolve_render`). If `_resolve_render` fails on the exception line, check that `+IGNORE_EXCEPTION_DETAIL` is on that example — it makes doctest ignore the `sphinx.errors.` module prefix.

- [ ] **Step 3: Gate and commit**

Run: `./test.sh` → `local gate: OK`.

```bash
git add src/sphinx_likec4/_directives.py
git commit -m "feat(directives): render-mode validator and resolver

:render: is a preference: iframe falls back to the builder default off HTML,
images fall back on builders with no image support, and asking for a format
that was not exported is an authoring error naming the fix."
```

---

### Task 3: Builder wiring — default mode, image export, new env state

**Files:**
- Modify: `src/sphinx_likec4/__init__.py`
- Modify: `tests/test_extension.py` (fixtures + new tests)
- Modify: `tests/test_setup.py`

**Interfaces:**
- Consumes: `_runner.ensure_build`, `_runner.ensure_views`, `_runner.ensure_images`, `_runner.LikeC4Missing` (Task 1).
- Produces (read by Task 4's directives):
  - config `likec4_render: dict[str, str]` (default `{}`, rebuild `"env"`)
  - `_default_render(builder, overrides: dict) -> str`
  - `env.likec4_mode ∈ {"ready", "warn", "non-html"}` (`"ready"` replaces the old `"html"`)
  - `env.likec4_render_default: str`
  - `env.likec4_images: dict[str, str]` — format → absolute directory holding `<view-id>.<fmt>`
  - `env.likec4_views`, `env.likec4_dist`, `env.likec4_sources` as before (`likec4_dist` is `None` off HTML)

- [ ] **Step 1: Update fixtures and write the failing tests**

In `tests/test_extension.py`, replace the `fake_build` fixture and `_build` helper with:

```python
# 1×1 transparent PNG; Sphinx only sniffs the header, so it also stands in for .jpg files
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da"
    "63f8ffff3f0300050001ff5fd5ac0000000049454e44ae426082")


@pytest.fixture(autouse=True)
def fake_images(monkeypatch):
    """Every image-capable build exports images; fake both export entry points, record formats."""
    calls = []

    def fake(source_dir, cache_dir, version, fmt):
        calls.append(fmt)
        out = cache_dir / f"images-{fmt}"
        out.mkdir(parents=True, exist_ok=True)
        for view in ("index", "seqA"):
            (out / f"{view}.{fmt}").write_bytes(_PNG)
        return out

    monkeypatch.setattr(_runner, "ensure_images", fake)
    monkeypatch.setattr(_runner, "ensure_views", lambda source_dir, cache_dir, version: {"index", "seqA"})
    return calls


@pytest.fixture
def fake_build(monkeypatch):
    calls = []

    def fake(source_dir, cache_dir, version, build_args):
        calls.append(build_args)
        dist = cache_dir / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "index.html").write_text("<html>fake viewer</html>")
        return dist, {"index", "seqA"}
    monkeypatch.setattr(_runner, "ensure_build", fake)
    return calls


def _app(tmp_path, srcdir=ROOT, confoverrides=None, builder="html", strict=True):
    out = tmp_path / "out"
    app = Sphinx(str(srcdir), str(srcdir), str(out), str(tmp_path / "doctrees"),
                 builder, confoverrides=confoverrides or {}, warningiserror=strict)
    app.build()
    return app, out


def _build(tmp_path, srcdir=ROOT, confoverrides=None):
    return _app(tmp_path, srcdir, confoverrides)[1]
```

Append these tests:

```python
def test_html_default_is_iframe_and_still_exports_png(tmp_path, fake_build, fake_images):
    app, _ = _app(tmp_path)
    assert app.env.likec4_mode == "ready"
    assert app.env.likec4_render_default == "iframe"
    assert set(app.env.likec4_images) == {"png"} and fake_images == ["png"]
    assert app.env.likec4_dist is not None


def test_latex_default_is_png_without_viewer_build(tmp_path, fake_build, fake_images):
    app, _ = _app(tmp_path, builder="latex")
    assert app.env.likec4_mode == "ready"
    assert app.env.likec4_render_default == "png"
    assert fake_images == ["png"]
    assert fake_build == []                                 # no viewer build off HTML
    assert app.env.likec4_dist is None
    assert app.env.likec4_views == {"index", "seqA"}        # ids come from ensure_views


def test_text_builder_exports_nothing(tmp_path, fake_images):
    app, _ = _app(tmp_path, builder="text")
    assert app.env.likec4_mode == "non-html"
    assert app.env.likec4_render_default == "text"
    assert fake_images == []


def test_likec4_render_override_adds_jpg_export(tmp_path, fake_build, fake_images):
    app, _ = _app(tmp_path, builder="latex", confoverrides={"likec4_render": {"latex": "jpg"}})
    assert app.env.likec4_render_default == "jpg"
    assert sorted(fake_images) == ["jpg", "png"]            # png is always exported


def test_likec4_render_for_another_format_still_exports_that_format(tmp_path, fake_build, fake_images):
    # an HTML build must export jpg too when some other builder's config names it —
    # the same .rst may carry ":render: jpg" and the resolver only knows what was exported
    _app(tmp_path, confoverrides={"likec4_render": {"latex": "jpg"}})
    assert sorted(fake_images) == ["jpg", "png"]


def test_likec4_render_rejects_unknown_mode(tmp_path, fake_build):
    with pytest.raises(SphinxError, match="likec4_render"):
        _app(tmp_path, confoverrides={"likec4_render": {"html": "svg"}})


def test_epub_is_image_capable(tmp_path, fake_build, fake_images):
    # strict=False: Sphinx's epub builder warns about its own unset epub_* config values,
    # which has nothing to do with this extension
    app, _ = _app(tmp_path, builder="epub", strict=False)
    assert app.env.likec4_render_default == "png" and fake_images == ["png"]
```

In `tests/test_setup.py` add to `test_setup_registers_config_values`:

```python
    assert app.config_values["likec4_render"] == ({}, "env")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_extension.py tests/test_setup.py -q`
Expected: new tests FAIL (`AttributeError: ... likec4_render_default` / `ConfigError`-less build / `likec4_render` unknown config). Existing tests may also fail on `likec4_mode == "html"` assumptions — that is expected until Step 3.

- [ ] **Step 3: Implement**

In `src/sphinx_likec4/__init__.py`, add after `logger = ...` (the mode tuple itself lives in
`_directives._RENDER_MODES` from Task 2 — import it, don't duplicate it):

```python
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
```

Replace the whole body of `_builder_inited` (keep its docstring, updating the mode list) with:

```python
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
    env.likec4_render_default = _default_render(app.builder, cfg.likec4_render)
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
        if app.builder.format == "html":
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
```

In `setup()`, add after the `likec4_build_args` line:

```python
    app.add_config_value("likec4_render", {}, "env")
```

In `src/sphinx_likec4/_directives.py`, both `run` methods read `getattr(env, "likec4_mode", "html")` — change the default literal to `"ready"` in both places (the value is otherwise unused by the directives until Task 4).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest src/ tests/ -q`
Expected: all pass (the pre-existing extension tests still pass because HTML defaults are unchanged and `fake_images` is autouse).

- [ ] **Step 5: Gate and commit**

Run: `./test.sh` → `local gate: OK`.

```bash
git add src/sphinx_likec4/__init__.py src/sphinx_likec4/_directives.py tests/test_extension.py tests/test_setup.py
git commit -m "feat: per-builder default render mode and image export at builder-inited

Builders that can embed images get png exported (jpg when likec4_render asks);
LaTeX/epub take view ids from export json instead of a viewer build; builders
without image support (text, linkcheck) export nothing. likec4_mode 'html'
becomes 'ready' since it now also covers non-HTML builders."
```

---

### Task 4: Directive image branch, passthrough options, model text off HTML

**Files:**
- Modify: `src/sphinx_likec4/_directives.py` (`LikeC4View`, `LikeC4Model`)
- Test: `tests/test_extension.py`

**Interfaces:**
- Consumes: `_resolve_render`, `_render`, `_RENDER_MODES` (Task 2); `env.likec4_mode`, `env.likec4_render_default`, `env.likec4_images`, `env.likec4_views`, `env.likec4_sources` (Task 3); `env.app.builder.format`; `env.doc2path(env.docname)`.
- Produces: `likec4-view` options `render`, `width`, `alt`, `align`, `scale`; image mode emits `nodes.image`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_extension.py`:

```python
def _src(tmp_path, name, index_rst):
    src = tmp_path / name
    shutil.copytree(ROOT, src)
    (src / "index.rst").write_text(index_rst)
    (src / "sub" / "page.rst").unlink()
    return src


def test_render_png_on_html_emits_img_and_copies_file(tmp_path, fake_build):
    src = _src(tmp_path, "s", "P\n=\n\n.. likec4-view:: index\n   :render: png\n   :width: 50%\n")
    out = _build(tmp_path, srcdir=src)
    html = (out / "index.html").read_text()
    assert "<iframe" not in html
    assert 'src="_images/index.png"' in html
    assert 'alt="LikeC4 view index"' in html
    assert "width: 50%" in html
    assert (out / "_images" / "index.png").exists()


def test_alt_defaults_to_title(tmp_path, fake_build):
    src = _src(tmp_path, "s", "P\n=\n\n.. likec4-view:: index\n   :render: png\n   :title: Cloud\n")
    assert 'alt="Cloud"' in (_build(tmp_path, srcdir=src) / "index.html").read_text()


def test_latex_embeds_png_by_default(tmp_path, fake_build):
    _, out = _app(tmp_path, builder="latex")
    tex = next(out.glob("*.tex")).read_text()
    assert "\\sphinxincludegraphics" in tex and "index.png" in tex
    assert (out / "index.png").exists()
    assert "LikeC4 model (interactive" in tex                # likec4-model stays plain text off HTML


def test_render_iframe_falls_back_to_png_on_latex(tmp_path, fake_build):
    src = _src(tmp_path, "s", "P\n=\n\n.. likec4-view:: index\n   :render: iframe\n")
    _, out = _app(tmp_path, srcdir=src, builder="latex")
    assert "\\sphinxincludegraphics" in next(out.glob("*.tex")).read_text()


def test_render_png_on_text_builder_falls_back_to_text(tmp_path):
    src = _src(tmp_path, "s", "P\n=\n\n.. likec4-view:: index\n   :render: png\n")
    _, out = _app(tmp_path, srcdir=src, builder="text")
    assert "LikeC4 view 'index'" in (out / "index.txt").read_text()


def test_likec4_render_html_png_turns_every_view_static(tmp_path, fake_build):
    out = _build(tmp_path, confoverrides={"likec4_render": {"html": "png"}})
    html = (out / "index.html").read_text()
    assert '<iframe class="likec4-view"' not in html
    assert html.count('_images/') >= 2                       # index + seqA
    assert '<iframe class="likec4-model"' in html            # model embed unaffected on HTML


def test_render_jpg_without_config_is_an_error(tmp_path, fake_build):
    src = _src(tmp_path, "s", "P\n=\n\n.. likec4-view:: index\n   :render: jpg\n")
    with pytest.raises(SphinxError, match="likec4_render"):
        _build(tmp_path, srcdir=src)


def test_render_jpg_with_config_works(tmp_path, fake_build):
    src = _src(tmp_path, "s", "P\n=\n\n.. likec4-view:: index\n   :render: jpg\n")
    out = _build(tmp_path, srcdir=src, confoverrides={"likec4_render": {"latex": "jpg"}})
    assert 'src="_images/index.jpg"' in (out / "index.html").read_text()


def test_unknown_view_id_fails_latex_build_too(tmp_path, fake_build):
    src = _src(tmp_path, "s", "Bad\n===\n\n.. likec4-view:: nope\n")
    with pytest.raises(SphinxError):
        _app(tmp_path, srcdir=src, builder="latex")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_extension.py -q`
Expected: the 9 new tests FAIL (`render` is an unknown option → `SphinxError`; latex `.tex` lacks `\sphinxincludegraphics`).

- [ ] **Step 3: Implement**

In `src/sphinx_likec4/_directives.py`:

Add imports at the top:

```python
import os
from pathlib import Path

from docutils.parsers.rst.directives.images import Image
```

Add a module-level helper after `_placeholder`:

```python
def _text(text: str) -> nodes.paragraph:
    """Plain-text stand-in for builders that can't embed the viewer or an image."""
    para = nodes.paragraph()
    para += nodes.Text(text)
    return para
```

Replace `LikeC4View` entirely:

```python
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
            return [_text(f"LikeC4 view {view!r} (interactive — see the HTML docs)")]
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
        render = _resolve_render(self.options.get("render"), env.likec4_render_default,
                                 env.app.builder.format == "html", env.likec4_images)
        title = self.options.get("title", f"LikeC4 view {view}")
        if render == "text":
            return [_text(f"LikeC4 view {view!r} (interactive — see the HTML docs)")]
        if render in ("png", "jpg"):
            return [self._image(env, view, render, title)]
        height = self.options.get("height", "460px")
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
        uri = os.path.relpath(file, os.path.dirname(env.doc2path(env.docname)))
        opts = {k: v for k, v in self.options.items() if k in ("width", "height", "alt", "align", "scale")}
        opts.setdefault("alt", title)
        return nodes.image(uri=uri, **opts)
```

In `LikeC4Model.run`, after the `if mode == "warn":` block, add:

```python
        if env.app.builder.format != "html":               # the gallery has no single-image form
            return [_text("LikeC4 model (interactive — see the HTML docs)")]
```

and replace its existing `non-html` branch body (the two-line `para` construction) with `return [_text("LikeC4 model (interactive — see the HTML docs)")]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest src/ tests/ -q`
Expected: all pass. If `test_render_png_on_html_emits_img_and_copies_file` fails on `width: 50%`, check the html: Sphinx renders `<img ... style="width: 50%" .../>` — the assertion is on that substring.

- [ ] **Step 5: Gate and commit**

Run: `./test.sh` → `local gate: OK`.

```bash
git add src/sphinx_likec4/_directives.py tests/test_extension.py
git commit -m "feat(directives): render views as static PNG/JPG images

:render: selects iframe|png|jpg|text as a preference resolved against the
builder; image mode emits a standard image node into the export cache so
Sphinx's own collector copies or embeds it per builder. width/alt/align/scale
pass through with the docutils image validators; likec4-model degrades to
plain text off HTML."
```

---

### Task 5: User docs, agent skill, llms.txt, version bump

**Files:**
- Modify: `docs/example.md`, `docs/directives.md`, `docs/configuration.md`, `docs/index.md`, `docs/conf.py`
- Modify: `README.md`, `skills/sphinx-likec4/SKILL.md`, `llms.txt`
- Modify: `pyproject.toml`, `src/sphinx_likec4/__init__.py`

**Interfaces:**
- Consumes: option names from Task 4, config name from Task 3.
- Produces: nothing code-facing. The docs build (`./test.sh` third stage) is the test — it runs a **real** `likec4 export png` of the 19-view docs model (Chromium download on first run, then cached).

- [ ] **Step 1: Add the visible image example**

Append to `docs/example.md` before the `Source:` line:

````markdown
## Static image

The same structural view rendered as a **PNG** — this is what every non-HTML builder
(LaTeX/PDF, epub) gets by default, and what `:render: png` gives you on an HTML page:

```{likec4-view} cloud
:render: png
:width: 100%
:alt: cloud-system structural view, static PNG
```
````

- [ ] **Step 2: Document the directive option**

In `docs/directives.md`, after the paragraph ending `(appends the viewer's `?dynamic=` parameter):` and its code block, insert:

````markdown
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
````

Also update the `Options:` sentence to start with: ``Options: `height` (default `460px`), `title` (iframe title, for accessibility), `render` (see [Static images](#static-images)), and `mode` — …``

- [ ] **Step 3: Document the config value and the browser dependency**

In `docs/configuration.md`, add a table row after `likec4_build_args`:

```markdown
| `likec4_render` | `{}` | default render mode per output format, e.g. `{"latex": "jpg", "html": "png"}`; values `iframe`, `png`, `jpg`, `text` |
```

Append after the `suppress_warnings` paragraph:

````markdown
## Static images and PDF

Any builder that can embed images (LaTeX, epub — and HTML, for `:render: png`) exports every
view once via `likec4 export png --flat`, cached on the same content hash as the viewer. The
export renders in headless Chromium through Playwright. If no browser is present the extension
installs one **once**, using likec4's own Playwright so the revision matches:

```bash
npx -y --package likec4@1.59.2 -c 'playwright install chromium'   # what it runs for you
```

(≈150 MB, into Playwright's cache under your home directory.) On a minimal Linux CI image add
`--with-deps` to that command yourself if Chromium complains about missing shared libraries.

For a PDF: `sphinx-build -M latexpdf docs docs/_build` — nothing LikeC4-specific to configure.
The extension's own docs use `latex_engine = "xelatex"` for the Unicode arrows in the text.
````

- [ ] **Step 4: Link the PDF and switch the LaTeX engine**

In `docs/index.md`, after the first paragraph add:

```markdown
Also available as a [PDF](https://ckeller42.github.io/sphinx-likec4/sphinx-likec4.pdf) — built by
the same extension, with every view rendered as a static image.
```

(An absolute URL, deliberately: a relative link to a file that isn't in the source tree fails the
strict MyST build.)

In `docs/conf.py` append:

```python
latex_engine = "xelatex"        # Unicode arrows/≥ in the prose; pdflatex has no glyphs for them
```

- [ ] **Step 5: README, agent skill, llms.txt**

`README.md` — in the Quickstart, after the ` .. likec4-view:: cloud-to-amazon ` block add:

````markdown
Non-HTML builders (LaTeX/PDF, epub) get the views as static PNGs automatically; `:render: png`
does the same on an HTML page. See the [docs](https://ckeller42.github.io/sphinx-likec4/) —
also as a [PDF](https://ckeller42.github.io/sphinx-likec4/sphinx-likec4.pdf).
````

`skills/sphinx-likec4/SKILL.md` — in the `## Directives` rst block, after the line
`   :mode: sequence           # optional: diagram (default) | sequence — dynamic views only`
add:

```
   :render: png              # optional: iframe (HTML default) | png | jpg | text — a preference; non-HTML builders default to png
   :width: 80%               # image-mode passthroughs: width, height, alt, align, scale
```

and in `## Setup` after the `likec4_source_dir` line add:

```python
likec4_render = {"latex": "jpg"}     # optional: default render mode per output format
```

`llms.txt` — read it, then add one bullet under whatever list describes directives/config (keep
its existing style): `` `likec4-view` `:render:` iframe|png|jpg|text and `likec4_render` config
select static PNG/JPG per directive or per output format; non-HTML builders (PDF, epub) default to
PNG. Export uses Playwright/Chromium via the likec4 CLI; a browser is installed once if missing. ``

- [ ] **Step 6: Bump the version in both places**

`pyproject.toml`: `version = "0.2.0"`. `src/sphinx_likec4/__init__.py`: `__version__ = "0.2.0"`.

- [ ] **Step 7: Build the docs for real (this is the test) and gate**

Run: `./test.sh`
Expected: `local gate: OK`. The third stage runs a real Playwright export of the docs model; the
first run downloads Chromium (minutes), later runs hit the cache. Then check the rendered page:

Run: `grep -c '<img' docs/_build/html/example.html && grep -o 'src="_images/cloud[^"]*"' docs/_build/html/example.html`
Expected: a count ≥ 1 and `src="_images/cloud.png"`.

Also confirm the PDF pipeline is at least structurally sound without TeX:

Run: `.venv/bin/python -m sphinx -q -b latex -W docs docs/_build/latex && ls docs/_build/latex/*.png | head -3 && grep -c sphinxincludegraphics docs/_build/latex/sphinx-likec4.tex`
Expected: png files listed, count ≥ 3 (index, cloud, cloud-to-amazon, and the `:render: png` one).

- [ ] **Step 8: Commit**

```bash
git add docs README.md skills/sphinx-likec4/SKILL.md llms.txt pyproject.toml src/sphinx_likec4/__init__.py
git commit -m "docs: static image example, :render:/likec4_render reference, PDF link; 0.2.0"
```

---

### Task 6: Real-CLI integration tests and CI PDF build

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `.github/workflows/ci.yml` (`docs-build` job)

**Interfaces:**
- Consumes: everything above. `sphinx -M latexpdf` produces `docs/_build/latex/sphinx-likec4.pdf` (Sphinx derives the name from `project = "sphinx-likec4"`).

- [ ] **Step 1: Extend the integration test (real npx; skipped without node)**

Replace the body of `test_real_likec4_build_end_to_end` in `tests/test_integration.py` and add a latex sibling:

```python
def _src(tmp_path):
    src = tmp_path / "src"
    shutil.copytree(ROOT, src)
    # only the structural view exists in the real model — drop the fake-only seqA embed
    (src / "index.rst").write_text(
        "Basic\n=====\n\n.. likec4-view:: index\n\n"
        ".. likec4-view:: index\n   :render: png\n   :width: 60%\n\n"
        ".. likec4-model::\n   :link-only:\n")
    (src / "sub" / "page.rst").unlink()
    return src


def test_real_likec4_build_end_to_end(tmp_path):
    src = _src(tmp_path)
    out = tmp_path / "out"
    app = Sphinx(str(src), str(src), str(out), str(tmp_path / "dt"), "html",
                 warningiserror=True)
    app.build()
    assert (out / "_likec4" / "index.html").exists()
    html = (out / "index.html").read_text()
    assert 'src="_likec4/#/view/index/"' in html
    assert 'src="_images/index.png"' in html                # real export, --flat naming
    assert (out / "_images" / "index.png").stat().st_size > 1000


def test_real_likec4_latex_embeds_png(tmp_path):
    src = _src(tmp_path)
    out = tmp_path / "out"
    app = Sphinx(str(src), str(src), str(out), str(tmp_path / "dt"), "latex",
                 warningiserror=True)
    app.build()
    assert "\\sphinxincludegraphics" in next(out.glob("*.tex")).read_text()
    assert (out / "index.png").stat().st_size > 1000
```

- [ ] **Step 2: Run the integration tests locally**

Run: `.venv/bin/python -m pytest tests/test_integration.py -q -p no:cacheprovider`
Expected: 2 passed (uses the Chromium installed in Task 1 step 5). If it is skipped, node is not on PATH — CI will run it.

- [ ] **Step 3: CI — install TeX, build the PDF, ship it with the Pages site**

In `.github/workflows/ci.yml`, in the `docs-build` job replace

```yaml
      - run: pip install -e .[docs]
      - run: python -m sphinx -b html -W docs docs/_build/html
      - uses: actions/upload-pages-artifact@v5
```

with

```yaml
      - run: pip install -e .[docs]
      - name: Install TeX Live (PDF)
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends latexmk texlive-latex-recommended \
            texlive-latex-extra texlive-fonts-recommended texlive-xetex fonts-freefont-otf
      - run: python -m sphinx -b html -W docs docs/_build/html
      - name: Build PDF
        run: python -m sphinx -M latexpdf docs docs/_build -W
      - run: cp docs/_build/latex/sphinx-likec4.pdf docs/_build/html/
      - uses: actions/upload-pages-artifact@v5
```

Do **not** add a Playwright pre-install step: the extension's own install-on-first-failure path is
what should run in CI. GitHub's `ubuntu-latest` image already carries Chromium's shared libraries.
**Contingency (only if the first CI run fails inside `ensure_images` with a missing-library error
such as `libnss3.so` / `error while loading shared libraries`):** add, before the html build in
`docs-build` and before `pytest` in `test`,
`- run: npx -y --package likec4@1.59.2 -c 'playwright install --with-deps chromium'`.

- [ ] **Step 4: Validate the workflow file and gate**

Run: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')" && ./test.sh`
Expected: `yaml ok` then `local gate: OK`.

- [ ] **Step 5: Commit, push, open the PR**

```bash
git add tests/test_integration.py .github/workflows/ci.yml
git commit -m "ci: build the docs PDF with xelatex and publish it with the Pages site

Integration tests now exercise the real PNG export (html and latex), which
also verifies likec4's --flat naming end to end."
git push -u origin feat/static-images
gh pr create --title "feat: render views as static PNG/JPG; docs PDF in CI" --body "$(cat <<'EOF'
## Summary
- `likec4-view` gains `:render: iframe|png|jpg|text` (a preference resolved per builder) plus image passthroughs `width`/`alt`/`align`/`scale`; `likec4_render` config sets the default per output format.
- Non-HTML builders (LaTeX/PDF, epub) now embed views as PNG instead of a text stub; builders without image support export nothing.
- `_runner.ensure_images` exports all views flat into a hash-cached dir; installs Playwright's Chromium once via likec4's own Playwright if missing.
- Docs: static-image example, reference for the new option/config, PDF link; `latex_engine = xelatex`.
- CI: TeX Live + `latexpdf`, PDF published at `/sphinx-likec4.pdf` on the Pages site.
- Version 0.2.0.

Spec: `docs/specs/2026-09-05-static-images-design.md`. Plan: `docs/plans/2026-09-05-static-images.md`.

## Test plan
- [ ] CI green, including the real-npx integration tests (png export) and the PDF build
- [ ] After merge: `https://ckeller42.github.io/sphinx-likec4/example.html` shows the static PNG; `/sphinx-likec4.pdf` downloads and page 3+ contains diagrams
EOF
)"
```

- [ ] **Step 6: Watch CI and finish**

Run: `gh pr checks --watch` (then `gh run view --log-failed` on any red job). Expected: all jobs green. Known first-run risks and their fixes, in order of likelihood:
1. Chromium shared libraries missing → apply the Task 6 Step 3 contingency.
2. `latexpdf` fails on a glyph → the docs contain a character xelatex's default fonts lack; find it with `grep -n` on the character in `docs/_build/latex/*.log` and replace it in the `.md` source.
3. `docs-build` exceeds the default job timeout → not expected (TeX ≈ 2–3 min, export ≈ 1 min); if it does, split the PDF into its own job with `needs: docs-build` and download the html artifact.

Merging is the user's call (repo convention: PR review + merge from the main session, not from a subagent).
