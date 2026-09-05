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


def _fake_cli(calls, fail_first_export_with: bytes | None = None):
    """subprocess.run stand-in: fakes `likec4 export json|png|jpg` and `playwright install`."""
    state = {"failed": False}

    def fake_run(cmd, **kw):
        calls.append(cmd)
        ok = type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()
        if "export" not in cmd:                       # playwright install
            return ok
        fmt = cmd[cmd.index("export") + 1]
        if fmt == "json":
            Path(cmd[cmd.index("-o") + 1]).write_text(json.dumps({"views": {"index": {}}}))
            return ok
        if fail_first_export_with and not state["failed"]:
            state["failed"] = True
            return type("R", (), {"returncode": 1, "stdout": b"", "stderr": fail_first_export_with})()
        out = Path(cmd[cmd.index("-o") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / f"index.{fmt}").write_bytes(b"img")
        return ok

    return fake_run


def test_ensure_views_runs_export_json_once_then_caches(tmp_path, monkeypatch):
    src = _model(tmp_path)
    calls = []
    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", _fake_cli(calls))

    assert _runner.ensure_views(src, tmp_path / "c", "1.59.2") == {"index"}
    assert len(calls) == 1 and "json" in calls[0]
    assert _runner.ensure_views(src, tmp_path / "c", "1.59.2") == {"index"}
    assert len(calls) == 1                                  # cache hit


def test_ensure_images_exports_flat_then_caches(tmp_path, monkeypatch):
    src = _model(tmp_path)
    calls = []
    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", _fake_cli(calls))

    out = _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png")
    assert out == tmp_path / "c" / "images-png"
    assert (out / "index.png").exists()
    cmd = calls[0]
    assert cmd[:2] == ["npx", "-y"] and "likec4@1.59.2" in cmd
    assert cmd[cmd.index("export") + 1] == "png" and "--flat" in cmd
    assert cmd[cmd.index("-o") + 1] == str(out) and cmd[-1] == str(src)

    assert _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png") == out
    assert len(calls) == 1                                  # cache hit

    jpg = _runner.ensure_images(src, tmp_path / "c", "1.59.2", "jpg")
    assert jpg == tmp_path / "c" / "images-jpg" and len(calls) == 2   # separate cache per format


def test_ensure_images_installs_chromium_once_when_playwright_is_missing(tmp_path, monkeypatch):
    src = _model(tmp_path)
    calls = []
    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", _fake_cli(
        calls, fail_first_export_with=b"browserType.launch: Executable doesn't exist. "
                                      b"Please run: npx playwright install"))

    out = _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png")
    assert (out / "index.png").exists()
    # NOTE: matching on "-c" (the install invocation's flag), not a substring like "install" —
    # pytest's tmp_path for *this* test literally embeds "install" (from "installs" in the test
    # name) into every command's path arguments, so a bare substring check false-positives.
    assert [("export" in c, "-c" in c) for c in calls] == [
        (True, False), (False, True), (True, False)]
    install = calls[1]
    assert install[:2] == ["npx", "-y"]
    assert install[install.index("--package") + 1] == "likec4@1.59.2"
    assert install[install.index("-c") + 1] == "playwright install chromium"


def test_ensure_images_reraises_non_playwright_failures(tmp_path, monkeypatch):
    src = _model(tmp_path)
    calls = []
    monkeypatch.setattr(_runner, "_npx", lambda: "npx")
    monkeypatch.setattr(_runner.subprocess, "run", _fake_cli(
        calls, fail_first_export_with=b"Error: invalid view predicate"))
    with pytest.raises(RuntimeError, match="invalid view predicate"):
        _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png")
    assert len(calls) == 1                                  # no install attempt, no retry


def test_ensure_images_and_views_raise_when_npx_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(_runner, "_npx", lambda: None)
    # NOTE: _model(tmp_path) creates tmp_path/"model" with plain mkdir() (no exist_ok), so it
    # can only be called once per tmp_path — bind and reuse rather than calling it twice.
    src = _model(tmp_path)
    with pytest.raises(_runner.LikeC4Missing):
        _runner.ensure_images(src, tmp_path / "c", "1.59.2", "png")
    with pytest.raises(_runner.LikeC4Missing):
        _runner.ensure_views(src, tmp_path / "c", "1.59.2")
