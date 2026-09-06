import shutil
import urllib.request
from pathlib import Path

from sphinx_likec4 import __version__

project = "sphinx-likec4"
author = "ckeller"
copyright = "2026, ckeller"
release = __version__                 # full version on the title page / in the footer
version = ".".join(__version__.split(".")[:2])
extensions = ["sphinx_likec4", "myst_parser"]
myst_heading_anchors = 3        # lets "(#static-images)" resolve to the "### Static images" heading
html_theme = "furo"
html_extra_path = ["_extra"]   # llms.txt at the site root
exclude_patterns = ["_build", "specs", "plans"]

# The docs dogfood LikeC4's official cloud-system example (MIT) — fetched at build time from a
# pinned upstream commit rather than kept as a copy. Bump the SHA to follow upstream; the view
# ids the pages embed (index, cloud, cloud-to-amazon) must still exist there.
_EXAMPLE_REPO = "likec4/likec4"
_EXAMPLE_SHA = "2647f7f78319dc8e6916cb23ff1cb2734ec34e98"
_EXAMPLE_DIR = "examples/cloud-system"
_EXAMPLE_FILES = ["_spec.c4", "model.c4", "views.c4", "externals.c4", "deployment.c4",
                  "deployment.acc.c4", "cloud/legacy.c4", "cloud/next.c4", "cloud/ui.c4"]


def _fetch_example(dest: Path) -> None:
    """Download the example once per pinned SHA into ``dest`` (git-ignored, under _build)."""
    stamp = dest / ".sha"
    if stamp.exists() and stamp.read_text(encoding="utf-8") == _EXAMPLE_SHA:
        return
    shutil.rmtree(dest, ignore_errors=True)
    for rel in _EXAMPLE_FILES:
        url = f"https://raw.githubusercontent.com/{_EXAMPLE_REPO}/{_EXAMPLE_SHA}/{_EXAMPLE_DIR}/{rel}"
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, target)
    stamp.write_text(_EXAMPLE_SHA, encoding="utf-8")


_fetch_example(Path(__file__).parent / "_build" / "cloud-system")
likec4_source_dir = "_build/cloud-system"

# PDF: a short document — article-style ("howto") instead of the chaptered, two-sided
# "manual" class, which pads every chapter start with a blank verso page.
latex_engine = "xelatex"        # Unicode arrows/≥ in the prose; pdflatex has no glyphs for them
latex_theme = "howto"
latex_elements = {"papersize": "a4paper", "extraclassoptions": "oneside"}
