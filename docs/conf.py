project = "sphinx-likec4"
extensions = ["sphinx_likec4", "myst_parser"]
likec4_source_dir = "model"
html_theme = "furo"
html_extra_path = ["_extra"]   # llms.txt at the site root
exclude_patterns = ["_build", "specs", "plans"]
