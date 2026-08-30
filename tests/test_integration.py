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
