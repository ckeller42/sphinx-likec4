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
    return shutil.which("npx")


def source_hash(source_dir: Path, version: str, build_args: list[str]) -> str:
    h = hashlib.sha256()
    h.update(version.encode())
    h.update("\0".join(build_args).encode())
    for f in sorted(source_dir.rglob("*")):
        if f.suffix in (".c4", ".likec4") and f.is_file():
            h.update(str(f.relative_to(source_dir)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _run(npx: str, args: list[str], cwd: Path) -> None:
    cmd = [npx, "-y", *args]
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, check=False)  # checked manually below
    if res.returncode != 0:
        raise RuntimeError(
            f"likec4 failed: {' '.join(cmd)}\n{res.stderr.decode(errors='replace')}"
        )


def _view_ids(data: object) -> set[str]:
    """Extract view ids from `likec4 export json` output (dict- or list-shaped)."""
    ids: set[str] = set()
    if isinstance(data, dict):                 # single project: {"views": {<id>: ...}}
        views = data.get("views")
        if isinstance(views, dict):
            ids |= set(views.keys())
    elif isinstance(data, list):               # multi-project: a list of such dicts
        for item in data:
            ids |= _view_ids(item)
    return ids


def ensure_build(source_dir: Path, cache_dir: Path, version: str,
                 build_args: list[str]) -> tuple[Path, set[str]]:
    """Build the viewer into ``cache_dir/dist`` (skipped on hash match); return (dist, view ids)."""
    npx = _npx()
    if npx is None:
        raise LikeC4Missing("npx not found on PATH — node >= 20 is required to build LikeC4 views")

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
