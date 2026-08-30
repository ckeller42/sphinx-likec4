import json
from pathlib import Path

import pytest

from sphinx_likec4 import _runner


def _model(tmp_path: Path) -> Path:
    src = tmp_path / "model"
    src.mkdir()
    (src / "a.c4").write_text("specification { element system }")
    return src


def test_source_hash_changes_with_content_version_and_args(tmp_path):
    src = _model(tmp_path)
    h1 = _runner.source_hash(src, "1.59.2", [])
    (src / "a.c4").write_text("specification { element system }\n// changed")
    h2 = _runner.source_hash(src, "1.59.2", [])
    h3 = _runner.source_hash(src, "9.9.9", [])
    h4 = _runner.source_hash(src, "9.9.9", ["--flag"])
    assert len({h1, h2, h3, h4}) == 4


def test_ensure_build_runs_cli_once_then_caches(tmp_path, monkeypatch):
    src = _model(tmp_path)
    cache = tmp_path / "cache"
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "build" in cmd:
            dist = Path(cmd[cmd.index("-o") + 1])
            dist.mkdir(parents=True, exist_ok=True)
            (dist / "index.html").write_text("<html>viewer</html>")
        else:  # export json
            out = Path(cmd[cmd.index("-o") + 1])
            out.write_text(json.dumps({"views": {"index": {}, "seqA": {}}}))
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", fake_run)

    dist, views = _runner.ensure_build(src, cache, "1.59.2", [])
    assert (dist / "index.html").exists()
    assert views == {"index", "seqA"}
    n = len(calls)

    _dist2, views2 = _runner.ensure_build(src, cache, "1.59.2", [])
    assert len(calls) == n            # cache hit: no new CLI calls
    assert views2 == views


def test_ensure_build_raises_when_npx_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(_runner, "_npx", lambda: None)
    with pytest.raises(_runner.LikeC4Missing):
        _runner.ensure_build(_model(tmp_path), tmp_path / "c", "1.59.2", [])
