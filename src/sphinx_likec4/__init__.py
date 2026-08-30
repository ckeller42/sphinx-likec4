"""sphinx-likec4 — embed interactive LikeC4 views in Sphinx HTML documentation."""
__version__ = "0.1.0"

DEFAULT_LIKEC4_VERSION = "1.59.2"


def setup(app):
    app.add_config_value("likec4_source_dir", None, "env")
    app.add_config_value("likec4_version", DEFAULT_LIKEC4_VERSION, "env")
    app.add_config_value("likec4_missing", "error", "env")
    app.add_config_value("likec4_build_args", [], "env")
    return {"version": __version__, "parallel_read_safe": True, "parallel_write_safe": True}
