"""Shared test fixtures."""
import pytest
from sphinx.util.docutils import docutils_namespace


@pytest.fixture(autouse=True)
def _reset_docutils_registrations():
    # ponytail: Sphinx.add_node/add_role/etc. register into process-global docutils
    # registries; without resetting between tests, the *second* Sphinx() app built
    # in-process trips "already registered" warnings on Sphinx 7 (silently fine on
    # 8+, but our CI matrix now actually runs 7) — this is Sphinx's own documented
    # test-isolation helper (used internally by sphinx.testing.fixtures).
    with docutils_namespace():
        yield
