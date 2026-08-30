from sphinx_likec4 import setup


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
    assert app.config_values["likec4_version"][0] == "1.59.2"
    assert app.config_values["likec4_missing"] == ("error", "env")
    assert app.config_values["likec4_build_args"] == ([], "env")
    assert meta["parallel_read_safe"] is True
