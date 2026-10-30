"""
conftest.py — pytest configuration for the backend test suite.

Configures anyio to use asyncio as the backend.  This is needed because
anyio-4.x and Starlette's TestClient (which uses its own internal event loop)
can conflict when pytest-anyio auto-discovers tests.
"""

import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    """Tell anyio to use asyncio as the async backend for this test session."""
    return "asyncio"
