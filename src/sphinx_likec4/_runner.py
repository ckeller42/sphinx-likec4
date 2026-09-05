"""Hash-cached orchestration of the pinned likec4 CLI (build + view-id collection)."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


class LikeC4Missing(RuntimeError):
    """node/npx is not available on PATH."""


def _npx() -> str | None:
    """Return the path to ``npx`` on ``PATH``, or ``None`` if node isn't installed."""
    return shutil.which("npx")


def source_hash(source_dir: Path, version: str, build_args: list[str]) -> str:
    """Digest of the LikeC4 sources plus ``version`` and ``build_args``.

    Covers each ``.c4``/``.likec4`` file's relative path and contents, so any change
    to inputs or build config invalidates the cache.
    """
    h = hashlib.sha256()
    h.update(version.encode())
    h.update("\0".join(build_args).encode())
    for f in sorted(source_dir.rglob("*")):
        if f.suffix in (".c4", ".likec4") and f.is_file():
            h.update(str(f.relative_to(source_dir)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _run(npx: str, args: list[str], cwd: Path) -> None:
    """Run ``npx -y <args>`` in ``cwd``; raise ``RuntimeError`` with stdout/stderr on failure."""
    cmd = [npx, "-y", *args]
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, check=False)  # checked manually below
    if res.returncode != 0:
        raise RuntimeError(
            f"likec4 failed: {' '.join(cmd)}\n"
            f"stdout:\n{res.stdout.decode(errors='replace')}\n"
            f"stderr:\n{res.stderr.decode(errors='replace')}"
        )


def _view_ids(data: object) -> set[str]:
    """Extract view ids from `likec4 export json` output (dict- or list-shaped).

    >>> sorted(_view_ids({"views": {"index": {}, "seqA": {}}}))
    ['index', 'seqA']
    >>> sorted(_view_ids([{"views": {"a": {}}}, {"views": {"b": {}}}]))
    ['a', 'b']
    >>> _view_ids({"nodes": {}})
    set()
    """
    ids: set[str] = set()
    if isinstance(data, dict):                 # single project: {"views": {<id>: ...}}
        views = data.get("views")
        if isinstance(views, dict):
            ids |= set(views.keys())
    elif isinstance(data, list):               # multi-project: a list of such dicts
        for item in data:
            ids |= _view_ids(item)
    return ids


def _require_npx() -> str:
    """Return the ``npx`` path, or raise :class:`LikeC4Missing` when node isn't installed."""
    npx = _npx()
    if npx is None:
        raise LikeC4Missing("npx not found on PATH — node >= 20 is required to build LikeC4 views")
    return npx


def ensure_build(source_dir: Path, cache_dir: Path, version: str,
                 build_args: list[str]) -> tuple[Path, set[str]]:
    """Build the viewer into ``cache_dir/dist`` (skipped on hash match); return (dist, view ids)."""
    npx = _require_npx()

    cache_dir.mkdir(parents=True, exist_ok=True)
    dist = cache_dir / "dist"
    stamp = cache_dir / "stamp"
    views_file = cache_dir / "views.json"
    digest = source_hash(source_dir, version, build_args)

    if stamp.exists() and stamp.read_text() == digest and dist.exists() and views_file.exists():
        return dist, set(json.loads(views_file.read_text()))

    shutil.rmtree(dist, ignore_errors=True)    # stale hashed assets must not accumulate
    cli = f"likec4@{version}"
    _run(npx, [cli, "build", "--use-hash-history", "--base", "./",
               "-o", str(dist), *build_args, str(source_dir)], cwd=source_dir)
    export = cache_dir / "model.json"
    _run(npx, [cli, "export", "json", "-o", str(export), str(source_dir)], cwd=source_dir)
    views = _view_ids(json.loads(export.read_text()))
    views_file.write_text(json.dumps(sorted(views)))
    stamp.write_text(digest)
    return dist, views


def ensure_views(source_dir: Path, cache_dir: Path, version: str) -> set[str]:
    """Return the model's view ids via ``likec4 export json`` (cached on the source hash).

    For builders that need images but no viewer build (LaTeX, epub…); ``ensure_build``
    keeps its own copy of this step because its stamp already covers it.
    """
    npx = _require_npx()
    cache_dir.mkdir(parents=True, exist_ok=True)
    stamp, views_file = cache_dir / "views.stamp", cache_dir / "views-only.json"
    digest = source_hash(source_dir, version, ["json"])
    if stamp.exists() and stamp.read_text() == digest and views_file.exists():
        return set(json.loads(views_file.read_text()))
    export = cache_dir / "model.json"
    _run(npx, [f"likec4@{version}", "export", "json", "-o", str(export), str(source_dir)],
         cwd=source_dir)
    views = _view_ids(json.loads(export.read_text()))
    views_file.write_text(json.dumps(sorted(views)))
    stamp.write_text(digest)
    return views


def ensure_images(source_dir: Path, cache_dir: Path, version: str, fmt: str) -> Path:
    """Export every view as ``<view-id>.<fmt>`` into ``cache_dir/images-<fmt>`` (cached).

    ``fmt`` is ``"png"`` or ``"jpg"``. The export drives headless Chromium through
    Playwright; if the first attempt fails for lack of a browser, install Chromium once
    through likec4's *own* Playwright (so the browser revision matches) and retry. Any
    other failure, or a second one, propagates as ``RuntimeError``.
    """
    npx = _require_npx()
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"images-{fmt}"
    stamp = cache_dir / f"images-{fmt}.stamp"
    digest = source_hash(source_dir, version, [fmt])
    if stamp.exists() and stamp.read_text() == digest and out.is_dir():
        return out
    shutil.rmtree(out, ignore_errors=True)
    cli = f"likec4@{version}"
    export = [cli, "export", fmt, "--flat", "-o", str(out), str(source_dir)]
    try:
        _run(npx, export, cwd=source_dir)
    except RuntimeError as e:
        msg = str(e).lower()
        if not any(k in msg for k in ("playwright", "browser", "executable")):
            raise
        _run(npx, ["--package", cli, "-c", "playwright install chromium"], cwd=source_dir)
        _run(npx, export, cwd=source_dir)
    stamp.write_text(digest)
    return out
