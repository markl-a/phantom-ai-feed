"""Pytest configuration for the test suite.

Registers the ``live`` marker used by the gated cross-repo integration test
(``tests/test_mesh_roundtrip_live.py``) so ``-m live`` filtering works and no
"unknown marker" warning is emitted. Everything else in the suite stays
hermetic; ``live`` is the only test that shells out to a real ``phantom``.
"""
from __future__ import annotations


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: cross-repo integration test that exercises a real `phantom` "
        "binary (skipped unless phantom is on PATH and the store can be "
        "isolated); never touches the real ~/.phantom-mesh.",
    )
