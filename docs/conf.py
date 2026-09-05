project = "sphinx-likec4"
extensions = ["sphinx_likec4", "myst_parser"]
myst_heading_anchors = 3        # lets "(#static-images)" resolve to the "### Static images" heading
likec4_source_dir = "model"
html_theme = "furo"
html_extra_path = ["_extra"]   # llms.txt at the site root
exclude_patterns = ["_build", "specs", "plans"]
latex_engine = "xelatex"        # Unicode arrows/≥ in the prose; pdflatex has no glyphs for them
