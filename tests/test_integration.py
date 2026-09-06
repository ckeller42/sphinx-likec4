import shutil
from pathlib import Path

import pytest
from sphinx.application import Sphinx

ROOT = Path(__file__).parent / "roots" / "test-basic"

pytestmark = pytest.mark.skipif(shutil.which("npx") is None, reason="node/npx not available")


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
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'src="_likec4/#/view/index/"' in html
    assert 'src="_images/index.png"' in html                # real export, --flat naming
    assert (out / "_images" / "index.png").stat().st_size > 1000


def test_real_likec4_latex_embeds_png(tmp_path):
    src = _src(tmp_path)
    out = tmp_path / "out"
    app = Sphinx(str(src), str(src), str(out), str(tmp_path / "dt"), "latex",
                 warningiserror=True)
    app.build()
    assert "\\sphinxincludegraphics" in next(out.glob("*.tex")).read_text(encoding="utf-8")
    assert (out / "index.png").stat().st_size > 1000


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
