#!/bin/sh
# Local gate mirroring CI (house style): lint + suite + strict docs build.
set -e
PY="${PYTHON:-.venv/bin/python}"
"$PY" -m ruff check .
"$PY" -m pytest src/ tests/ -q
"$PY" -m sphinx -q -b html -W -E docs docs/_build/html
echo "local gate: OK"
