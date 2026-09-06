"""Hash-cached orchestration of the pinned likec4 CLI (build + view-id collection)."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Iterable
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


def _dynamic_view_ids(data: object) -> set[str]:
    """Ids of ``dynamic view``s in `likec4 export json` output (``"_type": "dynamic"``).

    >>> sorted(_dynamic_view_ids({"views": {"a": {"_type": "element"}, "b": {"_type": "dynamic"}}}))
    ['b']
    >>> _dynamic_view_ids([{"views": {"a": {"_type": "dynamic"}}}, {"views": {"b": {}}}])
    {'a'}
    >>> _dynamic_view_ids({"nodes": {}})
    set()
    """
    ids: set[str] = set()
    if isinstance(data, dict):
        views = data.get("views")
        if isinstance(views, dict):
            ids |= {k for k, v in views.items() if isinstance(v, dict) and v.get("_type") == "dynamic"}
    elif isinstance(data, list):
        for item in data:
            ids |= _dynamic_view_ids(item)
    return ids


def _require_npx() -> str:
    """Return the ``npx`` path, or raise :class:`LikeC4Missing` when node isn't installed."""
    npx = _npx()
    if npx is None:
        raise LikeC4Missing("npx not found on PATH — node >= 20 is required to build LikeC4 views")
    return npx


def ensure_build(source_dir: Path, cache_dir: Path, version: str, build_args: list[str]) -> Path:
    """Build the viewer into ``cache_dir/dist`` (skipped on hash match); return ``dist``.

    View ids come from :func:`ensure_views`, which every builder runs.
    """
    npx = _require_npx()
    cache_dir.mkdir(parents=True, exist_ok=True)
    dist = cache_dir / "dist"
    stamp = cache_dir / "stamp"
    digest = source_hash(source_dir, version, build_args)
    if stamp.exists() and stamp.read_text() == digest and dist.exists():
        return dist
    shutil.rmtree(dist, ignore_errors=True)    # stale hashed assets must not accumulate
    _run(npx, [f"likec4@{version}", "build", "--use-hash-history", "--base", "./",
               "-o", str(dist), *build_args, str(source_dir)], cwd=source_dir)
    stamp.write_text(digest)
    return dist


def ensure_views(source_dir: Path, cache_dir: Path, version: str) -> tuple[set[str], set[str]]:
    """Return ``(all view ids, dynamic view ids)`` via ``likec4 export json`` (cached).

    Dynamic views are the ones a ``--seq`` export renders as sequence diagrams.
    """
    npx = _require_npx()
    cache_dir.mkdir(parents=True, exist_ok=True)
    stamp, views_file = cache_dir / "views.stamp", cache_dir / "views-only.json"
    digest = source_hash(source_dir, version, ["json", "2"])   # "2": file schema with dynamic ids
    if stamp.exists() and stamp.read_text() == digest and views_file.exists():
        cached = json.loads(views_file.read_text())
        return set(cached["views"]), set(cached["dynamic"])
    export = cache_dir / "model.json"
    _run(npx, [f"likec4@{version}", "export", "json", "-o", str(export), str(source_dir)],
         cwd=source_dir)
    data = json.loads(export.read_text())
    views, dynamic = _view_ids(data), _dynamic_view_ids(data)
    views_file.write_text(json.dumps({"views": sorted(views), "dynamic": sorted(dynamic)}))
    stamp.write_text(digest)
    return views, dynamic


def ensure_images(source_dir: Path, cache_dir: Path, version: str, fmt: str,
                  views: Iterable[str], seq: bool = False) -> Path:
    """Export ``views`` as ``<view-id>.<fmt>`` into ``cache_dir/images-<fmt>[-seq]`` — additively.

    The directory is stamped with the source digest; a stale stamp (sources changed) wipes it
    first. Only views whose file is missing are exported, in one CLI run — nothing missing
    means no CLI call, so callers can ask freely. ``seq`` selects sequence layout (``--seq``)
    and the ``-seq`` directory, since the CLI's ``--seq`` applies to the whole run.

    The export drives headless Chromium through Playwright; if the first attempt fails for
    lack of a browser, install Chromium once through likec4's *own* Playwright (so the
    browser revision matches) and retry. Any other failure, or a second one, propagates as
    ``RuntimeError``.
    """
    npx = _require_npx()
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = f"images-{fmt}-seq" if seq else f"images-{fmt}"
    out, stamp = cache_dir / name, cache_dir / f"{name}.stamp"
    digest = source_hash(source_dir, version, [fmt, "seq"] if seq else [fmt])
    if not (stamp.exists() and stamp.read_text() == digest):
        shutil.rmtree(out, ignore_errors=True)               # stale renders must not survive
        out.mkdir(parents=True)
        stamp.write_text(digest)
    missing = sorted(v for v in set(views) if not (out / f"{v}.{fmt}").exists())
    if not missing:
        return out
    cli = f"likec4@{version}"
    export = [cli, "export", fmt, "--flat", *(["--seq"] if seq else []),
              *(arg for v in missing for arg in ("-f", v)), "-o", str(out), str(source_dir)]
    try:
        _run(npx, export, cwd=source_dir)
    except RuntimeError as e:
        msg = str(e).lower()
        if not any(k in msg for k in ("playwright", "browser", "executable")):
            raise
        _run(npx, ["--package", cli, "-c", "playwright install chromium"], cwd=source_dir)
        _run(npx, export, cwd=source_dir)
    return out
