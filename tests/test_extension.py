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
