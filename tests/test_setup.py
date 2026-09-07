from sphinx_likec4 import DEFAULT_LIKEC4_VERSION, setup


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
    assert DEFAULT_LIKEC4_VERSION.count(".") == 2 and DEFAULT_LIKEC4_VERSION[0].isdigit()   # exact pin, not a range
    assert app.config_values["likec4_missing"] == ("error", "env")
    assert app.config_values["likec4_build_args"] == ([], "env")
    assert app.config_values["likec4_render"] == ({}, "env")
    assert app.config_values["likec4_export_images"] == (True, "env")
    assert meta["parallel_read_safe"] is True
