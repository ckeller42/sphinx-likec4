import re
import sys
from pathlib import Path

import pytest

from sphinx_likec4 import DEFAULT_LIKEC4_VERSION, __version__, setup

_REPO_ROOT = Path(__file__).parent.parent


class _FakeApp:
    def __init__(self):
        self.config_values = {}

    def add_config_value(self, name, default, rebuild):
        self.config_values[name] = (default, rebuild)

    def connect(self, *a, **k):
        pass

    def add_directive(self, *a, **k):
        pass


def test_setup_registers_config_values():
    app = _FakeApp()
    meta = setup(app)
    assert app.config_values["likec4_source_dir"] == (None, "env")
    assert app.config_values["likec4_version"][0] == DEFAULT_LIKEC4_VERSION
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", DEFAULT_LIKEC4_VERSION)    # exact pin, not a range
    assert app.config_values["likec4_missing"] == ("error", "env")
    assert app.config_values["likec4_build_args"] == ([], "env")
    assert app.config_values["likec4_render"] == ({}, "env")
    assert app.config_values["likec4_export_images"] == (True, "env")
    assert meta["parallel_read_safe"] is True


def test_unreadable_pin_file_is_a_clear_import_error(monkeypatch):
    import importlib

    import sphinx_likec4

    def gone(self, *a, **k):
        raise FileNotFoundError(self)
    monkeypatch.setattr(Path, "read_text", gone)
    with pytest.raises(ImportError, match="package.json .*pinned likec4 version"):
        importlib.reload(sphinx_likec4)
    monkeypatch.undo()
    importlib.reload(sphinx_likec4)                          # restore the real module for other tests
    assert sphinx_likec4.DEFAULT_LIKEC4_VERSION == DEFAULT_LIKEC4_VERSION


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib requires Python 3.11+")
def test_version_matches_pyproject():
    import tomllib

    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ == pyproject["project"]["version"]
