# sphinx-likec4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pip-installable Sphinx extension that builds a LikeC4 model with the pinned CLI and embeds its interactive views (including `dynamic view` sequences) in Sphinx HTML docs.

**Architecture:** Three small modules — `_runner.py` (hash-cached `npx likec4` build + view-id collection), `_directives.py` (`likec4-view`, `likec4-model`), `__init__.py` (Sphinx wiring: config, `builder-inited`, `build-finished` copy to `_likec4/`). Docs dogfood the extension with LikeC4's official `cloud-system` example.

**Tech Stack:** Python ≥3.10, Sphinx ≥7, hatchling, pytest; Node ≥20 + `likec4@1.59.2` via npx at doc-build time only.

**Spec:** `docs/specs/2026-08-30-sphinx-likec4-design.md` (same repo — read it first).

## Global Constraints

- Repo root: `/Users/ckeller/src/sphinx-likec4` (git already initialized, branch `main`; the spec is committed).
- Package name `sphinx-likec4`, module `sphinx_likec4`, license MIT.
- Default pinned CLI: `likec4_version = "1.59.2"` — never invoke unpinned `likec4`.
- Every `likec4 build` MUST pass `--use-hash-history` and `--base ./` (subpath-independent routes).
- Iframe `src` must be depth-aware: `"../" * docname.count("/") + "_likec4/…"`.
- Unknown view id fails the build (Sphinx error → fails `-W`); `likec4_missing="warn"` downgrades ONLY the missing-node case, never the unknown-id case.
- Unit tests never invoke real npx (monkeypatch `sphinx_likec4._runner.ensure_build`); exactly one integration test uses real npx and skips when `npx` is absent.
- Use `python3.13` locally; work in `.venv` at repo root.
- Commit after every task; conventional-commit style messages.

---

### Task 1: Package scaffold + Sphinx wiring skeleton

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `.gitignore`, `README.md`
- Create: `src/sphinx_likec4/__init__.py`
- Test: `tests/test_setup.py`

**Interfaces:**
- Produces: `sphinx_likec4.setup(app)` registering config values `likec4_source_dir` (default `None`), `likec4_version` (default `"1.59.2"`), `likec4_missing` (default `"error"`), `likec4_build_args` (default `[]`) — all with rebuild `"env"`. Later tasks extend `setup()`.

- [ ] **Step 1: Write the scaffold files**

`pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sphinx-likec4"
version = "0.1.0"
description = "Embed interactive LikeC4 architecture views (including dynamic-view sequences) in Sphinx documentation"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
authors = [{ name = "ckeller" }]
dependencies = ["sphinx>=7"]
classifiers = [
  "Framework :: Sphinx :: Extension",
  "Programming Language :: Python :: 3",
]

[project.urls]
Homepage = "https://github.com/ckeller42/sphinx-likec4"

[project.optional-dependencies]
test = ["pytest>=8", "defusedxml"]
docs = ["furo", "myst-parser>=2"]

[tool.hatch.build.targets.wheel]
packages = ["src/sphinx_likec4"]
```

`.gitignore`:
```
.venv/
__pycache__/
dist/
docs/_build/
*.egg-info/
```

`LICENSE`: the standard MIT text, copyright `2026 ckeller`.

`README.md` (stub; Task 6 finishes it):
```markdown
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
```

`src/sphinx_likec4/__init__.py`:
```python
"""sphinx-likec4 — embed interactive LikeC4 views in Sphinx HTML documentation."""
__version__ = "0.1.0"

DEFAULT_LIKEC4_VERSION = "1.59.2"


def setup(app):
    app.add_config_value("likec4_source_dir", None, "env")
    app.add_config_value("likec4_version", DEFAULT_LIKEC4_VERSION, "env")
    app.add_config_value("likec4_missing", "error", "env")
    app.add_config_value("likec4_build_args", [], "env")
    return {"version": __version__, "parallel_read_safe": True, "parallel_write_safe": True}
```

- [ ] **Step 2: Create the venv and install editable**

Run: `cd /Users/ckeller/src/sphinx-likec4 && python3.13 -m venv .venv && .venv/bin/pip -q install -e .[test]`
Expected: exits 0.

- [ ] **Step 3: Write the failing test**

`tests/test_setup.py`:
```python
from sphinx_likec4 import setup


class _FakeApp:
    def __init__(self):
        self.config_values = {}

    def add_config_value(self, name, default, rebuild):
        self.config_values[name] = (default, rebuild)

    def connect(self, *a, **k):
        pass

    def add_directive(self, *a, **k):
        pass


def test_setup_registers_config_values():
    app = _FakeApp()
    meta = setup(app)
    assert app.config_values["likec4_source_dir"] == (None, "env")
    assert app.config_values["likec4_version"][0] == "1.59.2"
    assert app.config_values["likec4_missing"] == ("error", "env")
    assert app.config_values["likec4_build_args"] == ([], "env")
    assert meta["parallel_read_safe"] is True
```

- [ ] **Step 4: Run the test**

Run: `.venv/bin/python -m pytest tests/test_setup.py -q`
Expected: PASS (setup already written — this pins the contract).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: package scaffold + config registration"
```

---

### Task 2: `_runner.py` — hash-cached CLI build + view-id collection

**Files:**
- Create: `src/sphinx_likec4/_runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Produces:
  - `_runner.source_hash(source_dir: Path, version: str, build_args: list[str]) -> str`
  - `_runner.ensure_build(source_dir: Path, cache_dir: Path, version: str, build_args: list[str]) -> tuple[Path, set[str]]` — returns `(dist_dir, view_ids)`; raises `LikeC4Missing` when npx is unavailable; runs the CLI only when the hash stamp changed.
  - `_runner.LikeC4Missing(RuntimeError)`
- Consumes: nothing from other tasks.

- [ ] **Step 1: Write the failing tests**

`tests/test_runner.py`:
```python
import json
from pathlib import Path

import pytest

from sphinx_likec4 import _runner


def _model(tmp_path: Path) -> Path:
    src = tmp_path / "model"
    src.mkdir()
    (src / "a.c4").write_text("specification { element system }")
    return src


def test_source_hash_changes_with_content_version_and_args(tmp_path):
    src = _model(tmp_path)
    h1 = _runner.source_hash(src, "1.59.2", [])
    (src / "a.c4").write_text("specification { element system }\n// changed")
    h2 = _runner.source_hash(src, "1.59.2", [])
    h3 = _runner.source_hash(src, "9.9.9", [])
    h4 = _runner.source_hash(src, "9.9.9", ["--flag"])
    assert len({h1, h2, h3, h4}) == 4


def test_ensure_build_runs_cli_once_then_caches(tmp_path, monkeypatch):
    src = _model(tmp_path)
    cache = tmp_path / "cache"
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "build" in cmd:
            dist = Path(cmd[cmd.index("-o") + 1])
            dist.mkdir(parents=True, exist_ok=True)
            (dist / "index.html").write_text("<html>viewer</html>")
        else:  # export json
            out = Path(cmd[cmd.index("-o") + 1])
            out.write_text(json.dumps({"views": {"index": {}, "seqA": {}}}))
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", fake_run)

    dist, views = _runner.ensure_build(src, cache, "1.59.2", [])
    assert (dist / "index.html").exists()
    assert views == {"index", "seqA"}
    n = len(calls)

    dist2, views2 = _runner.ensure_build(src, cache, "1.59.2", [])
    assert len(calls) == n            # cache hit: no new CLI calls
    assert views2 == views


def test_ensure_build_raises_when_npx_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(_runner, "_npx", lambda: None)
    with pytest.raises(_runner.LikeC4Missing):
        _runner.ensure_build(_model(tmp_path), tmp_path / "c", "1.59.2", [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_runner.py -q`
Expected: FAIL / errors (`_runner` does not exist).

- [ ] **Step 3: Implement `_runner.py`**

```python
"""Hash-cached orchestration of the pinned likec4 CLI (build + view-id collection)."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


class LikeC4Missing(RuntimeError):
    """node/npx is not available on PATH."""


def _npx() -> str | None:
    return shutil.which("npx")


def source_hash(source_dir: Path, version: str, build_args: list[str]) -> str:
    h = hashlib.sha256()
    h.update(version.encode())
    h.update("\0".join(build_args).encode())
    for f in sorted(source_dir.rglob("*")):
        if f.suffix in (".c4", ".likec4") and f.is_file():
            h.update(str(f.relative_to(source_dir)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _run(npx: str, args: list[str], cwd: Path) -> None:
    cmd = [npx, "-y", *args]
    res = subprocess.run(cmd, cwd=cwd, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(
            "likec4 failed: %s\n%s" % (" ".join(cmd), res.stderr.decode(errors="replace"))
        )


def _view_ids(data: object) -> set[str]:
    """Extract view ids from `likec4 export json` output (dict- or list-shaped)."""
    ids: set[str] = set()
    if isinstance(data, dict):
        views = data.get("views", data)
        if isinstance(views, dict):
            ids |= set(views.keys())
        elif isinstance(views, list):
            ids |= {v.get("id") for v in views if isinstance(v, dict) and v.get("id")}
        for proj in data.get("projects", []) if isinstance(data.get("projects"), list) else []:
            ids |= _view_ids(proj)
    elif isinstance(data, list):
        for item in data:
            ids |= _view_ids(item)
    return ids


def ensure_build(source_dir: Path, cache_dir: Path, version: str,
                 build_args: list[str]) -> tuple[Path, set[str]]:
    """Build the viewer into ``cache_dir/dist`` (skipped on hash match); return (dist, view ids)."""
    npx = _npx()
    if npx is None:
        raise LikeC4Missing("npx not found on PATH — node >= 20 is required to build LikeC4 views")

    cache_dir.mkdir(parents=True, exist_ok=True)
    dist = cache_dir / "dist"
    stamp = cache_dir / "stamp"
    views_file = cache_dir / "views.json"
    digest = source_hash(source_dir, version, build_args)

    if stamp.exists() and stamp.read_text() == digest and dist.exists() and views_file.exists():
        return dist, set(json.loads(views_file.read_text()))

    cli = f"likec4@{version}"
    _run(npx, [cli, "build", "--use-hash-history", "--base", "./",
               "-o", str(dist), *build_args, str(source_dir)], cwd=source_dir)
    export = cache_dir / "model.json"
    _run(npx, [cli, "export", "json", "-o", str(export), str(source_dir)], cwd=source_dir)
    views = _view_ids(json.loads(export.read_text()))
    views_file.write_text(json.dumps(sorted(views)))
    stamp.write_text(digest)
    return dist, views
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: hash-cached likec4 CLI runner with view-id collection"
```

---

### Task 3: Directives + Sphinx events (the extension proper)

**Files:**
- Create: `src/sphinx_likec4/_directives.py`
- Modify: `src/sphinx_likec4/__init__.py` (wire events + directives into `setup()`)
- Test: `tests/test_extension.py`, test root `tests/roots/test-basic/` (`conf.py`, `index.rst`, `sub/page.rst`, `model/a.c4`)

**Interfaces:**
- Consumes: `_runner.ensure_build`, `_runner.LikeC4Missing` (Task 2 signatures).
- Produces: directives `likec4-view` (arg: view id; options `height`, `title`) and `likec4-model` (flag option `link-only`); env attribute `app.env.likec4_views: set[str] | None` (None = build unavailable in `warn` mode); `app.env.likec4_dist: str | None`.

- [ ] **Step 1: Write the test root**

`tests/roots/test-basic/conf.py`:
```python
extensions = ["sphinx_likec4"]
likec4_source_dir = "model"
exclude_patterns = ["_build"]
```

`tests/roots/test-basic/model/a.c4`:
```
specification { element system }
model { a = system 'A' }
views { view index { include * } }
```

`tests/roots/test-basic/index.rst`:
```rst
Basic
=====

.. likec4-view:: index

.. likec4-view:: seqA
   :height: 300px

.. likec4-model::

.. toctree::

   sub/page
```

`tests/roots/test-basic/sub/page.rst`:
```rst
Sub
===

.. likec4-view:: index
```

- [ ] **Step 2: Write the failing tests**

`tests/test_extension.py`:
```python
import shutil
from pathlib import Path

import pytest
from sphinx.application import Sphinx

from sphinx_likec4 import _runner

ROOT = Path(__file__).parent / "roots" / "test-basic"


@pytest.fixture
def fake_build(monkeypatch):
    def fake(source_dir, cache_dir, version, build_args):
        dist = cache_dir / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "index.html").write_text("<html>fake viewer</html>")
        return dist, {"index", "seqA"}
    monkeypatch.setattr(_runner, "ensure_build", fake)
    return fake


def _build(tmp_path, srcdir=ROOT, confoverrides=None):
    out = tmp_path / "out"
    app = Sphinx(str(srcdir), str(srcdir), str(out), str(tmp_path / "doctrees"),
                 "html", confoverrides=confoverrides or {}, warningiserror=True)
    app.build()
    return out


def test_view_iframes_and_viewer_copy(tmp_path, fake_build):
    out = _build(tmp_path)
    html = (out / "index.html").read_text()
    assert '<iframe class="likec4-view" src="_likec4/#/view/index/"' in html
    assert 'src="_likec4/#/view/seqA/"' in html            # dynamic view, same id space
    assert "height:300px" in html
    sub = (out / "sub" / "page.html").read_text()
    assert 'src="../_likec4/#/view/index/"' in sub          # depth-aware
    assert '<iframe class="likec4-model" src="_likec4/"' in html
    assert (out / "_likec4" / "index.html").exists()        # viewer copied


def test_unknown_view_id_fails_build(tmp_path, fake_build):
    bad = tmp_path / "srcbad"
    shutil.copytree(ROOT, bad)
    (bad / "index.rst").write_text("Bad\n===\n\n.. likec4-view:: nope\n")
    with pytest.raises(Exception):
        _build(tmp_path, srcdir=bad)


def test_missing_node_warn_renders_placeholder(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise _runner.LikeC4Missing("no npx")
    monkeypatch.setattr(_runner, "ensure_build", boom)
    good = tmp_path / "srcwarn"
    shutil.copytree(ROOT, good)
    (good / "index.rst").write_text("W\n=\n\n.. likec4-view:: index\n")
    (good / "sub" / "page.rst").unlink()
    out = tmp_path / "out"
    app = Sphinx(str(good), str(good), str(out), str(tmp_path / "dt"), "html",
                 confoverrides={"likec4_missing": "warn"})
    app.build()
    html = (out / "index.html").read_text()
    assert "likec4-placeholder" in html and "<iframe" not in html


def test_missing_node_error_fails_build(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise _runner.LikeC4Missing("no npx")
    monkeypatch.setattr(_runner, "ensure_build", boom)
    with pytest.raises(Exception):
        _build(tmp_path)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_extension.py -q`
Expected: FAIL (directives unknown).

- [ ] **Step 4: Implement `_directives.py`**

```python
"""The likec4-view / likec4-model directives."""
from __future__ import annotations

from docutils import nodes
from docutils.parsers.rst import Directive, directives


def _rel(docname: str) -> str:
    return "../" * docname.count("/")


def _placeholder(text: str) -> nodes.raw:
    return nodes.raw("", f'<p class="likec4-placeholder"><em>{text}</em></p>', format="html")


class LikeC4View(Directive):
    required_arguments = 1
    option_spec = {"height": directives.unchanged, "title": directives.unchanged}

    def run(self):
        env = self.state.document.settings.env
        view = self.arguments[0]
        views = getattr(env, "likec4_views", None)
        if views is None:                                   # warn mode, build unavailable
            return [_placeholder(f"LikeC4 view “{view}” (viewer not built — node/npx unavailable)")]
        if view not in views:
            raise self.error(
                f"likec4-view: unknown view id {view!r} (known: {', '.join(sorted(views))})"
            )
        height = self.options.get("height", "460px")
        title = self.options.get("title", f"LikeC4 view {view}")
        src = _rel(env.docname) + f"_likec4/#/view/{view}/"
        html = (
            f'<iframe class="likec4-view" src="{src}" loading="lazy" title="{title}" '
            f'style="width:100%;height:{height};border:1px solid rgba(120,120,120,.3);'
            f'border-radius:8px;"></iframe>'
        )
        return [nodes.raw("", html, format="html")]


class LikeC4Model(Directive):
    option_spec = {"link-only": directives.flag, "height": directives.unchanged}

    def run(self):
        env = self.state.document.settings.env
        if getattr(env, "likec4_views", None) is None:
            return [_placeholder("LikeC4 model (viewer not built — node/npx unavailable)")]
        src = _rel(env.docname) + "_likec4/"
        if "link-only" in self.options:
            html = f'<p><a class="likec4-model-link" href="{src}">Open the interactive model</a></p>'
        else:
            height = self.options.get("height", "600px")
            html = (
                f'<iframe class="likec4-model" src="{src}" loading="lazy" '
                f'title="LikeC4 model" style="width:100%;height:{height};'
                f'border:1px solid rgba(120,120,120,.3);border-radius:8px;"></iframe>'
            )
        return [nodes.raw("", html, format="html")]
```

- [ ] **Step 5: Wire events in `__init__.py`**

Replace `src/sphinx_likec4/__init__.py` with:
```python
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
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all PASS (test_setup.py's `_FakeApp` already stubs `connect`/`add_directive`).

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: likec4-view + likec4-model directives with build wiring"
```

---

### Task 4: Real-CLI integration test (skips without node)

**Files:**
- Create: `tests/test_integration.py`

**Interfaces:**
- Consumes: the test root from Task 3 and the real `_runner.ensure_build`.

- [ ] **Step 1: Write the test**

```python
import shutil
from pathlib import Path

import pytest
from sphinx.application import Sphinx

ROOT = Path(__file__).parent / "roots" / "test-basic"

pytestmark = pytest.mark.skipif(shutil.which("npx") is None, reason="node/npx not available")


def test_real_likec4_build_end_to_end(tmp_path):
    src = tmp_path / "src"
    shutil.copytree(ROOT, src)
    # only the structural view exists in the real model — drop the fake-only seqA embed
    (src / "index.rst").write_text(
        "Basic\n=====\n\n.. likec4-view:: index\n\n.. likec4-model::\n   :link-only:\n")
    (src / "sub" / "page.rst").unlink()
    out = tmp_path / "out"
    app = Sphinx(str(src), str(src), str(out), str(tmp_path / "dt"), "html",
                 warningiserror=True)
    app.build()
    assert (out / "_likec4" / "index.html").exists()
    assert 'src="_likec4/#/view/index/"' in (out / "index.html").read_text()
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_integration.py -q`
Expected: PASS locally (node v22 present; first run downloads the CLI, ~1 min).

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "test: real-CLI end-to-end integration (skips without node)"
```

---

### Task 5: Dogfooded docs (4 pages, cloud-system example)

**Files:**
- Create: `docs/conf.py`, `docs/index.md`, `docs/directives.md`, `docs/configuration.md`, `docs/example.md`
- Create: `docs/model/` — copy `_spec.c4`, `model.c4`, `views.c4` from `/Users/ckeller/src/likec4/examples/cloud-system/` (MIT; keep any header comments)
- Create: `docs/requirements.txt`

**Interfaces:**
- Consumes: the installed extension; view ids from the copied model (verify with the command in Step 2).

- [ ] **Step 1: Copy the example model + write conf**

```bash
mkdir -p docs/model
cp /Users/ckeller/src/likec4/examples/cloud-system/*.c4 docs/model/
```

`docs/conf.py`:
```python
project = "sphinx-likec4"
extensions = ["sphinx_likec4", "myst_parser"]
likec4_source_dir = "model"
html_theme = "furo"
exclude_patterns = ["_build", "specs", "plans"]
```

`docs/requirements.txt`:
```
sphinx>=7
furo
myst-parser>=2
```

- [ ] **Step 2: Discover the real view ids**

Run: `cd docs/model && npx -y likec4@1.59.2 export json -o /tmp/cs.json . && python3 -c "import json;d=json.load(open('/tmp/cs.json'));print(sorted((d.get('views') or {}).keys() if isinstance(d.get('views'),dict) else [v['id'] for v in d['views']]))"`
Expected: a list including `index` and `cloud-to-amazon`. Use ONLY ids from this list in the pages below; if a named id differs, substitute the real one everywhere it appears.

- [ ] **Step 3: Write the four pages**

`docs/index.md`:
````markdown
# sphinx-likec4

Embed interactive [LikeC4](https://likec4.dev) architecture views — including
`dynamic view` **sequence diagrams** — in Sphinx documentation. The extension runs the
pinned LikeC4 CLI for you, caches the build, and validates every embedded view id.

## Quickstart

```bash
pip install sphinx-likec4        # node >= 20 required at doc-build time
```

```python
# conf.py
extensions = ["sphinx_likec4"]
likec4_source_dir = "model"      # your *.c4 / *.likec4 files
```

```rst
.. likec4-view:: index
```

That renders this (LikeC4's official *cloud-system* example):

```{likec4-view} index
```

```{toctree}
:maxdepth: 1

directives
configuration
example
```
````

`docs/directives.md`:
````markdown
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
````

`docs/configuration.md`:
````markdown
# Configuration

| `conf.py` value | default | meaning |
|---|---|---|
| `likec4_source_dir` | — (required) | directory of `.c4`/`.likec4` sources, relative to `conf.py` |
| `likec4_version` | `"1.59.2"` | exact CLI version run via `npx -y likec4@<version>` |
| `likec4_missing` | `"error"` | when node/npx is absent: `error` fails the build, `warn` renders placeholders |
| `likec4_build_args` | `[]` | extra arguments appended to `likec4 build` |

Node ≥ 20 must be on `PATH` at doc-build time. The build is **cached** on a content hash of
the sources + version + args, so incremental Sphinx builds don't re-run the CLI. The viewer is
copied into the output at `_likec4/` and uses hash routing, so it works from any subpath.
````

`docs/example.md`:
````markdown
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
```

Source: [`model.c4`](https://github.com/likec4/likec4/blob/main/examples/cloud-system/model.c4)
````

Note: `cloud` in example.md is a guess — replace with a real structural id from Step 2's list
(e.g. `index` if no `cloud` view exists).

- [ ] **Step 4: Build strict and fix any warnings**

Run: `.venv/bin/pip -q install -e .[docs] && .venv/bin/python -m sphinx -b html -W docs docs/_build/html`
Expected: `build succeeded`; `docs/_build/html/_likec4/index.html` exists. If a view id is
wrong the build fails with the known-ids list — fix the page to a real id.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "docs: dogfooded 4-page docs embedding the cloud-system example"
```

---

### Task 6: CI, Pages deploy, README polish

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: the test suite and docs build from Tasks 1–5.

- [ ] **Step 1: Write `ci.yml`**

```yaml
name: CI
on:
  push: { branches: [main] }
  pull_request:
permissions: { contents: read }
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python: ["3.10", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22 }
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python }}" }
      - run: pip install -e .[test]
      - run: python -m pytest tests/ -q
  docs:
    runs-on: ubuntu-latest
    permissions: { contents: read, pages: write, id-token: write }
    environment: { name: github-pages }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }
      - run: pip install -e .[docs]
      - run: python -m sphinx -b html -W docs docs/_build/html
      - uses: actions/upload-pages-artifact@v3
        if: github.ref == 'refs/heads/main'
        with: { path: docs/_build/html }
      - uses: actions/deploy-pages@v4
        if: github.ref == 'refs/heads/main'
```

- [ ] **Step 2: Finish README.md**

```markdown
# sphinx-likec4

Embed interactive [LikeC4](https://likec4.dev) architecture views — including
`dynamic view` **sequence diagrams** — in Sphinx documentation.

The extension runs the **pinned** LikeC4 CLI for you (node ≥ 20 required at doc-build
time), caches the build on a content hash, validates every embedded view id at build time
(`-W` friendly), and serves the viewer with hash routing so it works from any subpath.

## Quickstart

```bash
pip install sphinx-likec4
```

```python
# conf.py
extensions = ["sphinx_likec4"]
likec4_source_dir = "model"
```

```rst
.. likec4-view:: cloud-to-amazon
```

Docs: https://ckeller42.github.io/sphinx-likec4/ · License: MIT
```

- [ ] **Step 3: Full local gate**

Run: `.venv/bin/python -m pytest tests/ -q && .venv/bin/python -m sphinx -b html -W -E docs docs/_build/html`
Expected: both green.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "ci: test matrix + strict docs build with Pages deploy"
```

---

### Task 7: Publish the GitHub repo + verify CI/Pages

**Files:** none (repo operations).

- [ ] **Step 1: Create the public repo and push**

```bash
cd /Users/ckeller/src/sphinx-likec4
gh repo create ckeller42/sphinx-likec4 --public --source . --description "Embed interactive LikeC4 architecture views (incl. sequence diagrams) in Sphinx docs" --push
```

- [ ] **Step 2: Enable Pages (Actions build type)**

Run: `gh api repos/ckeller42/sphinx-likec4/pages -X POST -f build_type=workflow`
Expected: JSON with `html_url`. (409 = already enabled — fine.)

- [ ] **Step 3: Watch CI**

Run: `gh run watch $(gh run list -R ckeller42/sphinx-likec4 --limit 1 --json databaseId --jq '.[0].databaseId') --exit-status` (or poll `gh run list`)
Expected: test + docs jobs green; then `curl -s -o /dev/null -w "%{http_code}" https://ckeller42.github.io/sphinx-likec4/` → 200, and spot-check that `/#/view/…` iframes render (fetch the page HTML and confirm the `likec4-view` iframes are present).

- [ ] **Step 4: Commit nothing — tag optional**

PyPI publishing is deliberately deferred (trusted-publishing setup is a manual owner step); note it in the session report.

---

### Task 8: Migrate open-california to the published extension

**Files (in `/Users/ckeller/src/open-california`, separate branch + PR):**
- Delete: `docs/_ext/likec4_embed.py`
- Modify: `docs/conf.py` (drop `_ext` path + `likec4_embed`; add `sphinx_likec4` + `likec4_source_dir = "likec4"`; keep every other setting)
- Modify: `docs/build_site.sh` (remove the `npx -y likec4@1.59.2 build …` line and its comment — the extension builds it now)
- Modify: `docs/requirements.txt` (add `sphinx-likec4 @ git+https://github.com/ckeller42/sphinx-likec4` until a PyPI release exists)
- Modify: `docs/index.rst` (`likec4-view`/`likec4-model` usage unchanged — directive names are identical; replace the manual `model <model/index.html>`_ link with `.. likec4-model::` + `:link-only:`)
- Modify: `docs/protocol-sequences.rst` (no change expected — verify the embed still builds)

**Interfaces:**
- Consumes: the published repo from Task 7. The viewer path changes `model/` → `_likec4/`; the old `/model/` URL disappears (acceptable — the index link is regenerated).

- [ ] **Step 1: Branch + apply the swap**

```bash
cd /Users/ckeller/src/open-california && git checkout -b use-sphinx-likec4
git rm docs/_ext/likec4_embed.py
pip3.13 install "sphinx-likec4 @ git+https://github.com/ckeller42/sphinx-likec4"
```
Edit the files as listed above (conf: replace `sys.path.insert(0, os.path.abspath("_ext"))` and the `likec4_embed` extension entry with `sphinx_likec4`, add `likec4_source_dir = "likec4"`; build_site.sh: delete the likec4 build line + its comment; requirements.txt: add the git dependency line).

- [ ] **Step 2: Build both site builds strict**

Run: `PYTHON=python3.13 sh docs/build_site.sh /tmp/siteMig`
Expected: green; `/tmp/siteMig/_likec4/index.html` exists; `grep -o '_likec4/#/view/seqArmedWrite/' /tmp/siteMig/protocol-sequences.html` matches.

- [ ] **Step 3: Full repo gate**

Run: `bash tools/ci.sh`
Expected: `local CI: OK`.

- [ ] **Step 4: Commit, PR, merge (repo convention), verify Pages deploy**

```bash
git add -A && git commit -m "docs: replace local likec4 embed with the sphinx-likec4 extension"
git push -u origin use-sphinx-likec4 && gh pr create --fill && gh pr merge --merge
```
Then after the docs workflow: `curl -s https://ckeller42.github.io/open-california/protocol-sequences.html | grep -c likec4-view` → ≥1, and the `_likec4/` page returns 200.
```

## Self-review notes

- Spec coverage: identity→T1/T7; architecture/cache/hash-history/pin→T2/T3; directives+sequences→T3 (+seqA dynamic-id test), unknown-id/-W→T3; config table→T1/T3/docs T5; dogfood docs incl. `cloud-to-amazon`→T5; CI/matrix/Pages→T6/T7; migration→T8. PyPI trusted publishing deferred (noted in T7) — owner-side manual step.
- Types/signatures consistent: `ensure_build(source_dir, cache_dir, version, build_args) -> (dist, set)` used identically in T2/T3 tests.
- No placeholders; every step has runnable content. The one deliberate lookup (real cloud-system view ids) has an exact discovery command and substitution rule.
