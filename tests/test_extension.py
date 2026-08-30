import shutil
from pathlib import Path

import pytest
from sphinx.application import Sphinx
from sphinx.errors import SphinxError
from sphinx.util.docutils import docutils_namespace

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
