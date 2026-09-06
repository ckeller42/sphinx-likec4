from sphinx_likec4 import __version__

project = "sphinx-likec4"
author = "ckeller"
copyright = "2026, ckeller"
release = __version__                 # full version on the title page / in the footer
version = ".".join(__version__.split(".")[:2])
extensions = ["sphinx_likec4", "myst_parser"]
myst_heading_anchors = 3        # lets "(#static-images)" resolve to the "### Static images" heading
likec4_source_dir = "model"
html_theme = "furo"
html_extra_path = ["_extra"]   # llms.txt at the site root
exclude_patterns = ["_build", "specs", "plans"]

# PDF: a short document — article-style ("howto") instead of the chaptered, two-sided
# "manual" class, which pads every chapter start with a blank verso page.
latex_engine = "xelatex"        # Unicode arrows/≥ in the prose; pdflatex has no glyphs for them
latex_theme = "howto"
latex_elements = {"papersize": "a4paper", "extraclassoptions": "oneside"}
