import shutil
from pathlib import Path

import pytest
from sphinx.application import Sphinx
from sphinx.errors import SphinxError
from sphinx.util.docutils import docutils_namespace

from sphinx_likec4 import _runner

ROOT = Path(__file__).parent / "roots" / "test-basic"


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
    with pytest.raises(SphinxError):
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
    with pytest.raises(SphinxError):
        _build(tmp_path)


def test_non_html_builder_renders_plain_text(tmp_path):
    out = tmp_path / "out"
    app = Sphinx(str(ROOT), str(ROOT), str(out), str(tmp_path / "dt"), "text",
                 warningiserror=True)
    app.build()
    txt = (out / "index.txt").read_text()
    assert "LikeC4 view" in txt and "iframe" not in txt


def test_incremental_build_detects_stale_view_after_rename(tmp_path, monkeypatch):
    src = tmp_path / "srcinc"
    shutil.copytree(ROOT, src)
    out = tmp_path / "out"
    dt = tmp_path / "dt"

    def fake_v1(source_dir, cache_dir, version, build_args):
        dist = cache_dir / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "index.html").write_text("<html>fake viewer</html>")
        return dist, {"index", "seqA"}

    monkeypatch.setattr(_runner, "ensure_build", fake_v1)
    # each Sphinx() app registers docutils nodes into a process-global registry;
    # nest each app's lifetime in its own docutils_namespace() so this test's two
    # in-process "fresh Sphinx object" builds don't trip a spurious re-registration
    # warning against each other (Sphinx <8; see tests/conftest.py).
    with docutils_namespace():
        app = Sphinx(str(src), str(src), str(out), str(dt), "html", warningiserror=True)
        app.build()

    # rename the view in the model source — the rst files themselves are untouched
    (src / "model" / "a.c4").write_text(
        "specification { element system }\n"
        "model { a = system 'A' }\n"
        "views { view renamed { include * } }\n"
    )

    def fake_v2(source_dir, cache_dir, version, build_args):
        dist = cache_dir / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "index.html").write_text("<html>fake viewer</html>")
        return dist, {"renamed", "seqA"}

    monkeypatch.setattr(_runner, "ensure_build", fake_v2)
    with docutils_namespace():
        app2 = Sphinx(str(src), str(src), str(out), str(dt), "html", warningiserror=True)
        with pytest.raises(SphinxError):  # "index" no longer exists post-rename
            app2.build()


def test_title_with_quote_is_html_escaped(tmp_path, fake_build):
    src = tmp_path / "srctitle"
    shutil.copytree(ROOT, src)
    (src / "index.rst").write_text(
        'T\n=\n\n.. likec4-view:: index\n   :title: a "quoted" title\n')
    (src / "sub" / "page.rst").unlink()
    out = _build(tmp_path, srcdir=src)
    html_text = (out / "index.html").read_text()
    assert 'title="a &quot;quoted&quot; title"' in html_text
    assert 'title="a "quoted" title"' not in html_text


def test_suppress_warnings_silences_missing_node_under_dash_w(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise _runner.LikeC4Missing("no npx")
    monkeypatch.setattr(_runner, "ensure_build", boom)
    out = tmp_path / "out"
    app = Sphinx(str(ROOT), str(ROOT), str(out), str(tmp_path / "dt"), "html",
                 confoverrides={"likec4_missing": "warn", "suppress_warnings": ["likec4"]},
                 warningiserror=True)
    app.build()             # would raise SphinxWarning under -W if not suppressed
    assert "likec4-placeholder" in (out / "index.html").read_text()


def test_view_mode_sequence_appends_dynamic_param(tmp_path, fake_build):
    import shutil as _sh
    src = tmp_path / "srcmode"
    _sh.copytree(ROOT, src)
    (src / "index.rst").write_text(
        "M\n=\n\n.. likec4-view:: seqA\n   :mode: sequence\n")
    (src / "sub" / "page.rst").unlink()
    out = _build(tmp_path, srcdir=src)
    assert 'src="_likec4/#/view/seqA/?dynamic=sequence"' in (out / "index.html").read_text()


def test_html_default_is_iframe_and_still_exports_png(tmp_path, fake_build, fake_images):
    app, _ = _app(tmp_path)
    assert app.env.likec4_mode == "ready"
    assert app.env.likec4_format == "html"
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
    assert app.env.likec4_format == "epub"
    assert app.env.likec4_render_default == "png" and fake_images == ["png"]


def test_likec4_render_epub_key_overrides_epub(tmp_path, fake_build, fake_images):
    app, _ = _app(tmp_path, builder="epub", strict=False, confoverrides={"likec4_render": {"epub": "jpg"}})
    assert app.env.likec4_render_default == "jpg"
    assert sorted(fake_images) == ["jpg", "png"]
    assert fake_build == []                                 # epub never builds the iframe viewer
