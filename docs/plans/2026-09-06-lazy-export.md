# Lazy Image Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export only the views a build embeds — on demand from the directive on first use, batched from a remembered set on rebuilds — instead of every view for every image-capable builder.

**Architecture:** `_runner.ensure_images` becomes view-scoped and additive (dir stamped with the source digest, wiped when stale, only missing files exported in one CLI run). `LikeC4View._image` records `(view, fmt, seq)` in `env.likec4_needed[docname]` and exports its own file when missing; `env-purge-doc`/`env-merge-info` keep that dict correct across incremental and parallel builds; `_builder_inited` exports the previous build's union batched. Everything else (validation via `ensure_views`, `likec4_render`, `:render:` resolution, `:mode: sequence`, `env-get-outdated`) is unchanged.

**Tech Stack:** Python ≥3.10, Sphinx ≥7, pytest (+doctests), `likec4@1.59.2` via npx.

**Spec:** `docs/specs/2026-09-05-static-images-design.md`, section "Lazy export (2026-09-06)" — read it first.

## Global Constraints

- Branch `feat/lazy-export` in `/Users/ckeller/src/sphinx-likec4` (checked out; spec committed). **Never commit to `main`.** `.superpowers/` is git-ignored scratch.
- `./test.sh` (ruff + `pytest src/ tests/` + strict docs build) must print `local gate: OK` before every commit; use `.venv/bin/python -m pytest …`. The docs stage runs the real CLI (Chromium installed).
- Verified CLI facts: `export <fmt> --flat -f <id> -o DIR` is additive (never clears DIR); concurrent exports into one DIR coexist. Do not add locking or wiping beyond the stamp logic below.
- Unit/extension tests never run a real `npx` (they monkeypatch `_runner.*`); only `tests/test_integration.py` does (skipped without node).
- `-W` in tests: the `_app()` helper raises `SphinxError` when a strict build ends with `statuscode != 0` (Sphinx ≥8.1 records instead of raising). Two `Sphinx()` apps in one test each need `with docutils_namespace():` (Sphinx 7). Directive exceptions must be `sphinx.errors.ExtensionError` (a raw `RuntimeError` from a directive would not match `pytest.raises(SphinxError)`).
- Commit prefixes `feat:`/`test:`/`docs:`; the harness appends trailers.

---

### Task 1: Runner — view-scoped, additive `ensure_images`

**Files:**
- Modify: `src/sphinx_likec4/_runner.py` (`ensure_images` only)
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: `_require_npx`, `source_hash`, `_run`, `LikeC4Missing` (unchanged).
- Produces: `ensure_images(source_dir: Path, cache_dir: Path, version: str, fmt: str, views: Iterable[str], seq: bool = False) -> Path` — returns `cache_dir / f"images-{fmt}"` or `…-seq`; guarantees `<view>.<fmt>` exists there for every `views` entry the CLI produced; makes **no** CLI call when nothing is missing.

- [ ] **Step 1: Rewrite the `ensure_images` tests**

In `tests/test_runner.py`, `_fake_cli` already honours `-f` filters and writes `b"seq"` for `--seq` runs. Replace `test_ensure_images_exports_flat_then_caches` and `test_ensure_images_seq_pass_exports_only_dynamic_views` with:

```python
def test_ensure_images_exports_only_missing_views_additively(tmp_path, monkeypatch):
    src = _model(tmp_path)
    calls = []
    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", _fake_cli(calls))

    out = _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png", ["index"])
    assert out == tmp_path / "c" / "images-png" and (out / "index.png").exists()
    cmd = calls[0]
    assert cmd[:2] == ["npx", "-y"] and "likec4@1.59.2" in cmd
    assert cmd[cmd.index("export") + 1] == "png" and "--flat" in cmd and "--seq" not in cmd
    assert [cmd[i + 1] for i, a in enumerate(cmd) if a == "-f"] == ["index"]
    assert cmd[cmd.index("-o") + 1] == str(out) and cmd[-1] == str(src)

    _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png", ["index", "seqA"])
    assert len(calls) == 2                                  # one more run, for the missing view only
    assert [calls[1][i + 1] for i, a in enumerate(calls[1]) if a == "-f"] == ["seqA"]
    assert (out / "index.png").exists() and (out / "seqA.png").exists()

    _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png", ["seqA", "index"])
    assert len(calls) == 2                                  # nothing missing: no CLI call

    jpg = _runner.ensure_images(src, tmp_path / "c", "1.59.2", "jpg", ["index"])
    assert jpg == tmp_path / "c" / "images-jpg" and len(calls) == 3   # separate dir per format


def test_ensure_images_wipes_the_dir_when_sources_change(tmp_path, monkeypatch):
    src = _model(tmp_path)
    calls = []
    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", _fake_cli(calls))
    out = _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png", ["index", "seqA"])
    (out / "stale.png").write_bytes(b"old")                  # something the CLI would not recreate

    (src / "a.c4").write_text("specification { element system }\n// changed")
    _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png", ["index"])
    assert not (out / "stale.png").exists() and not (out / "seqA.png").exists()   # wiped
    assert (out / "index.png").exists() and len(calls) == 2  # re-exported what was asked for


def test_ensure_images_seq_uses_its_own_dir_and_flag(tmp_path, monkeypatch):
    src = _model(tmp_path)
    calls = []
    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", _fake_cli(calls))
    plain = _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png", ["seqA"])
    seq = _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png", ["seqA"], seq=True)
    assert seq == tmp_path / "c" / "images-png-seq" and seq != plain
    assert "--seq" in calls[1] and "--seq" not in calls[0]
    assert (seq / "seqA.png").read_bytes() == b"seq" and (plain / "seqA.png").read_bytes() == b"img"
    _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png", ["seqA"], seq=True)
    assert len(calls) == 2                                  # cached independently of the plain dir
```

Update the two Playwright tests and `test_ensure_images_and_views_raise_when_npx_missing` to the new signature: pass `["index"]` as `views` (e.g. `_runner.ensure_images(src, tmp_path / "c", "1.59.2", "png", ["index"])`); their assertions stay.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_runner.py -q`
Expected: the rewritten/new tests FAIL with `TypeError` (unexpected positional/keyword `views`/`seq`) or missing-file assertions; the rest pass.

- [ ] **Step 3: Implement**

Replace `ensure_images` in `src/sphinx_likec4/_runner.py` with:

```python
def ensure_images(source_dir: Path, cache_dir: Path, version: str, fmt: str,
                  views: Iterable[str], seq: bool = False) -> Path:
    """Export ``views`` as ``<view-id>.<fmt>`` into ``cache_dir/images-<fmt>[-seq]`` — additively.

    The directory is stamped with the source digest; a stale stamp (sources changed) wipes it
    first. Only views whose file is missing are exported, in one CLI run — nothing missing
    means no CLI call, so callers can ask freely. ``seq`` selects sequence layout (``--seq``)
    and the ``-seq`` directory, since the CLI's ``--seq`` applies to the whole run.

    The export drives headless Chromium through Playwright; if the first attempt fails for
    lack of a browser, install Chromium once through likec4's *own* Playwright (so the
    browser revision matches) and retry. Any other failure, or a second one, propagates as
    ``RuntimeError``.
    """
    npx = _require_npx()
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = f"images-{fmt}-seq" if seq else f"images-{fmt}"
    out, stamp = cache_dir / name, cache_dir / f"{name}.stamp"
    digest = source_hash(source_dir, version, [fmt, "seq"] if seq else [fmt])
    if not (stamp.exists() and stamp.read_text() == digest):
        shutil.rmtree(out, ignore_errors=True)               # stale renders must not survive
        out.mkdir(parents=True)
        stamp.write_text(digest)
    missing = sorted(v for v in set(views) if not (out / f"{v}.{fmt}").exists())
    if not missing:
        return out
    cli = f"likec4@{version}"
    export = [cli, "export", fmt, "--flat", *(["--seq"] if seq else []),
              *(arg for v in missing for arg in ("-f", v)), "-o", str(out), str(source_dir)]
    try:
        _run(npx, export, cwd=source_dir)
    except RuntimeError as e:
        msg = str(e).lower()
        if not any(k in msg for k in ("playwright", "browser", "executable")):
            raise
        _run(npx, ["--package", cli, "-c", "playwright install chromium"], cwd=source_dir)
        _run(npx, export, cwd=source_dir)
    return out
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_runner.py src/sphinx_likec4/_runner.py -q`
Expected: all pass. (`tests/test_extension.py` will fail until Task 2 — expected; do not run `./test.sh` yet.)

- [ ] **Step 5: Commit**

```bash
git add src/sphinx_likec4/_runner.py tests/test_runner.py
git commit -m "feat(runner): view-scoped, additive image export

ensure_images now takes the views to guarantee and exports only the missing
ones in one CLI run; the directory is stamped with the source digest and
wiped when stale. Nothing missing means no CLI call."
```

(The gate is red between Task 1 and Task 2 by design; Task 2 restores it.)

---

### Task 2: Wiring + directive — remembered set, batched rebuild pass, on-demand export

**Files:**
- Modify: `src/sphinx_likec4/__init__.py` (`_builder_inited` export block, two new handlers, `setup`)
- Modify: `src/sphinx_likec4/_directives.py` (`LikeC4View._image`)
- Test: `tests/test_extension.py`

**Interfaces:**
- Consumes: Task 1's `ensure_images(source_dir, cache_dir, version, fmt, views, seq=False)`.
- Produces: `env.likec4_needed: dict[str, set[tuple[str, str, bool]]]` (docname → {(view, fmt, seq)}), `env.likec4_source_dir: str`; `env.likec4_images` / `likec4_images_seq` now list the dirs for every exported format whether or not files exist yet; handlers `_env_purge_doc(app, env, docname)` and `_env_merge_info(app, env, docnames, other)`.

- [ ] **Step 1: Update the fixture and existing tests, add the new ones**

In `tests/test_extension.py` replace the `fake` inside the `fake_images` fixture with:

```python
    def fake(source_dir, cache_dir, version, fmt, views, seq=False):
        views = tuple(sorted(views))
        calls.append((fmt, views, seq))
        out = cache_dir / (f"images-{fmt}-seq" if seq else f"images-{fmt}")
        out.mkdir(parents=True, exist_ok=True)
        for view in views:
            (out / f"{view}.{fmt}").write_bytes(_PNG_SEQ if seq else _PNG)
        return out
```

Every assertion on `fake_images` becomes call-shaped. Exact new values (the test root embeds `index` and `seqA` in `index.rst` and `index` again in `sub/page.rst`):

| test | new assertion(s) |
|---|---|
| `test_html_default_is_iframe_and_still_exports_png` → rename `test_html_default_is_iframe_and_exports_nothing` | `set(app.env.likec4_images) == {"png"} and fake_images == []` |
| `test_latex_default_is_png_without_viewer_build` | `fake_images == [("png", ("index",), False), ("png", ("seqA",), False)]` |
| `test_likec4_render_override_adds_jpg_export` | `{c[0] for c in fake_images} == {"jpg"} and set(app.env.likec4_images) == {"jpg", "png"}` |
| `test_likec4_render_for_another_format_still_exports_that_format` → rename `…_still_lists_that_format` | `app, _ = _app(...)`; `fake_images == [] and set(app.env.likec4_images) == {"jpg", "png"}` |
| `test_epub_is_image_capable` | `fake_images == [("png", ("index",), False), ("png", ("seqA",), False)]` |
| `test_likec4_render_epub_key_overrides_epub` | `{c[0] for c in fake_images} == {"jpg"}` |
| `test_mode_sequence_in_image_mode_uses_the_seq_export` | `fake_images == [("png", ("seqA",), True), ("png", ("seqA",), False), ("png", ("index",), False)]` (rest of the test unchanged) |
| `test_no_dynamic_views_means_no_seq_pass` | `fake_images == [("png", ("index",), False), ("png", ("seqA",), False)] and app.env.likec4_images_seq == {}` |
| `test_seq_pass_runs_for_latex_and_is_read_by_mode_sequence` | `fake_images == [("png", ("seqA",), True)] and app.env.likec4_dynamic_views == {"seqA"}` |
| `test_missing_exported_file_is_an_error` | the `partial` fake gets the new signature `(source_dir, cache_dir, version, fmt, views, seq=False)` and writes only `index` regardless of `views`; assertion unchanged |
| `test_text_builder_exports_nothing`, both `test_export_images_false_*` | unchanged (`[]`) |

Replace the two export-failure tests and the sequence-failure test:

```python
def test_batched_export_failure_is_a_warning_for_iframe_builders(tmp_path, fake_build, fake_images, monkeypatch):
    # build 1 remembers that index.rst embeds index as png
    src = _src(tmp_path, "s", "P\n=\n\n.. likec4-view:: index\n   :render: png\n")
    with docutils_namespace():
        _app(tmp_path, srcdir=src)
    assert fake_images == [("png", ("index",), False)]

    def boom(*a, **k):
        raise RuntimeError("chromium: error while loading shared libraries")
    monkeypatch.setattr(_runner, "ensure_images", boom)
    # build 2 on the same doctree dir: the batched pass at builder-inited fails → warning,
    # images disabled for this build, the iframe stands in (default render on HTML)
    (src / "index.rst").write_text("P\n=\n\n.. likec4-view:: index\n   :render: png\n\n.. note:: touched\n")
    with docutils_namespace():
        app, out = _app(tmp_path, srcdir=src, confoverrides={"suppress_warnings": ["likec4"]})
    assert app.env.likec4_images == {} and app.env.likec4_images_seq == {}
    assert '<iframe class="likec4-view"' in (out / "index.html").read_text()
    with pytest.raises(SphinxError), docutils_namespace():   # -W without suppression still fails
        _app(tmp_path, srcdir=src)


def test_on_demand_export_failure_is_fatal(tmp_path, fake_build, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("chromium: error while loading shared libraries")
    monkeypatch.setattr(_runner, "ensure_images", boom)
    src = _src(tmp_path, "s", "P\n=\n\n.. likec4-view:: index\n   :render: png\n")
    with pytest.raises(SphinxError, match="shared libraries"):     # explicit ask → fatal, on HTML too
        _app(tmp_path, srcdir=src)
    with pytest.raises(SphinxError, match="shared libraries"):     # image-default builder too
        _app(tmp_path / "l", builder="latex")


def test_html_render_png_exports_only_that_view(tmp_path, fake_build, fake_images):
    src = _src(tmp_path, "s", "P\n=\n\n.. likec4-view:: index\n   :render: png\n")
    out = _build(tmp_path, srcdir=src)
    assert fake_images == [("png", ("index",), False)]
    assert (out / "_images" / "index.png").exists()


def test_rebuild_exports_the_remembered_set_batched_before_reading(tmp_path, fake_build, fake_images):
    src = _src(tmp_path, "s", "P\n=\n\n.. likec4-view:: index\n   :render: png\n")
    with docutils_namespace():
        app, _ = _app(tmp_path, srcdir=src)
    assert app.env.likec4_needed == {"index": {("index", "png", False)}}
    fake_images.clear()
    with docutils_namespace():                                 # nothing changed: no doc re-read
        app2, _ = _app(tmp_path, srcdir=src)
    assert fake_images == [("png", ("index",), False)]         # one batched call, from the remembered set
    assert app2.env.likec4_needed == {"index": {("index", "png", False)}}


def test_removed_doc_leaves_the_remembered_set(tmp_path, fake_build, fake_images):
    src = _src(tmp_path, "s", "P\n=\n\n.. likec4-view:: index\n   :render: png\n\n.. toctree::\n\n   other\n")
    (src / "other.rst").write_text("O\n=\n\n.. likec4-view:: seqA\n   :render: png\n")
    with docutils_namespace():
        app, _ = _app(tmp_path, srcdir=src)
    assert set(app.env.likec4_needed) == {"index", "other"}
    (src / "other.rst").unlink()
    (src / "index.rst").write_text("P\n=\n\n.. likec4-view:: index\n   :render: png\n")
    fake_images.clear()
    with docutils_namespace():
        app2, _ = _app(tmp_path, srcdir=src)
    assert set(app2.env.likec4_needed) == {"index"}
    assert ("png", ("index", "seqA"), False) in fake_images    # batched pass used the OLD set …
    assert all(c[1] != ("seqA",) for c in fake_images)         # … but nothing re-embedded seqA


def test_seq_export_failure_on_demand_is_fatal(tmp_path, fake_build, monkeypatch):
    _with_dynamic_seqa(monkeypatch)

    def flaky(source_dir, cache_dir, version, fmt, views, seq=False):
        if seq:
            raise RuntimeError("chromium crashed during the --seq pass")
        out = cache_dir / f"images-{fmt}"
        out.mkdir(parents=True, exist_ok=True)
        for view in views:
            (out / f"{view}.{fmt}").write_bytes(_PNG)
        return out
    monkeypatch.setattr(_runner, "ensure_images", flaky)
    src = _src(tmp_path, "s", "S\n=\n\n.. likec4-view:: seqA\n   :render: png\n   :mode: sequence\n")
    with pytest.raises(SphinxError, match="--seq pass"):
        _app(tmp_path, srcdir=src)
```

Delete `test_image_export_failure_is_a_warning_for_iframe_builders`, `test_image_export_failure_fails_image_builders`, and `test_seq_export_failure_keeps_normal_images_on_iframe_builders` (superseded above). `test_switching_builders_on_a_shared_doctreedir_rerenders` stays as is.

- [ ] **Step 2: Run to verify the new tests fail**

Run: `.venv/bin/python -m pytest tests/test_extension.py -q`
Expected: many failures (`TypeError` from the old `ensure_images` call shape, missing `likec4_needed`, `KeyError`s). Read one traceback to confirm it is the expected cause.

- [ ] **Step 3: Implement — `__init__.py`**

Replace the `if image_capable:` block (from `# ponytail: exports png even if no directive asks…` through the seq pass) with:

```python
        if image_capable:
            env.likec4_images = {f: str(cache_dir / f"images-{f}") for f in sorted(formats)}
            env.likec4_images_seq = ({f: str(cache_dir / f"images-{f}-seq") for f in sorted(formats)}
                                     if dynamic else {})
            # Lazy export: the directives export what they embed (LikeC4View._image) and
            # remember it in env.likec4_needed; here, re-export the previous build's set in
            # one run per (format, layout) so doctrees that won't be re-read still find
            # their files after a source change wiped the dirs.
            needed: dict[tuple[str, bool], set[str]] = {}
            for entries in getattr(env, "likec4_needed", {}).values():
                for view, f, seq in entries:
                    if f in formats and (not seq or dynamic):
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
```

Right after `env.likec4_dynamic_views = set()` near the top of `_builder_inited`, add:

```python
    if not hasattr(env, "likec4_needed"):
        env.likec4_needed = {}                       # docname -> {(view, fmt, seq)}; survives via the env pickle
```

and after `source_dir` is validated: `env.likec4_source_dir = str(source_dir)`.

Add two module-level handlers (next to `_env_get_outdated`) and connect them in `setup()`:

```python
def _env_purge_doc(app, env, docname):
    """``env-purge-doc``: forget what a removed/re-read document embedded."""
    getattr(env, "likec4_needed", {}).pop(docname, None)


def _env_merge_info(app, env, docnames, other):
    """``env-merge-info``: fold a parallel read worker's embeds into the main env."""
    theirs = getattr(other, "likec4_needed", {})
    env.likec4_needed.update({d: theirs[d] for d in docnames if d in theirs})
```

```python
    app.connect("env-purge-doc", _env_purge_doc)
    app.connect("env-merge-info", _env_merge_info)
```

- [ ] **Step 4: Implement — `_directives.py`**

Add `from . import _runner` to the imports. Replace the body of `LikeC4View._image` from the `seq = (...)` assignment through the `if not file.exists(): raise …` block with:

```python
        # ":mode: sequence" on a dynamic view picks the --seq export (sequence layout)
        seq = (self.options.get("mode") == "sequence" and view in env.likec4_dynamic_views
               and fmt in env.likec4_images_seq)
        env.likec4_needed.setdefault(env.docname, set()).add((view, fmt, seq))
        images_dir = Path((env.likec4_images_seq if seq else env.likec4_images)[fmt])
        file = images_dir / f"{view}.{fmt}"
        if not file.exists():
            # first build / new embed: export on demand. Sphinx's image collector runs on
            # doctree-read, after this directive, so the file is in place in time — in a
            # parallel read worker too (concurrent CLI exports coexist; see the spec).
            try:
                _runner.ensure_images(Path(env.likec4_source_dir), images_dir.parent,
                                      env.config.likec4_version, fmt, [view], seq=seq)
            except RuntimeError as e:
                raise ExtensionError(f"likec4-view: image export failed for {view!r}: {e}") from e
        if not file.exists():
            raise ExtensionError(
                f"likec4-view: no exported {fmt} for view {view!r} in {file.parent} "
                f"(likec4 export names files by view id; check the export dir)")
```

- [ ] **Step 5: Run to verify they pass, then the gate**

Run: `.venv/bin/python -m pytest src/ tests/test_runner.py tests/test_extension.py tests/test_setup.py -q` → all pass. Then `./test.sh` → `local gate: OK` (the docs build now exports only the embedded views: watch the export dir — `ls docs/_build/html/.doctrees/likec4/images-png/` should list only `index.png`, `cloud.png`, `cloud-to-amazon.png`, and `images-png-seq/` only `cloud-to-amazon.png`; record that listing in your report).

- [ ] **Step 6: Commit**

```bash
git add src/sphinx_likec4/__init__.py src/sphinx_likec4/_directives.py tests/test_extension.py
git commit -m "feat: export only embedded views — on demand, then batched from the remembered set

Directives export their own view when its file is missing (the image collector
runs after them, in parallel workers too) and record (view, fmt, seq) in
env.likec4_needed; env-purge-doc/env-merge-info keep it correct across
incremental and parallel builds. builder-inited re-exports the previous
build's set in one run per (format, layout), so doctrees that are not
re-read still find their files after a source change. Plain HTML never
starts Chromium unless a page asks for an image. Closes #10."
```

---

### Task 3: Real parallel build, docs, gotchas

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `docs/configuration.md`, `CLAUDE.md`

- [ ] **Step 1: Integration test — two pages, two views, two read workers**

Append to `tests/test_integration.py`:

```python
def test_real_parallel_read_exports_per_worker(tmp_path):
    src = tmp_path / "par"
    shutil.copytree(ROOT, src)
    (src / "model" / "a.c4").write_text(
        "specification { element system }\n"
        "model { a = system 'A'\n        b = system 'B' }\n"
        "views { view index { include * }\n        view other { include b } }\n")
    (src / "index.rst").write_text(
        "P\n=\n\n.. likec4-view:: index\n   :render: png\n\n.. toctree::\n\n   sub/page\n")
    (src / "sub" / "page.rst").write_text("S\n=\n\n.. likec4-view:: other\n   :render: png\n")
    out = tmp_path / "out"
    app = Sphinx(str(src), str(src), str(out), str(tmp_path / "dt"), "html",
                 warningiserror=True, parallel=2)
    app.build()
    assert (out / "_images" / "index.png").stat().st_size > 1000
    assert (out / "_images" / "other.png").stat().st_size > 1000
    assert set(app.env.likec4_needed) == {"index", "sub/page"}     # merged from the workers
```

Run: `.venv/bin/python -m pytest tests/test_integration.py -q -p no:cacheprovider` → 3 passed (two real CLI runs happen inside the workers; ~30–60 s). If Sphinx refuses `parallel=2` for two documents (it needs enough docs to split), add a third page embedding `index` and keep the assertions.

- [ ] **Step 2: Docs**

`docs/configuration.md`, section "Static images and PDF": replace the first paragraph (the one beginning "Every builder that can embed images — LaTeX, epub, **and HTML** — exports all views as PNG once …") with:

```markdown
Only the views a build actually embeds are exported: a page's directive renders its view on
first use (`likec4 export png --flat -f <id>`), and rebuilds re-export the remembered set in
one run per format when the sources changed. Plain HTML never starts a browser unless a page
uses `:render: png`; unreferenced views are never rendered. The renders live under the doctree
dir (`likec4/images-<fmt>/`), cached on the same content hash as the viewer. If the batched
re-export fails on a builder whose default is the iframe, the build continues with a `likec4`
warning and `:render: png` falls back to the iframe; an export failure for an explicitly
requested image is an error. Set `likec4_export_images = False` to disable images entirely.
```

`CLAUDE.md`, Gotchas: replace the line about `_env_get_outdated` with:

```markdown
- Doctrees are cached per document, not per builder: builder-specific nodes need the `env-get-outdated` re-read (`_env_get_outdated`) or `-M html` then `-M latexpdf` shares stale nodes. Images are exported lazily: directives export their own view on demand and record it in `env.likec4_needed` (purged/merged via `env-purge-doc`/`env-merge-info`); `builder-inited` re-exports that set batched. Test fakes of `ensure_images` take `(source_dir, cache_dir, version, fmt, views, seq=False)`.
```

- [ ] **Step 3: Gate and commit**

`./test.sh` → `local gate: OK`.

```bash
git add tests/test_integration.py docs/configuration.md CLAUDE.md
git commit -m "test: real parallel-read export; docs for lazy export"
```

Pushing and the PR are the controller's job.
